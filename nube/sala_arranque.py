#!/usr/bin/env python3
"""El arranque y el semillero: lo que la ronda /sala hacía en la Mac y se perdió con la mudanza.

Dos trabajos, cada uno con su bandera (chinches #20 y #21 de Alejandro, 23-sep):

  --ideas    EL SEMILLERO. Por cada rama viva del árbol, 3 ideas nuevas de publicación (hoja IDEAS,
             estado `propuesta`) y, si hay menos de 5 ramas vivas, 1 premisa candidata (hoja ARBOL,
             nivel `premisa_candidata`). Él elige en el Árbol. Idempotente por día: si hoy ya se
             propusieron para una rama, no se repite.
  --arrancar EL ARRANQUE. Cada idea elegida (`elegida` / `en_produccion`) que todavía no tiene tira
             recibe su guion (una línea por lámina: dice / ve / entiende) y su PRIMERA lámina con 2
             tomas (cerebro → imagen → compositor, las mismas piezas que el montador de la mesa). La
             tira se escribe en datos/tiras y la carta queda en el plan.
  --montar   Monta en la mesa las cartas del plan (accion:proponer), después de publicar la tira.

Lo que NO hace: decidir por él (INVIOLABLE 3), borrar ideas, tocar piezas con tira o publicadas.
`--simular` dice lo que haría sin gastar ni escribir.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sys
import unicodedata

import sala_cliente as sala
from motores import cerebro
from motores._comun import MotorError

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'datos'
TIRAS = DATOS / 'tiras'
PLAN = RAIZ / 'nube' / '.producido' / 'plan-arranque.json'
N_LAMINAS = {'lámina': 1, 'lamina': 1, 'carrusel': 5, 'reel': 6}

INSTR_GUION = (
    'Eres guionista de piezas cortas para redes de Yo Desarrollo, una desarrolladora en Hermosillo, '
    'Sonora, que vende el Plan de Potencial de un terreno (qué puede llegar a ser, calculado, no opinado). '
    'Tono: cálido, directo, local, sin tecnicismos ni cifras de dinero, sin «gratis». Devuelve SOLO un '
    'JSON: {"promesa": "una frase", "laminas": [{"n": 1, "dice": "texto corto que va escrito en la '
    'lámina (máx 14 palabras)", "ve": "qué se ve en la ilustración, concreto: personas, lugar, luz", '
    '"entiende": "qué entiende quien la ve"}]}.')

INSTR_IDEAS = (
    'Eres editor de contenido de Yo Desarrollo (desarrolladora en Hermosillo, Sonora; vende el Plan de '
    'Potencial de un terreno). Propón ideas de publicación NUEVAS, distintas de las que ya existen, que '
    'defiendan la premisa dada. Sin cifras de dinero ni «gratis». Devuelve SOLO un JSON: {"ideas": '
    '[{"titulo": "título corto y memorable", "bajada": "una frase: de qué trata", "formato": "Lámina" | '
    '"Carrusel" | "Reel"}]}.')

INSTR_PREMISA = (
    'Eres estratega de marca de Yo Desarrollo (Plan de Potencial de terrenos, Hermosillo). Propón UNA '
    'premisa nueva —una afirmación que la marca pueda defender con varias publicaciones— distinta de las '
    'que ya existen. Devuelve SOLO un JSON: {"titulo": "la premisa en una frase", "bajada": "por qué '
    'importa, en una frase"}.')


def _leer(p, defecto=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defecto


def slug(texto):
    t = unicodedata.normalize('NFD', str(texto or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', t).strip('-')[:40] or 'idea'


def pensar(texto, instruccion, reglas, cola):
    """Gemini primero; OpenAI con tope si Gemini no contesta (la misma cascada del cerebro)."""
    fallas = []
    for nombre, f in (('gemini', lambda: cerebro._gemini(texto, reglas, instruccion)),
                      ('openai', lambda: cerebro._openai(texto, reglas, cola or [], instruccion))):
        try:
            crudo = f()
        except MotorError as e:
            fallas.append('%s: %s' % (nombre, e))
            continue
        d = cerebro._json_de(crudo)
        if d:
            return d
        fallas.append('%s contestó sin JSON: «%s»' % (nombre, re.sub(r'\s+', ' ', str(crudo))[:160]))
    raise MotorError('el cerebro no contestó con un JSON (%s)' % ' | '.join(fallas), intermitente=True)


def leer_hoja(recurso, clave, respaldo):
    try:
        r = sala.get(recurso) or {}
        v = r.get(clave)
        if isinstance(v, list):
            return v, 'sheet'
    except sala.SalaError as e:
        sala.avisar('⚠ no leí %s del Sheet (%s): uso la copia del repo' % (recurso, e))
    return (_leer(DATOS / respaldo, {}) or {}).get(clave) or [], 'copia'


def slugs_con_tira():
    out = set()
    for tid in _leer(TIRAS / 'index.json', []) or []:
        t = _leer(TIRAS / (tid + '.json'), {}) or {}
        for s in (t.get('pieza_slug'), slug(t.get('pieza')), str(tid).split('-')[0]):
            if s:
                out.add(slug(s))
    return out


# ───────────────────────────── el semillero (#20) ─────────────────────────────
def semillero(simular, reglas, cola):
    nodos, _ = leer_hoja('arbol', 'nodos', 'arbol.json')
    ideas, fuente = leer_hoja('ideas', 'ideas', 'ideas.json')
    hoy = sala.hoy_hermosillo()
    temas = [n for n in nodos if n.get('nivel') == 'tema' and 'cortada' not in str(n.get('estado') or '')]
    existentes = {slug(i.get('titulo')) for i in ideas} | {i.get('id') for i in ideas}
    nuevas = []
    for tm in temas:
        de_hoy = [i for i in ideas if i.get('premisa') == tm.get('id') and str(i.get('creada')) == hoy]
        if len(de_hoy) >= 3:
            sala.avisar('· %s: ya tiene sus 3 ideas de hoy' % tm.get('titulo'))
            continue
        ya = [i.get('titulo') for i in ideas if i.get('premisa') == tm.get('id')]
        if simular:
            sala.avisar('  — simulación — 3 ideas para «%s»' % tm.get('titulo'))
            continue
        try:
            d = pensar('Premisa: %s\nPor qué: %s\nIdeas que YA existen (no repitas): %s\nPropón 3.'
                       % (tm.get('titulo'), tm.get('bajada') or '', '; '.join(ya[:30]) or 'ninguna'),
                       INSTR_IDEAS, reglas, cola)
        except MotorError as e:
            sala.avisar('  ✗ %s: %s' % (tm.get('titulo'), e))
            continue
        for x in (d.get('ideas') or [])[:3]:
            iid = slug(x.get('titulo'))
            if not x.get('titulo') or iid in existentes:
                continue
            existentes.add(iid)
            fmt = str(x.get('formato') or 'Lámina').strip().capitalize()
            nuevas.append({'premisa': tm.get('id'), 'id': iid, 'titulo': x['titulo'][:90],
                           'bajada': str(x.get('bajada') or '')[:200],
                           'formato': fmt if fmt.lower() in N_LAMINAS else 'Lámina',
                           'estado': 'propuesta', 'creada': hoy, 'nota': 'propuesta por el semillero'})
    if nuevas:
        sala.post('ideas', forzar=1, filas=nuevas)
    sala.avisar('ideas nuevas: %d%s' % (len(nuevas), '' if fuente == 'sheet' else ' (leí la copia)'))

    vivas = len(temas)
    ya_cand = [n for n in nodos if n.get('nivel') == 'premisa_candidata' and n.get('estado') == 'candidata']
    if vivas < 5 and not ya_cand and not simular:
        try:
            p = pensar('Premisas vivas: %s' % '; '.join(t.get('titulo') or '' for t in temas),
                       INSTR_PREMISA, reglas, cola)
            fila = {'nivel': 'premisa_candidata', 'id': 'cand-' + slug(p.get('titulo')), 'padre': 'ppp',
                    'titulo': str(p.get('titulo') or '')[:120], 'bajada': str(p.get('bajada') or '')[:200],
                    'orden': 99, 'estado': 'candidata', 'nota': 'propuesta por el semillero ' + hoy}
            if fila['titulo']:
                sala.post('arbol', forzar=1, filas=[fila])
                sala.avisar('premisa candidata: «%s»' % fila['titulo'])
        except MotorError as e:
            sala.avisar('  ✗ premisa candidata: %s' % e)
    return 0


# ───────────────────────────── el arranque (#21) ─────────────────────────────
def arranque(simular, reglas, cola, tope):
    from sala_mesa import producir_tomas, guardia, vetadas
    ideas, _ = leer_hoja('ideas', 'ideas', 'ideas.json')
    hoy = sala.hoy_hermosillo()
    con_tira = slugs_con_tira()
    n_tomas = int(float(str(reglas.get('mesa_tomas_por_lamina') or 2)))
    pend = [i for i in ideas if re.search(r'elegida|produccion', str(i.get('estado') or ''))
            and slug(i.get('id')) not in con_tira and slug(i.get('titulo')) not in con_tira]
    sala.avisar('ideas elegidas sin arrancar: %d' % len(pend))
    plan = []
    bitacora = []   # 23-sep: lo que la Sala le dice a él de cada idea (datos/arranque.json, repo público)

    def apunta(nombre, resultado, motivo=''):
        m = re.sub(r'key=[^&\s"]+', 'key=***', str(motivo or ''))
        if ' 401' in m or 'invalid authentication' in m:
            m = 'Google rechazó la llave de Gemini (401): hay que renovar GEMINI_API_KEY'
        elif 'OPENAI' in m and 'gemini' not in m.lower():
            m = 'sin cerebro disponible (Gemini no contestó y no hay respaldo de pago)'
        bitacora.append({'pieza': nombre, 'resultado': resultado, 'motivo': m[:160]})

    for i in pend[:tope]:
        s, nombre = slug(i.get('id') or i.get('titulo')), str(i.get('titulo') or i.get('id'))
        n = N_LAMINAS.get(str(i.get('formato') or '').lower(), 1)
        sala.avisar('▶ %s (%s, %d lámina%s)' % (nombre, i.get('formato'), n, '' if n == 1 else 's'))
        if simular:
            continue
        veto = vetadas(s)
        try:
            g = pensar('Pieza: %s\nDe qué trata: %s\nFormato: %s de %d lámina(s).\nPalabras prohibidas: %s'
                       % (nombre, i.get('bajada') or '', i.get('formato'), n, ', '.join(veto) or 'ninguna'),
                       INSTR_GUION, reglas, cola)
        except MotorError as e:
            sala.avisar('  ✗ sin guion: %s' % e)
            apunta(nombre, 'sin guion', e)
            continue
        lams = [l for l in (g.get('laminas') or []) if l.get('dice')][:n]
        if not lams:
            sala.avisar('  ✗ el guion vino vacío')
            apunta(nombre, 'sin guion', 'el cerebro devolvió un guion vacío')
            continue
        for k, l in enumerate(lams, 1):
            l['n'] = k
            if guardia(str(l.get('dice')), veto):
                l['dice'] = ''
        lam1 = dict(lams[0])
        if not lam1.get('dice'):
            sala.avisar('  ✗ el texto de la lámina 1 trae algo prohibido; no se arranca')
            apunta(nombre, 'sin lámina', 'el texto traía una palabra vetada; se reintenta')
            continue
        t = {'pieza': nombre, 'pieza_slug': s, 'promesa': g.get('promesa') or i.get('bajada') or '',
             'laminas': [lam1]}
        carpeta = RAIZ / 'laminas' / ('%s-a%s' % (s, hoy))
        tomas, avisos = producir_tomas(s, t, lam1, '', reglas, cola, carpeta, n_tomas)
        for a in avisos:
            sala.avisar('     ⚠ %s' % a)
        if not tomas:
            sala.avisar('  ✗ sin tomas para la lámina 1: se intenta en la próxima corrida')
            apunta(nombre, 'sin lámina', '; '.join(avisos) or 'el motor de imagen no devolvió tomas')
            continue
        lam1.update({'src': tomas[0]['src'], 'estado': 'propuesta', 'version': 1, 'fecha': hoy,
                     'candidatas': tomas, 'dice': tomas[0].get('dice') or lam1['dice']})
        tid = '%s-arranque-%s-%s' % (s, hoy, hashlib.md5(json.dumps(lams, ensure_ascii=False).encode()).hexdigest()[:6])
        tira = {'pieza': nombre, 'pieza_slug': s, 'promesa': t['promesa'], 'formato': i.get('formato'),
                'laminas': [lam1], 'guion': lams, 'decidir': [1], 'mapa': {'1': 1}, 'fecha': hoy,
                'titulo': '%s · arranque: guion y lámina 1' % nombre,
                'nota': ('Idea elegida en el Árbol. Aquí va el guion completo y la PRIMERA lámina con %d tomas: '
                         'elige una con «Ésta». Cuando la apruebes, las demás se hacen a su semejanza.' % len(tomas)),
                'origen': 'arranque-de idea %s' % i.get('id'), 'base': None}
        (TIRAS / (tid + '.json')).write_text(json.dumps(tira, ensure_ascii=False, indent=1), encoding='utf-8')
        idx = _leer(TIRAS / 'index.json', []) or []
        if tid not in idx:
            (TIRAS / 'index.json').write_text(json.dumps([tid] + idx, ensure_ascii=False), encoding='utf-8')
        plan.append({'familia': s, 'tira_id': tid, 'carta': {
            'id': tid, 'titulo': tira['titulo'], 'tipo': 'laminas', 'laminas': [lam1['src']],
            'opciones': [], 'video': None, 'origen': tira['origen']}})
        apunta(nombre, 'arrancada', 'guion de %d lámina(s) y lámina 1 con %d tomas en tu mesa' % (len(lams), len(tomas)))
        sala.avisar('  ✓ guion de %d lámina(s) y %d tomas de la lámina 1 · tira %s' % (len(lams), len(tomas), tid))
    if not simular:
        PLAN.parent.mkdir(parents=True, exist_ok=True)
        PLAN.write_text(json.dumps({'fecha': hoy, 'cartas': plan}, ensure_ascii=False, indent=1), encoding='utf-8')
        import datetime
        (DATOS / 'arranque.json').write_text(json.dumps({'corrida': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%MZ'),
            'piezas': bitacora}, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    sala.avisar('resumen: %d pieza(s) arrancadas' % len(plan))
    return 0


def montar():
    plan = _leer(PLAN, None)
    if not plan or not plan.get('cartas'):
        sala.avisar('nada que montar')
        return 0
    for c in plan['cartas']:
        sala.post('proponer', fecha=plan['fecha'], propuestas=[c['carta']], familia=c['familia'])
        sala.avisar('✓ en tu mesa: %s' % c['tira_id'])
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ideas', action='store_true')
    ap.add_argument('--arrancar', action='store_true')
    ap.add_argument('--montar', action='store_true')
    ap.add_argument('--simular', action='store_true')
    ap.add_argument('--tope', type=int, default=4)
    args = ap.parse_args()
    sala.enmascarar_en_actions()
    if args.montar:
        return montar()
    try:
        reglas = (sala.get('reglas') or {}).get('reglas') or {}
        cola = (sala.get('cola') or {}).get('cola') or []
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer REGLAS/COLA: %s' % e)
        return 2
    rc = 0
    if args.ideas:
        rc |= semillero(args.simular, reglas, cola)
    if args.arrancar:
        rc |= arranque(args.simular, reglas, cola, args.tope)
    return rc


if __name__ == '__main__':
    sys.exit(main())
