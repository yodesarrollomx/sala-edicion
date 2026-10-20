import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
import sala_cliente as sala
import sala_produccion as prod
import sala_productor as planner
import sala_mesa as mesa
from motores._comun import lamina_de

P = "pieza-nube-2026-10-08-ab12cd"


def day(props=None, decisions=None, date="2026-10-11"):
    return {"fecha": date, "dias": ["2026-10-08", "2026-10-11"],
            "propuestas": props or [], "decisiones": {"propuestas": decisions or {}}}


def card():
    return {"id": P, "laminas": ["laminas/a.jpg"], "tipo": "laminas"}


def tira(fmt="Reel", count=3):
    return {"pieza": "Pieza sintética", "pieza_slug": "pieza", "fecha": "2026-10-08",
            "formato": fmt, "decidir": [1], "mapa": {"1": 1},
            "guion": [{"n": n, "dice": "Texto %d" % n, "ve": "Figura neutra"}
                      for n in range(1, count + 1)],
            "laminas": [{"n": 1, "src": "laminas/vieja.png", "dice": "Texto viejo",
                         "estado": "rehecha", "candidatas": [
                             {"src": "laminas/a.jpg", "original": "laminas/a.png", "dice": "Texto A"},
                             {"src": "laminas/b.jpg", "original": "laminas/b.png", "dice": "Texto B"}]}]}


def yes():
    return {"laminas": ["si"], "notas": ["[toma elegida: 2]"]}


class ProductionReadTests(unittest.TestCase):
    def test_closed_card_is_recovered_with_current_decision_not_old_date(self):
        calls = []
        def getter(resource, **kw):
            calls.append(kw)
            return day([card()], {P: {"laminas": ["no"]}}, "2026-10-08") if kw.get("f") else day(decisions={P: yes()})
        got = prod.cargar(getter, lambda p: tira())
        self.assertEqual([p["id"] for p in got["propuestas"]], [P])
        self.assertEqual(got["decisiones"]["propuestas"][P], yes())
        self.assertEqual(got["_produccion"]["recuperadas"], 1)
        self.assertTrue(all(c["fresco"] == "1" for c in calls))

    def test_retired_source_is_not_recreated_from_local_tira(self):
        def getter(resource, **kw):
            return day(date=kw["f"]) if kw.get("f") else day(decisions={P: yes()})
        got = prod.cargar(getter, lambda p: tira())
        self.assertEqual(got["propuestas"], [])
        self.assertEqual(got["_produccion"]["fuentes_sin_acreditar"], 1)
        self.assertIsNone(got["_produccion"]["fuentes_no_vigentes"])

    def test_network_error_cannot_become_empty_aligned_queue(self):
        def getter(resource, **kw):
            if kw.get("f"):
                raise sala.SalaError("sin lectura")
            return day(decisions={P: yes()})
        with self.assertRaises(sala.SalaError):
            prod.cargar(getter, lambda p: tira())

    def test_ok_false_or_wrong_date_is_rejected(self):
        for response in [{"ok": False}, day(date="2026-10-07")]:
            def getter(resource, **kw):
                return response if kw.get("f") else day(decisions={P: yes()})
            with self.assertRaises(sala.SalaError):
                prod.cargar(getter, lambda p: tira())

    def test_selected_image_text_are_exact_and_original_does_not_change(self):
        original = tira()
        resolved = prod.resolver_tira(original, yes())
        self.assertEqual(resolved["laminas"][0]["src"], "laminas/b.png")
        self.assertEqual(resolved["laminas"][0]["dice"], "Texto B")
        self.assertEqual(resolved["laminas"][0]["estado"], "aprobada")
        self.assertEqual(original["laminas"][0]["src"], "laminas/vieja.png")

    def test_ambiguous_or_out_of_range_selection_is_blocked(self):
        for note in ["", "[toma elegida: 0]", "[toma elegida: 9]"]:
            with self.assertRaises(sala.SalaError):
                prod.resolver_tira(tira(), {"laminas": ["si"], "notas": [note]})

    def test_editor_veto_does_not_become_approval(self):
        got = prod.resolver_tira(tira(), {"laminas": ["no"], "notas": ["Corrección reciente"],
                                          "firmas": [[{"marca": "si"}, {"marca": "no"}]]})
        self.assertEqual(got["laminas"][0]["estado"], "rechazada")
        self.assertEqual(got["laminas"][0]["nota_previa"], "Corrección reciente")

    def test_explicit_clear_revokes_carried_approval(self):
        old = tira()
        old["laminas"][0]["estado"] = "aprobada"
        got = prod.resolver_tira(old, {"laminas": [None], "firmas": [[{"marca": None}]]})
        self.assertEqual(got["laminas"][0]["estado"], "pendiente")

    def test_duplicate_guion_numbers_cannot_open_cut(self):
        old = tira()
        old["guion"].append(old["guion"][0])
        with self.assertRaises(sala.SalaError):
            prod.guion_faltante(old)


class PlanningTests(unittest.TestCase):
    def test_legacy_script_never_opens_cut_but_keeps_approved_branches(self):
        for legacy in ('datos/guiones/SINTETICA-VIDEO.json', 'Guion de voz heredado'):
            t = tira(count=1)
            t['guion'] = legacy
            before = copy.deepcopy(t)
            jobs, log = self.plan(t)
            self.assertEqual({j['etapa'] for j in jobs}, {'escena', 'voz'})
            self.assertTrue(any('NO se abre: guion heredado' in line for line in log))
            self.assertEqual(t, before)

    def plan(self, t, queue=None, dec=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "laminas").mkdir()
            (root / "laminas" / "b.png").write_bytes(b"imagen-B-sintetica")
            with patch.object(planner, "tira_de", return_value=t), patch.object(planner, "RAIZ", root):
                return planner.planear(day([card()], {P: dec or yes()}), queue or [], {}, {})

    def test_first_approved_slide_opens_its_branches_and_never_short_cut(self):
        jobs, log = self.plan(tira())
        self.assertEqual({j["etapa"] for j in jobs}, {"escena", "voz"})
        self.assertEqual(len(jobs), 2)
        self.assertTrue(any("por producir" in l for l in log))

    def test_job_identity_matches_selected_png_and_voice_text(self):
        jobs, _ = self.plan(tira())
        expected = hashlib.md5(b"imagen-B-sintetica").hexdigest()[:8]
        for j in jobs:
            self.assertTrue(j["id"].endswith(":" + expected))
            self.assertEqual(j["evidencia"]["src"], "laminas/b.png")
            self.assertEqual(j["evidencia"]["dice"], "Texto B")
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            (folder / (P + ".json")).write_text(json.dumps(tira()))
            with patch("motores._comun.TIRAS", folder):
                self.assertEqual(lamina_de(jobs[0])["src"], "laminas/b.png")
                self.assertEqual(lamina_de(jobs[0])["dice"], "Texto B")

    def test_idempotent_second_pass_enqueues_nothing(self):
        first, _ = self.plan(tira())
        second, _ = self.plan(tira(), first)
        self.assertEqual(second, [])

    def test_carousel_is_not_silently_converted_to_video(self):
        jobs, _ = self.plan(tira("Carrusel"))
        self.assertEqual(jobs, [])

    def test_carried_approved_branch_advances_with_other_slides_unanswered(self):
        t = tira()
        t["laminas"][0].update(estado="aprobada", src="laminas/b.png", dice="Texto B", candidatas=[])
        t["laminas"].append({"n": 2, "src": "laminas/pendiente.png", "estado": "propuesta"})
        t["decidir"], t["mapa"] = [2], {"1": 2}
        jobs, _ = self.plan(t, dec={"laminas": [None]})
        self.assertEqual({j["item"] for j in jobs}, {"1"})
        self.assertEqual({j["etapa"] for j in jobs}, {"escena", "voz"})

    def test_whole_approved_piece_can_open_cut(self):
        t = tira(count=1)
        jobs, _ = self.plan(t)
        self.assertEqual({j["etapa"] for j in jobs}, {"escena", "voz", "corte"})


class MesaTests(unittest.TestCase):
    def test_legacy_script_keeps_existing_drafts_without_inventing_continuation(self):
        for legacy in ('datos/guiones/SINTETICA-VIDEO.json', 'Guion de voz heredado'):
            t = tira()
            t['guion'] = legacy
            t['laminas'].append({'n': 2, 'src': '', 'estado': 'pendiente', 'dice': 'Existente'})
            before = copy.deepcopy(t)
            with patch.object(mesa, 'decision_del_sheet', return_value=(yes(), ['laminas/a.jpg'])):
                opened = mesa.abiertas(P, t)
            self.assertEqual([item[0]['n'] for item in opened], [2])
            self.assertEqual(t, before)

    def test_invalid_visual_list_still_fails_instead_of_looking_complete(self):
        t = tira()
        t['guion'].append(t['guion'][0])
        with patch.object(mesa, 'decision_del_sheet', return_value=(yes(), ['laminas/a.jpg'])):
            with self.assertRaises(sala.SalaError):
                mesa.abiertas(P, t)

    def test_legacy_script_diagnostic_is_partial_and_only_contains_a_count(self):
        with tempfile.TemporaryDirectory() as td, patch.object(mesa, 'RAIZ', Path(td)), \
                patch.object(mesa.sala, 'avisar'):
            self.assertEqual(mesa.guardar_estado_mesa(0, 0, 0, 0,
                             seleccion={'tiras_con_guion_heredado': 2}), 'parcial')
            report = json.loads((Path(td) / 'datos/mesa-estado.json').read_text())
            self.assertEqual(report['seleccion']['tiras_con_guion_heredado'], 2)

    def test_current_rejection_note_wins_over_original_date(self):
        current = day([card()], {P: {"laminas": ["no"], "notas": ["Nota nueva"]}})
        with patch.object(mesa, "contexto_produccion", return_value=current):
            opened = mesa.abiertas(P, tira())
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0][1:], ("no", "Nota nueva"))

    def test_first_approval_creates_only_missing_guion_drafts(self):
        with patch.object(mesa, "decision_del_sheet", return_value=(yes(), ["laminas/a.jpg"])):
            opened = mesa.abiertas(P, tira())
        self.assertEqual([x[0]["n"] for x in opened], [2, 3])
        self.assertTrue(all(x[1] == "pendiente" for x in opened))
        self.assertTrue(all(x[0]["estado"] == "pendiente" for x in opened))

    def test_pending_new_candidates_are_not_rejected_by_old_note(self):
        t = tira()
        t["laminas"][0].update(marca_previa="no", nota_previa="Nota antigua")
        with patch.object(mesa, "decision_del_sheet", return_value=({}, ["laminas/a.jpg"])):
            self.assertEqual(mesa.abiertas(P, t), [])

    def test_candidates_never_shown_by_live_card_return_to_the_table(self):
        t = tira()
        t["laminas"].append({"n": 2, "src": "laminas/c.png", "estado": "rehecha",
                             "nota_previa": "Nota antigua",
                             "candidatas": [{"src": "laminas/c.png"}, {"src": "laminas/d.png"}]})
        with patch.object(mesa, "decision_del_sheet", return_value=({}, ["laminas/a.jpg"])):
            opened = mesa.abiertas(P, t)
        self.assertEqual([(x[0]["n"], x[1]) for x in opened], [(2, "sin_presentar")])
        self.assertEqual(len(opened[0][0]["candidatas"]), 2)

    def test_never_shown_takes_return_without_the_ones_the_gate_rejects(self):
        lam = {"n": 2, "estado": "rehecha", "src": "laminas/c.png", "candidatas": [
            {"motor": "cloudflare", "src": "laminas/c.png", "dice": "Texto limpio"},
            {"motor": "cloudflare", "src": "laminas/d.png", "dice": "En Hermosillo"}]}
        with patch.object(mesa.sala, "avisar"):
            kept = mesa.tomas_presentables(lam, {"contenido_ubicaciones_vetadas": "Hermosillo"})
        self.assertEqual([c["src"] for c in kept], ["laminas/c.png"])
        self.assertEqual(len(lam["candidatas"]), 2)

    def test_source_without_live_sheet_record_is_blocked(self):
        with patch.object(mesa, "decision_del_sheet", return_value=(None, None)):
            with self.assertRaises(sala.SalaError):
                mesa.abiertas(P, tira())

    def test_reference_for_following_slides_uses_the_approved_choice(self):
        resolved = prod.resolver_tira(tira(), yes())
        reference = mesa.referencia(resolved)
        self.assertEqual(reference["src"], "laminas/b.png")
        self.assertEqual(reference["dice"], "Texto B")

    def test_piece_with_open_request_does_not_produce_or_mount(self):
        with patch.object(sys, "argv", ["mesa", "--producir"]), \
             patch.object(prod, "peticiones_abiertas", return_value=True), \
             patch.object(mesa, "producir_tomas") as motor, patch.object(sala, "post") as post:
            self.assertEqual(mesa.main(), 0)
        motor.assert_not_called()
        post.assert_not_called()




class MesaIntegrationTests(unittest.TestCase):
    def run_wave(self, root, pid, original, decision, cap=1, variants=1):
        def fake_images(slug, reference, lam, note, rules, queue, folder, count):
            folder.mkdir(parents=True, exist_ok=True)
            stem = folder / ("L%d-1" % lam["n"])
            stem.with_suffix(".png").write_bytes(b"imagen-sintetica")
            stem.with_suffix(".jpg").write_bytes(b"vista-sintetica")
            return [{"src": str(stem.with_suffix(".jpg").relative_to(root)),
                     "original": str(stem.with_suffix(".png").relative_to(root)),
                     "motor": "doble", "dice": "Texto válido nuevo",
                     "huella": hashlib.md5(b"imagen-sintetica").hexdigest()} for _ in range(variants)], []
        d = day([{"id": pid, "laminas": ["laminas/a.jpg"]}], {pid: decision})
        rules = {"mesa_tope_laminas": str(cap), "mesa_tomas_por_lamina": "1"}
        def get(resource, **kw):
            return {"reglas": rules} if resource == "reglas" else {"cola": []}
        with patch.object(sys, "argv", ["mesa", "--producir"]), \
             patch.object(mesa, "RAIZ", root), \
             patch.object(mesa, "TIRAS", root / "datos" / "tiras"), \
             patch.object(mesa, "PLAN", root / "plan.json"), \
             patch.object(mesa, "contexto_produccion", return_value=d), \
             patch.object(mesa, "hidratar_tiras_activas", return_value=0), \
             patch.object(mesa, "tiras_por_pieza", return_value={"pieza": (pid, original)}), \
             patch.object(mesa, "publicadas", return_value=set()), \
             patch.object(mesa, "producir_tomas", side_effect=fake_images), \
             patch.object(prod, "peticiones_abiertas", return_value=False), \
             patch.object(sala, "get", side_effect=get):
            self.assertEqual(mesa.main(), 0)
        plan = json.loads((root / "plan.json").read_text())
        next_id = plan["cartas"][0]["tira_id"]
        return next_id, json.loads((root / "datos" / "tiras" / (next_id + ".json")).read_text())

    def test_two_limited_waves_preserve_approved_choice_and_unanswered_candidates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            pid, first = self.run_wave(root, P, tira(), yes())
            self.assertEqual(first["decidir"], [2])
            self.assertEqual(first["laminas"][0]["estado"], "aprobada")
            self.assertEqual(first["laminas"][0]["src"], "laminas/b.png")
            image2 = first["laminas"][1]["candidatas"][0]["src"]
            pid2, second = self.run_wave(root, pid, first, {})
            self.assertEqual(second["decidir"], [2, 3])
            self.assertEqual(second["laminas"][1]["candidatas"][0]["src"], image2)
            self.assertNotEqual(pid, pid2)
            self.assertTrue((root / image2).exists())
            self.assertEqual(prod.guion_faltante(second), [])
            self.assertTrue(all(l["estado"] != "aprobada" for l in second["laminas"][1:]))

    def test_two_corrections_same_day_never_overwrite_prior_images(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            _, first = self.run_wave(root, P, tira(), {"laminas": ["no"], "notas": ["Primera corrección"]})
            old_path = first["laminas"][0]["candidatas"][0]["src"]
            old_bytes = (root / old_path).read_bytes()
            _, second = self.run_wave(root, P, tira(), {"laminas": ["no"], "notas": ["Segunda corrección"]})
            new_path = second["laminas"][0]["candidatas"][0]["src"]
            self.assertNotEqual(old_path, new_path)
            self.assertEqual((root / old_path).read_bytes(), old_bytes)

    def test_unverified_historical_candidates_are_not_presented_as_new(self):
        t = tira()
        t["laminas"].append({"n": 2, "dice": "Historia conservada", "estado": "rehecha",
                             "src": "laminas/historia.png", "candidatas": [
                                 {"motor": "historia", "src": "laminas/historia.jpg",
                                  "dice": "Hermosillo"}]})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            _, result = self.run_wave(root, P, t, {"laminas": ["no"], "notas": ["Corrección vigente"]})
            self.assertEqual(result["decidir"], [1])
            self.assertEqual(result["laminas"][1], t["laminas"][1])



class RejectionSourceTests(unittest.TestCase):
    def test_rejection_reads_the_displayed_candidate_not_the_older_image(self):
        t = tira()
        got = prod.resolver_tira(t, {"laminas": ["no"], "notas": ["La imagen no cuadra con el texto"]},
                                {"laminas": ["laminas/a.jpg"]})
        self.assertEqual(got["laminas"][0]["src"], "laminas/a.png")
        self.assertEqual(got["laminas"][0]["dice"], "Texto A")
        self.assertEqual(t["laminas"][0]["src"], "laminas/vieja.png")

    def test_image_mismatch_note_preserves_displayed_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan = {"texto": "Texto que el cerebro quiso cambiar", "receta": "Figura neutra", "porque": "Imagen corregida"}
            lam = {"n": 1, "dice": "Texto aprobado visible", "ve": "Figura neutra"}
            with patch.object(mesa, "RAIZ", root), patch.object(mesa, "vetadas", return_value=[]), \
                 patch.object(mesa.cerebro, "lamina", return_value=(plan, "doble", [])), \
                 patch.object(mesa.imagen, "generar", return_value=(b"sintetico", "png", "doble", [])), \
                 patch("sala_compositor.componer") as compose:
                png, jpg = root / "nueva.png", root / "nueva.jpg"
                png.write_bytes(b"sintetico")
                compose.return_value = (png, jpg)
                candidates, _ = mesa.producir_tomas("pieza", {"pieza": "Sintética"}, lam,
                    "La imagen no cuadra con el texto", {"imagen_motores": "doble"}, [], root, 1)
            self.assertEqual(candidates[0]["dice"], "Texto aprobado visible")
            self.assertEqual(compose.call_args.args[1], "Texto aprobado visible")



class ProductionStatusTests(unittest.TestCase):
    def test_recent_saved_decisions_precede_old_alphabetical_backlog(self):
        old = "antigua-nube-2026-09-30-123"
        d = day(decisions={old: dict(yes(), heredada="2026-09-30"), P: yes()})
        order = mesa.piezas_por_prioridad({"a-vieja": (old, tira()), "z-reciente": (P, tira())}, d)
        self.assertEqual(order[0][0], "z-reciente")

    def test_second_wave_inherits_priority_of_its_saved_base(self):
        t = tira()
        t["base"] = P
        old = "antigua-nube-2026-09-30-123"
        d = day(decisions={old: dict(yes(), heredada="2026-09-30"), P: yes()})
        order = mesa.piezas_por_prioridad({"a-vieja": (old, tira()), "z-segunda": ("nueva-123", t)}, d)
        self.assertEqual(order[0][0], "z-segunda")

    def test_all_failed_images_fail_the_run_and_publish_blocked_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            d = day([card()], {P: yes()})
            with patch.object(sys, "argv", ["mesa", "--producir"]), \
                 patch.object(mesa, "RAIZ", root), patch.object(mesa, "TIRAS", root / "datos" / "tiras"), \
                 patch.object(mesa, "PLAN", root / "plan.json"), \
                 patch.object(mesa, "contexto_produccion", return_value=d), \
                 patch.object(mesa, "hidratar_tiras_activas", return_value=0), \
                 patch.object(mesa, "tiras_por_pieza", return_value={"pieza": (P, tira())}), \
                 patch.object(mesa, "publicadas", return_value=set()), \
                 patch.object(mesa, "producir_tomas", return_value=([], ["sin modelo disponible"])), \
                 patch.object(prod, "peticiones_abiertas", return_value=False), \
                 patch.object(sala, "get", side_effect=lambda r, **k: {"reglas": {}} if r=="reglas" else {"cola": []}):
                self.assertEqual(mesa.main(), 2)
            r = json.loads((root / "datos" / "mesa-estado.json").read_text())
            self.assertEqual(r["estado"], "bloqueado")
            self.assertEqual(r["generadas"], 0)
            self.assertEqual(r["fallidas"], 2)
            self.assertNotIn("nota", r)
            self.assertNotIn("propuestas", r)

    def test_partial_work_is_reported_partial_not_as_whole_success(self):
        with tempfile.TemporaryDirectory() as td, patch.object(mesa, "RAIZ", Path(td)):
            self.assertEqual(mesa.guardar_estado_mesa(2, 1, 3, 1), "parcial")
            r = json.loads((Path(td) / "datos" / "mesa-estado.json").read_text())
            self.assertEqual(r["estado"], "parcial")
            self.assertEqual(r["limite_pendiente"], 3)


class BrainAvailabilityTests(unittest.TestCase):
    def test_default_uses_live_light_alias_not_retired_model(self):
        import os
        from motores import cerebro
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sintetica"}), \
             patch.object(cerebro, "_post_json", return_value={"candidates": [
                 {"content": {"parts": [{"text": "respuesta"}]}}]}) as call:
            self.assertEqual(cerebro._gemini("sintético", {}), "respuesta")
        self.assertIn("/gemini-flash-lite-latest:generateContent", call.call_args.args[0])
        self.assertNotIn("2.5", call.call_args.args[0])

    def test_transient_primary_uses_verified_gemini_fallback(self):
        import os
        from motores import cerebro
        from motores._comun import MotorError
        effects = [MotorError("Gemini 503", intermitente=True),
                   {"candidates": [{"content": {"parts": [{"text": "respuesta"}]}}]}]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sintetica"}), \
             patch.object(cerebro, "_post_json", side_effect=effects) as call:
            self.assertEqual(cerebro._gemini("sintético", {}), "respuesta")
        self.assertEqual(call.call_count, 2)
        self.assertIn("gemini-3.6-flash", call.call_args.args[0])

    def test_thought_text_is_not_mixed_with_final_json(self):
        import os
        from motores import cerebro
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sintetica"}), \
             patch.object(cerebro, "_post_json", return_value={"candidates": [
                 {"content": {"parts": [{"thought": True, "text": "{\"razonamiento\":1}"},
                                       {"text": "{\"receta\":\"final\"}"}]}}]}):
            self.assertEqual(cerebro._json_de(cerebro._gemini("sintético", {})),
                             {"receta": "final"})

    def test_non_transient_authorization_error_is_not_bypassed(self):
        import os
        from motores import cerebro
        from motores._comun import MotorError
        with patch.dict(os.environ, {"GEMINI_API_KEY": "sintetica"}), \
             patch.object(cerebro, "_post_json", side_effect=MotorError("Gemini 403")) as call:
            with self.assertRaises(MotorError):
                cerebro._gemini("sintético", {})
        self.assertEqual(call.call_count, 1)

    def test_recorrido_does_not_repeat_mesa_with_the_same_run_id(self):
        wf = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "sala-recorrido.yml").read_text()
        self.assertEqual(wf.count("uses: ./.github/workflows/sala-mesa.yml"), 1)
        self.assertIn('"workflow","run","sala-recorrido.yml"', wf)
        self.assertIn('r.get("run_id")==os.environ["GITHUB_RUN_ID"]', wf)



class PublishedRecoveryTests(unittest.TestCase):
    def test_unmounted_new_tira_does_not_hide_active_parent(self):
        with tempfile.TemporaryDirectory() as td, patch.object(mesa, "TIRAS", Path(td)):
            (Path(td) / (P + ".json")).write_text(json.dumps(tira()))
            orphan = tira()
            orphan["base"] = P
            chosen = mesa.tiras_vigentes({"pieza": ("orphan-nube-2026-10-11-123", orphan)}, day([card()], {P: yes()}))
        self.assertEqual(chosen["pieza"][0], P)

    def test_new_generated_files_are_reused_without_new_image_calls(self):
        helper = MesaIntegrationTests()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            (root / "datos" / "tiras" / (P + ".json")).write_text(json.dumps(tira()))
            next_id, generated = helper.run_wave(root, P, tira(), yes())
            same_id, reused = helper.run_wave(root, P, tira(), yes())
            self.assertEqual(same_id, next_id)
            self.assertEqual(reused, generated)
            r = json.loads((root / "datos" / "mesa-estado.json").read_text())
            self.assertEqual(r["generadas"], 0)
            self.assertEqual(r["reutilizadas"], 1)
            self.assertEqual(r["limite_pendiente"], 1)

    def test_changed_approved_reference_creates_a_new_version(self):
        helper = MesaIntegrationTests()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "datos" / "tiras").mkdir(parents=True)
            first_id, first = helper.run_wave(root, P, tira(), yes())
            second_id, second = helper.run_wave(root, P, tira(), {"laminas": ["si"], "notas": ["[toma elegida: 1]"]})
            self.assertNotEqual(first_id, second_id)
            self.assertEqual(first["laminas"][0]["src"], "laminas/b.png")
            self.assertEqual(second["laminas"][0]["src"], "laminas/a.png")

    def test_snapshot_state_report_is_allowed_and_survives_archive_roundtrip(self):
        import snapshots_online as online
        raw = b'{"schema":1,"estado":"parcial","generadas":8}'
        prefixes = online.SALA_PATHS["mesa"]
        self.assertTrue(online.allowed("datos/mesa-estado.json", prefixes))
        data, manifest = online.encode_archive("yodesarrollomx/sala-edicion", "a"*40,
            {"datos/mesa-estado.json": raw}, [], prefixes)
        _, files = online.decode_archive(data, "yodesarrollomx/sala-edicion", prefixes)
        self.assertEqual(files["datos/mesa-estado.json"], raw)
        self.assertFalse(online.allowed("datos/otra-hoja-privada.json", prefixes))

    def test_montage_steps_receive_snapshot_identity_and_preserve_pipe_error(self):
        repo = Path(__file__).resolve().parents[1]
        for name, command in [("sala-mesa.yml", "sala_mesa.py --montar"),
                              ("sala-arranque.yml", "sala_arranque.py --montar")]:
            text = (repo / ".github" / "workflows" / name).read_text()
            step = next(s for s in text.split("      - name:") if command in s)
            self.assertIn("GH_TOKEN:", step)
            self.assertIn("set -o pipefail", step)

    def test_snapshot_read_error_is_explicit_not_missing_image(self):
        from snapshots_online import OnlineError
        class Fail:
            def __init__(self, *a): pass
            def file_is_published(self, p): raise OnlineError("no identity")
        with patch("snapshots_online.Snapshots", Fail), patch.object(mesa, "_snapshot_verifier", None):
            with self.assertRaises(sala.SalaError):
                mesa._snapshot_publicado("laminas/prueba.jpg")

if __name__ == "__main__":
    unittest.main()
