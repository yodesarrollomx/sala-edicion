import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'nube'))
import sala_produccion as prod
import sala_productor as planner
from contenido_reglas import revisar


class GuionReferenciaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ref = 'datos/guiones/SINTETICA-VIDEO.json'
        self.path = self.root / self.ref
        self.path.parent.mkdir(parents=True)
        self.script = {'escenas':[{'n':1,'partes':[{'rol':'narrador','dice':'Texto existente'}]}]}
        self.path.write_text(json.dumps(self.script))
        self.tira = {'pieza_slug':'sintetica','guion':self.ref,
                     'laminas':[{'n':1,'estado':'aprobada','dice':'Texto visible','src':'imagen.png'}]}

    def test_explicit_existing_script_resolves_without_changing_source_or_approval(self):
        before=copy.deepcopy(self.tira)
        with patch.object(prod,'ROOT',self.root):
            resolved=prod.resolver_guion(self.tira)
            self.assertEqual(prod.guion_faltante(self.tira),[])
        self.assertEqual(self.tira,before)
        self.assertEqual(resolved['laminas'],before['laminas'])
        self.assertEqual(resolved['guion'][0]['dice'],'Texto existente')
        self.assertEqual(resolved['guion_referencia'],self.ref)

    def test_missing_unstructured_outside_or_wrong_family_reference_stays_blocked(self):
        for ref in ('Texto libre','../otro.json','datos/guiones/OTRA-VIDEO.json','/tmp/SINTETICA-VIDEO.json'):
            self.tira['guion']=ref
            with patch.object(prod,'ROOT',self.root):
                self.assertEqual(prod.resolver_guion(self.tira)['guion'],ref)
                with self.assertRaises(Exception):prod.guion_faltante(self.tira)
        self.path.unlink();self.tira['guion']=self.ref
        with patch.object(prod,'ROOT',self.root):self.assertEqual(prod.resolver_guion(self.tira)['guion'],self.ref)

    def test_invalid_or_duplicate_scene_never_opens_a_cut(self):
        for scenes in ([self.script['escenas'][0]]*2,[{'n':True,'partes':[]}],[{'n':1,'partes':[{'rol':'narrador','dice':''}]}]):
            self.path.write_text(json.dumps({'escenas':scenes}))
            with patch.object(prod,'ROOT',self.root):self.assertEqual(prod.resolver_guion(self.tira)['guion'],self.ref)

    def test_script_content_is_visible_to_editorial_veto_and_missing_scenes_stay_missing(self):
        self.script['escenas'][0]['partes'][0]['dice']='Contenido en Hermosillo'
        self.script['escenas'].append({'n':2,'partes':[{'rol':'vecino','dice':'Otra escena'}]})
        self.path.write_text(json.dumps(self.script))
        with patch.object(prod,'ROOT',self.root):
            resolved=prod.resolver_guion(self.tira)
            self.assertEqual([x['n'] for x in prod.guion_faltante(self.tira)],[2])
        self.assertTrue(revisar(resolved))

    def test_existing_script_allows_only_fully_approved_cut_and_keeps_original_reference(self):
        day={'propuestas':[{'id':'sintetica-v1','titulo':'Pieza sintética','laminas':['imagen.png']}],
             'decisiones':{'propuestas':{'sintetica-v1':{'laminas':['si']}}}}
        before=copy.deepcopy(self.tira)
        with patch.object(prod,'ROOT',self.root), patch.object(planner,'tira_de',return_value=self.tira), patch.object(planner,'RAIZ',self.root), patch.object(planner.catalogo,'huella_de',return_value=None):
            jobs,_=planner.planear(day,[],{}, {})
            self.assertEqual({j['etapa'] for j in jobs},{'escena','voz','corte'})
            day['decisiones']['propuestas']['sintetica-v1']['laminas']=['no']
            jobs,_=planner.planear(day,[],{}, {})
            self.assertFalse(any(j['etapa']=='corte' for j in jobs))
        self.assertEqual(self.tira,before)


if __name__=='__main__':unittest.main()
