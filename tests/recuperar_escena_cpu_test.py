import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nube'))
from recuperar_escena_cpu import validar, RecuperacionError

class RecuperacionTests(unittest.TestCase):
    def setUp(self):
        self.ev={'de':'sintetica-v1','src':'imagen.png','dice':'Texto aprobado','nota':'','lamina':'1','n_real':True}
        self.row={'id':'sintetica:escena:1:12345678','pieza':'sintetica','etapa':'escena','item':'1',
                  'estado':'bloqueado','bloqueado_por':'ejecucion_cancelada_sin_acuse','evidencia':self.ev}
        self.plan=[dict(self.row,estado='pendiente')]
        self.rules={'nube_ejecuta_etapas':'escena,voz,corte'}
    def test_exact_approved_plan_and_empty_durable_inventory_allow_cpu_only_recovery(self):
        before=copy.deepcopy(self.row)
        self.assertEqual(validar(self.row,self.plan,self.rules,[]),self.ev)
        self.assertEqual(self.row,before)
    def test_changed_vote_input_or_identity_never_repeats_work(self):
        for key in ('src','dice','nota','de','lamina'):
            plan=copy.deepcopy(self.plan);plan[0]['evidencia'][key]='otro'
            with self.assertRaises(RecuperacionError):validar(self.row,plan,self.rules,[])
        for plan in ([],self.plan*2):
            with self.assertRaises(RecuperacionError):validar(self.row,plan,self.rules,[])
    def test_existing_or_ambiguous_media_block_even_without_queue_ack(self):
        for name in ('sintetica-L1-escena.mp4','sintetica-L1-escena-abcdef.mp4'):
            with self.assertRaises(RecuperacionError):validar(self.row,self.plan,self.rules,[{'name':name}])
        validar(self.row,self.plan,self.rules,[{'name':'sintetica-L10-escena.mp4'}])
    def test_done_running_unknown_state_or_disabled_stage_never_reexecute(self):
        for state in ('hecho','corriendo','pendiente','fallo'):
            with self.assertRaises(RecuperacionError):validar(dict(self.row,estado=state),self.plan,self.rules,[])
        with self.assertRaises(RecuperacionError):validar(self.row,self.plan,{'nube_ejecuta_etapas':'voz'},[])
        with self.assertRaises(RecuperacionError):validar(self.row,self.plan,dict(self.rules,escena_parallax='0',escena_respaldo_camara='0'),[])

if __name__=='__main__':unittest.main()
