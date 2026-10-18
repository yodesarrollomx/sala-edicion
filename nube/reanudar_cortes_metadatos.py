"""Operación manual: corregir metadatos exactos, publicar y reanudar cortes vigentes.

No genera textos ni aprobaciones. El manifiesto y los respaldos permanecen privados.
Una publicación confirmada no equivale a corte producido ni a entrega editorial.
"""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
from contextlib import contextmanager

import sala_cliente as sala
import sala_drive as drive
import sala_guion as guion
import sala_produccion as produccion
import sala_productor as productor
from auditar_fallos import fuentes, evaluar, verificar_medio
from corregir_metadatos_editoriales import apply, require
from medios_reconexion import evidence, signature, unique_row
from motores._comun import lamina_de
from plan_agregados import private_config
from recuperar_escena_cpu import guardar
from snapshots_online import GitHub, Snapshots, canonical, digest

ROOT = Path(__file__).resolve().parents[1]


def validate_manifest(manifest, pinned=True):
    require(isinstance(manifest, dict) and manifest.get('schema') == 1, 'parche_sin_contrato')
    if pinned:
        require(re.fullmatch(r'[a-f0-9]{40}', str(manifest.get('code_sha', ''))), 'codigo_sin_pin')
    targets = manifest.get('targets')
    require(isinstance(targets, list) and len(targets) == 4 and all(isinstance(t, dict) for t in targets), 'cuatro_objetivos_requeridos')
    require(len({t.get('id') for t in targets}) == 4 and len({t.get('pid') for t in targets}) == 4, 'objetivos_repetidos')
    for target in targets:
        require(re.fullmatch(r'[a-z0-9_-]+:corte:completo:[a-f0-9]{8}', str(target.get('id', ''))), 'corte_invalido')
        require(produccion.PID.fullmatch(str(target.get('pid', ''))), 'fuente_invalida')
        for key in (('source_sha256', 'row_sha256') if pinned else ('source_sha256',)):
            require(re.fullmatch(r'[a-f0-9]{64}', str(target.get(key, ''))), 'fuente_sin_pin')
    return targets


@contextmanager
def gas_read_only():
    original = sala.post
    def forbidden(*args, **kwargs):
        raise ValueError('preparar_prohibe_post_gas')
    sala.post = forbidden
    try:
        yield
    finally:
        sala.post = original


def read_queue():
    result = sala.get('cola', fresco='1')
    require(isinstance(result, dict) and isinstance(result.get('cola'), list), 'cola_sin_contrato')
    return result['cola']


def read_code_sha():
    # No Snapshots: ni bootstrap, mutex remoto, prepare, publish o archivos estado.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) and token, 'codigo_sin_identidad')
    main = GitHub(repo, token).request('git/ref/heads/main', method='GET')['object']['sha']
    require(re.fullmatch(r'[a-f0-9]{40}', head) and head == main, 'codigo_cambio')
    return head


def prepare_manifest(draft, read=None, code=None):
    read, code = read or read_queue, code or read_code_sha
    validate_manifest(draft, pinned=False)
    sha = code()
    queue = read()
    require(not any(r.get('estado') == 'corriendo' for r in queue), 'ejecucion_en_curso')
    prepared = copy.deepcopy(draft)
    prepared['code_sha'] = sha
    captured = []
    for target in prepared['targets']:
        row = unique_row(queue, target['id'])
        require(row.get('estado') == 'fallo' and row.get('etapa') == 'corte'
                and row.get('item') == 'completo' and evidence(row).get('de') == target['pid'], 'corte_fuera_de_alcance')
        require('ubicaci' in str(evidence(row).get('error', '')).lower(), 'fallo_no_editorial')
        target['row_sha256'] = digest(signature(row).encode())
        captured.append(copy.deepcopy(row))
    newer = read()
    require(not any(r.get('estado') == 'corriendo' for r in newer), 'ejecucion_en_curso')
    require(all(signature(unique_row(newer, row['id'])) == signature(row) for row in captured), 'cola_cambio')
    require(code() == sha, 'codigo_cambio')
    validate_manifest(prepared)
    return {'manifest': prepared, 'manifest_sha256': digest(canonical(prepared)), 'cola_capturada': captured,
            'source_sha_verificado': False, 'nota': 'Sólo captura de firmas; APLICAR valida fuentes y autorizaciones.'}


def immutable_effective(tira):
    """Todo lo resuelto excepto ve; las imágenes/textos/estados no cambian."""
    return [{k: v for k, v in lam.items() if k != 've'} for lam in tira.get('laminas') or []]


def check_target(target, queue, day, raw, corrected):
    row = unique_row(queue, target['id'])
    require(digest(signature(row).encode()) == target['row_sha256'], 'cola_cambio')
    require(row.get('estado') == 'fallo' and row.get('etapa') == 'corte'
            and row.get('item') == 'completo' and evidence(row).get('de') == target['pid'], 'corte_fuera_de_alcance')
    require('ubicaci' in str(evidence(row).get('error', '')).lower(), 'fallo_no_editorial')
    src = [p for p in day['propuestas'] if p.get('id') == target['pid']]
    require(len(src) == 1 and not str(src[0].get('estado', '')).lower().startswith('retirada')
            and not str(src[0].get('origen', '')).lower().startswith('retirada'), 'fuente_no_vigente')
    dec = day['decisiones']['propuestas'].get(target['pid'])
    before = produccion.resolver_tira(json.loads(raw), dec, src[0])
    after = produccion.resolver_tira(json.loads(corrected), dec, src[0])
    require(immutable_effective(before) == immutable_effective(after), 'contenido_elegido_cambio')
    require(produccion.es_video(after), 'fuente_no_es_video')
    from contenido_reglas import exigir
    exigir(after)
    return row, after


def ensure_voice_match(row, resolved, queue):
    """Huella de imagen sola no prueba que la voz contenga el texto vigente."""
    by_n = {str(l['n']): l for l in resolved['laminas']}
    for entry in evidence(row).get('laminas') or []:
        n, h = str(entry['item']), entry['huella']
        voice = unique_row(queue, ':'.join((row['pieza'], 'voz', n, h)))
        require(voice.get('estado') == 'hecho' and n in by_n, 'voz_no_confirmada')
        require(evidence(voice).get('src') and evidence(voice).get('dice'), 'voz_sin_insumos_registrados')
        require(str(lamina_de(voice).get('dice') or '').strip() == str(by_n[n].get('dice') or '').strip(), 'voz_texto_distinto')


def transition(rows, read, write):
    """Un único POST de estados; un acuse perdido se concilia, no se reenvía."""
    before = read()
    require(all(signature(unique_row(before, r['id'])) == signature(r) for r in rows), 'cola_cambio_antes_de_reanudar')
    require(not any(r.get('estado') == 'corriendo' for r in before), 'ejecucion_en_curso')
    try:
        response = write([{'id': r['id'], 'estado': 'pendiente'} for r in rows])
    except sala.SalaError:
        response = None
    after = read()
    for old in rows:
        actual = unique_row(after, old['id'])
        expected = {k: v for k, v in old.items() if k != 'actualizado'}
        expected['estado'] = 'pendiente'
        require({k: v for k, v in actual.items() if k != 'actualizado'} == expected, 'reanudacion_sin_acuse_no_reenviar')
    if response is not None:
        require(response.get('ok') is True and not response.get('ignoradas'), 'reanudacion_respuesta_invalida')
    return [unique_row(after, r['id']) for r in rows]


def main():
    snap = None
    report = {'schema': 1, 'decisiones_modificadas': 0, 'montajes': 0, 'reanudados': [], 'fase': 'inicio'}
    try:
        mode = os.environ.get('EDITORIAL_PATCH_MODE', 'preparar')
        require(mode in ('preparar', 'aplicar'), 'modo_invalido')
        report['modo'] = mode
        sala.enmascarar_en_actions()
        _, parent = private_config()
        fid = os.environ.get('EDITORIAL_PATCH_DOC_ID', '')
        expected_manifest = os.environ.get('EDITORIAL_PATCH_SHA256', '')
        require(re.fullmatch(r'[A-Za-z0-9_-]{10,128}', fid) and re.fullmatch(r'[a-f0-9]{64}', expected_manifest), 'parche_sin_pin')
        meta = drive._peticion('GET', drive.API+'/files/'+fid, params={'fields': 'id,mimeType,trashed,parents'}).json()
        require(meta.get('trashed') is False and parent in meta.get('parents', [])
                and meta.get('mimeType') == 'application/vnd.google-apps.document', 'parche_fuera_de_carpeta')
        raw_manifest = drive._peticion('GET', drive.API+'/files/'+fid+'/export', params={'mimeType': 'text/plain'}).content
        require(0 < len(raw_manifest) <= 131072, 'parche_tamano_invalido')
        manifest = json.loads(raw_manifest.decode('utf-8-sig'))
        # Pin del objeto JSON canónico, estable frente al salto final del export.
        require(digest(canonical(manifest)) == expected_manifest, 'parche_cambio')
        report['manifest_sha256'] = expected_manifest
        if mode == 'preparar':
            report['fase'] = 'capturar_firmas'
            with gas_read_only():
                report.update(prepare_manifest(manifest))
                guardar(report, parent, 'metadatos-manifiesto-preparado')
            print(json.dumps({'ok': True, 'modo': mode, 'firmas_capturadas': 4, 'metadatos_publicados': 0, 'cortes_reanudados': 0}))
            return 0
        targets = validate_manifest(manifest)
        snap = Snapshots(ROOT)
        require(snap.head() == manifest['code_sha'] and snap.main() == manifest['code_sha'], 'codigo_cambio')
        snap.bootstrap(process='mesa', lock=True)
        state = snap.state()
        report['fase'] = 'preparar'
        before = fuentes()
        rules, queue, day, cat = before
        require(not any(r.get('estado') == 'corriendo' for r in queue), 'ejecucion_en_curso')
        require(not produccion.peticiones_abiertas(), 'peticiones_abiertas')
        plans = []
        for target in targets:
            path = ROOT/'datos'/'tiras'/(target['pid']+'.json')
            require(path.is_file() and not path.is_symlink(), 'tira_ausente')
            raw = path.read_bytes()
            require(state['baseline'].get(str(path.relative_to(ROOT))) == digest(raw), 'fuente_fuera_de_snapshot')
            family = target['id'].split(':')[0]
            corrected = apply(raw, target['source_sha256'], target['replacements'], family_has_voice_script=guion.cargar(family) is not None)
            row, resolved = check_target(target, queue, day, raw, corrected)
            ensure_voice_match(row, resolved, queue)
            plans.append({'target': target, 'before': row, 'path': path, 'raw': raw, 'corrected': corrected})
        report['fuentes'] = [{'target': p['target'], 'cola_antes': p['before'], 'tira_antes': p['raw'].decode(), 'tira_despues': p['corrected'].decode()} for p in plans]
        guardar(report, parent, 'metadatos-antes')
        require(canonical(fuentes()) == canonical(before), 'fuentes_cambiaron')
        snap.assert_lease()
        for p in plans:
            require(p['path'].read_bytes() == p['raw'], 'tira_cambio_antes_de_escribir')
        for p in plans:
            p['path'].write_bytes(p['corrected'])
        report['fase'] = 'publicar'
        snap.prepare('mesa')
        snap.dispatch_publish(manifest['code_sha'])
        receipt = snap.state().get('published_receipt')
        require(receipt and receipt.get('code_sha') == manifest['code_sha'], 'publicacion_sin_acuse')
        report['publicacion'] = receipt
        report['fase'] = 'validar_reanudacion'
        current = fuentes()
        require(canonical(current) == canonical(before), 'fuentes_cambiaron_tras_publicar')
        # El veto del fallo anterior se conserva en COLA y respaldo. En una copia
        # de evaluación se elimina sólo ese diagnóstico ya corregido, para pasar
        # por TODAS las compuertas habituales de plan, votos, medios y snapshot.
        audit_queue = copy.deepcopy(queue)
        for p in plans:
            row = unique_row(audit_queue, p['target']['id'])
            ev = evidence(row)
            ev.pop('error', None)
            for candidate in audit_queue:
                if candidate['id'] == row['id']:
                    candidate['evidencia'] = ev
        audit = evaluar(audit_queue, day, rules, cat, planner=productor.planear,
                        resolver=produccion.resolver_tira, tira_reader=produccion.leer_tira,
                        media_check=verificar_medio, snapshot_check=lambda pid: any(p['target']['pid'] == pid and p['path'].read_bytes() == p['corrected'] for p in plans))
        report['auditoria'] = audit
        eligible = {r['id'] for r in audit['candidatos'] if r['elegible']}
        require(all(p['target']['id'] in eligible for p in plans), 'cortes_no_elegibles')
        require(canonical(fuentes()) == canonical(before), 'fuentes_cambiaron_antes_de_cola')
        snap.assert_lease()
        require(snap.main() == manifest['code_sha'], 'codigo_cambio_antes_de_cola')
        guardar(report, parent, 'metadatos-publicados-antes-cola')
        report['fase'] = 'reanudar'
        report['reanudados'] = transition([p['before'] for p in plans], lambda: fuentes()[1],
            lambda rows: sala.post('cola', op='estado', filas=rows))
        guardar(report, parent, 'metadatos-reanudados')
        print(json.dumps({'ok': True, 'metadatos_publicados': 4, 'cortes_reanudados': 4, 'cortes_producidos': 0, 'montajes': 0}))
        return 0
    except Exception as exc:
        report['error'] = str(exc)[:300]
        if 'parent' in locals():
            try:
                guardar(report, parent, 'metadatos-interrumpidos')
            except Exception:
                pass
        print(json.dumps({'ok': False, 'fase': report['fase'], 'cortes_producidos': 0, 'montajes': 0}))
        return 2
    finally:
        if snap is not None:
            snap.release()


if __name__ == '__main__':
    raise SystemExit(main())
