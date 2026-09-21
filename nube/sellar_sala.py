#!/usr/bin/env python3
"""El sello de versión de la Sala (invariante 24: nadie publica sin sellar).

Por qué existe: `index.html` se sirve por GitHub Pages, que cachea la raíz. Cuando el
navegador del editor se quedaba con una Sala vieja, «los arreglos no llegaban». El sello
arregla eso: la Sala baja el `index.html` servido, le saca el `SELLO_SALA` por regex
(`index.html`, la línea del `const m=t.match(...)`) y lo compara con el suyo. Si difieren,
ofrece recargar.

Hasta hoy el sello lo ponía `sellar_sala.py` en la Mac y lo exigía un hook `pre-push`. En la
nube **no hay hooks**: un push desde la web o desde un runner nunca los corre. Por eso el
sello pasa a ser un check de CI (`nube/verificar.py`), y este archivo es quien lo calcula.

Cómo se calcula: md5 del propio `index.html` con el VALOR del sello vaciado, primeros 10
caracteres. Vaciarlo es lo que lo hace estable — si se hasheara el archivo con el sello
dentro, cada sellada cambiaría la entrada del hash y nunca convergería.

Que el algoritmo sea éste y no el de la Mac es seguro: el cliente NO recalcula ningún hash,
sólo compara dos cadenas. Lo único que el sello tiene que cumplir es cambiar cuando el
archivo cambia, y no cambiar cuando no.
"""

import hashlib
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALA = RAIZ / 'index.html'
PATRON = re.compile(r"(const SELLO_SALA=')([^']*)(')")
LARGO = 10


def calcular(texto):
    vaciado = PATRON.sub(r"\1\3", texto, count=1)
    return hashlib.md5(vaciado.encode('utf-8')).hexdigest()[:LARGO]


def leer_actual(texto):
    m = PATRON.search(texto)
    return m.group(2) if m else None


def sellar(escribir=True):
    """Devuelve (sello_viejo, sello_nuevo). Con escribir=False sólo informa."""
    texto = SALA.read_text(encoding='utf-8')
    viejo = leer_actual(texto)
    if viejo is None:
        raise SystemExit('✗ no encontré «const SELLO_SALA=» en index.html: '
                         'el sellador y la Sala dejaron de hablar el mismo idioma')
    nuevo = calcular(texto)
    if escribir and viejo != nuevo:
        SALA.write_text(PATRON.sub(lambda m: m.group(1) + nuevo + m.group(3), texto, count=1),
                        encoding='utf-8')
    return viejo, nuevo


if __name__ == '__main__':
    solo_revisar = '--revisar' in sys.argv
    viejo, nuevo = sellar(escribir=not solo_revisar)
    if viejo == nuevo:
        print('✓ el sello está al día: %s' % nuevo)
        sys.exit(0)
    if solo_revisar:
        print('✗ el sello NO está al día: index.html dice «%s» y le toca «%s».' % (viejo, nuevo))
        print('  Corre: python3 nube/sellar_sala.py   y commitea el index.html.')
        print('  Sin esto, la Sala del editor no se entera de que hay una versión nueva')
        print('  y vuelve el «los arreglos no llegaban» (invariante 24).')
        sys.exit(1)
    print('✓ sellada: %s → %s' % (viejo, nuevo))
