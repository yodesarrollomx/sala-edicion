"""Compuerta común del contenido nuevo: no altera notas ni versiones históricas.

Chinche #49: las tres ubicaciones son un veto obligatorio del editor. REGLAS
puede añadir términos; una configuración vacía nunca elimina esos tres.
"""
import re
import unicodedata

UBICACIONES = ('Hermosillo', 'Sonora', 'México')
REGLA = 'contenido_ubicaciones_vetadas'
CAMPOS = frozenset(('titulo', 'bajada', 'promesa', 'dice', 've', 'entiende',
                    'texto', 'receta', 'porque', 'prompt_base', 'acento', 'firma'))
HISTORIA = frozenset(('versiones', 'historial', 'nota', 'nota_previa', 'origen'))


class ContenidoVetado(ValueError):
    """Contenido que debe rehacerse antes de producir o montar."""


def normalizar(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto or '').casefold())
                   if not unicodedata.combining(c))


def ubicaciones(reglas=None):
    extra = str((reglas or {}).get(REGLA) or '').split(',')
    out, vistas = [], set()
    for palabra in (*UBICACIONES, *extra):
        palabra = palabra.strip()
        clave = normalizar(palabra)
        if clave and clave not in vistas:
            out.append(palabra)
            vistas.add(clave)
    return out


def prohibidas(texto, reglas=None):
    limpio = normalizar(texto)
    return [p for p in ubicaciones(reglas)
            if re.search(r'(?<!\w)' + re.escape(normalizar(p)) + r'(?!\w)', limpio)]


def instruccion(reglas=None):
    return ('· Regla editorial obligatoria: nunca usar estas palabras en el contenido nuevo, '
            'ni con otra capitalización o sin acento: %s. Aplica a títulos, bajadas, promesas, '
            'guiones, texto de lámina, descripciones, recetas y explicaciones. Si aparecen en '
            'el material de referencia, reescribe la salida sin copiarlas.\n'
            % ', '.join(ubicaciones(reglas)))


def revisar(dato, reglas=None, ruta='contenido'):
    """Devuelve rutas y términos inválidos, sin divulgar textos del editor.

    Sólo inspecciona campos de contenido. IDs, rutas, URLs, fechas, estados,
    notas editoriales y versiones previas conservan su significado operativo.
    """
    fallas = []
    if isinstance(dato, str):
        malas = prohibidas(dato, reglas)
        return ['%s: %s' % (ruta, ', '.join(malas))] if malas else []
    if isinstance(dato, dict):
        for campo, valor in dato.items():
            if campo in HISTORIA:
                continue
            subruta = '%s.%s' % (ruta, campo)
            if campo in CAMPOS and isinstance(valor, str):
                fallas += revisar(valor, reglas, subruta)
            elif isinstance(valor, (dict, list)):
                fallas += revisar(valor, reglas, subruta)
    elif isinstance(dato, list):
        for i, valor in enumerate(dato):
            # Una lista de src/IDs no es texto publicitario.
            if isinstance(valor, (dict, list)):
                fallas += revisar(valor, reglas, '%s[%d]' % (ruta, i))
    return fallas


def exigir(dato, reglas=None, ruta='contenido'):
    fallas = revisar(dato, reglas, ruta)
    if fallas:
        raise ContenidoVetado('requiere reescritura; ubicación vetada en ' + '; '.join(fallas))
