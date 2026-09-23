#!/usr/bin/env python3
"""El montador de la mesa: lo que antes hacía `sala_publicar.py` en la Mac, ahora en la nube.

Para cada pieza viva toma su tira MÁS RECIENTE, le encima lo que los editores decidieron en el
Sheet (el Sheet manda: marcas y notas de `recurso=dia` del día en que se montó), y a cada lámina
que quedó en «no» (o que se quedó sin decidir) le prepara tomas nuevas que obedecen la nota:

  nota + texto + promesa → cerebro (Gemini; OpenAI con tope) → receta y, si la nota lo pide,
  texto nuevo → imagen (Cloudflare FLUX → Gemini) → compositor (texto de la casa) → tomas.

Luego escribe la tira nueva (la pieza COMPLETA, invariante 9: una carta nunca llega sola),
con `decidir`/`mapa` y las tomas en `candidatas`, y la carta con id NUEVO y
`origen: rehecha-de <tira anterior>` (invariante 16). Montar va aparte (`--montar`) para que
el workflow publique primero y la carta nunca llegue a la mesa sin su tira.

Lo que NO hace: decidir (INVIOLABLE 3), tocar una lámina aprobada, montar una pieza publicada.

Uso:
  python3 sala_mesa.py --simular          # dice qué haría; no gasta ni escribe
  python3 sala_mesa.py --producir         # genera tomas y escribe tiras/plan (no monta)
  python3 sala_mesa.py --montar           # lee el plan y hace accion:proponer
"""

import argparse
import hashlib
import json
import pathlib
import re
import sys
import tempfile

import sala_cliente as sala
from motores import cerebro, imagen
from motores._comun import MotorError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'datos'
TIRAS = DATOS / 'tiras'
PLAN = RAIZ / 'nube' / '.producido' / 'plan-mesa.json'
NO_PIEZA = re.compile(r'(corte|video|prueba|coherencia)', re.I)
DINERO = re.compile(r'(\$\s*\d|\d[\d.,]*\s*(pesos|mil|mdp|millones)\b|\bgratis\b)', re.I)


def _leer(p, defecto=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defecto


def fecha_de(t):
    fechas = [str(t.get('fecha') or '')]
    for lam in t.get('laminas') or []:
        fechas.append(str(lam.get('fecha') or ''))
        fechas += [str(v.get('fecha') or '') for v in lam.get('versiones') or []]
    return max(f for f in fechas if f) if any(fechas) else ''


def tiras_por_pieza():
    """{slug: (id, tira)} con la tira más reciente de cada pieza."""
    mejores = {}
    for ruta in TIRAS.glob('*.json'):
        if ruta.stem == 'index' or NO_PIEZA.search(ruta.stem):
            continue
        t = _leer(ruta, {})
        if not isinstance(t, dict) or not t.get('laminas'):
            continue
        slug = str(t.get('pieza_slug') or ruta.stem.split('-')[0])
        montada = (fechas_montada(ruta.stem) or [''])[-1]
        clave = (max(montada, fecha_de(t)), montada, ruta.stem)
        if slug not in mejores or clave > mejores[slug][0]:
            mejores[slug] = (clave, ruta.stem, t)
    return {s: (i, t) for s, (_, i, t) in mejores.items()}


def publicadas():
    """Slugs/títulos de piezas que ya salieron: «una publicada no vuelve»."""
    p = _leer(DATOS / 'piezas.json', {}) or {}
    e = _leer(DATOS / 'embudo.json', {}) or {}
    salieron = {str(x.get('pieza') or '').lower() for x in p.get('piezas') or []
                if str(x.get('etapa')) == 'publicada'}
    return salieron | {str(x.get('pieza') or '').lower() for x in e.get('piezas') or []}


def vetadas(slug):
    v = _leer(DATOS / 'vetados.json', {}) or {}
    out = []
    for clave in ('global', slug.upper()):
        for x in v.get(clave) or []:
            out.append(str(x.get('palabra') if isinstance(x, dict) else x))
    return [x for x in out if x]


def fechas_montada(pid):
    m = _leer(DATOS / 'manifiesto.json', {}) or {}
    return sorted(d for d, h in (m.get('historial') or {}).items()
                  if any(str(p.get('id')) == pid for p in (h or {}).get('propuestas') or []))


def decision_del_sheet(pid, fecha_tira):
    """Lo que los editores marcaron sobre esa carta, por índice de carta. El Sheet manda."""
    fechas = fechas_montada(pid) or ([fecha_tira] if fecha_tira else [])
    for f in reversed(fechas):
        try:
            d = sala.get('dia', f=f) or {}
        except sala.SalaError as e:
            sala.avisar('  ⚠ no pude leer el día %s del Sheet: %s' % (f, e))
            return None, None
        dec = ((d.get('decisiones') or {}).get('propuestas') or {}).get(pid)
        props = [p for p in d.get('propuestas') or [] if str(p.get('id')) == pid]
        if dec or props:
            return dec or {}, (props[0].get('laminas') if props else None)
    return {}, None


def abiertas(tid, t, leer_sheet=True):
    """[(lamina, marca, nota)] de las láminas que piden trabajo, ya con lo del Sheet encima."""
    mapa = t.get('mapa') or {str(i + 1): n for i, n in enumerate(t.get('decidir') or [])}
    dec, srcs = decision_del_sheet(tid, fecha_de(t)) if leer_sheet else ({}, None)
    marcas = (dec or {}).get('laminas') or []
    notas = (dec or {}).get('notas') or []
    por_n = {}
    for i, marca in enumerate(marcas):
        n = mapa.get(str(i + 1))
        if n is None and srcs and i < len(srcs):
            n = next((l.get('n') for l in t['laminas'] if l.get('src') == srcs[i]), None)
        if n is None:
            n = i + 1
        por_n[int(n)] = (str(marca or ''), str(notas[i] if i < len(notas) else '') or
                         str((dec or {}).get('nota') or ''))
    salida = []
    for lam in t['laminas']:
        n = int(lam.get('n') or 0)
        marca, nota = por_n.get(n, ('', ''))
        if marca == 'si' or (not marca and lam.get('estado') == 'aprobada'):
            continue
        nota = nota or str(lam.get('nota_previa') or '') or \
            str(((lam.get('versiones') or [{}])[-1]).get('nota') or '')
        salida.append((lam, marca or lam.get('marca_previa') or 'pendiente', nota))
    return salida


def guardia(texto, veto):
    malas = [v for v in veto if v and v.lower() in texto.lower()]
    if malas:
        return 'usa palabra vetada: %s' % ', '.join(malas)
    if DINERO.search(texto):
        return 'trae dinero o «gratis»'
    return ''


def referencia(t):
    """La lámina aprobada más temprana de la pieza: el mundo al que las demás se parecen
    (invariante 105: «todas tienen que parecerse a la primera lámina que aprobemos»)."""
    for lam in sorted(t.get('laminas') or [], key=lambda x: int(x.get('n') or 0)):
        if lam.get('estado') == 'aprobada':
            return lam
    return None


def producir_tomas(slug, t, lam, nota, reglas, cola, carpeta, n_tomas):
    from sala_compositor import componer, avisos as avisos_comp
    veto = vetadas(slug)
    tomas, avisos = [], []
    ref = referencia(t)
    ref_txt = ('Lámina %s aprobada — dice «%s»; muestra: %s' % (ref.get('n'), ref.get('dice'), ref.get('ve') or '(sin descripción)')
               if ref and ref.get('n') != lam.get('n') else '')
    if not nota and ref_txt:
        nota = 'Que se parezca a la lámina %s aprobada: mismos personajes, mismo lugar, misma luz.' % ref.get('n')
    for k in range(1, n_tomas + 1):
        try:
            d, quien, av = cerebro.lamina(t.get('pieza') or slug, t.get('promesa'), lam.get('dice'),
                                          lam.get('ve'), nota, veto, reglas, cola, k, ref_txt)
            avisos += av
            texto = d['texto']
            problema = guardia(texto, veto)
            if problema:
                avisos.append('toma %d: el texto propuesto %s; se queda el de la tira' % (k, problema))
                texto = str(lam.get('dice') or '')
                if guardia(texto, veto):
                    avisos.append('toma %d: el texto de la tira también %s — no se monta' % (k, guardia(texto, veto)))
                    continue
            datos, ext, motor, av2 = imagen.generar(d['receta'], reglas)
            avisos += av2
            with tempfile.NamedTemporaryFile(suffix='.' + ext) as tmp:
                tmp.write(datos)
                tmp.flush()
                png, jpg = componer(tmp.name, texto, carpeta / ('L%d-%d.png' % (lam['n'], k)))
            tomas.append({'src': str(jpg.relative_to(RAIZ)), 'original': str(png.relative_to(RAIZ)),
                          'titulo': chr(64 + k), 'texto': str(d.get('porque') or '')[:160],
                          'dice': texto, 'motor': motor, 'cerebro': quien,
                          'huella': hashlib.md5(png.read_bytes()).hexdigest()})
        except MotorError as e:
            avisos.append('toma %d: %s' % (k, e))
    return tomas, avisos + avisos_comp


def main():
    ap = argparse.ArgumentParser(description='El montador de la mesa de la Sala.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--simular', action='store_true')
    g.add_argument('--producir', action='store_true')
    g.add_argument('--montar', action='store_true')
    ap.add_argument('--pieza', help='sólo esta pieza (slug)')
    ap.add_argument('--sin-sheet', action='store_true', help='no leer el Sheet (pruebas locales)')
    args = ap.parse_args()
    sala.enmascarar_en_actions()

    if args.montar:
        return montar()

    reglas, cola = {}, []
    if not args.sin_sheet:
        try:
            reglas = (sala.get('reglas') or {}).get('reglas') or {}
            cola = (sala.get('cola') or {}).get('cola') or []
        except sala.SalaError as e:
            sala.avisar('✗ no pude leer REGLAS/COLA: %s — «no contestó» no es «no hay nada»' % e)
            return 2
    n_tomas = int(float(str(reglas.get('mesa_tomas_por_lamina') or 2)))
    tope = int(float(str(reglas.get('mesa_tope_laminas') or 8)))
    ya_salieron = publicadas()
    hoy = sala.hoy_hermosillo()
    plan, gastadas = [], 0

    for slug, (tid, t) in sorted(tiras_por_pieza().items()):
        if args.pieza and slug != args.pieza:
            continue
        nombre = str(t.get('pieza') or slug)
        if nombre.lower() in ya_salieron:
            sala.avisar('· %s: ya publicada, no vuelve a la mesa' % nombre)
            continue
        pend = abiertas(tid, t, leer_sheet=not args.sin_sheet)
        if not pend:
            sala.avisar('· %s (%s): todas sus láminas aprobadas — nada que rehacer' % (nombre, tid))
            continue
        sala.avisar('▶ %s · tira %s · %d lámina(s) abiertas' % (nombre, tid, len(pend)))
        nueva_id = '%s-nube-%s-%s' % (slug, hoy, hashlib.md5(
            json.dumps([(l['n'], n) for l, _, n in pend], ensure_ascii=False).encode()).hexdigest()[:6])
        carpeta = RAIZ / 'laminas' / ('%s-n%s' % (slug, hoy))
        tira = json.loads(json.dumps(t))
        decidir = []
        for lam, marca, nota in pend:
            sala.avisar('   L%s · %s · nota: «%s»' % (lam.get('n'), marca, (nota or '(sin nota)')[:140]))
            destino = next(l for l in tira['laminas'] if l.get('n') == lam.get('n'))
            destino['marca_previa'], destino['nota_previa'] = marca, nota
            if args.simular:
                decidir.append(lam['n'])
                continue
            if gastadas >= tope:
                sala.avisar('   ⏸ tope de %d láminas por corrida; ésta queda para mañana' % tope)
                continue
            if marca != 'no' and str(reglas.get('mesa_remontar_sin_decidir') or '0') == '1' \
                    and destino.get('candidatas'):
                sala.avisar('   ↺ nunca se decidió: se vuelve a montar con sus tomas')
                decidir.append(lam['n'])
                continue
            tomas, avisos = producir_tomas(slug, t, lam, nota, reglas, cola, carpeta, n_tomas)
            gastadas += 1
            for a in avisos:
                sala.avisar('     ⚠ %s' % a)
            if not tomas:
                sala.avisar('   ✗ sin tomas para L%s: se queda pendiente' % lam['n'])
                continue
            destino['estado'] = 'rehecha'
            destino['candidatas'] = tomas
            destino['fecha'] = hoy
            decidir.append(lam['n'])
        if not decidir:
            continue
        tira.update({'decidir': decidir, 'mapa': {str(i + 1): n for i, n in enumerate(decidir)},
                     'titulo': '%s · rehechas con tus notas (%d)' % (nombre, len(decidir)),
                     'nota': 'La pieza completa. Sólo las láminas marcadas piden respuesta: en cada '
                             'una vienen tomas nuevas hechas con tu última nota. Elige con «Ésta».',
                     'origen': 'rehecha-de %s' % tid, 'fecha': hoy, 'base': tid})
        carta = {'id': nueva_id, 'titulo': tira['titulo'], 'tipo': 'laminas',
                 'laminas': [next(l['src'] for l in tira['laminas'] if l['n'] == n) for n in decidir],
                 'opciones': [], 'video': None, 'origen': 'rehecha-de %s' % tid}
        plan.append({'familia': slug, 'tira_id': nueva_id, 'carta': carta})
        if not args.simular:
            (TIRAS / (nueva_id + '.json')).write_text(json.dumps(tira, ensure_ascii=False, indent=1),
                                                     encoding='utf-8')
            idx = _leer(TIRAS / 'index.json', []) or []
            if nueva_id not in idx:
                (TIRAS / 'index.json').write_text(json.dumps([nueva_id] + idx, ensure_ascii=False),
                                                  encoding='utf-8')

    sala.avisar('resumen: %d carta(s) %s' % (len(plan), 'que se montarían' if args.simular else 'listas para montar'))
    if not args.simular:
        PLAN.parent.mkdir(parents=True, exist_ok=True)
        PLAN.write_text(json.dumps({'fecha': hoy, 'cartas': plan}, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    return 0


def montar():
    plan = _leer(PLAN, None)
    if not plan or not plan.get('cartas'):
        sala.avisar('nada que montar (no hay plan de esta corrida)')
        return 0
    for c in plan['cartas']:
        r = sala.post('proponer', fecha=plan['fecha'], propuestas=[c['carta']], familia=c['familia'])
        sala.avisar('✓ montada %s · retiradas: %s' % (c['tira_id'], ', '.join(r.get('retiradas_familia') or []) or '—'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
