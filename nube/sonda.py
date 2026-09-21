#!/usr/bin/env python3
"""Reconocimiento en seco: confirma que la nube habla con el /exec, sin escribir nada.

Por qué existe: el resto del ciclo en la nube se construyó leyendo `gas/Code.gs`, que es un
ESPEJO del Apps Script — puede ir atrás del editor (lo dice CLAUDE.md, «Por confirmar»).
Antes de que un cron escriba en el Sheet de producción, esta sonda comprueba contra el /exec
VIVO que las llaves que esperamos están donde las esperamos.

Sólo hace GET. Nunca un POST: hacer POST a un /exec «para probar» está prohibido, porque hay
backends que escriben.

Lo que imprime es la FORMA, no el contenido: llaves y tipos. Así el artifact se puede leer
sin sacar a un repo público lo que se está decidiendo hoy.
"""

import json
import sys

import sala_cliente as sala

# Lo que armarDia_ promete devolver (gas/Code.gs). Si algo de esto falta, el /exec vivo va
# por delante o por detrás del espejo y hay que mirar antes de seguir.
DIA_ESPERADO = ['fecha', 'dias', 'propuestas', 'decisiones', 'retro', 'parrilla',
                'produccion', 'bitacora', 'ultima_revision', 'relevo_virtual']


def forma(v, hondo=0):
    """Describe un valor por su tipo y sus llaves. Nunca por su contenido."""
    if isinstance(v, dict):
        if hondo >= 2:
            return '{%d llaves}' % len(v)
        return {k: forma(x, hondo + 1) for k, x in list(v.items())[:25]}
    if isinstance(v, list):
        if not v:
            return '[] (vacía)'
        return ['%d elemento(s), el primero:' % len(v), forma(v[0], hondo + 1)]
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, (int, float)):
        return 'número'
    if v is None:
        return 'null'
    return 'texto (%d car.)' % len(str(v))


def main():
    sala.enmascarar_en_actions()
    informe, problemas = {}, []

    for recurso in ('dia', 'reglas', 'cola', 'catalogo'):
        try:
            datos = sala.get(recurso)
        except sala.SalaError as e:
            # Que un recurso no exista es información, no necesariamente una falla: el
            # espejo puede ir atrás. Se anota y se sigue.
            informe[recurso] = {'no contestó': sala.redactar(str(e))}
            problemas.append('%s: %s' % (recurso, sala.redactar(str(e))))
            continue
        informe[recurso] = forma(datos)
        if recurso == 'dia':
            faltan = [k for k in DIA_ESPERADO if k not in datos]
            if faltan:
                problemas.append('al día le faltan llaves que gas/Code.gs promete: %s' % faltan)
            sala.avisar('  día %s · %d propuesta(s) · rol %s · relevo_virtual=%s · cache=%s' % (
                datos.get('fecha'), len(datos.get('propuestas') or []),
                datos.get('rol'), datos.get('relevo_virtual'), datos.get('cache')))

    salida = json.dumps(informe, ensure_ascii=False, indent=2)
    salida = sala.redactar(salida)               # cinturón y tirantes
    with open('sonda-forma.json', 'w', encoding='utf-8') as f:
        f.write(salida)
    print(salida)

    print('\n--- lectura ---')
    if problemas:
        for p in problemas:
            print('  ⚠ %s' % p)
        print('\nLa sonda leyó, pero algo no cuadra con el espejo. Míralo antes de encender '
              'los crons que escriben.')
        return 1
    print('  ✓ el /exec vivo entrega lo que gas/Code.gs promete. Se puede seguir.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
