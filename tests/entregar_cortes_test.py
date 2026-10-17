import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nube'))
import entregar_cortes as m

class EntregaTests(unittest.TestCase):
    def setUp(self):
        self.ev={'de':'sintetica-v1','durable':True,'md5':'a'*32,'drive_id':'abc123def456','duracion_s':48,
                 'laminas':[{'item':'1','huella':'12345678'}]}
        self.row={'id':'sintetica:corte:completo:12345678','pieza':'sintetica','etapa':'corte',
                  'item':'completo','estado':'hecho','evidencia':copy.deepcopy(self.ev)}
        self.plan=[copy.deepcopy(self.row)]
        self.prop=m.preparar(self.row,self.plan,'Pieza sintética')
        self.day={'propuestas':[],'decisiones':{'propuestas':{}}}
    def test_independent_review_has_no_image_votes_or_retirement_family(self):
        self.assertEqual(self.prop['laminas'],[])
        self.assertEqual(self.prop['tipo'],'eje')
        self.assertEqual(self.prop['origen'],'corte-de sintetica-v1')
        self.assertNotIn('familia',self.prop)
        self.assertEqual(self.row['evidencia'],self.ev)
    def test_inactive_changed_source_hashes_or_missing_durability_block(self):
        for key,value in [('de','otra'),('laminas',[]),('durable',False),('md5','a'),('drive_id','bad/id')]:
            row=copy.deepcopy(self.row);row['evidencia'][key]=value
            with self.assertRaises(m.EntregaError):m.preparar(row,self.plan,'Pieza')
        for plan in ([],self.plan*2):
            with self.assertRaises(m.EntregaError):m.preparar(self.row,plan,'Pieza')
    def test_changed_or_duplicate_existing_proposal_is_never_overwritten(self):
        self.assertFalse(m.coincidencia(self.day,self.prop))
        day=copy.deepcopy(self.day);day['propuestas']=[dict(self.prop,fecha_fuente='2026-10-17')]
        self.assertTrue(m.coincidencia(day,self.prop))
        day['propuestas'][0]['video']='otro'
        with self.assertRaises(m.EntregaError):m.coincidencia(day,self.prop)
        day['propuestas']=[self.prop,self.prop]
        with self.assertRaises(m.EntregaError):m.coincidencia(day,self.prop)
    def test_missing_ack_prepared_marker_never_resends(self):
        self.row['evidencia']['entrega']={'estado':'preparada','prop_id':self.prop['id'],'video':self.prop['video']}
        with patch.object(m,'contexto',return_value=(self.prop,{})),patch.object(m.sala,'post') as post:
            with self.assertRaisesRegex(m.EntregaError,'acuse_incierto_no_reenviar'):
                m.entregar(self.row,self.day,[],{}, {})
            post.assert_not_called()
    def test_modified_bytes_or_silent_video_cannot_be_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'video.mp4';p.write_bytes(b'synthetic bytes')
            ev=dict(self.ev,md5=hashlib.md5(p.read_bytes()).hexdigest())
            meta={'trashed':False,'mimeType':'video/mp4','size':p.stat().st_size,'md5Checksum':ev['md5']}
            with patch.object(m.subprocess,'check_output',return_value=json.dumps({'streams':[{'codec_type':'video'}],'format':{'duration':'48'}}).encode()):
                with self.assertRaisesRegex(m.EntregaError,'falta_audio_o_video'):m.comprobar_medio(ev,meta,p)
            p.write_bytes(b'changed content')
            with self.assertRaises(m.EntregaError):m.comprobar_medio(ev,meta,p)
    def test_open_request_blocks_before_any_remote_read_or_write(self):
        with patch.object(m.sala,'enmascarar_en_actions'),patch.object(m.produccion,'peticiones_abiertas',return_value=True),patch.object(m.sala,'get') as get,patch.object(m.sala,'post') as post:
            self.assertEqual(m.main(),2)
            get.assert_not_called();post.assert_not_called()
    def test_source_must_remain_active(self):
        with self.assertRaises(m.EntregaError):m.fuente(self.day,self.ev)

if __name__=='__main__':unittest.main()
