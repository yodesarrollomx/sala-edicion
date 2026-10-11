#!/usr/bin/env python3
"""Conciliación de lectura. El único guardado permitido es su informe privado de auditoría."""
import collections
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sala_cliente as sala
import sala_catalogo as catalogo
import sala_drive as drive

FOLDER = 'application/vnd.google-apps.folder'
FIELDS = 'id,name,mimeType,size,md5Checksum,parents,trashed'
ROOT = pathlib.Path(__file__).resolve().parent.parent
MAX_BINARY = 200 * 1024 * 1024

def git_output(args, cwd=ROOT, *, no_lazy=False, timeout=90):
    """Acota Git y sus procesos hijos; una descarga incierta no bloquea el informe."""
    import signal
    env = dict(os.environ)
    if no_lazy: env['GIT_NO_LAZY_FETCH'] = '1'
    process = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env, start_new_session=True)
    try:
        output, errors = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate()
        raise RuntimeError('git_read_timeout')
    if process.returncode:
        raise RuntimeError('git_read_not_verified')
    return output

def public_blob(commit, path, oid, maximum=MAX_BINARY):
    """Descarga por HTTP una ruta inmutable y verifica su identidad de blob Git."""
    import requests
    url = 'https://raw.githubusercontent.com/yodesarrollomx/sala-edicion/' + commit + '/' + urllib.parse.quote(path)
    try:
        with requests.get(url, timeout=(10, 30), stream=True) as response:
            if response.status_code != 200: raise RuntimeError('public_blob_unavailable')
            length = int(response.headers.get('Content-Length') or 0)
            if length > maximum: raise RuntimeError('public_blob_size_bound')
            chunks, size = [], 0
            for chunk in response.iter_content(1024 * 1024):
                size += len(chunk)
                if size > maximum: raise RuntimeError('public_blob_size_bound')
                chunks.append(chunk)
    except requests.RequestException:
        raise RuntimeError('public_blob_unavailable')
    content = b''.join(chunks)
    actual = hashlib.sha1(b'blob ' + str(len(content)).encode() + bytes([0]) + content).hexdigest()
    if actual != oid: raise RuntimeError('public_blob_identity_not_verified')
    return content

def evidence_of(job):
    value = job.get('evidencia') or {}
    if isinstance(value, str):
        try: value = json.loads(value)
        except (TypeError, ValueError): value = {}
    return value if isinstance(value, dict) else {}

def md5_expected(ev):
    value = str(ev.get('md5') or ev.get('md5_salida') or '').lower()
    return value if re.fullmatch(r'[0-9a-f]{8,32}', value) else None

def file_id(value):
    value = str(value or '').strip()
    if re.fullmatch(r'[A-Za-z0-9_-]{15,160}', value): return value
    match = re.search(r'/d/([A-Za-z0-9_-]{15,160})', value)
    if match: return match.group(1)
    return (urllib.parse.parse_qs(urllib.parse.urlsplit(value).query).get('id') or [None])[0]

def main():
    sala.enmascarar_en_actions()
    report = {'at': datetime.now(timezone.utc).isoformat(), 'business_writes': 0,
              'decisions_changed': False, 'social_publications': 0,
              'publisher_app': {'id_configured': bool(re.fullmatch(r'[0-9]+', os.getenv('YOD_APP_ID', ''))),
                                'key_configured': bool(os.getenv('YOD_APP_KEY', '').strip())},
              'jobs': [], 'root_reads': [], 'errors': []}
    metadata_cache, binary_cache, git_assets = {}, {}, {}
    jobs = sala.get('cola').get('cola')
    if not isinstance(jobs, list): raise RuntimeError('queue_contract_missing')
    config = sala.get('reglas').get('reglas')
    if not isinstance(config, dict): raise RuntimeError('rules_contract_missing')
    catalog = sala.get('catalogo', fresco='1').get('catalogo')
    if not isinstance(catalog, dict): raise RuntimeError('catalog_contract_missing')
    report['queue_count'] = len(jobs)
    report['queue_states'] = dict(collections.Counter(str(j.get('estado')) for j in jobs))
    report['catalog_revisions'] = sum(len(c.get('revisiones') or []) for c in catalog.values())
    report['catalog_revisions_with_identity'] = sum(bool(r.get('huella')) for c in catalog.values() for r in c.get('revisiones') or [])

    def metadata(fid):
        if fid not in metadata_cache:
            response = drive._peticion('GET', drive.API + '/files/' + fid,
                                       params={'fields': FIELDS})
            data = response.json()
            if data.get('id') != fid or data.get('trashed'): raise RuntimeError('invalid_file_metadata')
            metadata_cache[fid] = data
        return metadata_cache[fid]

    def binary(fid):
        if fid not in binary_cache:
            meta = metadata(fid)
            size = int(meta.get('size') or 0)
            if size < 1 or size > MAX_BINARY: raise RuntimeError('file_size_out_of_bound')
            data = drive._peticion('GET', drive.API + '/files/' + fid, params={'alt': 'media'}).content
            if len(data) != size: raise RuntimeError('file_size_mismatch')
            result = {'bytes': len(data), 'md5': hashlib.md5(data).hexdigest(),
                      'sha256': hashlib.sha256(data).hexdigest()}
            if meta.get('md5Checksum') != result['md5']: raise RuntimeError('drive_content_checksum_mismatch')
            binary_cache[fid] = result
        return binary_cache[fid]

    roots = []
    current_root = file_id(config.get('drive_raiz'))
    if current_root: roots.append(current_root)
    # Raíces históricas derivadas de IDs que el catálogo canónico ya autoriza.
    for record in list(catalog.values())[:3]:
        for revision in (record.get('revisiones') or [])[:1]:
            fid = file_id(revision.get('original') or revision.get('drive_original'))
            if not fid: continue
            try:
                cursor = metadata(fid)
                for _ in range(6):
                    if cursor.get('mimeType') == FOLDER and str(cursor.get('name') or '').lower() == 'yod editorial':
                        if cursor['id'] not in roots: roots.append(cursor['id'])
                        break
                    parents = cursor.get('parents') or []
                    if len(parents) != 1: break
                    cursor = metadata(parents[0])
            except (drive.DriveError, RuntimeError, ValueError):
                report['errors'].append({'operation': 'catalog_ancestry', 'code': 'read_unavailable'})
    inventory = {}
    for root_id in roots:
        pending, seen, errors = collections.deque([root_id]), set(), 0
        while pending:
            folder_id = pending.popleft()
            if folder_id in seen: continue
            seen.add(folder_id)
            if len(seen) > 500: raise RuntimeError('folder_scan_bound')
            page_token = None
            while True:
                params = {'q': "'" + folder_id + "' in parents and trashed = false",
                          'fields': 'nextPageToken,files(' + FIELDS + ')', 'pageSize': 100}
                if page_token: params['pageToken'] = page_token
                try: response = drive._peticion('GET', drive.API + '/files', params=params).json()
                except drive.DriveError:
                    errors += 1
                    break
                for item in response.get('files') or []:
                    metadata_cache[item['id']] = item
                    if item.get('mimeType') == FOLDER: pending.append(item['id'])
                    else: inventory[item['id']] = item
                if len(inventory) > 5000: raise RuntimeError('file_scan_bound')
                page_token = response.get('nextPageToken')
                if not page_token: break
        report['root_reads'].append({'root_id': root_id, 'folders': len(seen), 'errors': errors, 'complete': errors == 0})
    report['drive_files_scanned'] = len(inventory)

    names = git_output(['git', 'ls-tree', '-r', '--name-only', '-z', 'HEAD'], cwd=ROOT).decode().split('\0')
    legacy = [j for j in jobs if j.get('estado') == 'hecho' and not evidence_of(j).get('drive_id') and not evidence_of(j).get('ruta_local')]
    references = {str(evidence_of(j).get('src') or '') for j in legacy}
    for job in legacy: references.update(evidence_of(job).get('candidatas') or [])
    for name in names:
        if not name or not (name in references or re.search(r'\.(mp4|wav|mp3|ogg|m4a|webm|mov)$', name, re.I)): continue
        if pathlib.PurePosixPath(name).is_absolute() or '..' in pathlib.PurePosixPath(name).parts: continue
        try:
            oid = git_output(['git', 'rev-parse', 'HEAD:' + name], cwd=ROOT).decode().strip()
            head = git_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
            data = public_blob(head, name, oid)
            if not data: continue
            git_assets[name] = {'bytes': len(data), 'md5': hashlib.md5(data).hexdigest(),
                                'sha256': hashlib.sha256(data).hexdigest(), 'blob_sha': oid}
        except RuntimeError:
            report['errors'].append({'operation': 'git_current_read', 'code': 'not_verified'})
    page_cache = {}
    def published(name):
        if name not in page_cache:
            import requests
            url = 'https://yodesarrollomx.github.io/sala-edicion/' + urllib.parse.quote(name)
            response = requests.get(url, timeout=30)
            page_cache[name] = {'url': url, 'http': response.status_code,
                                'sha256': hashlib.sha256(response.content).hexdigest(),
                                'matches_git': response.status_code == 200 and hashlib.sha256(response.content).hexdigest() == git_assets[name]['sha256']}
        return page_cache[name]

    for job in jobs:
        if job.get('estado') != 'hecho': continue
        ev = evidence_of(job)
        expected = md5_expected(ev)
        result = {'id': job.get('id'), 'stage': job.get('etapa'), 'source_hash': str(job.get('id') or '').split(':')[-1],
                  'record_updated': job.get('actualizado'), 'expected_output_hash': expected,
                  'legacy': job in legacy}
        fid = file_id(ev.get('drive_id'))
        if fid:
            try:
                meta, content = metadata(fid), binary(fid)
                result.update({'drive_id': fid, 'content': content, 'expected_hash_complete': bool(expected and len(expected) == 32)})
                result['status'] = 'durable_verified' if expected and content['md5'].startswith(expected) else 'stored_content_differs_from_record'
            except (drive.DriveError, RuntimeError, ValueError):
                result['status'] = 'drive_reference_unavailable'
        elif ev.get('candidatas'):
            candidates = ev.get('candidatas') or []
            checks = [dict(path=p, **published(p)) for p in candidates if p in git_assets]
            result.update({'outputs': checks, 'status': 'published_group_verified' if len(checks) == len(candidates) and all(x['matches_git'] for x in checks) else 'group_not_verified'})
        else:
            matched_drive = [f for f in inventory.values() if expected and str(f.get('md5Checksum') or '').startswith(expected)]
            matched_git = [(p, data) for p, data in git_assets.items() if expected and data['md5'].startswith(expected)]
            proofs = []
            for candidate in matched_drive:
                try: proofs.append({'drive_id': candidate['id'], 'name': candidate.get('name'), **binary(candidate['id'])})
                except (drive.DriveError, RuntimeError, ValueError): pass
            for p, data in matched_git:
                try:
                    visible = published(p)
                    if visible['matches_git']: proofs.append({'path': p, **data, **visible})
                except Exception: pass
            unique_hashes = {p['md5'] for p in proofs}
            result.update({'matches': proofs, 'expected_hash_complete': bool(expected and len(expected) == 32)})
            result['status'] = ('existing_outputs_located' if len(unique_hashes) == 1 else
                                'ambiguous_output_hash' if len(unique_hashes) > 1 else 'not_located_in_scanned_sources')
        report['jobs'].append(result)
    if '--incluir-historia' in sys.argv:
        wanted = {j.get('expected_output_hash') for j in report['jobs']
                  if j['status'] in ('not_located_in_scanned_sources',
                                     'stored_content_differs_from_record',
                                     'drive_reference_unavailable') and j.get('expected_output_hash')}
        archive, errors, seen = [], [], {x['blob_sha'] for x in git_assets.values()}
        scanned, total, skipped, complete = 0, 0, 0, True
        objects = git_output(['git', 'rev-list', '--objects', 'HEAD'],
                                          cwd=ROOT).decode().splitlines()
        image_dirs = {str(pathlib.PurePosixPath(p).parent) for p in references if p}
        eligible = []
        for line in objects:
            oid, separator, path = line.partition(' ')
            if not separator or oid in seen or not re.search(r'[.](mp4|wav|mp3|ogg|m4a|webm|mov|png|jpg|jpeg)$', path, re.I):
                continue
            if re.search(r'[.](png|jpg|jpeg)$', path, re.I) and str(pathlib.PurePosixPath(path).parent) not in image_dirs:
                continue
            seen.add(oid)
            eligible.append((oid, path))
        if len(eligible) > 1500:
            complete = False
            eligible = eligible[:1500]
        print(json.dumps({'operation': 'git_history', 'objects_selected': len(eligible),
                          'image_scope': 'canonical_output_directories'}), flush=True)
        for oid, path in eligible:
            if scanned >= 1500 or total >= 2 * 1024 ** 3:
                complete = False
                break
            try:
                commits = git_output(
                    ['git', 'log', '--no-renames', '-n', '20', '--format=%H', '--find-object=' + oid, 'HEAD', '--', path],
                    cwd=ROOT).decode().splitlines()
                resolved = None
                for commit in commits:
                    located = subprocess.run(['git', 'rev-parse', '--verify', commit + ':' + path],
                                             cwd=ROOT, capture_output=True, text=True, timeout=20)
                    if located.returncode == 0 and located.stdout.strip() == oid:
                        resolved = commit
                        break
                if not resolved: raise RuntimeError('archive_path_not_verified')
                data = public_blob(resolved, path, oid, maximum=min(MAX_BINARY, 2 * 1024 ** 3 - total))
                if not data:
                    skipped += 1
                    continue
                digest = hashlib.md5(data).hexdigest()
                scanned += 1
                total += len(data)
                if not any(digest.startswith(value) for value in wanted): continue
                proof = {'source': 'git_history', 'path': path, 'blob_sha': oid, 'bytes': len(data),
                         'md5': digest, 'sha256': hashlib.sha256(data).hexdigest(), 'download_verified': True}
                commits = git_output(
                    ['git', 'log', '--no-renames', '-n', '20', '--format=%H', '--find-object=' + oid, 'HEAD', '--', path],
                    cwd=ROOT).decode().splitlines()
                for commit in commits:
                    located = subprocess.run(['git', 'rev-parse', '--verify', commit + ':' + path],
                                             cwd=ROOT, capture_output=True, text=True, timeout=20)
                    if located.returncode == 0 and located.stdout.strip() == oid:
                        proof.update({'commit': commit, 'url': 'https://raw.githubusercontent.com/yodesarrollomx/sala-edicion/' + commit + '/' + urllib.parse.quote(path)})
                        break
                archive.append(proof)
            except (subprocess.SubprocessError, RuntimeError, ValueError, OSError):
                errors.append({'operation': 'git_archive_read', 'code': 'not_verified'})
        revision_reads, revision_count = [], 0
        revision_files = {j.get('drive_id') for j in report['jobs']
                          if j['status'] == 'stored_content_differs_from_record' and j.get('drive_id')}
        for fid in revision_files:
            token, available, count = None, [], 0
            try:
                while True:
                    params = {'pageSize': 100, 'fields': 'nextPageToken,revisions(id,size,md5Checksum,keepForever)'}
                    if token: params['pageToken'] = token
                    page = drive._peticion('GET', drive.API + '/files/' + fid + '/revisions', params=params).json()
                    available.extend(page.get('revisions') or [])
                    count += len(page.get('revisions') or [])
                    token = page.get('nextPageToken')
                    if not token or count >= 1000: break
                revision_count += count
                revision_reads.append({'file_id': fid, 'count': count, 'complete': not token})
                for revision in available:
                    digest = str(revision.get('md5Checksum') or '')
                    if not digest or not any(digest.startswith(value) for value in wanted): continue
                    size = int(revision.get('size') or 0)
                    if size < 1 or size > MAX_BINARY: continue
                    content = drive._peticion('GET', drive.API + '/files/' + fid + '/revisions/' + revision['id'],
                                             params={'alt': 'media'}).content
                    if len(content) != size or hashlib.md5(content).hexdigest() != digest: continue
                    archive.append({'source': 'drive_history', 'drive_id': fid, 'revision_id': revision['id'],
                                    'bytes': len(content), 'md5': digest,
                                    'sha256': hashlib.sha256(content).hexdigest(),
                                    'keep_forever': bool(revision.get('keepForever')), 'download_verified': True})
            except (drive.DriveError, RuntimeError, ValueError):
                revision_reads.append({'file_id': fid, 'code': 'revisions_unavailable'})
        recovered = 0
        for job in report['jobs']:
            expected = job.get('expected_output_hash')
            if not expected or job['status'] not in ('not_located_in_scanned_sources',
                                                    'stored_content_differs_from_record',
                                                    'drive_reference_unavailable'): continue
            proofs = [p for p in archive if p['md5'].startswith(expected)]
            if not proofs: continue
            job['historical_matches'] = proofs
            if len({p['md5'] for p in proofs}) == 1:
                recovered += 1
                if job['status'] == 'not_located_in_scanned_sources':
                    job['prior_status'] = job['status']
                    job['status'] = 'historical_output_located'
            else: job['historical_match_ambiguous'] = True
        report['history'] = {'git_assets_scanned': scanned, 'git_bytes_scanned': total,
                             'git_scan_complete': complete and skipped == 0 and not errors,
                             'git_assets_skipped': skipped, 'git_objects_selected': len(eligible),
                             'git_image_scope': 'canonical_output_directories', 'drive_revisions_scanned': revision_count,
                             'drive_revision_reads': revision_reads, 'recovered_jobs': recovered, 'errors': errors}
    report['summary'] = dict(collections.Counter(j['status'] for j in report['jobs']))
    report['legacy_summary'] = dict(collections.Counter(j['status'] for j in report['jobs'] if j['legacy']))
    report['git_assets_scanned'] = len(git_assets)
    report['git_current_scan_complete'] = not any(x.get('operation') == 'git_current_read' for x in report['errors'])
    report['verified_drive_downloads'] = len(binary_cache)
    report['full_report_contains_private_technical_references'] = True
    output = json.dumps(report, ensure_ascii=False, indent=2).encode()
    if '--guardar-informe' in sys.argv:
        if not current_root: raise RuntimeError('current_drive_root_required')
        folder = drive.asegurar_carpeta(current_root, '_CONEXIONES')
        filename = 'SALA-CONEXIONES-' + os.getenv('GITHUB_RUN_ID', 'manual') + '-' + os.getenv('GITHUB_RUN_ATTEMPT', '1') + '.json'
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / filename
            path.write_bytes(output)
            report_id = drive.subir(str(path), folder, filename)
            received = drive._peticion('GET', drive.API + '/files/' + report_id, params={'alt': 'media'}).content
            if received != output: raise RuntimeError('private_report_save_not_verified')
        saved = True
    else: saved = False
    # Únicamente agregados en el log público. Los IDs y rutas quedan en Drive privado.
    print(json.dumps({'read_only_business': True, 'private_report_saved': saved,
                      'queue_count': report['queue_count'], 'queue_states': report['queue_states'],
                      'publisher_app': report['publisher_app'],
                      'catalog_revisions': report['catalog_revisions'],
                      'catalog_revisions_with_identity': report['catalog_revisions_with_identity'],
                      'drive_files_scanned': report['drive_files_scanned'],
                      'git_current_scan_complete': report['git_current_scan_complete'],
                      'source_read_errors': len(report['errors']),
                      'roots_complete': [x['complete'] for x in report['root_reads']],
                      'summary': report['summary'], 'legacy_summary': report['legacy_summary'],
                      'verified_drive_downloads': len(binary_cache),
                      'history': {k: v for k, v in report.get('history', {}).items() if k not in ('drive_revision_reads', 'errors')},
                      'report_sha256': hashlib.sha256(output).hexdigest()}, sort_keys=True))
    return 0

if __name__ == '__main__':
    try: sys.exit(main())
    except Exception as error:
        print(json.dumps({'ok': False, 'code': type(error).__name__, 'business_writes': 0}))
        sys.exit(1)
