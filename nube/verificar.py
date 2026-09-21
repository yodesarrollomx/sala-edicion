#!/usr/bin/env python3
"""Las pruebas que corren SIN red, en cada push y en cada pull request.

Por qué existe: hasta hoy las reglas del repo vivían en prosa (`CLAUDE.md`,
`docs/SALA-SISTEMA.md`) y en un hook `pre-push` de la Mac. Un push desde la web, desde el
teléfono o desde un runner no corre hooks: las reglas se caían solas en cuanto el ciclo
dejaba la Mac. Aquí quedan como código que bloquea.

Es deliberadamente DE RED CERO: corre en pull requests, donde no hay secrets y donde hacer
POST al /exec «para probar» está prohibido (regla de yod-portal, y de la Sala).

Cada prueba dice qué regla cuida y qué se rompe si falla. Añadir una prueba es añadir una
función `prueba_*`: se descubren solas, igual que las reglas de `sala_guardia.py`.
"""

import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FALLAS = []
NOTAS = []


def falla(regla, que, remedio):
    FALLAS.append((regla, que, remedio))


def nota(t):
    NOTAS.append(t)


# --------------------------------------------------------------- las pruebas

def prueba_sello():
    """INVIOLABLE 24 — nadie publica sin sellar la versión.
    Si falla: GitHub Pages sirve la raíz cacheada, el editor se queda con una Sala vieja
    y vuelve el «los arreglos no llegaban»."""
    sys.path.insert(0, str(RAIZ / 'nube'))
    import sellar_sala
    viejo, nuevo = sellar_sala.sellar(escribir=False)
    if viejo != nuevo:
        falla('INVIOLABLE 24 · sellar la versión',
              'index.html dice «%s» y le toca «%s»' % (viejo, nuevo),
              'corre  python3 nube/sellar_sala.py  y commitea index.html')


def prueba_sin_claves():
    """INVIOLABLE 2 — el repo es PÚBLICO, nunca una clave adentro.
    Si falla: la clave queda en el historial de git para siempre, y rotarla no la borra."""
    # La liga /exec NO se persigue: no es secreta (sin clave no entrega nada, comprobado con
    # curl el 4-sep) y está documentada a propósito en CLAUDE.md y en index.html. Lo que no
    # puede aparecer nunca es una CLAVE.
    sospechosos = [
        (re.compile(r"clave\s*[:=]\s*['\"][A-Za-z0-9]{8,}['\"]"), 'una clave literal'),
        (re.compile(r"clave_agente\s*[:=]\s*['\"][^'\"…]{6,}['\"]"), 'la clave del agente'),
    ]
    for rel in ('gas/Code.gs', 'nube/sala_cliente.py', 'nube/verificar.py'):
        p = RAIZ / rel
        if not p.exists():
            continue
        texto = p.read_text(encoding='utf-8', errors='replace')
        for patron, que in sospechosos:
            for m in patron.finditer(texto):
                if '…' in m.group(0) or 'os.environ' in m.group(0):
                    continue
                falla('INVIOLABLE 2 · cero claves en el repo',
                      '%s parece traer %s: %s' % (rel, que, m.group(0)[:60]),
                      'sácala a un secret de Actions y deja el hueco «…»')


def prueba_workflows_no_filtran():
    """INVIOLABLE 2 — un workflow de pull_request NUNCA recibe secrets.
    Si falla: cualquiera que abra un PR puede imprimir la clave del agente en un log público."""
    d = RAIZ / '.github' / 'workflows'
    if not d.is_dir():
        return
    for y in sorted(d.glob('*.yml')):
        texto = y.read_text(encoding='utf-8', errors='replace')
        usa_secrets = 'secrets.SALA_' in texto
        en_pr = re.search(r'^\s*pull_request\s*:', texto, re.M) is not None
        if usa_secrets and en_pr:
            falla('INVIOLABLE 2 · secrets fuera de los pull requests',
                  '%s usa secrets Y se dispara en pull_request' % y.name,
                  'quita el disparador pull_request, o el uso de secrets')
        if re.search(r'echo .*secrets\.', texto):
            falla('INVIOLABLE 2 · cero claves en el log',
                  '%s imprime un secret con echo' % y.name,
                  'nunca imprimas un secret; usa ::add-mask:: y redactar()')


def prueba_workflows_no_deciden():
    """INVIOLABLE 3 — decidir es de los editores; el agente no marca.
    Si falla: un bot marcaría cartas en nombre de Alejandro o de Sayri.

    En los .py se mira el CÓDIGO, no la prosa: un `ast` en vez de un grep, porque el propio
    cliente tiene que poder EXPLICAR la prohibición en su docstring sin activarla."""
    import ast
    prohibidas = {'decidir', 'parrilla_decision'}

    def literal(nodo):
        return nodo.value if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) else None

    for p in sorted((RAIZ / 'nube').glob('*.py')):
        try:
            arbol = ast.parse(p.read_text(encoding='utf-8'))
        except SyntaxError as e:
            falla('el código compila', '%s no parsea: %s' % (p.name, e), 'arregla la sintaxis')
            continue
        for nodo in ast.walk(arbol):
            malo = None
            if isinstance(nodo, ast.Call):       # post('decidir', ...)
                f = nodo.func
                nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', '')
                if nombre == 'post' and nodo.args and literal(nodo.args[0]) in prohibidas:
                    malo = literal(nodo.args[0])
                for kw in nodo.keywords:         # post(accion='decidir')
                    if kw.arg == 'accion' and literal(kw.value) in prohibidas:
                        malo = literal(kw.value)
            if isinstance(nodo, ast.Dict):       # {'accion': 'decidir'}
                for k, v in zip(nodo.keys, nodo.values):
                    if literal(k) == 'accion' and literal(v) in prohibidas:
                        malo = literal(v)
            if malo:
                falla('INVIOLABLE 3 · el agente no decide',
                      '%s manda accion:%s' % (p.name, malo),
                      'la nube entra como agente: propone, retira y reporta. Nada más')

    d = RAIZ / '.github' / 'workflows'
    for y in (sorted(d.glob('*.yml')) if d.is_dir() else []):
        texto = y.read_text(encoding='utf-8', errors='replace')
        for accion in prohibidas:
            if re.search(r"""accion['"]?\s*[:=]\s*['"]%s['"]""" % accion, texto):
                falla('INVIOLABLE 3 · el agente no decide',
                      '%s manda accion:%s' % (y.name, accion),
                      'la nube entra como agente: propone, retira y reporta. Nada más')

    # Y el candado de verdad: el cliente tiene que traer la lista de prohibidas.
    cli = (RAIZ / 'nube' / 'sala_cliente.py')
    if cli.exists() and 'PROHIBIDAS' not in cli.read_text(encoding='utf-8'):
        falla('INVIOLABLE 3 · el agente no decide',
              'sala_cliente.py se quedó sin su lista PROHIBIDAS',
              'el cliente debe negarse a decidir ANTES de la red, no depender del GAS')


def prueba_workflows_no_despliegan_gas():
    """INVIOLABLE 1 — el repo es ESPEJO del Apps Script.
    Si falla: un CI «desplegaría» gas/Code.gs y rompería el /exec vivo. Subir código al GAS
    es a mano: clasp push → Manage deployments → lápiz → New version → Deploy."""
    d = RAIZ / '.github' / 'workflows'
    if not d.is_dir():
        return
    for y in sorted(d.glob('*.yml')):
        texto = y.read_text(encoding='utf-8', errors='replace')
        if re.search(r'\bclasp\b|create-deployment|update-deployment', texto):
            falla('INVIOLABLE 1 · el repo es espejo, no fuente',
                  '%s intenta desplegar el Apps Script' % y.name,
                  'quítalo: desplegar el GAS es a mano, y create-deployment rompe la entrada web')


def prueba_json_parsean():
    """Si falla: la Sala cae al respaldo espejo y encuentra basura; la mesa amanece vacía
    sin que nadie lo note (INVIOLABLE 4, el otro lado de la misma moneda)."""
    for p in sorted((RAIZ / 'datos').rglob('*.json')):
        try:
            json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, UnicodeDecodeError) as e:
            falla('datos íntegros',
                  '%s no parsea: %s' % (p.relative_to(RAIZ), str(e)[:90]),
                  'arréglalo o revierte el commit que lo tocó')


def prueba_manifiesto_completo():
    """INVIOLABLE 4 — «no contestó» nunca es «no hay nada».
    Si falla: el respaldo espejo se quedó sin las llaves que la Sala espera y el plan B no
    sirve de plan B."""
    p = RAIZ / 'datos' / 'manifiesto.json'
    if not p.exists():
        falla('INVIOLABLE 4 · el respaldo espejo existe',
              'falta datos/manifiesto.json', 'restáuralo de git')
        return
    try:
        m = json.loads(p.read_text(encoding='utf-8'))
    except ValueError:
        return                                   # ya lo reportó prueba_json_parsean
    for llave in ('fecha', 'propuestas', 'decisiones', 'peticiones'):
        if llave not in m:
            falla('INVIOLABLE 4 · el respaldo espejo está completo',
                  'a datos/manifiesto.json le falta «%s»' % llave,
                  'el relevo lo reescribe: nube/sala_relevo.py')


def prueba_peticiones_bien_formadas():
    """INVIOLABLE 10 — nada avanza sobre una pieza con petición abierta.
    El productor lee este registro antes de abrir compuertas: si está mal formado, el PASO 0
    no puede hacer su trabajo."""
    p = RAIZ / 'datos' / 'manifiesto.json'
    if not p.exists():
        return
    try:
        pet = json.loads(p.read_text(encoding='utf-8')).get('peticiones') or []
    except ValueError:
        return
    if not isinstance(pet, list):
        falla('INVIOLABLE 10 · el registro de peticiones',
              'manifiesto.peticiones no es una lista', 'el relevo lo reescribe')
        return
    abiertas = [x for x in pet if isinstance(x, dict) and x.get('estado') != 'cumplida']
    for x in pet:
        if not isinstance(x, dict) or 'pedido' not in x or 'estado' not in x:
            falla('INVIOLABLE 10 · el registro de peticiones',
                  'una petición sin «pedido» o sin «estado»',
                  'toda petición se rastrea y no se cierra sin evidencia verificable')
    nota('peticiones: %d registradas, %d abiertas' % (len(pet), len(abiertas)))


def prueba_tiras_sanas():
    """INVIOLABLE 6 — nunca montar una rehecha sin su tira.
    Aquí sólo se comprueba lo que se puede comprobar en reposo: que cada tira diga su pieza y
    traiga láminas. El «tira completa al montar» vive en sala_guardia.py, en el momento del
    montaje, que es cuando se puede saber."""
    d = RAIZ / 'datos' / 'tiras'
    if not d.is_dir():
        return
    n = 0
    for p in sorted(d.glob('*.json')):
        if p.name == 'index.json':
            continue
        try:
            t = json.loads(p.read_text(encoding='utf-8'))
        except ValueError:
            continue
        n += 1
        if not isinstance(t, dict):
            continue
        if not t.get('pieza') and not t.get('pieza_slug'):
            falla('INVIOLABLE 8 · nunca un id interno en pantalla',
                  '%s no dice de qué pieza es' % p.name,
                  'sin «pieza» la Sala no puede nombrarla y enseña el id crudo')
        lam = t.get('laminas')
        if lam is not None and not isinstance(lam, list):
            falla('INVIOLABLE 6 · la carta nunca llega sola',
                  '%s tiene «laminas» que no es lista' % p.name, 'revisa el publicador')
    nota('tiras revisadas: %d' % n)


# --------------------------------------------------------------- el corredor

def main():
    pruebas = sorted((n, f) for n, f in globals().items() if n.startswith('prueba_'))
    for nombre, fn in pruebas:
        try:
            fn()
        except Exception as e:                    # una prueba rota no puede pasar por «todo bien»
            falla('el verificador mismo',
                  '%s reventó: %s: %s' % (nombre, type(e).__name__, e),
                  'arregla la prueba antes de confiar en el resultado')

    print('Sala · verificación local (sin red) — %d pruebas' % len(pruebas))
    for t in NOTAS:
        print('  · %s' % t)
    if not FALLAS:
        print('\n✓ todo en orden. Se puede publicar.')
        return 0
    print('\n✗ %d cosa(s) que impiden publicar:\n' % len(FALLAS))
    for regla, que, remedio in FALLAS:
        print('  [%s]' % regla)
        print('    qué pasa : %s' % que)
        print('    remedio  : %s\n' % remedio)
    return 1


if __name__ == '__main__':
    sys.exit(main())
