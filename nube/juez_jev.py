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
existían. Endpoint y forma según la documentación pública (POST
https://api.typesafe.ai/v1/systemone, Bearer; preguntas Noul/Choice/Score). Si el SDK oficial
`typesafe_sdk` está instalado se usa ése; si no, HTTP directo. Sin `TYPESAFE_API_KEY` sale con
código 0 y lo dice — no es un fallo, es que todavía no se da de alta.
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

PREGUNTAS = {
    'sujeto_primero': ('noul', 'Does the visual description start with the concrete subject '
                       'that the slide text names (not with the neighbourhood or context)?'),
    'coherencia': ('noul', 'Does the visual description actually illustrate what the slide '
                   'text says?'),
    'claridad': ('score', 'Rate 0-10 how clearly the slide text reads in one pass, in plain '
                 'Spanish, for a family in Hermosillo who owns an empty lot.'),
}


def _estado(lam):
    return ('TEXTO DE LA LÁMINA (dice): %s\nDESCRIPCIÓN VISUAL (ve): %s\nQUÉ DEBE ENTENDER '
            '(entiende): %s' % (lam.get('dice', ''), lam.get('ve', ''), lam.get('entiende', '')))


def _con_sdk(estado):
    from typesafe_sdk import Noul, Score, TypeSafeClient
    q = {k: (Noul(instructions=t) if tipo == 'noul' else Score(instructions=t))
         for k, (tipo, t) in PREGUNTAS.items()}
    r = TypeSafeClient().system_one(state=estado, questions=q)
    out = {}
    for k, (tipo, _) in PREGUNTAS.items():
        a = r.answers[k]
        out[k] = getattr(a, 'noul', None) if tipo == 'noul' else getattr(a, 'score', None)
    return out


def _con_http(estado, llave):
    cuerpo = {'state': estado,
              'questions': {k: {'type': tipo, 'instructions': t}
                            for k, (tipo, t) in PREGUNTAS.items()}}
    pet = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + llave,
                                          'Content-Type': 'application/json'})
    with urllib.request.urlopen(pet, timeout=60) as r:
        datos = json.loads(r.read().decode())
    res = datos.get('answers', datos)
    return {k: (v.get('noul', v.get('score', v)) if isinstance(v, dict) else v)
            for k, v in res.items()}


def juzgar(estado, llave):
    try:
        return _con_sdk(estado)
    except ImportError:
        return _con_http(estado, llave)


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
