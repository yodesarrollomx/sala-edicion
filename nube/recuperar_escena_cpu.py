"""Recuperación manual de una escena interrumpida: fuente vigente, ausencia durable y CPU."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile

import sala_cliente as sala
import sala_drive as drive
import sala_catalogo as catalogo
import sala_produccion as produccion
import sala_productor as productor
from medios_reconexion import unique_row, signature
from snapshots_online import canonical

ROOT = Path(__file__).resolve().parents[1]


class RecuperacionError(RuntimeError):
    pass


def exigir(ok, code):
    if not ok:
        raise RecuperacionError(code)


def validar(row, plan, reglas, archivos):
    """Sin efectos: ni un archivo ambiguo ni una decisión distinta permiten repetir."""
    exigir(row.get('estado') == 'bloqueado'
           and row.get('bloqueado_por') == 'ejecucion_cancelada_sin_acuse'
           and row.get('etapa') == 'escena', 'estado_no_recuperable')
    exigir(re.fullmatch(r'[A-Za-z0-9_-]+:escena:[0-9]+:[a-f0-9]{8}', str(row.get('id') or '')), 'identidad_invalida')
    exigir(row['id'].split(':')[:3] == [row.get('pieza'),'escena',str(row.get('item'))], 'descriptor_invalido')
    exigir('escena' in str(reglas.get('nube_ejecuta_etapas') or '').split(','), 'etapa_no_habilitada')
    exigir(any(str(reglas.get(key,'1')).strip() not in ('0','no','false')
                for key in ('escena_parallax','escena_respaldo_camara')), 'cpu_no_habilitada')
    expected = [p for p in plan if p.get('id') == row['id']]
    exigir(len(expected) == 1, 'plan_no_coincide')
    old = row.get('evidencia') or {}
    if isinstance(old, str):
        old = json.loads(old)
    new = expected[0].get('evidencia') or {}
    for key in ('de', 'src', 'dice', 'nota', 'lamina', 'n_real'):
        exigir(old.get(key) == new.get(key), 'insumo_o_decision_distintos')
    exigir(old.get('src') and old.get('dice') and not old.get('drive_id'), 'insumo_sin_confirmar')
    prefix = '%s-L%s-escena' % (row['pieza'], row['item'])
    exigir(not any(f.get('name') == prefix + '.mp4' or f.get('name', '').startswith(prefix + '-')
                   for f in archivos), 'salida_existente_requiere_conciliacion')
    return copy.deepcopy(old)


def inventario(reglas, row):
    root = str(reglas.get('drive_raiz') or '')
    exigir(re.fullmatch(r'[A-Za-z0-9_-]{10,128}', root), 'drive_sin_configurar')
    # Lectura estricta; un 404 no se interpreta como carpeta vacía.
    def child(parent, name):
        q = "'%s' in parents and name = '%s' and trashed = false and mimeType = 'application/vnd.google-apps.folder'" % (parent, name)
        response = drive._peticion('GET', drive.API + '/files', params={'q':q,'fields':'files(id),nextPageToken','pageSize':100}).json()
        exigir(len(response.get('files') or []) == 1 and not response.get('nextPageToken'), 'carpeta_no_unica')
        return response['files'][0]['id']
    folder = child(child(root, row['pieza'].upper()), '_producidos')
    response = drive._peticion('GET', drive.API + '/files', params={
        'q':"'%s' in parents and trashed = false" % folder,
        'fields':'files(id,name,createdTime,md5Checksum,size),nextPageToken','pageSize':1000}).json()
    exigir(isinstance(response.get('files'), list) and not response.get('nextPageToken'), 'inventario_incompleto')
    return folder, response['files']


def guardar(report, folder, phase):
    data = canonical(report) + b'\n'
    name = 'recuperacion-%s-%s-%s.json' % (os.environ['GITHUB_RUN_ID'],os.environ.get('GITHUB_RUN_ATTEMPT','1'),phase)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)/name;path.write_bytes(data)
        fid = drive.subir(path, folder, name)
        exigir(drive.bajar(fid, Path(tmp)/'verificado').read_bytes() == data, 'auditoria_no_confirmada')


def main():
    phase = 'lectura'; effects = False
    try:
        sala.enmascarar_en_actions()
        drive.INTENTOS = 1
        job = os.environ.get('RECUPERAR_JOB_ID', '')
        exigir(re.fullmatch(r'[A-Za-z0-9_-]+:escena:[0-9]+:[a-f0-9]{8}', job), 'identidad_invalida')
        rules = (sala.get('reglas', fresco='1') or {}).get('reglas') or {}
        queue = (sala.get('cola', fresco='1') or {}).get('cola') or []
        row = unique_row(queue, job)
        exigir(not any(r.get('estado') == 'corriendo' for r in queue), 'ejecucion_en_curso')
        exigir(not produccion.peticiones_abiertas(), 'peticiones_abiertas')
        day = produccion.cargar()
        cat = catalogo.cargar()
        plan, _ = productor.planear(day, [r for r in queue if r.get('id') != job], rules, cat)
        folder, files = inventario(rules, row)
        ev = validar(row, plan, rules, files)
        report = {'schema':1,'antes':row,'plan':next(p for p in plan if p['id']==job),
                  'decision':day['decisiones']['propuestas'].get(ev['de']),
                  'inventario':files,'modo':'cpu_sin_reenvio_a_proveedor','code_sha':os.environ.get('GITHUB_SHA')}
        guardar(report, folder, 'antes')
        phase = 'segunda_lectura'
        again = unique_row((sala.get('cola', fresco='1') or {}).get('cola') or [], job)
        exigir(signature(again) == signature(row), 'cola_cambio')
        exigir(canonical(produccion.cargar()) == canonical(day), 'decisiones_cambiaron')
        exigir((sala.get('reglas', fresco='1') or {}).get('reglas') == rules, 'reglas_cambiaron')
        _, latest_files = inventario(rules, row)
        validar(row, plan, rules, latest_files)
        phase = 'produccion_cpu';effects = True
        ack = sala.post('cola',op='estado',filas=[{'id':job,'estado':'corriendo'}])
        exigir(ack.get('ok') and not ack.get('ignoradas'), 'inicio_sin_acuse')
        from sala_ejecutor import ejecutar_uno
        # Lista de proveedores vacía y Modal apagado: una recuperación nunca repite
        # una petición externa cuyo resultado quedó incierto al cancelar el runner.
        local_rules = dict(rules, escena_modal='0')
        current = copy.deepcopy(row);current['evidencia'] = ev
        state, output = ejecutar_uno(current,local_rules,[],cat,str(rules['drive_raiz']),queue)
        exigir(state == 'hecho' and output.get('durable') is True
               and output.get('motor') in ('parallax','camara') and output.get('generativa') is False,
               'producto_cpu_sin_confirmar')
        final_ev = {**ev,**output,'recuperacion':'cpu_tras_interrupcion_sin_salida_durable',
                    'recuperacion_run':os.environ['GITHUB_RUN_ID']}
        report['resultado'] = final_ev
        guardar(report,folder,'resultado')
        phase = 'guardar_resultado'
        ack = sala.post('cola',op='estado',filas=[{'id':job,'estado':'hecho','bloqueado_por':'','evidencia':final_ev}])
        exigir(ack.get('ok') and not ack.get('ignoradas'), 'resultado_sin_acuse')
        actual = unique_row((sala.get('cola', fresco='1') or {}).get('cola') or [],job)
        actual_ev = actual.get('evidencia') or {}
        if isinstance(actual_ev,str):actual_ev=json.loads(actual_ev)
        exigir(actual.get('estado')=='hecho' and actual_ev.get('md5')==output['md5']
               and actual_ev.get('drive_id')==output['drive_id'],'readback_no_coincide')
        print(json.dumps({'ok':True,'hechos':1,'durable':True,'motor':output['motor'],
                          'generativa':False,'proveedores_invocados':0,'decisiones_modificadas':0}))
        return 0
    except Exception as error:
        print(json.dumps({'ok':False,'fase':phase,'efectos_iniciados':effects,
                          'codigo':str(error) if isinstance(error,RecuperacionError) else type(error).__name__}))
        return 2


if __name__=='__main__':raise SystemExit(main())
