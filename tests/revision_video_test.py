"""Regresiones con corte y decisiones sintéticos; no usan red ni negocio real."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nube'))
import sala_productor as productor
import sala_produccion as produccion

class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.source={'id':'prueba-nube-2026-10-20-base','titulo':'Prueba','tipo':'laminas','laminas':['a.png']}
        self.cut={'id':'prueba-corte-nube-'+'a'*12,'titulo':'Prueba · corte','tipo':'eje','laminas':[], 'video':'https://drive.google.com/file/d/syntheticVideo123/preview'}
        self.decision={'laminas':['no'],'notas':[''],'nota':'Editor: Voz natural y video real', 'firmas':[[{'rol':'editor','marca':'no','quien':'Editor','nota':'','guardado':'2026-10-20T21:00:00.000Z'}]], 'firmas_nota':[{'rol':'editor','quien':'Editor','nota':'Voz natural y video real','guardado':'2026-10-20T21:00:00.000Z'}]}
        self.day={'fecha':'2026-10-20','propuestas':[self.source,self.cut],'decisiones':{'propuestas':{self.source['id']:{'laminas':['si'],'notas':['']}, self.cut['id']:self.decision}}}
        self.old={'id':'prueba:corte:completo:12345678','pieza':'prueba','item':'completo','etapa':'corte','estado':'hecho','evidencia':{'de':self.source['id'],'laminas':[{'item':'1','huella':'12345678'}],'durable':True,'md5':'a'*32,'drive_id':'syntheticVideo123','entrega':{'prop_id':self.cut['id'],'estado':'montada'}}}
        self.tira={'pieza':'Prueba','pieza_slug':'prueba','mapa':{'1':1},'guion':[{'n':1,'dice':'Prueba breve'}],'laminas':[{'n':1,'src':'a.png','dice':'Prueba breve','ve':'Una escena','estado':'aprobada'}]}
        self.rules={'video_revision_piezas':'prueba'}
        self.patches=[patch.object(productor,'tira_de',side_effect=lambda pid:self.tira if pid==self.source['id'] else None),patch.object(productor,'huella_insumo',return_value=('12345678','catalogo')),patch('sala_vigencia.registro_publicadas',return_value=set())]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def plan(self,queue=None):
        return productor.planear(self.day,queue if queue is not None else [self.old],self.rules,{})[0]

    def test_cut_rejection_creates_new_version_without_changing_visual_decisions(self):
        before=copy.deepcopy(self.day)
        jobs=self.plan()
        revised=[j for j in jobs if j.get('evidencia',{}).get('correccion')]
        self.assertEqual({'escena','voz','corte'},{j['etapa'] for j in revised})
        self.assertEqual(len(revised),3)
        self.assertNotIn(self.old['id'],[j['id'] for j in revised])
        self.assertTrue(all(j['evidencia']['correccion']['de']==self.cut['id'] for j in revised))
        self.assertEqual(before,self.day)

    def test_same_rejection_is_idempotent_and_note_change_versions_again(self):
        jobs=self.plan();self.assertTrue(jobs)
        self.assertEqual([],self.plan([self.old]+jobs))
        self.decision['nota']='Editor: Otro ritmo'
        self.decision['firmas_nota'][0]['nota']='Otro ritmo'
        again=self.plan([self.old]+jobs)
        self.assertTrue(again)
        self.assertFalse(set(j['id'] for j in jobs)&set(j['id'] for j in again))

    def test_unconfirmed_rejection_or_missing_source_never_creates_revision(self):
        for key in ('firmas','firmas_nota'):
            original=self.decision[key];self.decision[key]=[]
            self.assertFalse(any(j['evidencia'].get('correccion') for j in self.plan()))
            self.decision[key]=original
        self.day['propuestas'].remove(self.source)
        self.assertFalse(any(j['evidencia'].get('correccion') for j in self.plan()))

    def test_changed_visual_source_does_not_reuse_old_cut_dependencies(self):
        with patch.object(productor,'huella_insumo',return_value=('87654321','catalogo')):
            self.assertFalse(any(j['evidencia'].get('correccion') for j in self.plan()))

    def test_non_durable_cut_cannot_open_revision(self):
        self.old['evidencia']['durable']=False
        self.assertFalse(any(j['evidencia'].get('correccion') for j in self.plan()))


class EnginePolicyTests(unittest.TestCase):
    def test_generative_failure_never_enters_withdrawn_camera_or_parallax(self):
        import sala_ejecutor as executor
        from motores._comun import MotorError
        job={'pieza':'prueba','item':'1','etapa':'escena','evidencia':{'dice':'Texto sintético','correccion':{'de':'corte-sintetico'}}}
        with patch.object(executor.motores,'elegir_motor',return_value=({'motor':'wan_hf'},'ok')),\
             patch('motores.escena_wan_hf.producir',side_effect=MotorError('cuota',intermitente=True)),\
             patch('motores.escena_camara.producir',side_effect=AssertionError('cámara prohibida')),\
             patch('motores.escena_parallax.producir_con_evidencia',side_effect=AssertionError('parallax prohibido')):
            state,ev=executor.ejecutar_uno(job,{},[],{},None,[])
        self.assertEqual('pendiente',state)
        self.assertIn('generativo',ev['error'])

    def test_gemini_uses_its_own_voices_and_preserves_turn_order(self):
        import tempfile
        import wave
        from motores import voz_gemini as voice
        pcm=b'\x01\x00'*2400
        turns=[('narrador','Un texto'),('vecino','Otra respuesta')]
        with tempfile.TemporaryDirectory() as tmp,\
             patch.object(voice.guion,'cargar',return_value={'escenas':[]}),\
             patch.object(voice.guion,'desde_lamina',return_value={}),\
             patch.object(voice.guion,'partes_de',return_value=turns),\
             patch.object(voice,'_pedir',return_value={}) as ask,\
             patch.object(voice,'_decodificar_pcm',return_value=(pcm,24000)):
            output=voice.producir({'pieza':'prueba','item':'1'},{'voz_narrador':'em_alex','voz_vecino':'em_santa'},{},tmp)
            with wave.open(str(output),'rb') as stream:self.assertEqual(4800,stream.getnframes())
        self.assertEqual(['Aoede','Puck'],[call.args[1] for call in ask.call_args_list])
        self.assertIn('Un texto',ask.call_args_list[0].args[0])
        self.assertIn('Otra respuesta',ask.call_args_list[1].args[0])


if __name__=='__main__':unittest.main()
