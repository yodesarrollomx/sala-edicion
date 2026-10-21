"""Versiona un corte rechazado sin cambiar las aprobaciones de sus imágenes."""
import hashlib
import json
import re

POLITICA = 'video-real-voz-gemini-sin-congelar-v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def evidence(row):
    value = row.get('evidencia') or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def firma(decision):
    """El contrato histórico valida firmas; aquí además exige el rechazo explícito."""
    if not isinstance(decision, dict) or decision.get('laminas') != ['no']:
        return None
    groups = decision.get('firmas') or []
    notes = decision.get('firmas_nota') or []
    if (len(groups) != 1 or not any(s.get('marca') == 'no' and
            s.get('rol') in ('editor', 'editor2') and s.get('guardado') for s in groups[0])
            or not notes or not decision.get('nota')):
        return None
    return hashlib.sha256(canonical(decision).encode()).hexdigest()


def perfil(reglas):
    """Este perfil nunca convierte una limitación de cuota en un medio rechazado."""
    return dict(reglas, escena_parallax='0', escena_respaldo_camara='0',
                escena_camara_si_cuota='0', escena_video_real='1',
                voz_motor='gemini_tts', audio_margen_s='0', audio_cola_s='0.15',
                montaje_video_real='1', escena_segundos='5')


def planear(dia, cola, reglas, cat, plan_base):
    habilitadas = {p.strip() for p in str(reglas.get('video_revision_piezas') or '').split(',') if p.strip()}
    if not habilitadas:
        return [], []
    props = {p['id']: p for p in dia.get('propuestas') or []}
    decisions = dia.get('decisiones', {}).get('propuestas') or {}
    existing = {r.get('id') for r in cola}
    result, diary = [], []
    from sala_productor import tira_de, datos_lamina
    from sala_produccion import resolver_tira
    from sala_vigencia import publicada
    for pid, prop in props.items():
        match = re.fullmatch(r'([a-z0-9_-]+)-corte-nube-([a-f0-9]{12})', pid)
        decision = decisions.get(pid)
        signed = firma(decision)
        if not match or match[1] not in habilitadas or not signed or publicada(prop):
            continue
        family = match[1]
        candidates = [r for r in cola if r.get('pieza') == family and r.get('etapa') == 'corte'
                      and r.get('estado') == 'hecho' and evidence(r).get('md5', '')[:12] == match[2]
                      and evidence(r).get('durable') is True
                      and (evidence(r).get('entrega') or {}).get('prop_id') == pid]
        if len(candidates) != 1:
            diary.append('revisión de video: corte durable sin linaje único')
            continue
        old = evidence(candidates[0])
        if prop.get('video') != 'https://drive.google.com/file/d/%s/preview' % old.get('drive_id'):
            continue
        source = props.get(old.get('de'))
        if not source:
            diary.append('revisión de video: fuente retirada o no activa')
            continue
        tira = tira_de(source['id'])
        if not tira:
            continue
        try:
            resolved = resolver_tira(tira, decisions.get(source['id']), source)
        except Exception:
            diary.append('revisión de video: fuente sin aprobación confirmada')
            continue
        expected = [j for j in plan_base if j.get('etapa') == 'corte'
                    and j.get('pieza') == family and evidence(j).get('de') == old['de']
                    and canonical(evidence(j).get('laminas')) == canonical(old.get('laminas_fuente') or old.get('laminas'))]
        if len(expected) != 1:
            diary.append('revisión de video: dependencias o aprobaciones cambiaron')
            continue
        revision = hashlib.sha256(canonical([pid, signed, POLITICA]).encode()).hexdigest()
        correction = {'de': pid, 'firma': signed, 'politica': POLITICA, 'revision': revision}
        by_n = {str(l['n']): l for l in resolved.get('laminas') or []}
        dependencies, jobs = [], []
        for dep in old.get('laminas_fuente') or old['laminas']:
            item = str(dep['item'])
            lam = by_n.get(item)
            if not lam or lam.get('estado') != 'aprobada':
                jobs = []
                break
            version = hashlib.sha256(canonical([dep, revision]).encode()).hexdigest()[:8]
            dependencies.append({'item': item, 'huella': version})
            for stage in ('escena', 'voz'):
                jobs.append({'id': '%s:%s:%s:%s' % (family, stage, item, version),
                             'pieza': family, 'etapa': stage, 'item': item,
                             'estado': 'pendiente', 'prioridad': 8, 'pidio': 'revision-video',
                             'evidencia': {'de': old['de'], 'lamina': item, 'n_real': True,
                                           'correccion': correction, 'nota': decision['nota'],
                                           **datos_lamina(lam)}})
        if not jobs:
            continue
        version = hashlib.sha256(canonical([dependencies, revision]).encode()).hexdigest()[:8]
        jobs.append({'id': '%s:corte:completo:%s' % (family, version), 'pieza': family,
                     'etapa': 'corte', 'item': 'completo', 'estado': 'pendiente',
                     'prioridad': 7, 'pidio': 'revision-video',
                     'evidencia': {'de': old['de'], 'laminas': dependencies, 'laminas_fuente': old.get('laminas_fuente') or old['laminas'], 'correccion': correction}})
        result.extend(j for j in jobs if j['id'] not in existing)
        diary.append('revisión de video: %d dependencias nuevas; política de video real' %
                     sum(j['id'] not in existing for j in jobs))
    return result, diary


def vigente(trabajo, dia, cola, reglas, cat):
    """Sólo las entradas de un plan fresco exacto pueden consumir motores."""
    from sala_productor import planear as plan
    planned, _ = plan(dia, [], reglas, cat, incluir_revisiones=False)
    # La fila ya existe: se reconstruye el plan excluyéndola únicamente por ID.
    jobs, _ = planear(dia, [r for r in cola if r.get('id') != trabajo['id']], reglas, cat, planned)
    found = [j for j in jobs if j['id'] == trabajo['id']]
    if len(found) != 1:
        return False
    expected, actual = evidence(found[0]), evidence(trabajo)
    return all(canonical(actual.get(k)) == canonical(v) for k, v in expected.items())
