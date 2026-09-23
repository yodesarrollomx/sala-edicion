#!/usr/bin/env python3
"""El productor, en la nube: abre compuertas y ENCOLA. Nunca ejecuta.

Qué hace: lee las marcas del día y, lámina por lámina, escribe en la hoja COLA los trabajos
que quedaron habilitados. Es el `--planear` del productor de la Mac.

Qué NO hace, y por qué: **no ejecuta ninguna etapa**. Una escena cuesta ~17 minutos de
máquina con GPU; un runner de GitHub no tiene GPU. Pero además no debe: la invariante 54 dice
que el productor encola y que ejecutar lo enciende Alejandro desde el Sheet
(`productor_ejecuta_etapas`, vacía de fábrica). Encolar no destruye nada; por eso el estado de
fábrica es el seguro. En la nube ese seguro es además físico.

Las reglas que cuida:

  · INVIOLABLE 10 / PASO 0 — con una petición abierta no se abre ninguna compuerta nueva.
  · Invariante 51 — la compuerta se abre RAMA POR RAMA: un «sí» abre la escena y la voz de
    ESA lámina aunque sus hermanas sigan abiertas. El corte es la única de todo-o-nada.
  · Invariante 48 — el id de un trabajo es `pieza:etapa:item:version`, con `version` = huella
    del INSUMO, nunca un consecutivo. De ahí sale que correr esto diez veces no repita nada.
  · Invariante 53 — nunca dos productores a la vez. En la nube el candado de archivo no sirve
    (el runner es efímero): lo hace `concurrency:` en el workflow.
  · Invariante 10 del manual — el agente no decide. Sólo escribe COLA.
"""

import argparse
import hashlib
import json
import pathlib
import sys

import sala_catalogo as catalogo
import sala_cliente as sala

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MANIFIESTO = RAIZ / 'datos' / 'manifiesto.json'

DEFAULTS = {
    'prospectos_por_rechazo': 2,
    'productor_silencio_desde': 23,
    'productor_silencio_hasta': 7,
    'productor_piezas': 'apodo',
    'productor_ejecuta_etapas': '',
}


def regla(reglas, nombre):
    """Lee del Sheet y, si no está, del default de fábrica — dejando dicho de dónde salió.
    (Regla 46: ningún reporte puede decir «esto lo puso Alejandro» cuando es un default.)"""
    if nombre in reglas and str(reglas[nombre]).strip() != '':
        return reglas[nombre], 'Sheet'
    return DEFAULTS.get(nombre), 'default de fábrica'


def entero(v, si_falla):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return si_falla


def en_silencio(desde, hasta, hora):
    """Cruza la medianoche bien: 23→7 significa callado a las 23, 0, …, 6."""
    if desde == hasta:
        return False
    if desde < hasta:
        return desde <= hora < hasta
    return hora >= desde or hora < hasta


def huella_insumo(lam, cat=None):
    """La `version` del id. INVARIANTE 29: el número de lámina lo dice la TIRA, no el nombre
    del archivo, y la identidad de una lámina es su SERIAL + huella del CATÁLOGO — derivarla
    de una ruta del repo es justo lo que corrompió 8 seriales el 8-sep.

    Orden de preferencia, cada uno declarado en la evidencia del trabajo:
      1. catálogo (`sala_catalogo.huella_de`) — la fuente de verdad, Drive + Sheet.
      2. md5 del archivo en el repo — SÓLO si el catálogo no conoce esa ruta todavía (una
         lámina recién montada que aún no pasó por `accion:catalogar`). Declarado como
         respaldo, nunca como si fuera la identidad canónica.
      3. hash de `{src, dice}` de la tira — si ni el archivo existe (la imagen vive sólo en
         Drive y el catálogo tampoco la conoce todavía).
    """
    src = str((lam or {}).get('src') or '')
    if src:
        d = catalogo.huella_de(src, cat)
        if d:
            return d['huella'][:8], 'catalogo:' + d['serial']
        p = RAIZ / src.lstrip('/')
        if p.is_file():
            return hashlib.md5(p.read_bytes()).hexdigest()[:8], 'archivo-sin-catalogar'
    semilla = json.dumps({'src': src, 'dice': (lam or {}).get('dice', '')},
                         sort_keys=True, ensure_ascii=False)
    return hashlib.md5(semilla.encode('utf-8')).hexdigest()[:8], 'tira-sin-imagen'


def tira_de(pid):
    try:
        return json.loads((RAIZ / 'datos' / 'tiras' / ('%s.json' % pid)).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def lamina_tira(tira, n):
    return next((l for l in (tira or {}).get('laminas') or [] if str(l.get('n')) == str(n)), None)


def datos_lamina(lam):
    """Lo que un motor necesita para trabajar sin volver a preguntarle al día: qué imagen es
    y qué dice/muestra. Antes la evidencia no llevaba `src` y ninguna escena podía encontrar
    su lámina (se quedaban `pendiente` para siempre con «sin id de Drive»)."""
    lam = lam if isinstance(lam, dict) else {}
    return {k: str(lam.get(k) or '') for k in ('src', 'dice', 've') if lam.get(k)}


def nota_de(dia, pid, i):
    """La nota que el editor dejó junto a su «no» en esa lámina: el prospecto la tiene que
    atender (LA-LEY §2: la nota persigue a la lámina)."""
    dec = ((dia.get('decisiones') or {}).get('propuestas') or {}).get(pid) or {}
    notas = dec.get('notas') or dec.get('notas_laminas') or []
    if isinstance(notas, list) and i < len(notas):
        return str(notas[i] or '')
    return str(dec.get('nota') or '')


def marcas_de(dia, pid):
    dec = (dia.get('decisiones') or {}).get('propuestas') or {}
    return ((dec.get(pid) or {}).get('laminas')) or []


def planear(dia, cola, reglas, cat=None):
    """Devuelve (trabajos_nuevos, bitácora_de_lo_decidido). `cat` es el catálogo ya cargado
    (sala_catalogo.cargar()) — se pasa una vez para no releerlo por cada lámina."""
    piezas_txt, _ = regla(reglas, 'productor_piezas')
    vigiladas = [x.strip() for x in str(piezas_txt or '').split(',') if x.strip()]
    prospectos = entero(regla(reglas, 'prospectos_por_rechazo')[0], 2)

    ya = {t.get('id') for t in cola}
    nuevos, diario = [], []

    for p in (dia.get('propuestas') or []):
        pid = str(p.get('id') or '')
        # 23-sep: la pieza la dice su tira (`mesa-vacia`, no `mesa`), y el número real de cada
        # lámina lo dice su mapa: la carta «lámina 1 de 1» del Apodo es la L6, no la L1.
        tira = tira_de(pid)
        mapa = (tira or {}).get('mapa') or {}
        familia = str((tira or {}).get('pieza_slug') or (pid.split('-')[0] if pid else ''))
        if vigiladas and familia not in vigiladas and '-nube-' not in pid:
            diario.append('%s no se vigila (REGLA productor_piezas = %s)' % (pid, ','.join(vigiladas)))
            continue
        laminas = p.get('laminas') or []
        if not isinstance(laminas, list) or not laminas:
            continue
        marcas = marcas_de(dia, pid)
        estados = []

        for i, lam in enumerate(laminas):
            marca = str(marcas[i]) if i < len(marcas) else ''
            estados.append(marca or 'pendiente')
            item = str(mapa.get(str(i + 1), i + 1)) if tira else str(i + 1)
            lam_t = lamina_tira(tira, item) if tira else None
            ver, de_donde = huella_insumo(lam_t or (lam if isinstance(lam, dict) else {}), cat)
            extra = {'n_real': True, **datos_lamina(lam_t)} if lam_t else datos_lamina(lam)

            if marca == 'si':
                # Invariante 51: se abre ESTA rama, sin esperar a las hermanas.
                for etapa in ('escena', 'voz'):
                    tid = '%s:%s:%s:%s' % (familia, etapa, item, ver)
                    if tid in ya:
                        continue
                    nuevos.append({'id': tid, 'pieza': familia, 'etapa': etapa, 'item': item,
                                   'estado': 'pendiente', 'prioridad': 5, 'pidio': 'productor-nube',
                                   'evidencia': {'de': pid, 'lamina': item, 'insumo': de_donde,
                                                 'nota': nota_de(dia, pid, i), **extra}})
                    diario.append('abre %s de la lámina %s de %s' % (etapa, item, pid))

            elif marca == 'no' and '-nube-' in pid:
                # Las cartas del montador las rehace el propio montador (05:40): tomas nuevas
                # con esta nota, compuestas y MONTADAS. Un prospecto aquí sólo gastaría cuota
                # en imágenes que nadie ve.
                diario.append('lámina %s de %s: la rehace el montador de la mesa con tu nota' % (item, pid))

            elif marca == 'no':
                # Un «no» abre candidatas, y sólo si no existen ya para ESA lámina en ESA
                # versión — que es justo lo que el id garantiza.
                for k in range(1, prospectos + 1):
                    tid = '%s:prospecto:%s-%d:%s' % (familia, item, k, ver)
                    if tid in ya:
                        continue
                    nuevos.append({'id': tid, 'pieza': familia, 'etapa': 'prospecto',
                                   'item': '%s-%d' % (item, k), 'estado': 'pendiente',
                                   'prioridad': 3, 'pidio': 'productor-nube',
                                   'evidencia': {'de': pid, 'lamina': item, 'insumo': de_donde,
                                                 'nota': nota_de(dia, pid, i), **extra}})
                    diario.append('abre candidata %d de la lámina %s de %s (por un «no»)'
                                  % (k, item, pid))
            # 'pendiente' → nada. Eso le toca al editor, no al productor.

        # El corte es la ÚNICA compuerta de todo-o-nada: todas aprobadas.
        if tira:
            # 23-sep: con tira, «todas» es la PIEZA entera, no la carta (que sólo trae lo que
            # faltaba decidir). Antes una carta de 1 lámina abría el corte de un video de 1 escena.
            nuevos_ids = {x['id'] for x in nuevos}
            por_n = {str(mapa.get(str(i + 1), i + 1)): e for i, e in enumerate(estados)}
            listas, faltan = [], []
            for lt in tira.get('laminas') or []:
                n = str(lt.get('n'))
                ok = por_n.get(n) == 'si' or (n not in por_n and lt.get('estado') == 'aprobada')
                (listas if ok else faltan).append(lt)
            if faltan:
                diario.append('el corte de %s NO se abre: láminas sin aprobar %s'
                              % (familia, [l.get('n') for l in faltan]))
                continue
            lam_ev = []
            for lt in listas:
                n, h = str(lt.get('n')), huella_insumo(lt, cat)[0]
                lam_ev.append({'item': n, 'huella': h})
                for etapa in ('escena', 'voz'):   # lo aprobado antes que aún no tiene escena/voz
                    tid = '%s:%s:%s:%s' % (familia, etapa, n, h)
                    if tid in ya or tid in nuevos_ids:
                        continue
                    nuevos.append({'id': tid, 'pieza': familia, 'etapa': etapa, 'item': n,
                                   'estado': 'pendiente', 'prioridad': 5, 'pidio': 'productor-nube',
                                   'evidencia': {'de': pid, 'lamina': n, 'n_real': True,
                                                 **datos_lamina(lt)}})
                    nuevos_ids.add(tid)
            ver_pieza = hashlib.md5(json.dumps(lam_ev, sort_keys=True).encode()).hexdigest()[:8]
            tid = '%s:corte:completo:%s' % (familia, ver_pieza)
            if tid not in ya:
                nuevos.append({'id': tid, 'pieza': familia, 'etapa': 'corte', 'item': 'completo',
                               'estado': 'pendiente', 'prioridad': 7, 'pidio': 'productor-nube',
                               'evidencia': {'de': pid, 'laminas': lam_ev}})
                diario.append('abre el corte de %s (las %d láminas de la pieza)' % (familia, len(lam_ev)))
            continue
        todas_si = bool(estados) and all(e == 'si' for e in estados)
        if todas_si:
            ver_pieza = hashlib.md5(
                json.dumps([huella_insumo(l if isinstance(l, dict) else {}, cat)[0]
                            for l in laminas], sort_keys=True).encode()).hexdigest()[:8]
            tid = '%s:corte:completo:%s' % (familia, ver_pieza)
            if tid not in ya:
                # El corte se ensambla en un runner distinto (o mucho después) del que abrió
                # escena/voz de cada lámina — nunca se puede asumir que `.producido/` local
                # sigue ahí. Por eso la evidencia lleva TODO lo que el montador necesita para
                # reconstruir, sin volver a preguntarle al día: la lista de láminas con su
                # `item` y su huella (la misma `ver` que ya identifica sus trabajos de escena
                # y voz en la COLA).
                lam_ev = [{'item': str(i + 1),
                          'huella': huella_insumo(l if isinstance(l, dict) else {}, cat)[0]}
                         for i, l in enumerate(laminas)]
                nuevos.append({'id': tid, 'pieza': familia, 'etapa': 'corte', 'item': 'completo',
                               'estado': 'pendiente', 'prioridad': 7, 'pidio': 'productor-nube',
                               'evidencia': {'de': pid, 'laminas': lam_ev}})
                diario.append('abre el corte de %s (las %d láminas aprobadas)' % (pid, len(laminas)))
        elif estados:
            abiertas = [i + 1 for i, e in enumerate(estados) if e != 'si']
            diario.append('el corte de %s NO se abre: láminas sin aprobar %s' % (pid, abiertas))

    return nuevos, diario


def main():
    ap = argparse.ArgumentParser(description='El productor de la Sala: planea y encola.')
    ap.add_argument('--planear', action='store_true', default=True,
                    help='(único modo que existe en la nube)')
    ap.add_argument('--simular', action='store_true', help='dice qué encolaría y no escribe')
    ap.add_argument('--ignorar-silencio', action='store_true',
                    help='sólo para pruebas a mano; los crons nunca lo usan')
    args = ap.parse_args()

    sala.enmascarar_en_actions()

    # PASO 0 — INVIOLABLE 10. Esto va ANTES de la red: si hay una petición abierta, no se
    # abre ninguna compuerta, punto.
    if MANIFIESTO.exists():
        try:
            pet = json.loads(MANIFIESTO.read_text(encoding='utf-8')).get('peticiones') or []
        except ValueError:
            pet = []
        abiertas = [x for x in pet if isinstance(x, dict) and x.get('estado') != 'cumplida']
        if abiertas:
            sala.avisar('PASO 0 · hay %d petición(es) abierta(s). No se abre ninguna compuerta '
                        'nueva (INVIOLABLE 10).' % len(abiertas))
            for x in abiertas:
                sala.avisar('   · %s' % str(x.get('pedido'))[:120])
            return 0
        sala.avisar('PASO 0 · sin peticiones abiertas: se puede planear.')

    try:
        reglas_resp = sala.get('reglas')
        reglas = reglas_resp.get('reglas') or {}
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer REGLAS: %s' % e)
        return 2

    desde = entero(regla(reglas, 'productor_silencio_desde')[0], 23)
    hasta = entero(regla(reglas, 'productor_silencio_hasta')[0], 7)
    hora = sala.hora_hermosillo()
    if en_silencio(desde, hasta, hora) and not args.ignorar_silencio:
        sala.avisar('son las %d h en Hermosillo y el horario quieto va de %d a %d. '
                    'El productor se calla.' % (hora, desde, hasta))
        return 0

    ejecuta, de_donde = regla(reglas, 'productor_ejecuta_etapas')
    if str(ejecuta or '').strip():
        sala.avisar('⚠ productor_ejecuta_etapas = «%s» (viene del %s), pero la nube NO ejecuta '
                    'ninguna etapa: no hay GPU en un runner, y ejecutar lo enciende Alejandro '
                    'para la Mac (invariante 54). Aquí sólo se encola.' % (ejecuta, de_donde))

    try:
        dia = sala.get('dia', fresco='1')
        cola = (sala.get('cola') or {}).get('cola') or []
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer el día o la COLA: %s' % e)
        sala.avisar('  No se encola nada. «No contestó» no es «no hay nada» (INVIOLABLE 4).')
        return 2

    try:
        cat = catalogo.cargar()
    except sala.SalaError as e:
        # El catálogo (Sheet + respaldo del repo) fallaron los DOS. No es lo mismo que una
        # lámina que el catálogo simplemente no conoce todavía (eso ya lo maneja
        # huella_insumo con su respaldo declarado) — esto es no tener con qué verificar NADA,
        # así que no se encola con identidades adivinadas.
        sala.avisar('✗ no pude leer el catálogo (ni Sheet ni respaldo): %s' % e)
        sala.avisar('  No se encola nada: sin catálogo, la identidad de cada trabajo se '
                    'basaría en puro nombre de archivo (invariante 29 — así se corrompieron '
                    '8 seriales el 8-sep).')
        return 2

    nuevos, diario = planear(dia, cola, reglas, cat)
    sala.avisar('día %s · %d propuesta(s) · COLA con %d trabajo(s)'
                % (dia.get('fecha'), len(dia.get('propuestas') or []), len(cola)))
    for linea in diario:
        sala.avisar('   · %s' % linea)

    if not nuevos:
        sala.avisar('✓ nada nuevo que encolar. La COLA ya refleja lo decidido.')
        return 0

    if args.simular:
        sala.avisar('— simulación — encolaría %d trabajo(s):' % len(nuevos))
        for t in nuevos:
            sala.avisar('     %s' % t['id'])
        return 0

    r = sala.post('cola', op='upsert', filas=nuevos)
    sala.avisar('✓ COLA: %s nueva(s), %s actualizada(s)'
                % (r.get('creadas'), r.get('actualizadas')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
