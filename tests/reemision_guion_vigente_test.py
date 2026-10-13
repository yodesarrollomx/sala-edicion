import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
import sala_mesa as mesa
import sala_compositor

class GuionVigenteTest(unittest.TestCase):
    def test_reemision_no_llama_cerebro_y_conserva_caption_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/"laminas/synthetic";folder.mkdir(parents=True)
            def compose(source,text,png):
                png.write_bytes(b"synthetic png");jpg=png.with_suffix(".jpg");jpg.write_bytes(b"synthetic jpg")
                return png,jpg
            lam={"n":2,"dice":"Tres ideas sobre el mismo terreno","ve":"Personas observando un plano",
                 "reemplazo_modelo":mesa.POLITICA["revision"]}
            with patch.object(mesa,"RAIZ",root),patch.object(mesa,"vetadas",return_value=[]),\
                 patch.object(mesa.cerebro,"lamina",side_effect=AssertionError("no requiere cerebro")),\
                 patch.object(mesa.imagen,"generar",return_value=(b"synthetic","png","openai_broker",[])) as image,\
                 patch.object(sala_compositor,"componer",side_effect=compose),patch.object(sala_compositor,"avisos",[]):
                rows,_=mesa.producir_tomas("synthetic",{"pieza":"Synthetic","laminas":[]},lam,
                    "La imagen no cuadra con el texto",{"imagen_motores":"openai_broker"},[],folder,1)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["dice"],lam["dice"])
            self.assertEqual(rows[0]["modelo"],"gpt-image-1.5")
            self.assertIn(lam["dice"],image.call_args.args[0])
            self.assertIn("concrete action and physical objects",image.call_args.args[0])
            self.assertRegex(image.call_args.args[1]["_imagen_request_id"],"^[a-f0-9]{64}$")

class ReferenciaVigenteTest(unittest.TestCase):
    def test_neutraliza_ubicacion_historica_sin_cambiar_caption(self):
        value=mesa.contexto_visual("Una familia revisa planos en Hermosillo con luz natural")
        self.assertNotIn("Hermosillo",value)
        self.assertIn("familia revisa planos",value)
        self.assertEqual(mesa.contexto_visual("Mesa con planos y luz natural"),"Mesa con planos y luz natural")

if __name__=="__main__":unittest.main()
