"""Entrega de cortes durables a una revisión nueva, sin decidir ni cambiar permisos."""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import sala_cliente as sala
import sala_drive as drive
import sala_catalogo as catalogo
import sala_produccion as produccion
import sala_productor as productor
from contenido_reglas import exigir as contenido_valido
from medios_reconexion import evidence, signature, unique_row
from recuperar_escena_cpu import guardar, inventario
from snapshots_online import canonical


class EntregaError(RuntimeError):
    pass


def exigir(ok, code):
    if not ok:
        raise EntregaError(code)


def preparar(row, plan, titulo):
    ev = evidence(row)
    exigir(row.get('estado') == 'hecho' and row.get('etapa') == 'corte'
           and row.get('item') == 'completo' and ev.get('durable') is True, 'corte_no_durable')
    exigir(re.fullmatch(r'[a-z0-9_-]+:corte:completo:[a-f0-9]{8}', str(row.get('id') or ''))
           and row['id'].split(':')[0] == row.get('pieza'), 'identidad_invalida')
    exigir(re.fullmatch(r'[a-f0-9]{32}', str(ev.get('md5') or ''))
           and re.fullmatch(r'[A-Za-z0-9_-]{10,128}', str(ev.get('drive_id') or '')), 'medio_sin_identidad')
    expected = [p for p in plan if p.get('id') == row['id']]
    exigir(len(expected) == 1, 'corte_no_vigente')
    pe = expected[0].get('evidencia') or {}
    exigir(ev.get('de') and ev.get('laminas') and pe.get('de') == ev['de']
           and canonical(pe.get('laminas')) == canonical(ev['laminas']), 'insumos_distintos')
    exigir(isinstance(titulo, str) and titulo.strip(), 'pieza_sin_titulo')
    prop = {'id': '%s-corte-nube-%s' % (row['pieza'], ev['md5'][:12]),
            'titulo': titulo.split(' · ')[0] + ' · corte completo · para revisar',
            'tipo': 'eje', 'laminas': [],
            'opciones': {'porque': 'Revisa el corte completo: imagen, voz y secuencia. Esta revisión conserva las decisiones de tus láminas.',
                         'candidatas': [{'titulo': 'Conservar este corte', 'texto': 'El corte está bien como lo veo y escucho.'}]},
            'video': 'https://drive.google.com/file/d/%s/preview' % ev['drive_id'],
            'origen': 'corte-de ' + ev['de']}
    contenido_valido(prop)
    return prop


def comprobar_medio(ev, metadata, path):
    exigir(metadata.get('trashed') is False and metadata.get('mimeType') == 'video/mp4'
           and metadata.get('md5Checksum') == ev['md5'], 'metadatos_distintos')
    exigir(0 < int(metadata.get('size') or 0) <= 256 * 1024 * 1024, 'tamano_invalido')
    exigir(path.stat().st_size == int(metadata['size'])
           and hashlib.md5(path.read_bytes()).hexdigest() == ev['md5'], 'bytes_distintos')
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries',
                        'stream=codec_type:format=duration','-of','json',str(path)], timeout=40))
    exigir({'video','audio'} <= {s.get('codec_type') for s in probe.get('streams') or []}, 'falta_audio_o_video')
    duration = float(probe.get('format',{}).get('duration') or 0)
    exigir(duration > 0 and abs(duration - float(ev.get('duracion_s') or 0)) <= 1, 'duracion_distinta')


def coincidencia(day, prop):
    found = [p for p in day.get('propuestas') or [] if p.get('id') == prop['id']]
    exigir(len(found) <= 1, 'propuesta_duplicada')
    if not found:
        return False
    exigir(all(canonical(found[0].get(k)) == canonical(v) for k,v in prop.items()), 'propuesta_distinta')
    return True


def fuente(day, ev):
    found = [p for p in day.get('propuestas') or [] if p.get('id') == ev['de']]
    exigir(len(found) == 1, 'fuente_no_activa')
    return {'propuesta': found[0], 'decision': day['decisiones']['propuestas'].get(ev['de'])}


def contexto(day, queue, rules, cat, row):
    ev = evidence(row)
    src = fuente(day, ev)
    tira = productor.tira_de(ev['de'])
    exigir(tira is not None, 'tira_ausente')
    tira = produccion.resolver_tira(tira, src['decision'], src['propuesta'])
    contenido_valido(tira, rules)
    plan, _ = productor.planear(day, [r for r in queue if r.get('id') != row['id']], rules, cat)
    return preparar(row, plan, tira.get('pieza') or src['propuesta'].get('titulo')), src


def guardar_fila(row, ev):
    ack = sala.post('cola', op='estado', filas=[{'id': row['id'], 'estado': 'hecho', 'evidencia': ev}])
    exigir(ack.get('ok') and not ack.get('ignoradas'), 'cola_sin_acuse')
    actual = unique_row((sala.get('cola', fresco='1') or {}).get('cola') or [], row['id'])
    exigir(actual.get('estado') == 'hecho' and canonical(evidence(actual)) == canonical(ev), 'cola_readback_distinto')
    return actual


def entregar(row, day, queue, rules, cat):
    ev = evidence(row)
    prop, src = contexto(day, queue, rules, cat, row)
    previous = ev.get('entrega') or {}
    exists = coincidencia(day, prop)
    if previous:
        exigir(previous.get('estado') == 'preparada' and previous.get('prop_id') == prop['id']
               and previous.get('video') == prop['video'], 'entrega_previa_distinta')
        exigir(exists, 'acuse_incierto_no_reenviar')
    else:
        exigir(not exists, 'propuesta_existente_sin_recibo')
    metadata = drive._peticion('GET', drive.API+'/files/'+ev['drive_id'], params={
        'fields':'id,mimeType,size,md5Checksum,trashed,parents'}).json()
    with tempfile.TemporaryDirectory() as tmp:
        path = drive.bajar(ev['drive_id'], Path(tmp)/'corte.mp4')
        comprobar_medio(ev, metadata, path)
    folder, files = inventario(rules, row)
    exigir(folder in metadata.get('parents',[]) and any(f.get('id') == ev['drive_id'] for f in files), 'medio_fuera_de_pieza')
    report = {'schema':1,'antes':row,'fuente':src,'propuesta':prop,'medio':metadata,
              'decisiones_modificadas':0,'permisos_modificados':0,'publicaciones_sociales':0}
    guardar(report, folder, 'entrega-%s-antes' % ev['md5'][:12])
    latest_queue = (sala.get('cola', fresco='1') or {}).get('cola') or []
    exigir(signature(unique_row(latest_queue,row['id'])) == signature(row), 'cola_cambio')
    exigir(not any(r.get('estado') == 'corriendo' for r in latest_queue), 'ejecucion_en_curso')
    latest_day = produccion.cargar()
    exigir(canonical(fuente(latest_day,ev)) == canonical(src), 'fuente_cambio')
    exigir((sala.get('reglas',fresco='1') or {}).get('reglas') == rules, 'reglas_cambiaron')
    current_prop, _ = contexto(latest_day, latest_queue, rules, cat, row)
    exigir(canonical(current_prop) == canonical(prop), 'plan_cambio')
    exigir(coincidencia(latest_day,prop) == exists, 'mesa_cambio')
    if not exists:
        ev['entrega'] = {'estado':'preparada','prop_id':prop['id'],'video':prop['video'],
                         'run':os.environ['GITHUB_RUN_ID']}
        row = guardar_fila(row, ev)
        # Un solo POST. El transporte nunca repite escrituras; si se pierde el
        # acuse se concilia en una lectura posterior, nunca se decide por él.
        try:
            ack = sala.post('proponer', propuestas=[prop])
            exigir(ack.get('ok') and not ack.get('retiradas_familia'), 'montaje_sin_acuse')
        except sala.SalaError:
            pass
        exigir(coincidencia(produccion.cargar(), prop), 'acuse_incierto_no_reenviar')
    ev['entrega'] = {**ev['entrega'],'estado':'montada'}
    report['resultado'] = ev['entrega']
    guardar(report, folder, 'entrega-%s-resultado' % ev['md5'][:12])
    guardar_fila(row, ev)
    return True


def main():
    try:
        sala.enmascarar_en_actions()
        drive.INTENTOS = 1
        rules = (sala.get('reglas', fresco='1') or {}).get('reglas') or {}
        queue = (sala.get('cola', fresco='1') or {}).get('cola') or []
        exigir(not any(r.get('estado') == 'corriendo' for r in queue), 'ejecucion_en_curso')
        day, cat = produccion.cargar(), catalogo.cargar()
        count = 0
        for row in queue:
            if row.get('etapa') != 'corte' or row.get('estado') != 'hecho':
                continue
            ev = evidence(row)
            if ev.get('durable') is not True or (ev.get('entrega') or {}).get('estado') == 'montada':
                continue
            if entregar(row, day, queue, rules, cat):
                count += 1
                day = produccion.cargar()
                queue = (sala.get('cola',fresco='1') or {}).get('cola') or []
        print(json.dumps({'ok':True,'montadas':count,'decisiones_modificadas':0,'permisos_modificados':0}))
        return 0
    except Exception as error:
        print(json.dumps({'ok':False,'codigo':str(error) if isinstance(error,EntregaError) else type(error).__name__}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
