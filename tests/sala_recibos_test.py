import copy
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'nube'))
from motores import cerebro, imagen, imagen_hidream as hi
from motores._comun import MotorError
from sala_recibos import Recibos, ejecutar, pack, unpack, KIND
from snapshots_online import OnlineError, GitHub, Snapshots, digest, canonical

ENV = {'GITHUB_REPOSITORY': 'yodesarrollomx/sala-edicion', 'GH_TOKEN': 'synthetic',
       'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'a'*40}
RID = 'b'*64
SOURCE = {'dice': 'Un plan para decidir', 'nota': 'Acerca el plano'}
PLAN = {'d': {'texto': 'Un plan para decidir', 'receta': 'Architects compare a scale model'},
        'texto': 'Un plan para decidir', 'cerebro': 'synthetic', 'avisos': [], 'prompt_imagen': 'synthetic'}
PHOTO = b'synthetic-photo-no-provider'

class API:
    def __init__(self):
        self.releases = []
        self.assets = {}
        self.lost_create = False
        self.lost_upload = False
        self.uploads = 0
    def request(self, path, body=None):
        if body:
            r = dict(body, id=len(self.releases)+1, assets=[], upload_url='synthetic')
            self.releases.append(r)
            if self.lost_create:
                self.lost_create = False
                raise OnlineError('ACK perdido')
            return copy.deepcopy(r)
        if path.startswith('releases?'):
            return copy.deepcopy(self.releases)
        return copy.deepcopy(next(r for r in self.releases if r['id'] == int(path.split('/')[-1])))
    def upload(self, release, data, name='snapshot.zip'):
        self.uploads += 1
        aid = len(self.assets)+1
        self.assets[aid] = data
        self.releases[release['id']-1]['assets'].append({'name':name,'id':aid})
        if self.lost_upload:
            self.lost_upload = False
            raise OnlineError('ACK perdido')
        return {'id':aid}
    def asset(self, aid):
        return self.assets[aid]

class Repairs(unittest.TestCase):
    def test_negative_or_visual_notes_preserve_exact_caption_both_paths(self):
        for note in ['No cambies el texto; acerca el plano.', 'Sin modificar el texto, más luz',
                     'Conserva el texto; cambia el plano', 'El texto no se cambia',
                     'No quiero que cambies el texto', 'La imagen no cuadra con el texto']:
            with self.subTest(note=note), patch.object(cerebro, '_gemini', return_value=json.dumps({'texto':'Texto alterado','scene':'Architects compare models','receta':'Architects compare models'})):
                self.assertEqual(cerebro.fotografia_guion('Original intacto','Plano',note,'',{})[0]['texto'],'Original intacto')
                self.assertEqual(cerebro.lamina('P','','Original intacto','Plano',note,[],{})[0]['texto'],'Original intacto')
    def test_visual_correction_never_disappears_when_translator_fails(self):
        with patch.object(cerebro,'_gemini',side_effect=MotorError('offline')):
            for note in ['Acerca el plano','Retira la mesa y muestra la maqueta']:
                with self.subTest(note=note), self.assertRaisesRegex(MotorError,'Corrección visual pendiente'):
                    cerebro.fotografia_guion('Texto','Tres personas con planos',note,'',{})
            self.assertEqual(cerebro.fotografia_guion('Texto','Tres personas con planos','','',{})[1],'guion-visual')
    def test_new_caption_limit_both_paths_and_historical_not_rewritten(self):
        long=' '.join(['palabra']*20)
        response=json.dumps({'texto':long,'scene':'Architects compare models','receta':'Architects compare models'})
        with patch.object(cerebro,'_gemini',return_value=response),patch.object(cerebro,'_openai',return_value=response):
            with self.assertRaises(MotorError):cerebro.lamina('P','','Original','Plano','Cambia el texto',[],{})
            with self.assertRaises(MotorError):cerebro.fotografia_guion('Original','Plano','Cambia el texto','',{})
            self.assertEqual(cerebro.lamina('P','',long,'Plano','Más luz',[],{})[0]['texto'],long)
    def test_receipt_only_preserves_original_recipe_hash(self):
        with tempfile.TemporaryDirectory() as td, patch.object(hi,'RAIZ',pathlib.Path(td)),patch.object(hi,'validar',return_value=(PHOTO,(600,600))),patch.object(hi,'_client',side_effect=AssertionError('no provider')):
            folder=pathlib.Path(td)/'laminas/recibos-hidream';folder.mkdir(parents=True)
            (folder/(RID+'.png')).write_bytes(PHOTO)
            original=hashlib.sha256(b'original').hexdigest()
            (folder/(RID+'.json')).write_text(json.dumps({'modelo':hi.MODELO,'receta_sha256':original,'foto_sha256':hashlib.sha256(PHOTO).hexdigest()}))
            rules={'_imagen_request_id':RID,'_imagen_solo_recibo':True}
            hi.generar('consulta distinta',rules)
            self.assertEqual(rules['_receta_proveedor_sha256'],original)
    def test_positive_edit_allowed(self):
        for note in ['Cambia el texto','Que diga algo concreto','Reescribe el mensaje']:
            self.assertTrue(cerebro.edita_texto(note))

class Persistence(unittest.TestCase):
    def setUp(self): self.api=API()
    def store(self, **env): return Recibos(RID,api=self.api,env=dict(ENV,**env))
    def run_image(self, store=None, source=SOURCE, rules=None, prepare=None):
        return ejecutar(RID,source,prepare or (lambda:copy.deepcopy(PLAN)),rules or {},store=store or self.store())
    def test_completed_result_survives_new_client_without_generation(self):
        with patch.object(imagen,'generar',return_value=(PHOTO,'png','hidream_demo',[])) as generate:
            first=self.run_image()
        with patch.object(imagen,'generar',side_effect=AssertionError('must not generate')):
            second=self.run_image(self.store(GITHUB_RUN_ID='124'),prepare=lambda: self.fail('must not think'))
        self.assertEqual(first,second);self.assertEqual(generate.call_count,1)
    def test_plan_saved_before_dispatch_and_only_safe_configuration(self):
        def gen(*args):
            self.assertIsNotNone(self.store().get('plan.zip'))
            self.assertTrue(self.store().pending(digest(canonical(self.store().get('plan.zip')[0]))))
            return PHOTO,'png','hidream_demo',[]
        with patch.object(imagen,'generar',side_effect=gen):
            plan,_,_=self.run_image(rules={'GEMINI_API_KEY':'never-store-this','imagen_motores':'hidream_demo'})
        self.assertNotIn('never-store-this',json.dumps(plan))
        self.assertEqual(plan['configuracion']['imagen_motores'],'hidream_demo')
    def test_default_engine_stays_frozen_when_configuration_changes(self):
        with patch.object(imagen,'generar',side_effect=MotorError('timeout')):
            with self.assertRaises(MotorError):self.run_image()
        def lookup(prompt,rules):
            self.assertEqual(rules['imagen_motores'],'hidream_demo')
            self.assertEqual(rules['_imagen_prompt_confirmado'],PLAN['prompt_imagen'])
            raise imagen.ReciboNoConfirmado('missing')
        with patch.object(imagen,'generar',side_effect=lookup):
            with self.assertRaises(imagen.ReciboNoConfirmado):
                self.run_image(self.store(GITHUB_RUN_ID='124'),rules={'imagen_motores':'openai_broker'})
    def test_corrupt_quota_refusal_cannot_authorize_another_send(self):
        with patch.object(imagen,'generar',side_effect=imagen.CupoImagen('429')):
            with self.assertRaises(imagen.CupoImagen):self.run_image()
        self.api.assets[max(self.api.assets)] = b'corrupt'
        with patch.object(imagen,'generar',side_effect=AssertionError('no generation')):
            with self.assertRaises(MotorError):self.run_image(self.store(GITHUB_RUN_ID='124'))
    def test_changed_input_requires_new_identity(self):
        with patch.object(imagen,'generar',return_value=(PHOTO,'png','hidream_demo',[])):
            self.run_image()
        with self.assertRaisesRegex(MotorError,'entradas cambiaron'):
            self.run_image(source={'nota':'Otra'})
    def test_uncertain_send_only_attempts_receipt_lookup(self):
        with patch.object(imagen,'generar',side_effect=MotorError('timeout')):
            with self.assertRaises(MotorError):self.run_image()
        def lookup(prompt,rules):
            self.assertTrue(rules['_imagen_solo_recibo'])
            raise imagen.ReciboNoConfirmado('missing')
        with patch.object(imagen,'generar',side_effect=lookup) as gen:
            with self.assertRaisesRegex(imagen.ReciboNoConfirmado,'conciliación'):
                self.run_image(self.store(GITHUB_RUN_ID='124'))
        self.assertEqual(gen.call_count,1)
    def test_uncertain_send_can_recover_provider_receipt(self):
        with patch.object(imagen,'generar',side_effect=MotorError('timeout')):
            with self.assertRaises(MotorError):self.run_image()
        def lookup(prompt,rules):
            self.assertTrue(rules['_imagen_solo_recibo'])
            rules['_receta_proveedor_sha256']='c'*64
            return PHOTO,'png','hidream_demo',[]
        with patch.object(imagen,'generar',side_effect=lookup):
            _,_,meta=self.run_image(self.store(GITHUB_RUN_ID='124'))
        self.assertEqual(meta['receta_sha256'],'c'*64)
    def test_quota_refusal_allows_next_run_but_not_same_attempt(self):
        with patch.object(imagen,'generar',side_effect=imagen.CupoImagen('429')) as gen:
            for _ in range(2):
                with self.assertRaises(imagen.CupoImagen):self.run_image()
        self.assertEqual(gen.call_count,1)
        with patch.object(imagen,'generar',return_value=(PHOTO,'png','hidream_demo',[])) as gen:
            self.run_image(self.store(GITHUB_RUN_ID='124'))
        self.assertFalse(gen.call_args.args[1]['_imagen_solo_recibo'])
    def test_lost_create_and_upload_ack_reconciled_without_duplicate(self):
        self.api.lost_create=True;self.api.lost_upload=True
        self.store().put('plan.zip',PLAN)
        self.assertEqual(len(self.api.releases),1);self.assertEqual(self.api.uploads,1)
        self.store().put('plan.zip',PLAN)
        self.assertEqual(self.api.uploads,1)
    def test_existing_conflicting_plan_not_overwritten(self):
        self.store().put('plan.zip',PLAN)
        with self.assertRaises(MotorError):self.store().put('plan.zip',{'other':1})
        self.assertEqual(self.api.uploads,1)
    def test_missing_upload_ack_without_remote_file_does_not_succeed(self):
        with patch.object(self.api,'upload',side_effect=OnlineError('offline')):
            with self.assertRaises(MotorError):self.store().put('plan.zip',PLAN)
    def test_published_release_is_rejected(self):
        self.store().put('plan.zip',PLAN);self.api.releases[0]['draft']=False
        with self.assertRaises(MotorError):self.store().get('plan.zip')
    def test_corrupt_result_is_not_reused(self):
        with patch.object(imagen,'generar',return_value=(PHOTO,'png','hidream_demo',[])):
            self.run_image()
        self.api.assets[max(self.api.assets)]=b'corrupt'
        with patch.object(imagen,'generar',side_effect=AssertionError('no generation')):
            with self.assertRaises(MotorError):self.run_image()
    def test_private_upload_requires_exclusive_draft(self):
        with self.assertRaises(OnlineError):
            GitHub('org/repo','synthetic').upload({'draft':False},b'zip',name='plan.zip')
    def test_snapshot_latest_ignores_private_receipts(self):
        # Same releases endpoint, different contract. No private asset is read.
        self.store().put('plan.zip',PLAN)
        with tempfile.TemporaryDirectory() as td:
            snap=Snapshots(root=td,env=ENV,api=self.api)
            self.assertEqual(snap.latest(),(None,None))
    def test_invalid_photo_hash_rejected(self):
        import zipfile
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('registro.json',json.dumps({'schema':1,'record':{},'foto_sha256':'0'*64}))
            z.writestr('foto.bin',PHOTO)
        with self.assertRaises(MotorError):unpack(out.getvalue())

if __name__=='__main__':unittest.main()
