import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nube"))
import plan_agregados as p
from snapshots_online import receipt_matches

def lead(**values):
    row = {"Primer contacto": 46200, "Folio": "POT-fixture-1", "Tipo": "lead_potencial",
           "Estado": "NUEVO", "Sesión agendada": "", "UTM campaign": "fb-2026-07-01",
           "UTM content": "pieza-fixture"}
    row.update(values)
    return row

class Aggregates(unittest.TestCase):
    def test_prueba_excluida_aunque_tenga_sesion_y_utm(self):
        output = p.aggregate([lead(**{"Estado": "PRUEBA", "Sesión agendada": "valor de prueba"})], "2026-10-11T16:00:00Z")
        self.assertEqual(output["campanas"], [])
        self.assertEqual(output["conteos"]["pruebas_excluidas"], 1)
        self.assertEqual(output["conteos"]["leads_historicos"], 0)

    def test_clic_en_agendar_no_es_cita_confirmada(self):
        output = p.aggregate([lead(**{"Estado": "INVITADO A VIDEOLLAMADA"})], "t")
        self.assertEqual(output["campanas"][0]["citas"], 0)

    def test_confirmacion_exige_estado_y_fecha_real(self):
        rows = [lead(**{"Estado": "SESIÓN AGENDADA", "Sesión agendada": 46204.4375}),
                lead(**{"Folio": "POT-fixture-2", "Estado": "NUEVO", "Sesión agendada": 46204.4375})]
        output = p.aggregate(rows, "t")
        self.assertEqual(output["campanas"][0]["leads"], 2)
        self.assertEqual(output["campanas"][0]["citas"], 1)

    def test_estado_agendado_sin_confirmacion_es_error(self):
        with self.assertRaises(p.PlanError):
            p.aggregate([lead(**{"Estado": "SESIÓN AGENDADA"})], "t")

    def test_texto_y_booleano_no_sustituyen_fecha_de_sesion(self):
        for value in ("clic", True, "30/7/2026 10:00 - prueba", float("nan")):
            with self.subTest(value=value), self.assertRaises(p.PlanError):
                p.aggregate([lead(**{"Sesión agendada": value})], "t")

    def test_dos_registros_del_mismo_folio_no_duplican_lead(self):
        output = p.aggregate([lead(), lead()], "t")
        self.assertEqual(output["conteos"]["leads_historicos"], 1)
        self.assertEqual(output["conteos"]["duplicados_identicos"], 1)

    def test_folio_duplicado_contradictorio_aborta(self):
        with self.assertRaises(p.PlanError):
            p.aggregate([lead(), lead(**{"Estado": "INVITADO A VIDEOLLAMADA"})], "t")

    def test_sin_campana_no_inventa_atribucion(self):
        output = p.aggregate([lead(**{"UTM campaign": ""})], "t")
        self.assertEqual(output["campanas"], [])
        self.assertEqual(output["conteos"]["sin_campana"], 1)
        self.assertEqual(output["periodo"], "historico")

    def test_salida_no_contiene_folios_ni_pii(self):
        output = p.aggregate([lead(Nombre="PERSONA_PRIVADA", Email="privado@example.invalid",
                                   Notas="NOTA_PRIVADA")], "t")
        serialized = json.dumps(output)
        for forbidden in ("POT-fixture", "PERSONA_PRIVADA", "privado@", "NOTA_PRIVADA",
                          "Primer contacto", "Folio", "Nombre", "Email"):
            self.assertNotIn(forbidden, serialized)

    def test_utm_con_email_url_o_texto_libre_se_rechaza(self):
        for value in ("nombre@example.invalid", "https://example.invalid", "persona privada"):
            with self.subTest(value=value), self.assertRaises(p.PlanError):
                p.aggregate([lead(**{"UTM campaign": value})], "t")

    def test_campanas_y_piezas_se_agrupan_sin_expandir_filas(self):
        rows = [lead(), lead(**{"Folio": "POT-fixture-2"}),
                lead(**{"Folio": "POT-fixture-3", "UTM content": "otra-pieza"})]
        output = p.aggregate(rows, "t")
        self.assertEqual(sorted(x["leads"] for x in output["campanas"]), [1, 2])

    def test_folio_incompleto_o_tipo_desconocido_no_certifica_cero(self):
        for values in ({"Folio": ""}, {"Tipo": "desconocido"}):
            with self.subTest(values=values), self.assertRaises(p.PlanError):
                p.aggregate([lead(**values)], "t")

    def test_lista_vacia_acreditada_es_cero_valido(self):
        output = p.aggregate([], "t")
        self.assertTrue(output["ok"])
        self.assertTrue(output["completo"])
        self.assertEqual(output["conteos"]["leads_historicos"], 0)

    def test_encabezados_obligatorios_y_alias_de_sesion(self):
        headers = list(p.FIELDS) + ["Sesi√≥n agendada"]
        found = p.header_positions(headers)
        self.assertEqual(len(found["Sesión agendada"]), 2)
        with self.assertRaises(p.PlanError):
            p.header_positions(headers[:-2])

    def test_encabezado_duplicado_no_sesion_es_error(self):
        with self.assertRaises(p.PlanError):
            p.header_positions(list(p.FIELDS) + ["Folio"])

    def test_rangos_seleen_solo_columnas_permitidas(self):
        headers = ["Primer contacto", "Folio", "Tipo", "Nombre", "Email", "Estado",
                   "Sesión agendada", "Notas", "UTM campaign", "UTM content"]
        metadata = {"properties": {"timeZone": "America/Phoenix"}, "sheets": [{"properties":
            {"sheetId": 3, "title": "LEADS - POTENCIAL", "gridProperties": {"rowCount": 4, "columnCount": 10}}}]}
        calls = []
        row = lead()
        def api(suffix, params):
            calls.append((suffix, params))
            if suffix == "fixture_sheet":
                return metadata
            if "/values/" in suffix:
                return {"values": [headers]}
            return {"valueRanges": [{"range": rng, "majorDimension": "COLUMNS",
                     "values": [[row.get(headers[int(ord(rng.split("!")[1][0]) - 65)], "")]]}
                     for rng in params["ranges"]]}
        with patch.object(p, "sheet_get", side_effect=api):
            output = p.read_source({"spreadsheet_id": "fixture_sheet", "sheet_id": 3,
                                    "sheet_title": "LEADS - POTENCIAL"})
        read = calls[-1][1]["ranges"]
        self.assertEqual(len(read), 7)
        self.assertFalse(any("!D" in r or "!E" in r or "!H" in r for r in read))
        self.assertEqual(output[0]["Folio"], "POT-fixture-1")
        self.assertNotIn("Nombre", output[0])

    def test_rango_devuelto_distinto_se_rechaza(self):
        metadata = {"properties": {"timeZone": "America/Phoenix"}, "sheets": [{"properties":
            {"sheetId": 3, "title": "LEADS - POTENCIAL", "gridProperties": {"rowCount": 4, "columnCount": 7}}}]}
        with patch.object(p, "sheet_get", side_effect=[metadata, {"values": [list(p.FIELDS)]},
                {"valueRanges": [{"range": "OTRA!A2:A4", "majorDimension": "COLUMNS"}] * 7}]):
            with self.assertRaises(p.PlanError):
                p.read_source({"spreadsheet_id": "fixture_sheet", "sheet_id": 3, "sheet_title": "LEADS - POTENCIAL"})

    def test_rechazo_google_no_imprime_url_token_o_cuerpo_privado(self):
        response = type("Response", (), {"status_code": 403, "content": b"PRIVATE_ERROR_WITH_TOKEN"})()
        with patch.object(p.drive, "_token", return_value="SECRET_FIXTURE"), \
             patch.object(p.requests, "get", return_value=response) as req:
            with self.assertRaises(p.PlanError) as ctx:
                p.sheet_get("private_sheet_id")
        self.assertEqual(str(ctx.exception), "sheets_http_403")
        self.assertFalse(req.call_args.kwargs["allow_redirects"])

    def test_recibo_debe_vincular_hash_del_archivo_plan(self):
        receipt = {"schema": 1, "code_sha": "a" * 40, "data_sha": "b" * 64,
                   "snapshot_id": 4, "run_id": "7", "plan_sha256": "c" * 64}
        args = dict(code_sha="a" * 40, data_sha="b" * 64, snapshot_id=4, run_id="7")
        self.assertTrue(receipt_matches(receipt, **args, plan_sha256="c" * 64))
        self.assertFalse(receipt_matches(receipt, **args, plan_sha256="d" * 64))
        del receipt["plan_sha256"]
        self.assertFalse(receipt_matches(receipt, **args, plan_sha256="c" * 64))

if __name__ == "__main__":
    unittest.main()
