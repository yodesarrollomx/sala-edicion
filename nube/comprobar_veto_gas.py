"""Comprueba el rechazo del backend, sin enviar una lista que pueda crear propuestas."""
import json
import sala_cliente as sala


def comprobar():
    # Objeto, NO lista: la guardia lo inspecciona, pero el handler histórico
    # no puede recorrerlo con forEach ni insertar una propuesta si faltara el veto.
    payload = {'accion': 'proponer', 'clave': sala._clave(),
               'propuestas': {'titulo': 'HERMOSILLO SONORA Me\u0301xico'}}
    raw = sala._urllib(sala._exec_url(), json.dumps(payload))
    r = json.loads(raw)
    if r.get('codigo') != 'contenido_vetado' or not r.get('error'):
        raise RuntimeError('No se acreditó rechazo de contenido.')
    detalle = r.get('detalle', '')
    if not all(p in detalle for p in ('Hermosillo', 'Sonora', 'México')):
        raise RuntimeError('No se acreditaron los tres vetos.')
    return {'backend_rechazo_verificado': True, 'vetos': 3,
            'lista_de_propuestas_enviada': False}


if __name__ == '__main__':
    sala.enmascarar_en_actions()
    try:
        print(json.dumps(comprobar(), ensure_ascii=False))
    except Exception:
        raise SystemExit('Comprobación del backend no confirmada; no se declara cierre.')
