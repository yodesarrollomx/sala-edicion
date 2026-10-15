#!/usr/bin/env python3
"""Prueba sintética en dos runners. Sin modelos, Sheets, votos ni medios reales."""
import argparse
import hashlib
import json
import os
from unittest.mock import patch
from motores import imagen
from sala_recibos import ejecutar, Recibos, digest, canonical


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('fase', choices=['guardar', 'recuperar'])
    args = ap.parse_args()
    rid = digest(('prueba-persistencia-v1:' + os.environ['GITHUB_RUN_ID'] + ':' + os.environ['GITHUB_RUN_ATTEMPT']).encode())
    store = Recibos(rid)
    source = {'tipo': 'prueba-sintetica', 'run_id': os.environ['GITHUB_RUN_ID']}
    photo = b'SALA-PERSISTENCIA-SINTETICA-v1'
    def prepare():
        if args.fase == 'recuperar':
            raise AssertionError('La recuperación volvió a pedir un plan')
        return {'d': {'texto': 'Prueba de continuidad', 'receta': 'Synthetic geometric photograph'},
                'texto': 'Prueba de continuidad', 'cerebro': 'doble-sin-red', 'avisos': []}
    def generate(*args_):
        if args.fase == 'recuperar':
            raise AssertionError('La recuperación volvió a llamar un motor')
        return photo, 'png', 'hidream_demo', []
    with patch.object(imagen, 'generar', side_effect=generate) as motor:
        plan, recovered, meta = ejecutar(rid, source, prepare, {}, store=store)
    assert recovered == photo
    assert meta['plan_sha256'] == digest(canonical(plan))
    assert store.find()['draft'] is True
    if args.fase == 'recuperar':
        assert motor.call_count == 0
    # Sólo hashes y conteos sintéticos, nunca el contenido de recibos de negocio.
    print(json.dumps({'fase': args.fase, 'request_id': rid, 'bytes': len(recovered),
                      'sha256': hashlib.sha256(recovered).hexdigest(), 'llamadas_motor': motor.call_count,
                      'draft_privado': True, 'release_id': store.release['id']}))

if __name__ == '__main__':
    main()
