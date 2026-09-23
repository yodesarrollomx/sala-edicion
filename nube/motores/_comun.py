"""Lo que comparten los motores: el error tipado y cómo encontrar la lámina de un trabajo."""

import json
import pathlib
import shutil

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
TIRAS = RAIZ / 'datos' / 'tiras'


class MotorError(RuntimeError):
    """El motor no pudo producir. Quien llama decide si eso dice `pendiente` (inténtalo
    después, o que lo haga la Mac) o `fallo` (algo está mal de verdad) — el motor nunca
    decide por sí mismo cuál de los dos es: sólo reporta qué pasó."""

    def __init__(self, mensaje, intermitente=False):
        super().__init__(mensaje)
        # intermitente=True: «no me tocó esta vez» (cuota, servicio ocupado) — sala_ejecutor
        # lo deja 'pendiente' para la Mac o para el siguiente intento, NUNCA 'fallo'.
        self.intermitente = intermitente


def lamina_de(trabajo):
    """{src, dice, ve, nota} de la lámina de un trabajo. Primero la evidencia; si le falta
    `src` (los trabajos encolados antes del 23-sep no la traían), la tira `datos/tiras/<de>.json`.
    El número sale de `evidencia.lamina` (la tira manda, invariante 29), no del nombre."""
    ev = trabajo.get('evidencia') or {}
    datos = {k: str(ev.get(k) or '') for k in ('src', 'dice', 've', 'nota')}
    if datos['src']:
        return datos
    n = str(ev.get('lamina') or trabajo.get('item') or '').split('-')[0]
    ruta = TIRAS / ('%s.json' % str(ev.get('de') or ''))
    if not n or not ruta.is_file():
        return datos
    try:
        tira = json.loads(ruta.read_text(encoding='utf-8'))
    except ValueError:
        return datos
    for i, lam in enumerate(tira.get('laminas') or []):
        if isinstance(lam, dict) and str(lam.get('n') or i + 1) == n:
            for k in datos:
                datos[k] = datos[k] or str(lam.get(k) or '')
            break
    return datos


def traer_imagen(trabajo, cat, destino):
    """Deja la imagen de la lámina en `destino`: del repo si el archivo está en el checkout,
    si no de Drive vía catálogo. Sin ninguna de las dos, intermitente (falta catalogar)."""
    import sala_catalogo as catalogo
    import sala_drive as drive
    lam = lamina_de(trabajo)
    src = lam['src']
    if not src:
        raise MotorError('el trabajo %s no dice qué lámina es (ni evidencia.src ni tira)'
                         % trabajo.get('id'), intermitente=True)
    local = RAIZ / src.lstrip('/')
    if local.is_file():
        shutil.copyfile(local, destino)
        return lam
    d = catalogo.drive_de(src, cat)
    if not d or not d.get('original'):
        raise MotorError('la lámina %s no está en el repo ni en el catálogo de Drive '
                         '(accion:catalogar)' % src, intermitente=True)
    drive.bajar(d['original'], destino)
    return lam
