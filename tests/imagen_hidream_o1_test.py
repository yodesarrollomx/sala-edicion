import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import numpy as np
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
from motores import imagen, imagen_hidream_o1 as o1
from motores._comun import MotorError

class O1Test(unittest.TestCase):
    def payload(self):
        b=io.BytesIO()
        Image.fromarray(np.random.default_rng(2).integers(0,256,(600,800,3),dtype=np.uint8)).save(b,"PNG")
        return b.getvalue()
    def test_real_format_confirmed_then_reused_without_second_request(self):
        with tempfile.TemporaryDirectory() as td,patch.object(o1,"RAIZ",Path(td)):
            data=self.payload();client=Mock()
            def factory(folder):
                p=folder/"out.png";p.write_bytes(data)
                client.submit.return_value.result.return_value=({"path":str(p)},"done")
                return client
            rules={"_imagen_request_id":"a"*64}
            with patch.object(o1,"_client",side_effect=factory) as create:
                a=o1.generar("Architects around a plan",rules)
                b=o1.generar("Architects around a plan",rules)
                self.assertEqual(a,b);self.assertEqual(create.call_count,1)
                self.assertEqual(client.submit.call_args.args[1:3],("3:4",False))
                self.assertEqual(client.submit.call_args.kwargs,{"api_name":"/_generate_wrapped"})
                self.assertEqual(rules["_imagen_parametros"]["space"],o1.SPACE)
                with self.assertRaises(MotorError):o1.generar("Another plan",rules)
            rules["_imagen_solo_recibo"]=True
            with patch.object(o1,"_client",side_effect=AssertionError("no generation")):
                self.assertEqual(o1.generar("receipt lookup",rules),a)
                self.assertEqual(rules["_receta_proveedor_sha256"],hashlib.sha256(b"Architects around a plan").hexdigest())
    def test_missing_receipt_never_resends(self):
        with tempfile.TemporaryDirectory() as td,patch.object(o1,"RAIZ",Path(td)),patch.object(o1,"_client",side_effect=AssertionError("no request")):
            with self.assertRaises(imagen.ReciboNoConfirmado):
                o1.generar("A plan",{"_imagen_solo_recibo":True})
    def test_uncertain_result_no_fallback_and_no_negative_claim(self):
        for result in ((None,"provider did not confirm"),TimeoutError("timeout")):
            client=Mock()
            if isinstance(result,Exception):client.submit.return_value.result.side_effect=result
            else:client.submit.return_value.result.return_value=result
            with tempfile.TemporaryDirectory() as td,patch.object(o1,"RAIZ",Path(td)),patch.object(o1,"_client",return_value=client):
                with self.assertRaises(imagen.ServicioImagen) as e:o1.generar("A plan",{})
                self.assertNotIsInstance(e.exception,imagen.RechazoImagen)
    def test_foreign_path_rejected(self):
        client=Mock();client.submit.return_value.result.return_value=("/etc/passwd","done")
        with tempfile.TemporaryDirectory() as td,patch.object(o1,"RAIZ",Path(td)),patch.object(o1,"_client",return_value=client):
            with self.assertRaises(imagen.ServicioImagen):o1.generar("A plan",{})
    def test_paid_fallback_not_called(self):
        paid=Mock()
        with patch.dict(imagen.MOTORES,{"hidream_o1":Mock(side_effect=imagen.ServicioImagen("offline")),"openai_broker":paid},clear=True):
            with self.assertRaises(imagen.ServicioImagen):
                imagen.generar("A plan",{"imagen_motores":"hidream_o1,openai_broker"})
        paid.assert_not_called()
        self.assertEqual(imagen.modelo_de("hidream_o1"),o1.MODELO)

if __name__=="__main__":unittest.main()
