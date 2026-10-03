"""Activa el veto editorial existente y verifica su lectura, sin producir contenido."""
from contenido_reglas import REGLA, UBICACIONES, normalizar


def activar(cliente, solicitadas=''):
    def leer():
        respuesta = cliente.get('reglas')
        if respuesta.get('ok') is not True or not isinstance(respuesta.get('reglas'), dict):
            raise RuntimeError('No se pudo comprobar REGLAS; no se cambia configuración.')
        valor = respuesta['reglas'].get(REGLA, '')
        if not isinstance(valor, str):
            raise RuntimeError('La regla existente no es texto; requiere revisión.')
        return valor

    previo = leer()
    existentes = {normalizar(p.strip()) for p in previo.split(',') if p.strip()}
    faltantes = []
    for p in (*UBICACIONES, *solicitadas.split(',')):
        p = p.strip()
        if p and normalizar(p) not in existentes:
            faltantes.append(p)
            existentes.add(normalizar(p))
    esperado = previo
    if faltantes:
        esperado = previo + (',' if previo and not previo.endswith(',') else '') + ','.join(faltantes)
        if leer() != previo:
            raise RuntimeError('La regla cambió durante la lectura; no se sobrescribe.')
        resultado = cliente.post('regla', set={REGLA: esperado})
        if resultado.get('ok') is not True or resultado.get('editadas') != 1:
            raise RuntimeError('Escritura sin confirmación; conciliar antes de reintentar.')
    if leer() != esperado:
        raise RuntimeError('Lectura posterior distinta; no se confirma activación.')
    return {'regla': REGLA, 'verificada': True, 'modificada': bool(faltantes),
            'vetos_obligatorios': len(UBICACIONES), 'produccion_ejecutada': False}


if __name__ == '__main__':
    import json
    import sala_cliente
    sala_cliente.enmascarar_en_actions()
    try:
        print(json.dumps(activar(sala_cliente), ensure_ascii=False))
    except Exception:
        # Respuestas, claves y valores previos no se publican en este repositorio.
        raise SystemExit('No se confirmó la activación de la regla; revisar estado antes de reintentar.')
