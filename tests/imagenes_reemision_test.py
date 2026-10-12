import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
from motores import imagen,politica_imagen as p,_comun
import sala_mesa as mesa
import sala_produccion as prod
import sala_productor as productor

BAD="laminas/synthetic/bad.png"
GOOD="laminas/synthetic/good.png"
def fixture(estado="rehecha"):
    return {"pieza":"Synthetic","pieza_slug":"synthetic","fecha":"2026-10-12",
            "decidir":[1],"mapa":{"1":1},"laminas":[{"n":1,"estado":estado,
            "src":BAD,"dice":"Original caption","candidatas":[{"src":BAD,"original":BAD,
            "motor":"pollinations","dice":"Visible caption"}]}]}

class ReemisionTest(unittest.TestCase):
    def test_retiro_administrativo_conserva_historia_sin_reescribir_original(self):
        t=fixture("aprobada");t["laminas"][0]["seleccion"]={"toma":1,"src":BAD}
        before=copy.deepcopy(t)
        with patch.object(p,"FUENTES",{BAD}):
            out,changed=p.depurar_tira(t)
        l=out["laminas"][0]
        self.assertEqual(t,before)
        self.assertEqual(changed,{1})
        self.assertEqual((l["src"],l["estado"],l["candidatas"]),("","pendiente",[]))
        self.assertEqual(l["dice"],"Visible caption")
        self.assertEqual(l["revision_retirada"]["seleccion"],before["laminas"][0]["seleccion"])
        self.assertEqual(l["revision_retirada"]["estado"],"aprobada")

    def test_candidata_no_elegida_retirada_no_reabre_fuente_aprobada_sana(self):
        t=fixture("aprobada")
        l=t["laminas"][0];l["src"]=GOOD;l["candidatas"].insert(0,{"motor":"cloudflare","src":GOOD})
        with patch.object(p,"FUENTES",{BAD}):out,changed=p.depurar_tira(t)
        self.assertEqual(changed,set())
        self.assertEqual(out,t)

    def test_si_anterior_no_salta_reemision_ni_se_convierte_en_voto(self):
        t=fixture();decision={"laminas":["si"],"notas":["[toma elegida: 1]"]}
        before=copy.deepcopy(decision)
        with patch.object(p,"FUENTES",{BAD}):
            resolved=prod.resolver_tira(t,decision,{"laminas":[BAD]})
            with patch.object(mesa,"decision_del_sheet",return_value=(decision,[BAD])):
                work=mesa.abiertas("synthetic",t)
        self.assertEqual(decision,before)
        self.assertEqual(resolved["laminas"][0]["estado"],"pendiente")
        self.assertEqual(work[0][1],"reemplazar_modelo")
        self.assertIn("conservar exactamente el texto visible",work[0][2])

    def test_productor_no_abre_escena_voz_o_corte_sobre_imagen_retirada(self):
        t=fixture();dia={"propuestas":[{"id":"synthetic-nube-2026-10-12-abc","laminas":[BAD]}],
            "decisiones":{"propuestas":{"synthetic-nube-2026-10-12-abc":
            {"laminas":["si"],"notas":["[toma elegida: 1]"]}}}}
        with patch.object(p,"FUENTES",{BAD}),patch.object(productor,"tira_de",return_value=t),\
             patch.object(productor,"huella_insumo",return_value=("synthetic","fixture")):
            jobs,notes=productor.planear(dia,[],{})
        self.assertEqual(jobs,[])
        self.assertTrue(any("fuente retirada" in x for x in notes))

    def test_ejecutor_no_copia_imagen_retirada_de_evidencia_antigua(self):
        with patch.object(p,"FUENTES",{BAD}),patch.object(_comun,"lamina_de",return_value={"src":BAD}):
            with self.assertRaisesRegex(_comun.MotorError,"retirada"):
                _comun.traer_imagen({"id":"synthetic"},{},"/tmp/synthetic-no-write.png")

    def test_flux2_usa_multipart_y_modelo_nuevo_fijo(self):
        class Response:
            status_code=200
            headers={"Content-Type":"image/png"}
            content=b"synthetic-image"
        with patch.dict(os.environ,{"CF_ACCOUNT_ID":"synthetic-account","CF_API_TOKEN":"synthetic-token"}),\
             patch("requests.post",return_value=Response()) as http:
            data,ext=imagen.cloudflare_flux2("Synthetic scene",{})
        self.assertEqual((data,ext),(b"synthetic-image","png"))
        args,kw=http.call_args
        self.assertTrue(args[0].endswith(imagen.MODELO_FLUX2))
        self.assertEqual(kw["files"]["width"],(None,"1024"))
        self.assertEqual(kw["files"]["height"],(None,"1280"))
        self.assertNotIn("json",kw)

    def test_quota_multipart_se_declara_intermitente(self):
        class Response:
            status_code=429
            text="daily free allocation exceeded"
        with patch.dict(os.environ,{"CF_ACCOUNT_ID":"synthetic-account","CF_API_TOKEN":"synthetic-token"}),\
             patch("requests.post",return_value=Response()):
            with self.assertRaises(_comun.MotorError) as ctx:imagen.cloudflare_flux2("Synthetic",{})
        self.assertTrue(ctx.exception.intermitente)

    def test_regla_vieja_no_reactiva_pollinations_ni_cpu(self):
        calls=[]
        def fail(*args):raise _comun.MotorError("CF 429 daily free allocation",intermitente=True)
        def bad(*args):calls.append("bad");return b"bad","png"
        with patch.dict(imagen.MOTORES,{"cloudflare_flux2":fail,"pollinations":bad,"cpu":bad},clear=True):
            with self.assertRaises(imagen.CupoImagen):
                imagen.generar("Synthetic object",{"imagen_motores":"pollinations,cpu,cloudflare_flux2"})
        self.assertEqual(calls,[])

    def test_estado_de_cupo_se_publica_aunque_no_haya_tarjeta_generada(self):
        wf=(Path(__file__).resolve().parents[1]/".github/workflows/sala-mesa.yml").read_text()
        guardar=wf.split("- name: Guardar snapshot privado",1)[1].split("- name:",1)[0]
        montaje=wf.split("- name: Montar cartas",1)[1].split("- name:",1)[0]
        self.assertIn("cupo_bloqueado == 'si'",guardar)
        self.assertNotIn("cupo_bloqueado",montaje)
        self.assertIn("outputs.codigo == '0'",montaje)

    def test_modelo_pro_se_fija_sin_usar_regla_del_modelo_anterior(self):
        with patch.object(imagen,"gemini",return_value=(b"synthetic","png")) as api:
            imagen.gemini_pro("Synthetic",{"imagen_gemini_modelo":"old-model"})
        self.assertEqual(api.call_args.args[1]["imagen_gemini_modelo"],"gemini-3-pro-image")

if __name__=="__main__":unittest.main()
