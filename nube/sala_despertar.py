"""El despertador del Ejecutor (23-sep).

Por qué existe: el Ejecutor corre por cron cada 2 h, pero GitHub se salta corridas (el 23-sep
sólo llegaron 2 de ~12) y las que llegan, llegan 5-30+ min tarde. Un trabajo en cola podía
esperar medio día mientras la Sala prometía «≈ 9:20». Esto lo llaman el Productor y el puente
de chinches (cada hora): si hay trabajo pendiente de una etapa que la nube ejecuta y no es
horario quieto, escribe `despertar=si` en $GITHUB_OUTPUT y el workflow enciende al Ejecutor.

Sólo lee (REGLAS y COLA). Nunca escribe en el Sheet.
"""
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_cliente as sala
from sala_productor import en_silencio, entero, regla

ETAPAS_SOPORTADAS = {'escena', 'voz', 'corte', 'prospecto'}


def main():
    sala.enmascarar_en_actions()
    try:
        r = sala.get('reglas')
        reglas = r.get('reglas') or {}
        cola = (sala.get('cola') or {}).get('cola') or []
    except sala.SalaError as e:
        sala.avisar('despertador: no pude leer REGLAS/COLA (%s); no se enciende nada' % e)
        return 0
    hab = {x.strip() for x in str(reglas.get('nube_ejecuta_etapas') or '').split(',') if x.strip()}
    hab &= ETAPAS_SOPORTADAS
    desde = entero(regla(reglas, 'productor_silencio_desde')[0], 23)
    hasta = entero(regla(reglas, 'productor_silencio_hasta')[0], 7)
    hora = sala.hora_hermosillo()
    pend = [t for t in cola if str(t.get('estado')) == 'pendiente' and str(t.get('etapa')) in hab]
    si = bool(pend) and not en_silencio(desde, hasta, hora)
    sala.avisar('despertador: %d trabajo(s) pendiente(s) de %s · %d h Hermosillo%s → %s'
                % (len(pend), ','.join(sorted(hab)) or '—', hora,
                   ' (horario quieto)' if en_silencio(desde, hasta, hora) else '',
                   'enciendo al Ejecutor' if si else 'nada que encender'))
    salida = os.environ.get('GITHUB_OUTPUT')
    if salida:
        with open(salida, 'a') as f:
            f.write('despertar=%s\n' % ('si' if si else 'no'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
