"""Parche puro y acotado: entradas exactas, sin I/O, marcas ni narración nueva.

El operador entrega bytes del snapshot confirmado y reemplazos revisados. El
orquestador conserva respaldo privado y publica usando el mutex existente de Mesa.
Este módulo no monta propuestas, reencola ni certifica medios o aprobaciones.
"""
import copy
import hashlib
import json

from contenido_reglas import exigir, prohibidas


class CorreccionError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise CorreccionError(code)


def allowed(path):
    return (path == ['promesa'] or
            len(path) == 3 and path[0] in ('guion', 'laminas')
            and type(path[1]) is int and path[1] >= 0
            and (path[2] == 've' or path[0] == 'guion' and path[2] == 'dice'))


def apply(raw, expected_sha256, replacements, *, family_has_voice_script=False):
    """Devuelve bytes corregidos; nunca deduce ni sustituye textos por regex global."""
    require(isinstance(raw, bytes) and hashlib.sha256(raw).hexdigest() == expected_sha256,
            'fuente_cambio')
    before = json.loads(raw)
    after = copy.deepcopy(before)
    require(isinstance(replacements, list) and replacements, 'parche_vacio')
    seen = set()
    for replacement in replacements:
        path = replacement.get('path')
        require(isinstance(path, list) and allowed(path), 'campo_fuera_de_alcance')
        require(tuple(path) not in seen, 'ruta_duplicada')
        seen.add(tuple(path))
        # Sólo las cuatro familias sin guion de voz externo están acreditadas.
        require(not family_has_voice_script, 'requiere_revision_guion_de_voz')
        old, new = replacement.get('before'), replacement.get('after')
        require(isinstance(old, str) and isinstance(new, str) and old != new
                and new.strip() and prohibidas(old) and not prohibidas(new), 'reescritura_no_acotada')
        target = after
        try:
            for key in path[:-1]:
                target = target[key]
            require(target[path[-1]] == old, 'texto_fuente_cambio')
            target[path[-1]] = new
        except (KeyError, IndexError, TypeError):
            raise CorreccionError('ruta_fuente_ausente') from None
    # Inspecciona candidatas también: no permite que una ve vetada escondida
    # vuelva a entrar al resolver la toma. No las modifica automáticamente.
    exigir(after)
    # La allowlist sólo admite ve en láminas: todo su texto, imagen, candidata,
    # selección, huella, estado y notas permanece exactamente como antes.
    for index, lam in enumerate(before.get('laminas') or []):
        old = {k: v for k, v in lam.items() if k != 've'}
        new = {k: v for k, v in after['laminas'][index].items() if k != 've'}
        require(old == new, 'cambio_operativo_no_autorizado')
    return (json.dumps(after, ensure_ascii=False, indent=1) + '\n').encode()
