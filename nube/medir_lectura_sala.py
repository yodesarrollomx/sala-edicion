#!/usr/bin/env python3
"""Dos lecturas del día con agente. Sólo métricas; no escribe ni expone respuestas."""
import json
import time
import urllib.parse
import sala_cliente as sala


def medir():
    sala.enmascarar_en_actions()
    results = []
    for numero in (1, 2):
        start = time.monotonic()
        result = {"muestra": numero, "timeout_ms": 8000, "rol": "agente"}
        try:
            url = sala._exec_url() + '?' + urllib.parse.urlencode({'recurso': 'dia', 'clave': sala._clave()})
            raw = sala._curl(url, espera=8)
            result.update(sala.metadatos_publicos(getattr(raw, 'metadatos', {})))
            data = sala._leer_json(raw, 'medicion_dia')
            sala._validar_lectura('dia', data)
            result['ok'] = True
            result['cache_hit'] = data.get('cache') if isinstance(data.get('cache'), bool) else None
        except sala.SalaError as error:
            result.update(sala.metadatos_publicos(error.metadatos))
            result.update(ok=False, codigo=error.codigo)
        result['duracion_total_ms'] = round((time.monotonic()-start)*1000)
        results.append(result)
        if numero == 1:
            time.sleep(.4)
    return {'solo_lectura': True, 'arranque_frio_acreditado': False,
            'nota': 'Primera lectura y consecutiva; cache_hit no prueba arranque frio del runtime.', 'muestras': results}


if __name__ == '__main__':
    print(json.dumps(medir(), ensure_ascii=False, sort_keys=True))
