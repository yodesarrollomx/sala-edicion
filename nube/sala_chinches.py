"""El puente de las chinches: de la Sala (Sheet) a GitHub, y de vuelta.

Por qué existe: en la Sala, clavar una chinche escribe una fila `ENCARGO · chinche · <vista>` en
PRODUCCION. Quien las cosechaba era `encargos.py` + la ronda `/sala` en la Mac; al mudarse el ciclo a
la nube (21-sep) eso no se portó y las chinches se quedaban en el Sheet para siempre (el 23-sep había
8 en `pendiente`, la más vieja del 14-sep).

Qué hace, cada hora:
  1. Lee `recurso=dia` → `produccion` (las últimas filas de PRODUCCION) y toma las chinches (`CHN-…`).
  2. Por cada chinche sin issue, abre un issue 📌 con etiqueta `chinche` en este repo (el texto
     textual, la vista, el elemento y la página) y apunta `ENCARGO TOMADO · chinche` en el Sheet.
     El revisor trabaja esos issues: corrige, verifica, publica y cierra.
  3. Por cada issue `chinche` cerrado como completado, apunta `ENCARGO CUMPLIDO · chinche` en el
     Sheet. El checkpoint previo y la lectura posterior por id/evento evitan repetir
     un append ambiguo; sólo el recibo verificado obtiene la etiqueta `en-sheet`.
  4. Reescribe `datos/encargos.json` (lo que leen «Tus recados» y la Línea) desde los issues.
  5. Las peticiones de ideas quedan SOLICITADAS con un marcador durable por id.
     Pedir el workflow no acredita ideas producidas ni publicadas.

Sólo AGREGA filas al Sheet (nunca borra ni edita). `--simular` sólo dice lo que haría.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

import sala_cliente as sala

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ENCARGOS = RAIZ / 'datos' / 'encargos.json'
RE_ID = re.compile(r'CHN-\d{8}-\d{4}-[0-9a-f]{4}')


def gh(*args):
    r = subprocess.run(['gh', *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('gh %s: %s' % (' '.join(args[:3]), r.stderr.strip()[:300]))
    return r.stdout


def issues_con_etiqueta(etiqueta):
    out = gh('issue', 'list', '--label', etiqueta, '--state', 'all', '--limit', '300',
             '--json', 'number,title,body,state,stateReason,labels,createdAt,closedAt,url')
    lista = json.loads(out or '[]')
    for it in lista:
        m = RE_ID.search(it.get('body') or '')
        it['chn'] = m.group(0) if m else None
        it['etiquetas'] = [l.get('name') for l in (it.get('labels') or [])]
    return lista


def issues_chinche():
    return issues_con_etiqueta('chinche')


def etiquetas_issue(it, agregar, quitar=None):
    """El checkpoint precede al efecto externo y sobrevive a un runner perdido."""
    args = ['issue', 'edit', str(it['number']), '--add-label', agregar]
    if quitar:
        args += ['--remove-label', quitar]
    gh(*args)
    it['etiquetas'] = sorted((set(it.get('etiquetas') or []) | {agregar}) - {quitar})


def dia_fresco():
    dia = sala.get('dia', fresco='1')
    if (not isinstance(dia, dict) or dia.get('error') or dia.get('ok') is False
            or dia.get('cache') is True or not isinstance(dia.get('produccion'), list)):
        raise sala.SalaError('el día fresco no acredita una lectura de PRODUCCION')
    return dia


def produccion_fresca():
    return dia_fresco()['produccion']


def tiene_recibo(filas, cid, evento, clave):
    """También reconoce el recibo antiguo por su id y evento, sin reinterpretar texto."""
    for f in filas:
        if f.get('pieza') != evento:
            continue
        try:
            d = json.loads(f.get('detalle')) if isinstance(f.get('detalle'), str) else f.get('detalle')
        except (ValueError, TypeError):
            continue
        if isinstance(d, dict) and d.get('id') == cid and d.get('recibo_clave', clave) == clave:
            return True
    return False


def post_produccion_una_vez(**campos):
    # PRODUCCION es append-only. El cliente usa una sola escritura; la conciliación
    # posterior corre exclusivamente en lectura, nunca como otro POST.
    recibo = sala.post('produccion', **campos)
    if not isinstance(recibo, dict) or recibo.get('ok') is not True:
        raise sala.SalaError('PRODUCCION no confirmó la solicitud')
    return recibo


def apuntar_una_vez(it, evento, estado, pendiente, confirmado, primer_intento=False):
    """Confirma por clave; una ausencia en las últimas 30 filas no prueba no escrito.

    Tras guardar el checkpoint sólo se concilia en lectura. Si el POST o su acuse
    se pierde, se conserva pendiente incluso cuando el recibo salió de esa ventana.
    Nunca se borra el checkpoint para repetir un append ambiguo.
    """
    cid = it['chn']
    clave = '%s:%s' % (evento, cid)
    if confirmado in it.get('etiquetas', []):
        return True
    try:
        filas = produccion_fresca()
    except sala.SalaError as e:
        sala.avisar('⚠ recibo pendiente · %s: %s' % (cid, e))
        return False
    if tiene_recibo(filas, cid, evento, clave):
        etiquetas_issue(it, confirmado, pendiente)
        return True
    if pendiente in it.get('etiquetas', []) and not primer_intento:
        sala.avisar('⚠ recibo no concluyente · %s: no se repite el POST' % cid)
        return False
    if pendiente not in it.get('etiquetas', []):
        etiquetas_issue(it, pendiente)
    try:
        post_produccion_una_vez(pieza=evento, estado=estado,
                               detalle=json.dumps({'id': cid, 'issue': it['url'],
                                                   'recibo_clave': clave}, ensure_ascii=False),
                               enlace=it['url'])
    except sala.SalaError as e:
        sala.avisar('⚠ respuesta de escritura no concluyente · %s: %s' % (cid, e))
    try:
        if tiene_recibo(produccion_fresca(), cid, evento, clave):
            etiquetas_issue(it, confirmado, pendiente)
            return True
    except sala.SalaError as e:
        sala.avisar('⚠ no pude verificar el recibo · %s: %s' % (cid, e))
    sala.avisar('⚠ %s queda pendiente de confirmar; no se repite el POST' % cid)
    return False


def completado(it):
    return it.get('state') == 'CLOSED' and it.get('stateReason') == 'COMPLETED'


def estado_encargo(it):
    if completado(it):
        return 'cumplida'
    return 'no realizada' if it.get('state') == 'CLOSED' else 'en curso'


def solicitar_semillero(it):
    """El acuse de dispatch sólo acredita solicitud, nunca ideas producidas."""
    if 'semillero-solicitado' in it['etiquetas']:
        return True
    if 'semillero-por-confirmar' in it['etiquetas']:
        sala.avisar('⚠ solicitud de semillero no concluyente · %s; no se repite' % it['chn'])
        return False
    etiquetas_issue(it, 'semillero-por-confirmar')
    try:
        gh('workflow', 'run', 'sala-arranque.yml', '--ref', 'main', '-f', 'modo=ideas')
    except RuntimeError as e:
        sala.avisar('⚠ no pude confirmar solicitud del semillero · %s: %s' % (it['chn'], e))
        return False
    etiquetas_issue(it, 'semillero-solicitado', 'semillero-por-confirmar')
    return True


def ideas_solicitadas(produccion, simular):
    """Un marcador público genérico por solicitud real, sin copiar texto del Sheet.

    La ventana de PRODUCCION es limitada. El issue conserva el checkpoint incluso
    si el runner cae antes de guardar el snapshot o la fila sale de esa ventana.
    Los recibos antiguos CUMPLIDO sólo prueban el dispatch que los originó.
    """
    pedidas, ya_solicitadas = set(), set()
    for f in produccion:
        evento = str(f.get('pieza') or '')
        if evento not in ('ENCARGO · ideas', 'ENCARGO SOLICITADO · ideas', 'ENCARGO CUMPLIDO · ideas'):
            continue
        try:
            d = json.loads(f.get('detalle')) if isinstance(f.get('detalle'), str) else f.get('detalle')
        except (ValueError, TypeError):
            continue
        cid = d.get('id') if isinstance(d, dict) else None
        if not isinstance(cid, str) or not RE_ID.fullmatch(cid):
            continue
        pedidas.add(cid)
        if evento != 'ENCARGO · ideas':
            ya_solicitadas.add(cid)
    if simular:
        for cid in sorted(pedidas):
            sala.avisar('  ✦ solicitud de ideas · %s · no acredita producción' % cid)
        return
    existentes = {i['chn']: i for i in issues_con_etiqueta('ideas-solicitud') if i['chn']}
    for cid in sorted(pedidas):
        if cid in existentes:
            continue
        cuerpo = ('Solicitud recibida desde la Sala. Este marcador acredita la solicitud, '
                  'no la producción ni publicación de ideas.\n\n- id %s' % cid)
        labels = ['ideas-solicitud']
        if cid in ya_solicitadas:
            labels.append('semillero-solicitado')
        url = gh('issue', 'create', '--title', '🌱 Solicitud del semillero · ' + cid,
                 '--body', cuerpo, '--label', ','.join(labels)).strip()
        existentes[cid] = {'number': int(url.rstrip('/').split('/')[-1]), 'url': url,
                           'chn': cid, 'etiquetas': labels, 'state': 'OPEN'}
    for it in existentes.values():
        if it.get('state') == 'CLOSED' or 'ideas-en-sheet' in it['etiquetas']:
            continue
        if solicitar_semillero(it):
            apuntar_una_vez(it, 'ENCARGO SOLICITADO · ideas', 'solicitada',
                           'ideas-sheet-pendiente', 'ideas-en-sheet')


def chinches_del_sheet(produccion):
    """Filas `ENCARGO · chinche…` → {id: {fecha, vista, texto, elemento, url}} (gana la primera)."""
    vistas = {}
    for f in produccion or []:
        evento = str(f.get('pieza') or '')
        if not evento.startswith('ENCARGO') or 'chinche' not in evento or 'TOMADO' in evento \
                or 'CUMPLIDO' in evento:
            continue
        det = f.get('detalle') or ''
        try:
            d = json.loads(det) if isinstance(det, str) else dict(det)
        except ValueError:
            m = RE_ID.search(str(det))
            d = {'id': m.group(0) if m else None, 'texto': str(det)}
        cid = d.get('id') or (RE_ID.search(str(det)) or [None])[0]
        if not cid or cid in vistas:
            continue
        el = d.get('elemento') or {}
        vistas[cid] = {'fecha': str(f.get('fecha') or '')[:10], 'vista': d.get('vista') or '',
                       'texto': d.get('texto') or '', 'seccion': el.get('seccion') or '',
                       'css': el.get('css') or '', 'dice': (el.get('texto') or '')[:200],
                       'url': d.get('url') or '', 'popup': d.get('popup') or '',
                       'carta': d.get('carta'), 'repo': d.get('repo') or '', 'codigo': d.get('codigo') or ''}
    return vistas


def cuerpo_issue(cid, c):
    L = ['# Encargo desde la Sala de Edición · 1 cambio',
         'Alejandro · %s · clavada en %s (llegó por el puente `nube/sala_chinches.py`)'
         % (c['fecha'], ('el tablero ' + c['vista']) if c.get('repo') else 'la Sala'),
         'Repo: yodesarrollomx/%s' % (c.get('repo') or 'sala-edicion'), '',
         '## 1 · %s · vista "%s"' % (c.get('repo') or 'sala-edicion', c['vista'] or '—')]
    if c['url']:
        L.append('- **Página:** %s' % c['url'])
    L += ['', '**Dice Alejandro:** "%s"' % c['texto'], '']
    if c['seccion']:
        L.append('- **Sección:** %s' % c['seccion'])
    if c['css']:
        L.append('- **Elemento:** `%s`' % c['css'])
    if c['dice']:
        L.append('- **Dice el elemento:** "%s"' % c['dice'])
    if c['popup']:
        L.append('- **Pop-up abierto:** %s' % c['popup'])
    if c.get('codigo'):
        L.append('- **Dónde vive en el código:** %s' % c['codigo'])
    if c['carta']:
        L.append('- **Carta:** `%s`' % json.dumps(c['carta'], ensure_ascii=False)[:300])
    L += ['- id %s' % cid, '',
          '> Al cerrar este issue como completado, el puente apunta «ENCARGO CUMPLIDO» en el Sheet.']
    return '\n'.join(L)


def refrescar_piezas(simular):
    """23-sep: datos/piezas.json lo escribía la Mac y se congeló el 15-sep; la Sala creía abiertas
    piezas ya publicadas. Aquí sólo se SUBE el estado a «publicada» cuando el expediente del Sheet
    lo dice (nunca se baja, y del expediente no se copia nada más: el repo es público)."""
    ruta = RAIZ / 'datos' / 'piezas.json'
    try:
        exp = (sala.get('expedientes') or {}).get('expedientes') or {}
    except sala.SalaError as e:
        sala.avisar('⚠ no leí los expedientes: %s' % e)
        return False
    try:
        fab = {str(f.get('pieza')): f for f in ((sala.get('fabrica') or {}).get('fabrica') or [])}
    except sala.SalaError as e:
        sala.avisar('⚠ no leí la fábrica: %s' % e)
        fab = {}
    pz = json.loads(ruta.read_text(encoding='utf-8'))
    cambio = False
    for p in pz.get('piezas') or []:
        e = exp.get(p.get('pieza')) or {}
        hitos = ' '.join(str(h.get('que') or '') for h in (e.get('hitos') or []) if isinstance(h, dict))
        f = fab.get(p.get('pieza')) or {}
        pub = (str(f.get('activa')) in ('0', 'False', '') and bool(f) and 'publicad' in str(f.get('nota') or '').lower()) or \
            p.get('etapa') == 'publicada' or e.get('estado') == 'publicada' or bool(re.search(r'publicad|IG \d{6,}', hitos, re.I))
        sala.avisar('  pieza · %s · repo=%s · sheet=%s%s' % (p.get('pieza'), p.get('estado'), e.get('estado') or '—',
                                                          ' → publicada' if pub and p.get('estado') != 'publicada' else ''))
        if pub and p.get('estado') != 'publicada':
            p['estado'] = 'publicada'
            cambio = True
    if cambio and not simular:
        pz['actualizado'] = str(sala.hoy_hermosillo())
        ruta.write_text(json.dumps(pz, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return cambio


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--simular', action='store_true')
    args = ap.parse_args()
    sala.enmascarar_en_actions()

    try:
        dia = dia_fresco()
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer el día del Sheet: %s' % e)
        return 2
    enSheet = chinches_del_sheet(dia.get('produccion') or [])
    issues = issues_chinche()
    porId = {it['chn']: it for it in issues if it['chn']}
    sala.avisar('chinches en el Sheet (últimas filas): %d · issues chinche: %d' % (len(enSheet), len(porId)))

    if not args.simular:
        gh('label', 'create', 'chinche', '--color', 'B08637', '--force',
           '--description', 'Pedido clavado con la 📌 en un tablero')
        gh('label', 'create', 'en-sheet', '--color', 'C5DEF5', '--force',
           '--description', 'El puente ya apuntó CUMPLIDO en el Sheet de la Sala')
        for etiqueta in ('chinche-cumplido-pendiente', 'chinche-tomado-pendiente',
                         'tomado-en-sheet', 'ideas-solicitud', 'semillero-por-confirmar',
                         'semillero-solicitado', 'ideas-sheet-pendiente', 'ideas-en-sheet'):
            gh('label', 'create', etiqueta, '--color', 'C5DEF5', '--force',
               '--description', 'Checkpoint del puente: confirmar por id y evento sin repetir POST')

    nuevas = 0
    for cid, c in sorted(enSheet.items()):
        if cid in porId:
            continue
        titulo = '📌 %s · %s' % (c['vista'] if c.get('repo') else 'sala · ' + (c['vista'] or 'sala'),
                                 re.sub(r'\s+', ' ', c['texto'])[:70])
        sala.avisar('  + %s · %s' % (cid, titulo))
        nuevas += 1
        if args.simular:
            continue
        url = gh('issue', 'create', '--title', titulo, '--body', cuerpo_issue(cid, c),
                 '--label', 'chinche,chinche-tomado-pendiente').strip()
        it = {'number': int(url.rstrip('/').split('/')[-1]), 'url': url, 'chn': cid,
              'etiquetas': ['chinche', 'chinche-tomado-pendiente'], 'state': 'OPEN'}
        apuntar_una_vez(it, 'ENCARGO TOMADO · chinche', 'en curso',
                       'chinche-tomado-pendiente', 'tomado-en-sheet', primer_intento=True)

    # Un issue creado antes de perder el acuse del Sheet no vuelve a crearse ni
    # vuelve a escribir TOMADO: sólo se reconcilia el checkpoint durable.
    if not args.simular:
        for it in issues:
            if it['chn'] and 'chinche-tomado-pendiente' in it['etiquetas']:
                apuntar_una_vez(it, 'ENCARGO TOMADO · chinche', 'en curso',
                               'chinche-tomado-pendiente', 'tomado-en-sheet')

    # «✦ Proponme ideas ahora» pide al semillero; el dispatch NO es entrega.
    ideas_solicitadas(dia.get('produccion') or [], args.simular)

    refrescar_piezas(args.simular)
    # la calificación de los motores según lo que aprueban (sala_puntajes)
    if not args.simular:
        try:
            import sala_puntajes
            cola = (sala.get('cola') or {}).get('cola') or []
            if sala_puntajes.actualizar(dia, cola):
                sala.avisar('calificación de motores actualizada: %s' % json.dumps(
                    sala_puntajes.leer().get('etapas'), ensure_ascii=False))
        except Exception as e:                      # nunca tumba el puente
            sala.avisar('⚠ no pude calificar los motores: %s' % e)

    cumplidas = 0
    for it in issues:
        if not it['chn'] or not completado(it) \
                or 'en-sheet' in it['etiquetas']:
            continue
        sala.avisar('  ✓ cumplida · %s · %s' % (it['chn'], it['url']))
        if args.simular:
            cumplidas += 1
            continue
        if apuntar_una_vez(it, 'ENCARGO CUMPLIDO · chinche', 'cumplida',
                          'chinche-cumplido-pendiente', 'en-sheet'):
            cumplidas += 1

    # «Tus recados» y la Línea leen este archivo: su verdad ahora son los issues
    if not args.simular:
        issues = issues_chinche()
        regs = []
        for it in sorted([i for i in issues if i['chn']], key=lambda i: i['createdAt']):
            c = enSheet.get(it['chn']) or {}
            txt = c.get('texto') or re.sub(r'^📌\s*sala\s*·\s*[^·]*·\s*', '', it['title'])
            regs.append({'que': json.dumps({'id': it['chn'], 'texto': txt}, ensure_ascii=False),
                         'estado': estado_encargo(it),
                         'cuando': c.get('fecha') or it['createdAt'][:10],
                         'tomado': it['createdAt'][11:16], 'issue': it['url']})
        nuevo = {'_que_es': 'Las chinches de la Sala y su estado, desde sus issues (nube/sala_chinches.py).',
                 'encargos': regs}
        viejo = ENCARGOS.read_text(encoding='utf-8') if ENCARGOS.exists() else ''
        txt = json.dumps(nuevo, ensure_ascii=False, indent=1) + '\n'
        if txt != viejo:
            ENCARGOS.write_text(txt, encoding='utf-8')
            sala.avisar('datos/encargos.json reescrito (%d chinches)' % len(regs))

    sala.avisar('resumen: %d nueva(s) · %d cumplida(s) apuntadas' % (nuevas, cumplidas))
    return 0


if __name__ == '__main__':
    sys.exit(main())
