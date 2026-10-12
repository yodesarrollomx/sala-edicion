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
        self.assertEqual(got["_produccion"]["fuentes_no_vigentes"], 1)

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
    def run_wave(self, root, pid, original, decision, cap=1):
        def fake_images(slug, reference, lam, note, rules, queue, folder, count):
            folder.mkdir(parents=True, exist_ok=True)
            stem = folder / ("L%d-1" % lam["n"])
            stem.with_suffix(".png").write_bytes(b"imagen-sintetica")
            stem.with_suffix(".jpg").write_bytes(b"vista-sintetica")
            return [{"src": str(stem.with_suffix(".jpg").relative_to(root)),
                     "original": str(stem.with_suffix(".png").relative_to(root)),
                     "motor": "doble", "dice": "Texto válido nuevo",
                     "huella": hashlib.md5(b"imagen-sintetica").hexdigest()}], []
        d = day([{"id": pid, "laminas": ["laminas/a.jpg"]}], {pid: decision})
        rules = {"mesa_tope_laminas": str(cap), "mesa_tomas_por_lamina": "1"}
        def get(resource, **kw):
            return {"reglas": rules} if resource == "reglas" else {"cola": []}
        with patch.object(sys, "argv", ["mesa", "--producir"]), \
             patch.object(mesa, "RAIZ", root), \
             patch.object(mesa, "TIRAS", root / "datos" / "tiras"), \
             patch.object(mesa, "PLAN", root / "plan.json"), \
             patch.object(mesa, "contexto_produccion", return_value=d), \
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

if __name__ == "__main__":
    unittest.main()
