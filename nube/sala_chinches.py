"""El puente de las chinches: de la Sala (Sheet) a GitHub, y de vuelta.

Por qué existe: en la Sala, clavar una chinche escribe una fila `ENCARGO · chinche · <vista>` en
PRODUCCION. Quien las cosechaba era `encargos.py` + la ronda `/sala` en la Mac; al mudarse el ciclo a
la nube (21-sep) eso no se portó y las chinches se quedaban en el Sheet para siempre (el 23-sep había
8 en `pendiente`, la más vieja del 14-sep).

Qué hace, cada hora:
  1. Lee `recurso=dia` → `produccion` (las últimas filas de PRODUCCION) y toma las chinches (`CHN-…`).
  2. Por cada chinche sin issue, abre un issue 📌 con etiqueta `chinche` en este repo (el texto
     textual, la vista, el elemento y la página) y apunta `ENCARGO TOMADO · chinche` en el Sheet.
     El revisor de chinches (rutina diaria de Claude) trabaja esos issues: corrige, verifica,
     publica y cierra.
  3. Por cada issue `chinche` cerrado como completado, apunta `ENCARGO CUMPLIDO · chinche` en el
     Sheet (una sola vez: el issue queda con la etiqueta `en-sheet`).
  4. Reescribe `datos/encargos.json` (lo que leen «Tus recados» y la Línea) desde los issues.

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


def issues_chinche():
    out = gh('issue', 'list', '--label', 'chinche', '--state', 'all', '--limit', '300',
             '--json', 'number,title,body,state,stateReason,labels,createdAt,closedAt,url')
    lista = json.loads(out or '[]')
    for it in lista:
        m = RE_ID.search(it.get('body') or '')
        it['chn'] = m.group(0) if m else None
        it['etiquetas'] = [l.get('name') for l in (it.get('labels') or [])]
    return lista


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
                       'carta': d.get('carta')}
    return vistas


def cuerpo_issue(cid, c):
    L = ['# Encargo desde la Sala de Edición · 1 cambio',
         'Alejandro · %s · clavada en la Sala (llegó por el puente `nube/sala_chinches.py`)' % c['fecha'],
         'Repo: yodesarrollomx/sala-edicion · publicado en yodesarrollomx.github.io/sala-edicion/', '',
         '## 1 · sala-edicion · vista "%s"' % (c['vista'] or '—')]
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
        dia = sala.get('dia')
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

    nuevas = 0
    for cid, c in sorted(enSheet.items()):
        if cid in porId:
            continue
        titulo = '📌 sala · %s · %s' % (c['vista'] or 'sala', re.sub(r'\s+', ' ', c['texto'])[:70])
        sala.avisar('  + %s · %s' % (cid, titulo))
        nuevas += 1
        if args.simular:
            continue
        url = gh('issue', 'create', '--title', titulo, '--body', cuerpo_issue(cid, c),
                 '--label', 'chinche').strip()
        sala.post('produccion', pieza='ENCARGO TOMADO · chinche', estado='en curso',
                  detalle=json.dumps({'id': cid, 'issue': url}, ensure_ascii=False), enlace=url)

    # «✦ Proponme ideas ahora» (Árbol, chinche #20): la fila `ENCARGO · ideas` enciende el semillero
    hechas = set()
    pedidas = {}
    for f in dia.get('produccion') or []:
        ev, det = str(f.get('pieza') or ''), str(f.get('detalle') or '')
        m = re.search(r'"id"\s*:\s*"([^"]+)"', det)
        if not ev.startswith('ENCARGO') or 'ideas' not in ev or not m:
            continue
        if 'CUMPLIDO' in ev:
            hechas.add(m.group(1))
        else:
            pedidas.setdefault(m.group(1), f)
    for iid in sorted(set(pedidas) - hechas):
        sala.avisar('  ✦ pidió ideas · %s → semillero' % iid)
        if args.simular:
            continue
        gh('workflow', 'run', 'sala-arranque.yml', '--ref', 'main', '-f', 'modo=ideas')
        sala.post('produccion', pieza='ENCARGO CUMPLIDO · ideas', estado='cumplida',
                  detalle=json.dumps({'id': iid, 'que': 'semillero encendido'}, ensure_ascii=False))

    refrescar_piezas(args.simular)

    cumplidas = 0
    for it in issues:
        if not it['chn'] or it['state'] != 'CLOSED' or it.get('stateReason') == 'NOT_PLANNED' \
                or 'en-sheet' in it['etiquetas']:
            continue
        sala.avisar('  ✓ cumplida · %s · %s' % (it['chn'], it['url']))
        cumplidas += 1
        if args.simular:
            continue
        sala.post('produccion', pieza='ENCARGO CUMPLIDO · chinche', estado='cumplida',
                  detalle=json.dumps({'id': it['chn'], 'issue': it['url']}, ensure_ascii=False),
                  enlace=it['url'])
        gh('issue', 'edit', str(it['number']), '--add-label', 'en-sheet')

    # «Tus recados» y la Línea leen este archivo: su verdad ahora son los issues
    if not args.simular:
        issues = issues_chinche()
        regs = []
        for it in sorted([i for i in issues if i['chn']], key=lambda i: i['createdAt']):
            c = enSheet.get(it['chn']) or {}
            txt = c.get('texto') or re.sub(r'^📌\s*sala\s*·\s*[^·]*·\s*', '', it['title'])
            regs.append({'que': json.dumps({'id': it['chn'], 'texto': txt}, ensure_ascii=False),
                         'estado': 'cumplida' if it['state'] == 'CLOSED' else 'en curso',
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
