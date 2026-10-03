#!/usr/bin/env python3
"""Juez Jev (TypeSafe System One): una segunda opinión automática sobre las láminas PROPUESTAS,
antes de que lleguen a la mesa de Alejandro y Sayri. **Sólo opina, nunca decide**
(INVIOLABLE 3): no escribe en el Sheet ni marca cartas; deja un reporte (resumen del job +
`juez-jev.json` como artifact) para que el editor lo vea o lo ignore.

Qué pregunta, por lámina (sólo texto — Jev no ve imágenes):
  · sujeto_primero (sí/no): ¿la descripción visual (`ve`) arranca con el sujeto concreto que
    nombra el texto (`dice`)? — la regla del 15-sep (hoja PROMPTS, apodo L2).
  · claridad (0–10): ¿el texto se entiende en una lectura, en llano, para una familia de
    Hermosillo con un terreno?
  · coherencia (sí/no): ¿lo que se ve ilustra lo que se dice?

**Instalado el 3-oct-2026 sin probar contra la API real**: la cuenta y la llave aún no
existían. La forma de la petición sigue la referencia oficial (docs.typesafe.ai/api.md, leída
ese día), en HTTP directo. Sin `TYPESAFE_API_KEY` sale con código 0 y lo dice — no es un
fallo, es que todavía no se da de alta. Claridad es un Score de 3 niveles (0–2): 2 = claro.
"""

import glob
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TIRAS = RAIZ / 'datos' / 'tiras'
URL = 'https://api.typesafe.ai/v1/systemone'
MAX_LAMINAS = int(os.environ.get('JUEZ_MAX', '40'))     # cuida el crédito gratis

MODELO = os.environ.get('JEV_MODELO', 'jev-latest')

# Forma según https://docs.typesafe.ai/api.md (leída el 3-oct-2026): state estructurado,
# `model` obligatorio, Noul con criteria true/false, Score con niveles ordenados (2–10).
PREGUNTAS = {
    'sujeto_primero': {
        'type': 'noul',
        'instructions': 'Does `lamina.ve` (the visual description) open with the concrete '
                        'subject that `lamina.dice` (the slide text) names, rather than with '
                        'the neighbourhood or general context?',
        'criteria': {'true': 'The first thing described is the subject the text talks about',
                     'false': 'It opens with setting/context and the subject comes later or '
                              'is missing'}},
    'coherencia': {
        'type': 'noul',
        'instructions': 'Would an image matching `lamina.ve` clearly illustrate what '
                        '`lamina.dice` says?',
        'criteria': {'true': 'The image shows what the text says',
                     'false': 'The image is about something else or contradicts the text'}},
    'claridad': {
        'type': 'score',
        'instructions': 'How clearly does `lamina.dice` read in one pass, in plain Spanish, '
                        'for a family in Hermosillo who owns an empty lot?',
        'criteria': ['Confusing: needs rereading or uses jargon',
                     'Understandable with some effort',
                     'Clear on first read, plain words']},
}


def _estado(lam):
    return {'lamina': {k: lam.get(k, '') for k in ('dice', 've', 'entiende')},
            'contexto': 'Slide of a real-estate development carousel/reel in Hermosillo, '
                        'Sonora; audience: families who own an empty urban lot.'}


def juzgar(estado, llave):
    cuerpo = {'state': estado, 'model': MODELO, 'questions': PREGUNTAS}
    pet = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + llave,
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(pet, timeout=60) as r:
        resp = json.loads(r.read().decode())
    out = {}
    for k, a in resp['answers'].items():
        valor = a.get('noul', a.get('score'))
        out[k] = round(valor, 2) if isinstance(valor, (int, float)) else valor
        if 'confidence' in a:
            out[k + '_confianza'] = round(a['confidence'], 2)
    return out


def propuestas():
    for f in sorted(glob.glob(str(TIRAS / '*.json'))):
        try:
            tira = json.loads(pathlib.Path(f).read_text(encoding='utf-8'))
        except ValueError:
            continue
        if not isinstance(tira, dict):
            continue
        for lam in tira.get('laminas') or []:
            if isinstance(lam, dict) and lam.get('estado') == 'propuesta' and lam.get('dice'):
                yield pathlib.Path(f).stem, lam


def main():
    llave = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if not llave:
        print('Jev instalado pero sin llave: falta el secret TYPESAFE_API_KEY. No se juzga nada.')
        return 0
    reporte, errores = [], 0
    for i, (tira, lam) in enumerate(propuestas()):
        if i >= MAX_LAMINAS:
            break
        try:
            r = juzgar(_estado(lam), llave)
        except (urllib.error.URLError, ValueError, KeyError, AttributeError) as e:
            errores += 1
            print('!! %s L%s: %s' % (tira, lam.get('n'), str(e)[:200]))
            if errores >= 3:
                print('!! 3 errores seguidos: paro para no gastar crédito')
                break
            continue
        reporte.append({'tira': tira, 'lamina': lam.get('n'), 'dice': lam.get('dice'), **r})
        print('· %s L%s → %s' % (tira, lam.get('n'), r))
    pathlib.Path('juez-jev.json').write_text(json.dumps(reporte, ensure_ascii=False, indent=1))
    resumen = os.environ.get('GITHUB_STEP_SUMMARY')
    if resumen:
        with open(resumen, 'a', encoding='utf-8') as s:
            s.write('## Juez Jev · %d lámina(s) propuestas\n\n| tira | L | sujeto primero | '
                    'coherencia | claridad |\n|---|---|---|---|---|\n' % len(reporte))
            for x in reporte:
                s.write('| %s | %s | %s | %s | %s |\n' % (x['tira'], x['lamina'],
                        x.get('sujeto_primero'), x.get('coherencia'), x.get('claridad')))
    return 1 if errores and not reporte else 0


if __name__ == '__main__':
    sys.exit(main())
