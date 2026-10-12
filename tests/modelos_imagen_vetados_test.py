import copy
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
from motores import imagen,politica_imagen as politica
from motores._comun import MotorError
import sala_mesa as mesa

class VetoModelosTest(unittest.TestCase):
    def test_fallo_remoto_no_reactiva_cpu_heredado(self):
        calls=[]
        def fail(*args): raise MotorError("sin cuota",intermitente=True)
        def cpu(*args): calls.append("cpu"); return b"imagen","png"
        with patch.dict(imagen.MOTORES,{"cloudflare":fail,"cpu":cpu},clear=True):
            for rules in [{"imagen_motores":"cloudflare","imagen_respaldo_cpu":"1"},
                          {"imagen_motores":"cpu,cloudflare","imagen_respaldo_cpu":"1"}]:
                with self.assertRaises(MotorError): imagen.generar("Synthetic object",rules)
        self.assertEqual(calls,[])

    def test_motor_permitido_sigue_funcionando(self):
        with patch.dict(imagen.MOTORES,{"cpu":lambda *x: self.fail("cpu vetado"),
                         "gemini_pro":lambda *x:(b"allowed","jpg")},clear=True):
            result=imagen.generar("Synthetic object",{"imagen_motores":"cpu,gemini_pro"})
        self.assertEqual(result[2],"gemini_pro")

    def test_depuracion_no_modifica_aprobado_ni_origen(self):
        original={"laminas":[
            {"n":1,"estado":"aprobada","src":"approved.png","seleccion":{"toma":2},
             "candidatas":[{"motor":"cpu","src":"approved.png"}]},
            {"n":2,"estado":"rehecha","src":"bad.png","candidatas":[
                {"motor":"cpu","src":"bad.png"},{"motor":"gemini_pro","src":"good.jpg"}]},
            {"n":3,"estado":"rehecha","src":"bad2.png","candidatas":[{"motor":"cpu","src":"bad2.png"}]}]}
        baseline=copy.deepcopy(original)
        cleaned,changed=politica.depurar_tira(original)
        self.assertEqual(original,baseline)
        self.assertEqual(cleaned["laminas"][0],baseline["laminas"][0])
        self.assertEqual(changed,{2,3})
        self.assertEqual(cleaned["laminas"][1]["src"],"good.jpg")
        self.assertEqual(cleaned["laminas"][2]["src"],"")
        self.assertEqual(cleaned["laminas"][2]["estado"],"pendiente")

    def test_pendiente_mixta_se_depurara_sin_gastar_generacion(self):
        t={"fecha":"2026-10-01","laminas":[{"n":2,"estado":"rehecha","src":"bad.jpg",
            "candidatas":[{"motor":"cpu","src":"bad.jpg"},{"motor":"cloudflare","src":"good.jpg"}]}],
            "decidir":[2],"mapa":{"1":2}}
        with patch.object(mesa,"decision_del_sheet",return_value=({"laminas":[]},[])):
            pending=mesa.abiertas("synthetic",t)
        self.assertEqual(pending[0][1],"depurar_modelo")
        self.assertEqual(pending[0][0]["candidatas"],[{"motor":"cloudflare","src":"good.jpg"}])

    def test_tira_revisable_no_admite_modelo_vetado(self):
        t={"decidir":[2],"laminas":[{"n":2,"candidatas":[{"motor":"cpu","src":"bad.jpg"}]}]}
        with self.assertRaises(mesa.sala.SalaError):mesa.validar_nuevas_tomas(t,{})
        self.assertFalse(politica.para_revision(t))

    def test_recuperar_solo_tira_activa_con_original_verificado(self):
        image=b"\x89PNG synthetic"
        t={"pieza_slug":"synthetic","laminas":[{"n":1,"src":"laminas/synthetic/L1.png",
            "candidatas":[{"motor":"cloudflare","src":"laminas/synthetic/L1.png",
             "original":"laminas/synthetic/L1.png","huella":hashlib.md5(image).hexdigest()}]}]}
        payload={"datos/tiras/index.json":b'["active","retired"]',
            "datos/tiras/active.json":json.dumps(t).encode(),"laminas/synthetic/L1.png":image}
        called=[]
        def read(p):called.append(p);return payload[p]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(mesa,"RAIZ",root),patch.object(mesa,"TIRAS",root/"datos/tiras"):
                n=mesa.hidratar_tiras_activas({"propuestas":[{"id":"active","laminas":["x"]}]},read)
                self.assertEqual(n,1)
                self.assertTrue((root/"datos/tiras/active.json").is_file())
        self.assertNotIn("datos/tiras/retired.json",called)

    def test_fuente_publicada_con_ruta_ajena_se_bloquea(self):
        t={"pieza_slug":"synthetic","laminas":[{"n":1,"src":"../private.png"}]}
        payload={"datos/tiras/index.json":b'["active"]',"datos/tiras/active.json":json.dumps(t).encode()}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(mesa,"RAIZ",root),patch.object(mesa,"TIRAS",root/"datos/tiras"):
                with self.assertRaises(mesa.sala.SalaError):
                    mesa.hidratar_tiras_activas({"propuestas":[{"id":"active","laminas":["x"]}]},payload.__getitem__)
                self.assertFalse((root/"datos/tiras/active.json").exists())

if __name__=="__main__":unittest.main()
