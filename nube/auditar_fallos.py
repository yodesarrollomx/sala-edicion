#!/usr/bin/env python3
"""Auditoría de cortes fallidos: lecturas frescas, ningún cambio de COLA ni producción."""
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.parse
import urllib.request

import sala_cliente as sala
import sala_drive as drive
import sala_catalogo as catalogo
import sala_produccion as produccion
import sala_productor as productor
from contenido_reglas import revisar
from plan_agregados import private_config
from snapshots_online import Snapshots, canonical, digest, receipt_matches

ROOT = Path(__file__).resolve().parent.parent
CODIGOS = frozenset({'fuente_no_vigente','veto_editorial','formato_no_video','guion_incompleto',
    'aprobacion_incompleta','fuente_retirada','contenido_vetado','snapshot_sin_acuse',
    'plan_no_coincide','dependencias_incompletas','medio_no_confirmado','ventana_cambio',
    'cola_id_duplicada','lectura_no_confirmada','etapa_no_habilitada','peticiones_abiertas'})


class AuditoriaError(RuntimeError):
    pass


class ReadOnlyGitHub:
    """Limita el token que puede ver borradores a las operaciones lectoras del bootstrap."""
    def __init__(self, delegate):
        self._delegate=delegate

    def request(self,path,body=None,method=None,raw=False):
        if body is not None or method not in (None,'GET'):
            raise AuditoriaError('github_solo_lectura')
        return self._delegate.request(path,method='GET',raw=raw)

    def asset(self,asset_id):
        # GitHub.asset sólo hace GET y valida el destino de la redirección firmada.
        return self._delegate.asset(asset_id)

    def upload(self,*args,**kwargs):
        raise AuditoriaError('github_solo_lectura')


def evidencia(row):
    value = row.get('evidencia') or {}
    if isinstance(value, str):
        try: value = json.loads(value)
        except ValueError: return {}
    return value if isinstance(value, dict) else {}


def vetado(row):
    text = str(evidencia(row).get('error') or '').lower()
    return any(t in text for t in ('ubicación vetada','ubicacion_vetada','ubicacion vetada'))


def firmas_no(decision):
    return any(isinstance(f, dict) and f.get('marca') == 'no'
               for group in decision.get('firmas') or [] if isinstance(group, list) for f in group)


def laminas(value):
    if not isinstance(value, list) or not value:
        return None
    pairs = [(str(l.get('item','')),str(l.get('huella',''))) for l in value if isinstance(l,dict)]
    if len(pairs)!=len(value) or len(set(x[0] for x in pairs))!=len(pairs): return None
    if any(not n.isdigit() or int(n)<1 or not re.fullmatch(r'[a-fA-F0-9]{8,64}',h) for n,h in pairs): return None
    return sorted(pairs,key=lambda x:int(x[0]))


def descriptor(row):
    return tuple(str(row.get(k) or '') for k in ('pieza','etapa','item'))


def descriptor_coherente(row):
    parts=str(row.get('id') or '').split(':')
    return len(parts)==4 and tuple(parts[:3])==descriptor(row)


def evaluar(cola,dia,reglas,cat,*,planner,resolver,tira_reader,media_check,snapshot_check,ventana_estable=True):
    """Función inyectable y sin escrituras; las identificaciones sólo van al informe privado."""
    queue=copy.deepcopy(cola)
    if (not isinstance(queue,list) or any(not isinstance(x,dict) for x in queue)
            or not isinstance(dia,dict) or not isinstance(dia.get('propuestas'),list)
            or not isinstance(dia.get('decisiones'),dict) or not isinstance(reglas,dict)):
        raise AuditoriaError('lectura_no_confirmada')
    selected=[r for r in queue if r.get('estado')=='fallo' and r.get('etapa')=='corte' and not vetado(r)]
    counts=Counter(str(r.get('id')) for r in queue)
    byid={str(r.get('id')):r for r in queue}
    selected_ids={str(r.get('id')) for r in selected}
    proposals={p['id']:p for p in dia['propuestas'] if isinstance(p,dict) and isinstance(p.get('id'),str)}
    prop_counts=Counter(p.get('id') for p in dia['propuestas'] if isinstance(p,dict))
    decisions=dia['decisiones'].get('propuestas') or {}
    # Sólo quitar candidatos en una copia; conservar vetos y otros fallos.
    try:
        planned,_=planner(copy.deepcopy(dia),[r for r in queue if str(r.get('id')) not in selected_ids],reglas,cat)
        planned_by_id={str(x.get('id')):x for x in planned}
        plan_counts=Counter(str(x.get('id')) for x in planned)
    except Exception:
        planned_by_id={};plan_counts={}
    report={'schema':1,'ventana_estable':bool(ventana_estable),'candidatos':[],
            'fallos_totales':sum(r.get('estado')=='fallo' for r in queue),'omitidos_veto':sum(vetado(r) for r in queue)}
    for row in selected:
        rid=str(row.get('id') or ''); ev=evidencia(row); pid=str(ev.get('de') or '')
        result={'id':rid,'etapa':'corte','fuente':pid,'elegible':False,'bloqueos':[],'dependencias':[]}
        def block(code):
            if code not in result['bloqueos']:result['bloqueos'].append(code)
        if not ventana_estable:block('ventana_cambio')
        if counts[rid]!=1:block('cola_id_duplicada')
        if 'corte' not in {x.strip() for x in str(reglas.get('nube_ejecuta_etapas') or '').split(',')}:
            block('etapa_no_habilitada')
        prop=proposals.get(pid); decision=decisions.get(pid)
        if not prop or prop_counts[pid]!=1 or str(prop.get('origen','')).lower().startswith('retirada') or str(prop.get('estado','')).lower().startswith('retirada'):
            block('fuente_no_vigente')
        if not isinstance(decision,dict) or not any(x=='si' for x in decision.get('laminas') or []):
            block('aprobacion_incompleta')
        elif 'no' in (decision.get('laminas') or []) or firmas_no(decision):
            block('aprobacion_incompleta')
        tira=None;nums=[]
        if prop and isinstance(decision,dict):
            try:
                if not snapshot_check(pid):block('snapshot_sin_acuse')
                tira=tira_reader(pid)
                if not isinstance(tira,dict):raise ValueError()
                tira=resolver(tira,decision,prop)
            except Exception:block('lectura_no_confirmada')
        if isinstance(tira,dict):
            if not produccion.es_video(tira):block('formato_no_video')
            guion=tira.get('guion'); frames=tira.get('laminas')
            nums=[str(l.get('n','')) for l in guion if isinstance(l,dict)] if isinstance(guion,list) else []
            present=[str(l.get('n','')) for l in frames if isinstance(l,dict)] if isinstance(frames,list) else []
            if (not nums or len(nums)!=len(guion) or len(set(nums))!=len(nums)
                    or any(not n.isdigit() or int(n)<1 for n in nums) or set(nums)!=set(present)
                    or len(present)!=len(nums)):
                block('guion_incompleto')
            if not isinstance(frames,list) or not frames or any(not isinstance(l,dict) or l.get('estado')!='aprobada' for l in frames):block('aprobacion_incompleta')
            if isinstance(frames,list) and any(isinstance(l,dict) and l.get('reemplazo_modelo') for l in frames):block('fuente_retirada')
            if revisar(tira,reglas):block('contenido_vetado')
        expected=planned_by_id.get(rid)
        old_lams=laminas(ev.get('laminas'))
        if old_lams and set(n for n,_ in old_lams)!=set(nums):block('guion_incompleto')
        if (not expected or plan_counts.get(rid)!=1 or descriptor(row)!=descriptor(expected)
                or not descriptor_coherente(row) or not descriptor_coherente(expected)
                or evidencia(expected).get('de')!=pid or not old_lams
                or laminas(evidencia(expected).get('laminas'))!=old_lams):
            block('plan_no_coincide')
        # No descargar ni generar medios si antes falló una compuerta.
        if not result['bloqueos']:
            dependencies=[]
            for item,huella in old_lams:
                for stage in ('escena','voz'):
                    depid=':'.join((str(row.get('pieza') or ''),stage,item,huella))
                    dep=byid.get(depid)
                    detail={'id':depid,'estado':dep.get('estado') if dep else None,'medio_confirmado':False}
                    dependencies.append((dep,detail))
                    if (not dep or counts[depid]!=1 or dep.get('estado')!='hecho'
                            or descriptor(dep)!=(str(row.get('pieza') or ''),stage,item)
                            or not descriptor_coherente(dep)):
                        block('dependencias_incompletas')
            if not result['bloqueos']:
                for dep,detail in dependencies:
                    try:
                        proof=media_check(dep)
                        detail['medio_confirmado']=isinstance(proof,dict) and proof.get('ok') is True
                    except Exception:detail['medio_confirmado']=False
                    if not detail['medio_confirmado']:block('medio_no_confirmado')
            result['dependencias']=[detail for _,detail in dependencies]
        result['elegible']=not result['bloqueos']
        report['candidatos'].append(result)
    return report


def resumen_publico(report):
    rows=report.get('candidatos') or []
    reasons=Counter(code for r in rows for code in set(r.get('bloqueos') or []) if code in CODIGOS)
    eligible=sum(r.get('elegible') is True for r in rows)
    return {'ok':True,'candidatos':len(rows),'elegibles':eligible,'bloqueados':len(rows)-eligible,
            'motivos':dict(sorted(reasons.items())),'escrituras_negocio':0,'produccion_ejecutada':0}


def verificar_medio(job):
    ev=evidencia(job); fid=str(ev.get('drive_id') or ''); expected=str(ev.get('md5') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{10,128}',fid) or not re.fullmatch(r'[a-f0-9]{32}',expected):return {'ok':False}
    meta=drive._peticion('GET',drive.API+'/files/'+fid,params={'fields':'id,size,md5Checksum,trashed'}).json()
    if (meta.get('id')!=fid or meta.get('trashed') or meta.get('md5Checksum')!=expected
            or not 0<int(meta.get('size',0))<=128*1024*1024):return {'ok':False}
    with tempfile.TemporaryDirectory() as tmp:
        raw=drive.bajar(fid,Path(tmp)/'medio').read_bytes()
    return {'ok':len(raw)==int(meta['size']) and hashlib.md5(raw).hexdigest()==expected}


def fresh(resource,**params):
    if resource not in {'dia','cola','reglas','catalogo'}:raise AuditoriaError('lectura_no_confirmada')
    return sala.get(resource,**{**params,'fresco':'1'})


def fuentes():
    rules=fresh('reglas'); queue=fresh('cola'); rawcat=fresh('catalogo')
    if (not isinstance(rules.get('reglas'),dict) or not isinstance(queue.get('cola'),list)
            or not isinstance(rawcat.get('catalogo'),dict)):raise AuditoriaError('lectura_no_confirmada')
    day=produccion.cargar(getter=fresh)
    return rules['reglas'],queue['cola'],day,catalogo.normalizar(rawcat['catalogo'])


def digest_lecturas(values):return digest(canonical(values))


def confirmar_snapshot(s):
    state=s.state()
    parent=state.get('parent_id')
    if type(parent) is not int or parent<=0:raise AuditoriaError('snapshot_sin_acuse')
    release=s.api.request('releases/'+str(parent))
    try:body=json.loads(release.get('body') or '')
    except (ValueError,TypeError):raise AuditoriaError('snapshot_sin_acuse') from None
    s.validate_release(release,body)
    code=s.head();run=str(body.get('published_run',''))
    if (release.get('id')!=parent or body.get('state')!='published' or not run.isdecimal()
            or body.get('published_code_sha')!=code or body.get('data_sha')!=state.get('data_sha')):
        raise AuditoriaError('snapshot_sin_acuse')
    site=s.api.request('pages').get('html_url','')
    parsed=urllib.parse.urlsplit(site)
    if parsed.scheme!='https' or parsed.username or parsed.password:raise AuditoriaError('snapshot_sin_acuse')
    with urllib.request.urlopen(urllib.request.Request(site.rstrip('/')+'/version-online.json',
                               headers={'Cache-Control':'no-cache'}),timeout=30) as response:
        receipt=json.loads(response.read(32768))
    if not receipt_matches(receipt,code_sha=code,data_sha=state['data_sha'],
            snapshot_id=state['parent_id'],run_id=run):raise AuditoriaError('snapshot_sin_acuse')
    return state,receipt


def guardar_privado(report,parent):
    with tempfile.TemporaryDirectory() as tmp:
        name='SALA-AUDITORIA-FALLOS-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ.get('GITHUB_RUN_ATTEMPT','1')+'.json'
        raw=canonical(report)+b'\n'; path=Path(tmp)/name;path.write_bytes(raw)
        fid=drive.subir(path,parent,name)
        if drive.bajar(fid,Path(tmp)/'verificado').read_bytes()!=raw:raise AuditoriaError('acuse_privado_no_confirmado')


def main():
    phase='iniciar';post_anterior=sala.post
    try:
        sala.enmascarar_en_actions()
        # Defensa adicional: ningún helper importado puede escribir al GAS.
        def prohibida(*args,**kwargs):raise AuditoriaError('escritura_gas_prohibida')
        sala.post=prohibida
        phase='snapshot'; s=Snapshots(ROOT,env={**os.environ,'GITHUB_OUTPUT':''})
        s.api=ReadOnlyGitHub(s.api)
        s.bootstrap(lock=False)
        state,receipt=confirmar_snapshot(s)
        baseline=state['baseline']
        def snapshot_check(pid):
            if not produccion.PID.fullmatch(pid):return False
            rel='datos/tiras/'+pid+'.json';path=ROOT/rel
            return path.is_file() and not path.is_symlink() and baseline.get(rel)==digest(path.read_bytes())
        phase='fuentes'; before=fuentes()
        phase='evaluar'
        report=evaluar(before[1],before[2],before[0],before[3],planner=productor.planear,
            resolver=produccion.resolver_tira,tira_reader=produccion.leer_tira,
            media_check=verificar_medio,snapshot_check=snapshot_check)
        if produccion.peticiones_abiertas():
            for row in report['candidatos']:
                row['elegible']=False;row['bloqueos'].append('peticiones_abiertas')
        phase='conciliar'; after=fuentes();latest,_=s.latest()
        stable=(not any(r.get('estado')=='corriendo' for r in before[1]+after[1])
                and digest_lecturas(before)==digest_lecturas(after) and s.main()==s.head()
                and (latest['id'] if latest else 0)==state['parent_id'] and s.fingerprint()==baseline)
        report['ventana_estable']=stable
        if not stable:
            for row in report['candidatos']:
                row['elegible']=False
                if 'ventana_cambio' not in row['bloqueos']:row['bloqueos'].append('ventana_cambio')
        report.update(fecha=datetime.now(timezone.utc).isoformat(),snapshot=receipt,
                      lecturas_sha256=digest_lecturas(before),modo='solo_auditoria_sin_reencolar')
        phase='acuse';_,parent=private_config();guardar_privado(report,parent)
        print('SALA_AUDITORIA_FALLOS '+json.dumps(resumen_publico(report),sort_keys=True))
        return 0
    except Exception:
        print('SALA_AUDITORIA_FALLOS '+json.dumps({'ok':False,'error':'auditoria_sin_confirmar','fase':phase,
              'escrituras_negocio':0,'produccion_ejecutada':0},sort_keys=True))
        return 2
    finally:
        sala.post=post_anterior


if __name__=='__main__':raise SystemExit(main())
