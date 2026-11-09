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
    def test_pago_apagado_por_omision_y_con_tope(self):
        with patch('sala_puntajes.leer',return_value={'etapas':{}}):
            for i in range(50):
                self.assertNotIn('omni_flash',a.candidatos('escena',{'id':str(i)},{},self.rows,[])[0])
                self.assertNotIn('omni_flash',a.candidatos('escena',{'id':str(i)},{'omni_flash_tope_dia':'no'},self.rows,[])[0])
                # Autorizado: gratis generativo primero, pago después, código al final.
                self.assertEqual(['wan_hf','omni_flash','codigo'],a.candidatos('escena',{'id':str(i)},{'omni_flash_tope_dia':'2'},self.rows,[])[0])
            r={'omni_flash_tope_dia':'2','motores_vetados':'omni_flash'}
            self.assertNotIn('omni_flash',a.candidatos('escena',{'id':'x'},r,self.rows,[])[0])
            # Una fila de MOTORES encendida no basta: sin la regla de Dirección no hay gasto.
            rows=self.rows+[dict(etapa='escena',motor='omni_flash',encendido=1,costo='pago',tope_dia=9,orden=3)]
            self.assertNotIn('omni_flash',a.candidatos('escena',{'id':'x'},{},rows,[])[0])
            q=[dict(etapa='escena',estado='fallo',evidencia={'usos_motores':{'2026-01-01':{'omni_flash':2}}})]
            with patch.object(m,'_hoy_prefijo',return_value='2026-01-01'):
                self.assertNotIn('omni_flash',a.candidatos('escena',{'id':'x'},{'omni_flash_tope_dia':'2'},self.rows,q)[0])
    def test_escena_voz_larga_usa_pago_y_respeta_15s(self):
        cola=lambda s:[{'id':'x:voz:1:h','estado':'hecho','evidencia':{'durable':True,'duracion_s':s}}]
        t={'id':'x:escena:1:h'}; r={'omni_flash_tope_dia':'2'}; usados=[]
        with patch('sala_puntajes.leer',return_value={'etapas':{}}), patch('motores.escena_omni.producir',return_value='v.mp4') as omni:
            ruta,motor,extra=a.escena(t,r,self.rows,{},'/tmp',cola(8.84),usados.append)
            self.assertEqual(('v.mp4','omni_flash',['omni_flash']),(ruta,motor,usados))
            self.assertEqual(8.99,omni.call_args[0][4])
            self.assertTrue(extra['generativa']); self.assertEqual('video_generativo',extra['formato'])
            self.assertEqual('incompatible',extra['intentos_motores'][0]['estado'])
            self.assertIn('pago',extra['cuota'])
        with patch('sala_puntajes.leer',return_value={'etapas':{}}), patch('motores.escena_omni.producir') as omni, patch('motores.escena_codigo.producir',return_value='c.mp4'):
            self.assertEqual('codigo',a.escena(t,r,self.rows,{},'/tmp',cola(20))[1])
            omni.assert_not_called()
    def test_omni_contrato_y_errores(self):
        import base64, io, urllib.error
        from motores import escena_omni as o
        self.assertEqual([3,9,15],[o.duracion(x) for x in (1.2,8.99,15)])
        video=base64.b64encode(b'mp4').decode()
        self.assertEqual(b'mp4',o.extraer_video({'steps':[{'type':'model_output','content':[{'type':'video','mime_type':'video/mp4','data':video}]}]},lambda u:b''))
        self.assertEqual(b'bajado',o.extraer_video({'steps':[{'content':[{'type':'video','uri':'files/abc'}]}]},lambda u:b'bajado' if u=='files/abc' else b''))
        with self.assertRaises(MotorError):o.extraer_video({'steps':[]},lambda u:b'')
        cuerpo=o.peticion(b'jpg','mueve',9,'gemini-omni-1.2-flash')
        self.assertEqual({'type':'video','duration':'9s','aspect_ratio':'9:16','resolution':'720p'},cuerpo['response_format'])
        self.assertEqual('image',cuerpo['input'][0]['type'])
        self.assertEqual('texto',o.peticion(None,'texto',15,'m')['input'])
        self.assertNotIn('generation_config',o.peticion(None,'texto',15,'m'))
        import piloto_omni as p
        u=json.loads(p.UNIVERSO.read_text(encoding='utf-8'))
        for hid,h in u['historias'].items():
            prompt,seg=p.armar(u,hid)
            self.assertEqual(15,seg); self.assertIn(h['dialogo'],prompt); self.assertIn(h['vertice'],u['vertices'])
            self.assertLessEqual(len(h['dialogo'].split()),38)   # cabe hablado en 15 s
            import contenido_reglas; contenido_reglas.exigir({'p':prompt},None,'piloto')
        with patch.object(o,'generar') as g:
            self.assertEqual(0,p.main(['piloto-terreno','--simular'])); g.assert_not_called()
            self.assertEqual(2,p.main(['no-existe']))
        def http(code):
            return urllib.error.HTTPError('u',code,'x',{},io.BytesIO(json.dumps({'error':{'code':code,'message':'m AIzaSECRETO'}}).encode()))
        with patch.dict('os.environ',{'GEMINI_API_KEY':'AIzaSECRETO'}):
            with patch('urllib.request.urlopen',side_effect=http(429)), self.assertRaises(MotorError) as e:o.llamar('POST','interactions',{})
            self.assertTrue(e.exception.intermitente and e.exception.esperar)
            with patch('urllib.request.urlopen',side_effect=http(400)), self.assertRaises(MotorError) as e:o.llamar('POST','interactions',{})
            self.assertFalse(e.exception.intermitente)
        with patch.dict('os.environ',{'GEMINI_API_KEY':''}), self.assertRaises(MotorError):o.llamar('POST','interactions',{})
if __name__=='__main__':unittest.main()
