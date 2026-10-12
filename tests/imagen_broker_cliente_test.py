import base64,hashlib,hmac,json
from pathlib import Path
import sys
import unittest
import urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
from motores import imagen

class Response:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self):return json.dumps({"ok":True,"model":"gpt-image-1.5","image":base64.b64encode(b"synthetic").decode(),"recipe_sha":"sha-confirmada"}).encode()

class BrokerClienteTest(unittest.TestCase):
    def test_recibo_confirmado_se_recupera_sin_generar(self):
        rules={"_imagen_request_id":"a"*64}
        with patch.object(imagen.sala,"_clave",return_value="synthetic-agent"),\
             patch.object(imagen.urllib.request,"urlopen",return_value=Response()) as get,\
             patch.object(imagen,"_pedir") as post:
            data,ext=imagen.openai_broker("Synthetic",rules)
        self.assertEqual((data,ext),(b"synthetic","png"))
        post.assert_not_called()
        self.assertEqual(rules["_receta_proveedor_sha256"],"sha-confirmada")
        req=get.call_args.args[0]
        expected=hmac.new(b"synthetic-agent",b"yod:sala:image-broker:v1",hashlib.sha256).hexdigest()
        self.assertEqual(req.headers["Authorization"],"Bearer "+expected)
        self.assertTrue(req.full_url.endswith("/result/"+"a"*64))

    def test_sin_recibo_se_genera_con_identidad_y_espera_acotada(self):
        import io
        error=urllib.error.HTTPError("https://synthetic.invalid",404,"not found",{},io.BytesIO(b'{"error":"not_confirmed"}'))
        payload=Response().read()
        with patch.object(imagen.sala,"_clave",return_value="synthetic-agent"),\
             patch.object(imagen.urllib.request,"urlopen",side_effect=error),\
             patch.object(imagen,"_pedir",return_value=(payload,"application/json")) as post:
            imagen.openai_broker("Synthetic",{"_imagen_request_id":"b"*64})
        self.assertEqual(post.call_args.args[1]["request_id"],"b"*64)
        self.assertEqual(post.call_args.kwargs["espera"],240)

    def test_resultado_incierto_no_envia_otro_post(self):
        import io
        error=urllib.error.HTTPError("https://synthetic.invalid",409,"conflict",{},io.BytesIO(b'{"error":"generation_uncertain_do_not_repeat"}'))
        with patch.object(imagen.sala,"_clave",return_value="synthetic-agent"),\
             patch.object(imagen.urllib.request,"urlopen",side_effect=error),patch.object(imagen,"_pedir") as post:
            with self.assertRaises(imagen.MotorError):imagen.openai_broker("Synthetic",{})
        post.assert_not_called()

if __name__=="__main__":unittest.main()
