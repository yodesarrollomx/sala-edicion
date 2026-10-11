#!/usr/bin/env python3
"""Conserva versiones sobrescritas por su hash; no modifica COLA ni decisiones."""
import hashlib
import json
import os
import pathlib
import re
import sys
import tempfile
from datetime import datetime, timezone
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_cliente as sala
import sala_drive as drive
from conciliar_medios import evidence_of, file_id, md5_expected
from sala_ejecutor import subir_producto

def main():
    sala.enmascarar_en_actions()
    config = sala.get('reglas').get('reglas')
    jobs = sala.get('cola').get('cola')
    if not isinstance(config, dict) or not isinstance(jobs, list):
        raise RuntimeError('canonical_contract_missing')
    root = file_id(config.get('drive_raiz'))
    if not root: raise RuntimeError('drive_root_required')
    report = {'at': datetime.now(timezone.utc).isoformat(), 'queue_writes': 0,
              'decisions_changed': False, 'social_publications': 0,
              'copies': [], 'retained_revisions': [], 'unconfirmed': [], 'targets_checked': 0}
    metadata, revision_cache = {}, {}
    for job in jobs:
        if job.get('estado') != 'hecho': continue
        ev = evidence_of(job)
        fid, expected = file_id(ev.get('drive_id')), md5_expected(ev)
        if not fid or not expected or len(expected) != 32: continue
        if fid not in metadata:
            metadata[fid] = drive._peticion('GET', drive.API + '/files/' + fid,
                params={'fields': 'id,name,mimeType,md5Checksum,trashed'}).json()
        current = metadata[fid]
        if current.get('id') != fid or current.get('trashed'):
            raise RuntimeError('current_reference_unavailable')
        if current.get('md5Checksum') == expected: continue
        report['targets_checked'] += 1
        if fid not in revision_cache:
            available, token = [], None
            while True:
                params = {'pageSize': 100, 'fields': 'nextPageToken,revisions(id,size,md5Checksum,keepForever)'}
                if token: params['pageToken'] = token
                page = drive._peticion('GET', drive.API + '/files/' + fid + '/revisions',
                                       params=params).json()
                available.extend(page.get('revisions') or [])
                token = page.get('nextPageToken')
                if len(available) > 1000: raise RuntimeError('revision_bound')
                if not token: break
            revision_cache[fid] = available
        matches = [r for r in revision_cache[fid] if r.get('md5Checksum') == expected]
        if not matches:
            report['unconfirmed'].append({'id': job.get('id'), 'reason': 'matching_revision_unavailable'})
            continue
        revision = matches[0]
        size = int(revision.get('size') or 0)
        if size < 1 or size > 200 * 1024 * 1024: raise RuntimeError('revision_size_bound')
        # Drive exige conservar una revisión antigua antes de descargar su contenido.
        # Se cambia solo keepForever de la versión con el MD5 exacto; nunca sus bytes.
        if not revision.get('keepForever'):
            retained = drive._peticion('PATCH', drive.API + '/files/' + fid + '/revisions/' + revision['id'],
                                       params={'fields': 'id,size,md5Checksum,keepForever'},
                                       json={'keepForever': True}).json()
            if (retained.get('id') != revision['id'] or retained.get('md5Checksum') != expected
                    or not retained.get('keepForever')):
                raise RuntimeError('revision_retention_not_confirmed')
            report['retained_revisions'].append({'file_id': fid, 'revision_id': revision['id'],
                                                'md5': expected, 'keep_forever': True})
        content = drive._peticion('GET', drive.API + '/files/' + fid + '/revisions/' + revision['id'],
                                 params={'alt': 'media'}).content
        if len(content) != size or hashlib.md5(content).hexdigest() != expected:
            raise RuntimeError('source_revision_not_verified')
        extension = pathlib.PurePosixPath(str(current.get('name') or '')).suffix.lower()
        if extension not in ('.wav', '.mp3', '.mp4', '.m4a', '.ogg', '.webm', '.mov'):
            raise RuntimeError('media_extension_not_recognized')
        family = str(job.get('pieza') or '')
        stem = re.sub(r'[^a-zA-Z0-9_-]', '-', '%s-%s-%s' % (family, job.get('item'), job.get('etapa')))
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / (stem + extension)
            path.write_bytes(content)
            copied, error = subir_producto(path, family, root, config)
            if error or not copied: raise RuntimeError('archive_copy_not_confirmed')
        report['copies'].append({'job_id': job.get('id'), 'source_drive_id': fid,
                                'source_revision_id': revision['id'], 'new_drive_id': copied,
                                'md5': expected, 'sha256': hashlib.sha256(content).hexdigest(),
                                'bytes': size, 'storage_verified': True, 'queue_reconnected': False})
    output = json.dumps(report, ensure_ascii=False, indent=2).encode()
    folder = drive.asegurar_carpeta(root, '_CONEXIONES')
    name = 'SALA-ARCHIVOS-RECUPERADOS-' + os.getenv('GITHUB_RUN_ID', 'manual') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1') + '.json'
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / name
        path.write_bytes(output)
        report_id = drive.subir(str(path), folder, name)
        check = drive._peticion('GET', drive.API + '/files/' + report_id, params={'alt': 'media'}).content
        if check != output: raise RuntimeError('private_report_not_verified')
    print(json.dumps({'ok': not report['unconfirmed'], 'queue_writes': 0, 'decisions_changed': False,
                      'targets_checked': report['targets_checked'], 'copies_verified': len(report['copies']), 'versions_retained': len(report['retained_revisions']),
                      'unconfirmed': len(report['unconfirmed']), 'private_report_saved': True,
                      'report_sha256': hashlib.sha256(output).hexdigest()}))
    return 0 if not report['unconfirmed'] else 2

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print(json.dumps({'ok': False, 'code': type(error).__name__, 'queue_writes': 0}))
        sys.exit(1)
