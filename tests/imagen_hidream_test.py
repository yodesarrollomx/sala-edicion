import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
from motores import imagen, imagen_hidream as hi, cerebro
from motores._comun import MotorError

class HiDreamTest(unittest.TestCase):
    def payload(self):
        rng=np.random.default_rng(1)
        out=io.BytesIO();Image.fromarray(rng.integers(0,256,(600,600,3),dtype=np.uint8)).save(out,"PNG")
        return out.getvalue()
    def test_confirmado_y_cache_sin_segunda_llamada(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);data=self.payload()
            class Job:
                def result(self,timeout):
                    p=Path(client.dir)/"photo.png";p.write_bytes(data)
                    return str(p),123,"ok",{"model":hi.MODELO}
            class Client:
                def submit(self,*args,**kw):
                    self.args=args
                    return Job()
            client=Client()
            def factory(folder):client.dir=str(folder);return client
            rid="f"*64;rules={"_imagen_request_id":rid}
            with patch.object(hi,"RAIZ",root),patch.object(hi,"_client",side_effect=factory) as create:
                a=hi.generar("A photographer sees plans",rules)
                b=hi.generar("A photographer sees plans",rules)
                self.assertEqual(a,b);self.assertEqual(create.call_count,1)
                self.assertLess(client.args[2],1000000)
                self.assertEqual(rules["_imagen_recibo_id"],rid)
                self.assertEqual(len(list((root/"laminas/recibos-hidream").glob("*.json"))),1)
                with self.assertRaises(MotorError):hi.generar("A different scene",rules)
    def test_cupo_y_solo_recibo_no_caen_a_otro_motor(self):
        calls=[]
        with patch.dict(imagen.MOTORES,{"hidream_demo":lambda *x:(_ for _ in ()).throw(imagen.CupoImagen("429",intermitente=True)),
            "openai_broker":lambda *x:calls.append("pago")},clear=True):
            with self.assertRaises(imagen.CupoImagen):imagen.generar("Photo",{"imagen_motores":"hidream_demo,openai_broker"})
        self.assertEqual(calls,[])
        with tempfile.TemporaryDirectory() as td,patch.object(hi,"RAIZ",Path(td)),patch.object(hi,"_client",side_effect=AssertionError("no red")):
            with self.assertRaises(imagen.ReciboNoConfirmado):hi.generar("photo",{"_imagen_solo_recibo":True})
    def test_archivo_invalido_se_bloquea(self):
        with self.assertRaises(MotorError):hi.validar(b"not image"*1000)
    def test_texto_solo_cambia_por_peticion_explicita(self):
        with patch.object(cerebro,"_gemini",return_value='{"scene":"Architects compare scale models","texto":"El plan abre una ruta clara"}'):
            d,_,_=cerebro.fotografia_guion("Un caption anterior","Maquetas","Que diga una ruta clara","",{},1)
        self.assertEqual(d["texto"],"El plan abre una ruta clara")
        self.assertNotIn(d["texto"],d["receta"])
        with patch.object(cerebro,"_gemini",side_effect=MotorError("sin cuota")):
            with self.assertRaises(MotorError):cerebro.fotografia_guion("Anterior","Maquetas","Que diga una ruta clara","",{},1)
    def test_descripcion_visual_no_envia_caption_ni_cerebro_pagado(self):
        caption="Cuatro opiniones sobre nuestro proyecto"
        with patch.object(cerebro,"_gemini",side_effect=MotorError("sin cuota")),patch.object(cerebro,"_openai",side_effect=AssertionError("sin pago")):
            d,who,_=cerebro.fotografia_guion(caption,"Tres personas comparan un plano sin letras","Más luz","",{},2)
        self.assertEqual(d["texto"],caption)
        self.assertNotIn(caption,d["receta"])
        self.assertIn("Tres personas",d["receta"])
        self.assertEqual(who,"guion-visual")
if __name__=="__main__":unittest.main()
