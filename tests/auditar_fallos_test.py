"""La auditoría del corte es una lectura privada, sin reintentos ni red."""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
import auditar_fallos as auditoria


class AuditoriaFallosTests(unittest.TestCase):
    def setUp(self):
        self.pid = "propuesta-privada-sintetica-20261015"
        self.familia = "familia-sintetica"
        self.laminas = [
            {"item": "1", "huella": "a1b2c3d4"},
            {"item": "2", "huella": "e5f6a7b8"},
        ]
        self.corte = {
            "id": self.familia + ":corte:completo:0123abcd",
            "pieza": self.familia,
            "etapa": "corte", "item": "completo", "estado": "fallo",
            "evidencia": {"de": self.pid, "laminas": copy.deepcopy(self.laminas),
                          "error": "fallo_sintetico", "nota": "nota privada de prueba"},
        }
        self.dependencias = [
            {"id": "%s:%s:%s:%s" % (self.familia, etapa, lam["item"], lam["huella"]),
             "pieza": self.familia, "etapa": etapa, "item": lam["item"],
             "estado": "hecho", "evidencia": {"de": self.pid, "drive_id": "privado-sintetico"}}
            for lam in self.laminas for etapa in ("escena", "voz")
        ]
        self.cola = [copy.deepcopy(self.corte), *copy.deepcopy(self.dependencias)]
        self.prop = {"id": self.pid, "pieza": self.familia,
                     "laminas": [{"src": "sintetico-1.png"}, {"src": "sintetico-2.png"}]}
        self.decision = {"laminas": ["si", "si"], "nota": "decisión privada sintética"}
        self.dia = {"fecha": "2026-10-15", "propuestas": [copy.deepcopy(self.prop)],
                    "decisiones": {"propuestas": {self.pid: copy.deepcopy(self.decision)}}}
        self.tira = {
            "pieza_slug": self.familia, "formato": "video",
            "guion": [{"n": 1}, {"n": 2}], "mapa": {"1": 1, "2": 2},
            "laminas": [{"n": 1, "estado": "pendiente", "src": "sintetico-1.png"},
                        {"n": 2, "estado": "pendiente", "src": "sintetico-2.png"}],
        }
        self.plan = copy.deepcopy(self.corte)
        self.plan["estado"] = "pendiente"
        self.plan["evidencia"] = {"de": self.pid, "laminas": copy.deepcopy(self.laminas)}
        self.reglas = {"productor_piezas": self.familia,
                       "nube_ejecuta_etapas": "escena,voz,corte,prospecto"}
        self.cat = {"sintetico": True}
        self.planner = Mock(return_value=([self.plan], ["diario privado sintético"]))
        self.reader = Mock(side_effect=lambda pid: copy.deepcopy(self.tira))
        self.resolver = Mock(side_effect=self.resolver_sintetico)
        self.media = Mock(return_value={"ok": True, "codigo": "verificado"})
        self.snapshot = Mock(return_value=True)
        # Cualquier acceso HTTP es un defecto: los medios y las lecturas son dobles.
        self.sin_red = patch("requests.sessions.Session.request",
                             side_effect=AssertionError("la prueba no permite red ni POST"))
        self.sin_red.start()
        self.addCleanup(self.sin_red.stop)

    @staticmethod
    def resolver_sintetico(tira, decision, prop):
        result = copy.deepcopy(tira)
        for i, marca in enumerate((decision or {}).get("laminas", [])):
            if i < len(result["laminas"]):
                result["laminas"][i]["estado"] = {
                    "si": "aprobada", "no": "rechazada"}.get(marca, "pendiente")
        return result

    def evaluar(self, **kwargs):
        return auditoria.evaluar(
            self.cola, self.dia, self.reglas, self.cat,
            planner=self.planner, resolver=self.resolver, tira_reader=self.reader,
            media_check=self.media, snapshot_check=self.snapshot, **kwargs)

    def candidato(self, report):
        self.assertEqual(len(report["candidatos"]), 1)
        return report["candidatos"][0]

    def bloqueado(self, report, codigo):
        row = self.candidato(report)
        self.assertFalse(row["elegible"])
        self.assertIn(codigo, row["bloqueos"])
        return row

    def test_corte_validado_es_elegible_y_usa_decision_actual(self):
        row = self.candidato(self.evaluar())
        self.assertTrue(row["elegible"])
        self.assertEqual(row["bloqueos"], [])
        self.assertEqual(row["evaluado"], {"guion": True, "plan": True})
        self.assertEqual(row["id"], self.corte["id"])
        self.resolver.assert_called_once_with(self.tira, self.decision, self.prop)
        self.assertEqual({call.args[0]["id"] for call in self.media.call_args_list},
                         {job["id"] for job in self.dependencias})

    def test_etapas_ausentes_o_sin_corte_no_acreditan_habilitacion(self):
        for value in (None, "", "escena,voz,prospecto"):
            with self.subTest(etapas=value):
                if value is None:
                    self.reglas.pop("nube_ejecuta_etapas", None)
                else:
                    self.reglas["nube_ejecuta_etapas"] = value
                self.media.reset_mock()
                self.bloqueado(self.evaluar(), "etapa_no_habilitada")
                self.media.assert_not_called()

    def test_solo_considera_fallos_de_corte_y_excluye_veto_de_ubicacion(self):
        self.cola = [
            {**copy.deepcopy(self.corte), "id": "corte-hecho", "estado": "hecho"},
            {**copy.deepcopy(self.corte), "id": "voz-fallida", "etapa": "voz"},
            {**copy.deepcopy(self.corte), "id": "corte-vetado",
             "evidencia": {**self.corte["evidencia"], "error": "ubicacion_vetada"}},
        ]
        self.assertEqual(self.evaluar()["candidatos"], [])
        self.media.assert_not_called()

    def test_fuente_ausente_no_se_inventa_desde_decision_o_tira(self):
        self.dia["propuestas"] = []
        row = self.bloqueado(self.evaluar(), "fuente_no_vigente")
        self.assertEqual(row["bloqueos"], ["fuente_no_vigente"])
        self.assertEqual(row["evaluado"], {"guion": False, "plan": False})
        self.reader.assert_not_called()
        self.media.assert_not_called()

    def test_sin_fuente_ni_decision_no_atribuye_defectos_de_guion_o_plan(self):
        self.dia["propuestas"] = []
        self.dia["decisiones"]["propuestas"] = {}
        row = self.candidato(self.evaluar())
        self.assertFalse(row["elegible"])
        self.assertEqual(row["bloqueos"], ["fuente_no_vigente", "aprobacion_incompleta"])
        self.assertEqual(row["evaluado"], {"guion": False, "plan": False})
        self.reader.assert_not_called()
        self.resolver.assert_not_called()
        self.media.assert_not_called()

    def test_decision_ausente_no_evalua_guion_ni_plan_aunque_existan_locales(self):
        self.dia["decisiones"]["propuestas"] = {}
        row = self.bloqueado(self.evaluar(), "aprobacion_incompleta")
        self.assertEqual(row["bloqueos"], ["aprobacion_incompleta"])
        self.assertEqual(row["evaluado"], {"guion": False, "plan": False})
        self.reader.assert_not_called()
        self.media.assert_not_called()

    def test_tira_sin_resolver_no_se_evalua_ni_puede_ser_elegible(self):
        for fallo in (ValueError("detalle privado"), None):
            with self.subTest(resolucion=type(fallo).__name__):
                self.resolver.side_effect = fallo if isinstance(fallo, Exception) else None
                self.resolver.return_value = fallo
                row = self.bloqueado(self.evaluar(), "lectura_no_confirmada")
                self.assertEqual(row["bloqueos"], ["lectura_no_confirmada"])
                self.assertEqual(row["evaluado"], {"guion": False, "plan": False})
                self.media.assert_not_called()

    def test_fuente_retirada_no_autoriza_reintento(self):
        self.dia["propuestas"][0]["origen"] = "retirada-por-direccion"
        row = self.candidato(self.evaluar())
        self.assertFalse(row["elegible"])
        self.assertTrue(set(row["bloqueos"]) & {"fuente_no_vigente", "fuente_retirada"})

    def test_fuente_duplicada_no_acredita_vigencia_unica(self):
        self.dia["propuestas"].append(copy.deepcopy(self.prop))
        self.bloqueado(self.evaluar(), "fuente_no_vigente")

    def test_no_actual_bloquea_aunque_el_corte_se_planeo_antes(self):
        self.dia["decisiones"]["propuestas"][self.pid]["laminas"][1] = "no"
        self.bloqueado(self.evaluar(), "aprobacion_incompleta")

    def test_borrado_actual_no_hereda_la_aprobacion_anterior(self):
        for lamina in self.tira["laminas"]:
            lamina["estado"] = "aprobada"
        self.dia["decisiones"]["propuestas"][self.pid] = {"laminas": ["si", ""],
                                                            "firmas": [True, True]}
        self.bloqueado(self.evaluar(), "aprobacion_incompleta")

    def test_formato_imagen_no_se_convierte_en_video(self):
        self.tira["formato"] = "carrusel"
        self.bloqueado(self.evaluar(), "formato_no_video")

    def test_guion_con_lamina_ausente_no_esta_completo(self):
        self.tira["guion"].append({"n": 3})
        self.bloqueado(self.evaluar(), "guion_incompleto")

    def test_guion_vacio_o_con_numeros_duplicados_no_esta_completo(self):
        for guion in ([], [{"n": 1}, {"n": 1}], [{"n": "ilegible"}]):
            with self.subTest(guion=guion):
                self.tira["guion"] = guion
                self.bloqueado(self.evaluar(), "guion_incompleto")

    def test_candidato_y_plan_truncados_no_acreditan_tira_completa(self):
        self.cola[0]["evidencia"]["laminas"] = copy.deepcopy(self.laminas[:1])
        self.plan["evidencia"]["laminas"] = copy.deepcopy(self.laminas[:1])
        self.bloqueado(self.evaluar(), "guion_incompleto")

    def test_plan_con_otro_id_no_acredita_el_corte_fallido(self):
        self.plan["id"] = self.familia + ":corte:completo:ffffffff"
        self.bloqueado(self.evaluar(), "plan_no_coincide")

    def test_plan_con_otra_huella_no_hereda_identidad_del_corte(self):
        self.plan["evidencia"]["laminas"][1]["huella"] = "ffffffff"
        self.bloqueado(self.evaluar(), "plan_no_coincide")

    def test_plan_con_otra_fuente_no_acredita_mismo_id(self):
        self.plan["evidencia"]["de"] = "otra-propuesta-privada"
        self.bloqueado(self.evaluar(), "plan_no_coincide")

    def test_plan_con_id_duplicado_no_acredita_identidad_unica(self):
        self.planner.return_value = ([self.plan, copy.deepcopy(self.plan)], [])
        self.bloqueado(self.evaluar(), "plan_no_coincide")

    def test_id_de_corte_no_puede_usar_dependencias_de_otra_familia(self):
        otra_familia = "otra-familia-sintetica"
        self.cola[0]["pieza"] = otra_familia
        for dependencia in self.cola[1:]:
            dependencia["pieza"] = otra_familia
            dependencia["id"] = otra_familia + ":" + dependencia["id"].split(":", 1)[1]
        self.bloqueado(self.evaluar(), "plan_no_coincide")
        self.media.assert_not_called()

    def test_campos_del_plan_deben_coincidir_con_descriptor_del_corte(self):
        for field, value in (("pieza", "otra-familia-sintetica"),
                             ("etapa", "voz"), ("item", "1")):
            with self.subTest(field=field):
                self.plan.clear()
                self.plan.update(copy.deepcopy(self.corte))
                self.plan["estado"] = "pendiente"
                self.plan[field] = value
                self.media.reset_mock()
                self.bloqueado(self.evaluar(), "plan_no_coincide")
                self.media.assert_not_called()

    def test_candidato_y_plan_no_pueden_compartir_descriptor_incoherente_con_id(self):
        for field, value in (("pieza", "otra-familia-sintetica"), ("item", "1")):
            with self.subTest(field=field):
                self.cola[0] = copy.deepcopy(self.corte)
                self.plan.clear()
                self.plan.update(copy.deepcopy(self.corte))
                self.cola[0][field] = self.plan[field] = value
                self.plan["estado"] = "pendiente"
                self.media.reset_mock()
                self.bloqueado(self.evaluar(), "plan_no_coincide")
                self.media.assert_not_called()

    def test_plan_con_lamina_faltante_adicional_o_duplicada_no_coincide(self):
        for laminas in (self.laminas[:1],
                        self.laminas + [{"item": "3", "huella": "12345678"}],
                        self.laminas + [self.laminas[0]]):
            with self.subTest(laminas=laminas):
                self.plan["evidencia"]["laminas"] = copy.deepcopy(laminas)
                self.bloqueado(self.evaluar(), "plan_no_coincide")

    def test_plan_recibe_cola_sin_candidatos_y_conserva_todo_lo_demas(self):
        veto = {**copy.deepcopy(self.corte), "id": "corte-ubicacion-vetada",
                "evidencia": {**self.corte["evidencia"], "error": "ubicacion_vetada"}}
        otro = {"id": "otro-fallo", "etapa": "escena", "estado": "fallo"}
        self.cola.extend([veto, otro])
        before = copy.deepcopy(self.cola)
        self.assertTrue(self.candidato(self.evaluar())["elegible"])
        self.planner.assert_called_once()
        args = self.planner.call_args.args
        self.assertEqual(args, (self.dia, self.dependencias + [veto, otro], self.reglas, self.cat))
        self.assertEqual(self.cola, before)

    def test_dependencia_con_otra_version_no_suple_id_exacto(self):
        self.cola[1]["id"] = self.familia + ":escena:1:ffffffff"
        self.bloqueado(self.evaluar(), "dependencias_incompletas")

    def test_dependencia_existente_sin_hecho_bloquea(self):
        self.cola[1]["estado"] = "fallo"
        self.bloqueado(self.evaluar(), "dependencias_incompletas")

    def test_id_exacto_no_acredita_campos_incoherentes_de_dependencia(self):
        for field, value in (("pieza", "otra-familia-sintetica"),
                             ("etapa", "voz"), ("item", "2")):
            with self.subTest(field=field):
                self.cola[1] = copy.deepcopy(self.dependencias[0])
                self.cola[1][field] = value
                self.media.reset_mock()
                self.bloqueado(self.evaluar(), "dependencias_incompletas")
                self.media.assert_not_called()

    def test_medio_perdido_o_md5_distinto_bloquean_sin_exponer_detalle(self):
        for detalle in ("archivo_perdido", "badMD5:identificador-privado-sintetico"):
            with self.subTest(detalle=detalle):
                self.media.return_value = {"ok": False, "codigo": detalle}
                report = self.evaluar()
                self.bloqueado(report, "medio_no_confirmado")
                self.assertNotIn(detalle, json.dumps(auditoria.resumen_publico(report)))

    def test_snapshot_sin_acuse_bloquea(self):
        self.snapshot.return_value = False
        self.bloqueado(self.evaluar(), "snapshot_sin_acuse")

    def test_ventana_ambigua_no_acredita_elegibilidad(self):
        report = self.evaluar(ventana_estable=False)
        self.assertFalse(report["ventana_estable"])
        self.bloqueado(report, "ventana_cambio")

    def test_evaluar_no_muta_entradas_ni_produce_trabajos(self):
        before = copy.deepcopy((self.cola, self.dia, self.tira, self.reglas, self.cat))
        self.evaluar()
        self.assertEqual((self.cola, self.dia, self.tira, self.reglas, self.cat), before)

    def test_resumen_publico_solo_tiene_conteos_y_codigos_constantes(self):
        self.media.return_value = {"ok": False, "codigo": "payload-privado-sintetico"}
        report = self.evaluar()
        public = auditoria.resumen_publico(report)
        self.assertEqual(public, {
            "ok": True, "candidatos": 1, "elegibles": 0, "bloqueados": 1,
            "motivos": {"medio_no_confirmado": 1},
            "escrituras_negocio": 0, "produccion_ejecutada": 0,
        })
        encoded = json.dumps(public, ensure_ascii=False)
        for private in (self.pid, self.familia, self.corte["id"], "sintetico-1.png",
                        "nota privada", "payload-privado-sintetico", "diario privado"):
            self.assertNotIn(private, encoded)


class MediosRecibosYAcuseTests(unittest.TestCase):
    def setUp(self):
        self.sin_red = patch("requests.sessions.Session.request",
                             side_effect=AssertionError("la prueba no permite red ni POST"))
        self.sin_red.start()
        self.addCleanup(self.sin_red.stop)
        self.payload = b"medio-sintetico-inmutable"
        self.file_id = "drive_id_sintetico_123"
        self.md5 = hashlib.md5(self.payload).hexdigest()
        self.job = {"evidencia": {"drive_id": self.file_id, "md5": self.md5}}
        self.metadata = {"id": self.file_id, "md5Checksum": self.md5,
                         "size": str(len(self.payload)), "trashed": False}
        self.state = {"data_sha": "b" * 64, "parent_id": 4, "baseline": {}}
        self.receipt = {"schema": 1, "code_sha": "a" * 40, "data_sha": "b" * 64,
                        "snapshot_id": 4, "run_id": "7"}
        self.release_body = {
            "schema": 1, "kind": "yod-online-public-data", "repo": "fixture/sala",
            "state": "published", "source_sha": "a" * 40, "archive_sha256": "c" * 64,
            "data_sha": "b" * 64, "parent_id": 0, "asset_id": 11,
            "published_run": "7", "published_code_sha": "a" * 40,
        }
        self.release = {"id": 4, "draft": True, "body": json.dumps(self.release_body),
                        "assets": [{"id": 11, "name": "snapshot.zip"}]}

    @staticmethod
    def descarga(raw):
        def bajar(file_id, path):
            Path(path).write_bytes(raw)
            return Path(path)
        return bajar

    def snapshots_doble(self, body=None, release=None):
        snapshots = Mock()
        snapshots.state.return_value = self.state
        snapshots.head.return_value = "a" * 40
        snapshots.media_hash_for_receipt.return_value = None
        release = copy.deepcopy(self.release if release is None else release)
        if body is not None:
            release["body"] = json.dumps(body)
        def get(path, *args, **kwargs):
            if path == "pages":
                return {"html_url": "https://example.invalid/sala"}
            if path == "releases/4":
                return release
            raise AssertionError("lectura no prevista: " + path)
        snapshots.api.request.side_effect = get
        return snapshots

    def respuesta_recibo(self, receipt=None):
        response = Mock()
        response.read.return_value = json.dumps(self.receipt if receipt is None else receipt).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    def test_medio_exige_metadata_y_bytes_con_mismo_md5(self):
        response = Mock()
        response.json.return_value = self.metadata
        with patch.object(auditoria.drive, "_peticion", return_value=response) as request, \
             patch.object(auditoria.drive, "bajar", side_effect=self.descarga(self.payload)) as bajar:
            self.assertEqual(auditoria.verificar_medio(self.job), {"ok": True})
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertEqual(bajar.call_args.args[0], self.file_id)

    def test_metadata_correcta_no_acredita_bytes_alterados_del_mismo_tamano(self):
        response = Mock()
        response.json.return_value = self.metadata
        altered = b"X" * len(self.payload)
        with patch.object(auditoria.drive, "_peticion", return_value=response), \
             patch.object(auditoria.drive, "bajar", side_effect=self.descarga(altered)):
            self.assertEqual(auditoria.verificar_medio(self.job), {"ok": False})

    def test_recibo_vincula_codigo_datos_y_snapshot_antes_de_auditar(self):
        snapshots = self.snapshots_doble()
        response = self.respuesta_recibo()
        with patch.object(auditoria.urllib.request, "urlopen", return_value=response) as get:
            self.assertEqual(auditoria.confirmar_snapshot(snapshots), (self.state, self.receipt))
        snapshots.validate_release.assert_called_once_with(self.release, self.release_body)
        self.assertEqual({call.args[0] for call in snapshots.api.request.call_args_list},
                         {"releases/4", "pages"})
        self.assertEqual(get.call_args.args[0].get_method(), "GET")
        self.assertTrue(get.call_args.args[0].full_url.endswith("/version-online.json"))
        response.read.assert_called_once_with(32768)

    def test_recibo_de_medios_exige_el_pin_exacto_del_snapshot(self):
        for pin in (None, "e" * 64, "d" * 64):
            with self.subTest(pin=pin):
                snapshots = self.snapshots_doble()
                snapshots.media_hash_for_receipt.return_value = "d" * 64
                receipt = {**self.receipt}
                if pin is not None:
                    receipt["media_manifest_sha256"] = pin
                with patch.object(auditoria.urllib.request, "urlopen",
                                  return_value=self.respuesta_recibo(receipt)):
                    if pin == "d" * 64:
                        self.assertEqual(auditoria.confirmar_snapshot(snapshots),
                                         (self.state, receipt))
                    else:
                        with self.assertRaisesRegex(auditoria.AuditoriaError, "snapshot_sin_acuse"):
                            auditoria.confirmar_snapshot(snapshots)
    def test_recibo_ajeno_a_codigo_datos_o_snapshot_no_acredita_lectura(self):
        for field, value in (("code_sha", "c" * 40), ("data_sha", "d" * 64),
                             ("snapshot_id", 99), ("run_id", "no-numerico"),
                             ("run_id", "999")):
            with self.subTest(field=field):
                snapshots = self.snapshots_doble()
                response = self.respuesta_recibo({**self.receipt, field: value})
                with patch.object(auditoria.urllib.request, "urlopen", return_value=response):
                    with self.assertRaises(auditoria.AuditoriaError):
                        auditoria.confirmar_snapshot(snapshots)

    def test_release_sin_corrida_publicada_no_autoriza_recibo_autorreferente(self):
        body = {k: v for k, v in self.release_body.items() if k != "published_run"}
        snapshots = self.snapshots_doble(body=body)
        with patch.object(auditoria.urllib.request, "urlopen", return_value=self.respuesta_recibo()):
            with self.assertRaises(auditoria.AuditoriaError):
                auditoria.confirmar_snapshot(snapshots)
        snapshots.validate_release.assert_called_once()

    def test_release_publicada_debe_vincular_codigo_datos_e_identidad_del_padre(self):
        variants = [({**self.release_body, "published_code_sha": "f" * 40}, self.release),
                    ({**self.release_body, "published_run": "no-numerico"}, self.release),
                    ({**self.release_body, "data_sha": "d" * 64}, self.release),
                    ({**self.release_body, "state": "prepared"}, self.release),
                    (self.release_body, {**self.release, "id": 99})]
        for body, release in variants:
            with self.subTest(body=body, release_id=release["id"], draft=release["draft"]):
                snapshots = self.snapshots_doble(body=body, release=release)
                with patch.object(auditoria.urllib.request, "urlopen", return_value=self.respuesta_recibo()):
                    with self.assertRaises(auditoria.AuditoriaError):
                        auditoria.confirmar_snapshot(snapshots)
                snapshots.validate_release.assert_called_once()

    def test_release_sin_validacion_no_llega_a_leer_recibo(self):
        snapshots = self.snapshots_doble()
        snapshots.validate_release.side_effect = auditoria.AuditoriaError("snapshot_sin_acuse")
        with patch.object(auditoria.urllib.request, "urlopen") as get:
            with self.assertRaises(auditoria.AuditoriaError):
                auditoria.confirmar_snapshot(snapshots)
        snapshots.validate_release.assert_called_once_with(self.release, self.release_body)
        get.assert_not_called()

    def test_acuse_privado_relee_exactamente_los_bytes_subidos(self):
        report = {"candidatos": [{"id": "id-privado-sintetico", "elegible": False}]}
        captured = {}
        def subir(path, parent, name):
            captured.update(raw=Path(path).read_bytes(), parent=parent, name=name)
            return self.file_id
        def bajar(file_id, path):
            self.assertEqual(file_id, self.file_id)
            return self.descarga(captured["raw"])(file_id, path)
        with patch.dict(auditoria.os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}), \
             patch.object(auditoria.drive, "subir", side_effect=subir), \
             patch.object(auditoria.drive, "bajar", side_effect=bajar):
            auditoria.guardar_privado(report, "carpeta-privada-sintetica")
        self.assertEqual(captured["raw"], auditoria.canonical(report) + b"\n")
        self.assertEqual(captured["parent"], "carpeta-privada-sintetica")
        self.assertEqual(captured["name"], "SALA-AUDITORIA-FALLOS-123-2.json")

    def test_acuse_privado_con_bytes_distintos_no_declara_exito(self):
        with patch.dict(auditoria.os.environ, {"GITHUB_RUN_ID": "123"}), \
             patch.object(auditoria.drive, "subir", return_value=self.file_id), \
             patch.object(auditoria.drive, "bajar", side_effect=self.descarga(b"bytes-distintos")):
            with self.assertRaisesRegex(auditoria.AuditoriaError, "acuse_privado_no_confirmado"):
                auditoria.guardar_privado({"id": "privado"}, "carpeta-privada-sintetica")

    def test_main_confirma_ventana_y_acuse_sin_escrituras_de_negocio(self):
        snapshots = Mock()
        original_api = snapshots.api
        def bootstrap(*, lock):
            self.assertFalse(lock)
            self.assertIsInstance(snapshots.api, auditoria.ReadOnlyGitHub)
            with self.assertRaises(auditoria.AuditoriaError):
                snapshots.api.request("git/refs", {"ref": "rama-no-permitida"})
            original_api.request.assert_not_called()
        snapshots.bootstrap.side_effect = bootstrap
        snapshots.latest.return_value = ({"id": 4}, {})
        snapshots.main.return_value = snapshots.head.return_value = "a" * 40
        snapshots.fingerprint.return_value = self.state["baseline"]
        source = ({}, [], {"propuestas": [], "decisiones": {"propuestas": {}}}, {})
        report = {"schema": 1, "ventana_estable": True,
                  "candidatos": [{"id": "id-privado-sintetico", "elegible": True, "bloqueos": []}]}
        output = io.StringIO()
        def guardar(private, parent):
            self.assertEqual(parent, "carpeta-privada-sintetica")
            self.assertTrue(private["ventana_estable"])
            self.assertEqual(private["modo"], "solo_auditoria_sin_reencolar")
            with self.assertRaisesRegex(auditoria.AuditoriaError, "escritura_gas_prohibida"):
                auditoria.sala.post({"accion": "produccion"})
        with patch.object(auditoria.sala, "enmascarar_en_actions"), \
             patch.object(auditoria.sala, "post"), \
             patch.object(auditoria, "Snapshots", return_value=snapshots), \
             patch.object(auditoria, "confirmar_snapshot", return_value=(self.state, self.receipt)), \
             patch.object(auditoria, "fuentes", side_effect=[source, copy.deepcopy(source)]) as fuentes, \
             patch.object(auditoria, "evaluar", return_value=report), \
             patch.object(auditoria.produccion, "peticiones_abiertas", return_value=False), \
             patch.object(auditoria, "private_config", return_value=({}, "carpeta-privada-sintetica")), \
             patch.object(auditoria, "guardar_privado", side_effect=guardar) as save, \
             redirect_stdout(output):
            self.assertEqual(auditoria.main(), 0)
        self.assertEqual(fuentes.call_count, 2)
        save.assert_called_once()
        snapshots.bootstrap.assert_called_once_with(lock=False)
        public = json.loads(output.getvalue().removeprefix("SALA_AUDITORIA_FALLOS "))
        self.assertEqual(public["elegibles"], 1)
        self.assertEqual(public["escrituras_negocio"], 0)
        self.assertEqual(public["produccion_ejecutada"], 0)
        self.assertNotIn("id-privado-sintetico", output.getvalue())

    def test_main_no_confirma_si_falla_la_relectura_del_acuse_privado(self):
        snapshots = Mock()
        snapshots.latest.return_value = ({"id": 4}, {})
        snapshots.main.return_value = snapshots.head.return_value = "a" * 40
        snapshots.fingerprint.return_value = self.state["baseline"]
        source = ({}, [], {"propuestas": [], "decisiones": {"propuestas": {}}}, {})
        report = {"schema": 1, "ventana_estable": True, "candidatos": []}
        output = io.StringIO()
        with patch.object(auditoria.sala, "enmascarar_en_actions"), \
             patch.object(auditoria.sala, "post"), \
             patch.object(auditoria, "Snapshots", return_value=snapshots), \
             patch.object(auditoria, "confirmar_snapshot", return_value=(self.state, self.receipt)), \
             patch.object(auditoria, "fuentes", side_effect=[source, copy.deepcopy(source)]), \
             patch.object(auditoria, "evaluar", return_value=report), \
             patch.object(auditoria.produccion, "peticiones_abiertas", return_value=False), \
             patch.object(auditoria, "private_config", return_value=({}, "carpeta-privada-sintetica")), \
             patch.object(auditoria, "guardar_privado", side_effect=RuntimeError("SECRET_PAYLOAD_PRIVADO")), \
             redirect_stdout(output):
            self.assertEqual(auditoria.main(), 2)
        public = json.loads(output.getvalue().removeprefix("SALA_AUDITORIA_FALLOS "))
        self.assertFalse(public["ok"])
        self.assertEqual(public["fase"], "acuse")
        self.assertNotIn("SECRET_PAYLOAD_PRIVADO", output.getvalue())


class GitHubSoloLecturaTests(unittest.TestCase):
    def test_repositorio_se_expone_sin_ampliar_capacidad_de_escritura(self):
        delegate = Mock()
        delegate.repo = "yodesarrollomx/sala-edicion"
        api = auditoria.ReadOnlyGitHub(delegate)
        self.assertEqual(api.repo, delegate.repo)
        with self.assertRaises(AttributeError):
            api.repo = "otro/repositorio"
        with self.assertRaises(auditoria.AuditoriaError):
            api.request("releases", {"draft": False})
        delegate.request.assert_not_called()

    def test_get_implicitito_o_explicito_se_delega_como_get_sin_cuerpo(self):
        for method in (None, "GET"):
            with self.subTest(method=method):
                delegate = Mock()
                delegate.request.return_value = b"respuesta-sintetica"
                api = auditoria.ReadOnlyGitHub(delegate)
                self.assertEqual(api.request("releases/4", method=method, raw=True),
                                 b"respuesta-sintetica")
                delegate.request.assert_called_once()
                call = delegate.request.call_args
                self.assertEqual(call.args[0], "releases/4")
                self.assertEqual(call.kwargs.get("method"), "GET")
                self.assertIs(call.kwargs.get("raw"), True)
                self.assertTrue(len(call.args) == 1 or call.args[1] is None)
                self.assertIsNone(call.kwargs.get("body"))

    def test_metodos_de_escritura_se_rechazan_antes_del_delegado(self):
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            with self.subTest(method=method):
                delegate = Mock()
                api = auditoria.ReadOnlyGitHub(delegate)
                with self.assertRaises(auditoria.AuditoriaError):
                    api.request("git/refs", method=method)
                delegate.request.assert_not_called()

    def test_cuerpo_incluso_vacio_se_rechaza_antes_del_delegado(self):
        for body in ({}, {"sha": "contenido-privado-sintetico"}, b"", ""):
            for method in (None, "GET"):
                with self.subTest(body=body, method=method):
                    delegate = Mock()
                    api = auditoria.ReadOnlyGitHub(delegate)
                    with self.assertRaises(auditoria.AuditoriaError):
                        api.request("git/refs", body, method=method)
                    delegate.request.assert_not_called()

    def test_descarga_asset_delega_solo_el_get_existente(self):
        delegate = Mock()
        delegate.asset.return_value = b"snapshot-sintetico"
        api = auditoria.ReadOnlyGitHub(delegate)
        self.assertEqual(api.asset(11), b"snapshot-sintetico")
        delegate.asset.assert_called_once_with(11)
        delegate.request.assert_not_called()

    def test_upload_se_rechaza_antes_del_delegado(self):
        delegate = Mock()
        api = auditoria.ReadOnlyGitHub(delegate)
        with self.assertRaises(auditoria.AuditoriaError):
            api.upload({"id": 4}, b"snapshot-sintetico")
        delegate.upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
