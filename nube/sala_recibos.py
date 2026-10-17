"""Planes y resultados privados de Mesa/Arranque, fuera del snapshot de Pages.

Un draft por identidad de toma; activos inmutables, relectura después de cada
escritura y conciliación de envíos inciertos antes de otra llamada al motor.
No guarda credenciales, no convierte drafts en releases públicos.
"""
import hashlib
import io
import json
import os
import re
import zipfile

from motores._comun import MotorError
from snapshots_online import GitHub, OnlineError, canonical, digest

KIND = 'yod-sala-ejecucion-privada'
MAX_BYTES = 26 * 1024 * 1024
DEFAULTS = {'imagen_motores': 'hidream_demo', 'imagen_gemini_modelo': 'gemini-2.5-flash-image',
            'cerebro_modelo': 'gemini-flash-lite-latest', 'cerebro_respaldo_modelo': 'gpt-4o-mini',
            'cerebro_pago_tope_dia': '30', 'mesa_tomas_por_lamina': '2', 'mesa_tope_laminas': '8'}
CONFIG = ('imagen_motores', 'imagen_gemini_modelo', 'cerebro_modelo',
          'cerebro_respaldo_modelo', 'cerebro_pago_tope_dia',
          'mesa_tomas_por_lamina', 'mesa_tope_laminas')


def pack(record, photo=None):
    body = {'schema': 1, 'record': record, 'foto_sha256': digest(photo) if photo is not None else None}
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in [('registro.json', canonical(body))] + ([('foto.bin', photo)] if photo is not None else []):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    return out.getvalue()


def unpack(data):
    try:
        if len(data) > MAX_BYTES:
            raise ValueError()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            if names not in (['registro.json'], ['registro.json', 'foto.bin']):
                raise ValueError()
            if sum(x.file_size for x in z.infolist()) > MAX_BYTES:
                raise ValueError()
            body = json.loads(z.read('registro.json'))
            photo = z.read('foto.bin') if 'foto.bin' in names else None
        if (body.get('schema') != 1 or not isinstance(body.get('record'), dict)
                or body.get('foto_sha256') != (digest(photo) if photo is not None else None)):
            raise ValueError()
        return body['record'], photo
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError):
        raise MotorError('Recibo privado inválido; requiere conciliación') from None


class Recibos:
    def __init__(self, rid, api=None, env=None):
        self.env = os.environ if env is None else env
        if not re.fullmatch(r'[a-f0-9]{64}', rid):
            raise MotorError('Identidad de toma inválida')
        self.rid = rid
        self.tag = 'sala-ejecucion-' + rid
        repo = self.env.get('GITHUB_REPOSITORY', '')
        token = self.env.get('GH_TOKEN') or self.env.get('GITHUB_TOKEN')
        run, attempt = self.env.get('GITHUB_RUN_ID', ''), self.env.get('GITHUB_RUN_ATTEMPT', '')
        if not (repo == 'yodesarrollomx/sala-edicion' and token and run.isdecimal() and attempt.isdecimal()):
            raise MotorError('Falta identidad del workflow para conservar recibos privados')
        self.owner = run + '-' + attempt
        self.api = api or GitHub(repo, token)
        self.release = None

    def validate(self, r):
        try:
            body = json.loads(r['body'])
            if not (r.get('draft') is True and r['tag_name'] == self.tag
                    and body == {'kind': KIND, 'schema': 1, 'request_id': self.rid}):
                raise ValueError()
        except (KeyError, ValueError, TypeError):
            raise MotorError('Destino de recibo privado no coincide') from None
        self.release = r
        return r

    def find(self):
        if self.release:
            return self.validate(self.api.request('releases/' + str(self.release['id'])))
        # El endpoint por tag sólo garantiza releases publicados; enumerar drafts autenticados.
        for page in range(1, 101):
            rows = self.api.request('releases?per_page=100&page=' + str(page))
            matches = [r for r in rows if r.get('tag_name') == self.tag]
            if len(matches) > 1:
                raise MotorError('Identidad privada duplicada; requiere conciliación')
            if matches:
                return self.validate(matches[0])
            if len(rows) < 100:
                return None
        raise MotorError('Índice de recibos incompleto; no se asume ausencia')

    def ensure(self):
        found = self.find()
        if found:
            return found
        body = {'tag_name': self.tag, 'name': self.tag, 'draft': True,
                'body': json.dumps({'kind': KIND, 'schema': 1, 'request_id': self.rid}),
                'target_commitish': self.env.get('GITHUB_SHA') or 'main'}
        try:
            self.validate(self.api.request('releases', body))
        except OnlineError:
            if not self.find():
                raise MotorError('Creación del recibo incierta; no se repite') from None
        return self.find()

    def get(self, name):
        r = self.find()
        assets = [a for a in (r or {}).get('assets', []) if a.get('name') == name]
        if len(assets) > 1:
            raise MotorError('Activo privado duplicado')
        if not assets:
            return None
        return unpack(self.api.asset(assets[0]['id']))

    def put(self, name, record, photo=None):
        expected = pack(record, photo)
        existing = self.get(name)
        if existing is None:
            r = self.ensure()
            try:
                self.api.upload(r, expected, name=name)
            except OnlineError:
                pass  # Releer; nunca reenviar una escritura ambigua.
            existing = self.get(name)
        if existing is None or pack(*existing) != expected:
            raise MotorError('Escritura privada sin confirmar o en conflicto; requiere conciliación')
        return existing

    def pending(self, plan_sha):
        names = {a['name'] for a in (self.find() or {}).get('assets', [])}
        pending = False
        for name in sorted(names):
            if not name.startswith('envio-'):
                continue
            sent = self.get(name)
            if not sent or sent[0] != {'plan_sha256': plan_sha, 'estado': 'enviado'}:
                raise MotorError('Marcador de envío sin confirmar')
            refused = self.get(name.replace('envio-', 'rechazo-', 1))
            if refused is None:
                pending = True
            elif not negativa_confirmada(refused[0], plan_sha):
                raise MotorError('Negativa de cuota sin confirmar; no repetir')
        return pending


def negativa_confirmada(record, plan_sha):
    if record == {'estado': 'cupo_sin_imagen', 'plan_sha256': plan_sha}:
        return True
    return any(record == {'estado': 'rechazo_sin_imagen', 'plan_sha256': plan_sha,
                           'motivo': motivo}
               for motivo in ('tarea_fallida', 'tarea_cancelada', 'no_enviado'))


def ejecutar(rid, source, preparar, reglas, solo_recibo=False, store=None):
    """Devuelve plan y bytes confirmados. No interpreta decisiones editoriales."""
    from motores import imagen
    from motores.politica_imagen import vetada
    store = store or Recibos(rid)
    source_sha = digest(canonical(source))
    try:
        prior = store.get('plan.zip')
        if prior:
            plan = prior[0]
            if plan.get('source_sha256') != source_sha:
                raise MotorError('Las entradas cambiaron: requiere una nueva versión de la toma')
        else:
            if solo_recibo:
                raise imagen.ReciboNoConfirmado('Sin plan privado; sólo se permite conciliar el recibo histórico', intermitente=True)
            plan = preparar()
            plan.update({'schema': 1, 'source_sha256': source_sha, 'entradas': source,
                         'configuracion': {k: reglas.get(k) or DEFAULTS[k] for k in CONFIG},
                         'run_id': store.env.get('GITHUB_RUN_ID'),
                         'run_attempt': store.env.get('GITHUB_RUN_ATTEMPT'),
                         'code_sha': store.env.get('GITHUB_SHA')})
            store.put('plan.zip', plan)
        from contenido_reglas import exigir
        exigir(plan['d'], reglas, 'plan recuperado')
        exigir({'texto': plan['texto']}, reglas, 'texto recuperado')
        effective = dict(reglas, **plan['configuracion'])
        effective['_imagen_request_id'] = rid
        effective['_imagen_prompt_confirmado'] = plan.get('prompt_imagen') or imagen.preparar_receta(plan['d']['receta'], effective)
        result = store.get('resultado.zip')
        if result:
            meta, photo = result
            if (meta.get('plan_sha256') != digest(canonical(plan)) or not photo
                    or vetada({'motor': meta.get('motor')})):
                raise MotorError('Resultado privado incompatible con el plan o con el veto vigente')
            return plan, photo, meta
        pending = store.pending(digest(canonical(plan)))
        effective['_imagen_solo_recibo'] = solo_recibo or pending
        if not effective['_imagen_solo_recibo']:
            actuales = {m.strip() for m in str(reglas.get('imagen_motores') or 'hidream_demo').split(',')}
            previstos = {m.strip() for m in str(effective['imagen_motores']).split(',')}
            if not previstos.issubset(actuales):
                raise MotorError('Configuración de motores cambió; requiere nueva versión antes de generar')
            rechazo_actual = store.get('rechazo-' + store.owner + '.zip')
            if rechazo_actual and rechazo_actual[0].get('estado') == 'rechazo_sin_imagen':
                raise imagen.RechazoImagen(rechazo_actual[0]['motivo'])
            if rechazo_actual:
                raise imagen.CupoImagen('Cuota rechazada en este intento; esperar otra ejecución', intermitente=True)
            store.put('envio-' + store.owner + '.zip', {'plan_sha256': digest(canonical(plan)), 'estado': 'enviado'})
        try:
            photo, ext, motor, avisos = imagen.generar(plan['d']['receta'], effective)
        except imagen.RechazoImagen as e:
            if not effective['_imagen_solo_recibo'] and str(effective.get('imagen_motores') or 'hidream_demo').strip() in ('hidream_demo', 'hidream_o1'):
                store.put('rechazo-' + store.owner + '.zip',
                          {'estado': 'rechazo_sin_imagen', 'motivo': e.motivo,
                           'plan_sha256': digest(canonical(plan))})
            raise
        except imagen.CupoImagen:
            # Sólo el adaptador HiDream confirma la negativa explícita sin pago/fallback.
            if not effective['_imagen_solo_recibo'] and str(effective.get('imagen_motores') or 'hidream_demo').strip() == 'hidream_demo':
                store.put('rechazo-' + store.owner + '.zip', {'estado': 'cupo_sin_imagen', 'plan_sha256': digest(canonical(plan))})
            raise
        except imagen.ReciboNoConfirmado:
            raise imagen.ReciboNoConfirmado('Envío anterior sin resultado confirmado; pendiente de conciliación', intermitente=True) from None
        meta = {'ext': ext, 'motor': motor, 'modelo': imagen.modelo_de(motor, effective),
                'plan_sha256': digest(canonical(plan)),
                'receta_sha256': effective.get('_receta_proveedor_sha256') or digest(imagen.preparar_receta(plan['d']['receta'], effective).encode()),
                'recibo_imagen': effective.get('_imagen_recibo_id'),
                'parametros_confirmados': effective.get('_imagen_parametros', {}), 'avisos': avisos}
        store.put('resultado.zip', meta, photo)
        return plan, photo, meta
    except OnlineError:
        raise MotorError('Almacén privado no confirmado; la toma queda pendiente', intermitente=True) from None
