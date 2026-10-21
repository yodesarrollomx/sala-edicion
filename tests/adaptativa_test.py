import sys, tempfile, subprocess, json, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'nube'))
import sala_adaptativa as a
import sala_motores as m
from motores import escena_codigo as c
from motores._comun import MotorError

class AdaptativaTests(unittest.TestCase):
    def setUp(self):
        self.rows=[dict(etapa='escena',motor='wan_hf',encendido=1,costo=0,tope_dia=2,orden=1)]
    def test_vetos_costos_y_locales(self):
        rows=self.rows+[dict(etapa='escena',motor='ltx_local',encendido=1,costo=0,orden=2)]
        self.assertEqual([],a.candidatos('escena',{'id':'x'},{'motores_vetados':'codigo,wan_hf'},rows,[])[0])
        rows[0]['costo']='pago'
        self.assertEqual(['codigo'],a.candidatos('escena',{'id':'x'},{},rows,[])[0])
    def test_reservas_cuentan_aunque_falle(self):
        q=[dict(etapa='escena',estado='fallo',evidencia={'usos_motores':{'2026-01-01':{'wan_hf':2}}})]
        with patch.object(m,'_hoy_prefijo',return_value='2026-01-01'):
            self.assertEqual(['codigo'],a.candidatos('escena',{'id':'x'},{},self.rows,q)[0])
    def test_exploracion_reproducible(self):
        with patch('sala_puntajes.leer',return_value={'etapas':{}}):
            resultados=[a.candidatos('escena',{'id':str(i)},{},self.rows,[])[0][0] for i in range(1000)]
            self.assertTrue(150<resultados.count('codigo')<250)
            self.assertEqual(a.candidatos('escena',{'id':'x'},{},self.rows,[]),a.candidatos('escena',{'id':'x'},{},self.rows,[]))
    def test_voz_durable_y_duracion(self):
        t={'id':'x:escena:1:h'}
        with self.assertRaises(MotorError):a.duracion_objetivo(t,[])
        self.assertEqual(8.99,a.duracion_objetivo(t,[{'id':'x:voz:1:h','estado':'hecho','evidencia':{'durable':True,'duracion_s':8.84}}]))
    def test_render_real_no_congelado(self):
        self.assertNotEqual(c.frame('Texto sintético',.1,1).tobytes(),c.frame('Texto sintético',.9,1).tobytes())
        with tempfile.TemporaryDirectory() as tmp, patch.object(c,'lamina_de',return_value={'dice':'Prueba sintética de animación.'}):
            p=c.producir({'id':'sintetico'}, {}, {}, tmp, 1.15)
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(p)]))
            self.assertGreaterEqual(float(probe['format']['duration']),1.15)
if __name__=='__main__':unittest.main()
