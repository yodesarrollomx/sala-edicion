"""La publicación cloud no habilita montaje sin recibo, hashes y acuse de GAS."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nube"))
import sala_cliente as sala
import sala_mesa as mesa
import sala_arranque as arranque


class MountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.tiras = self.root / "datos/tiras"
        self.tiras.mkdir(parents=True)
        self.plan = self.root / "plan.json"
        self.card = {"id": "prueba", "tipo": "laminas",
                     "laminas": ["laminas/prueba/L1.jpg"], "origen": "prueba técnica"}
        self.plan.write_text(json.dumps({"fecha": "2026-10-11", "cartas": [{
            "tira_id": "prueba", "familia": "prueba", "carta": self.card}]}))
        (self.tiras / "prueba.json").write_text('{"laminas":[]}')
        self.patches = [patch.dict(os.environ, {"SALA_PUBLICADOR_MODO": "snapshots"}),
                        patch.object(mesa, "PLAN", self.plan), patch.object(mesa, "TIRAS", self.tiras),
                        patch.object(mesa, "RAIZ", self.root), patch.object(mesa, "validar_nuevas_tomas"),
                        patch.object(arranque, "PLAN", self.plan), patch.object(arranque, "TIRAS", self.tiras)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_unpublished_image_mounts_nothing(self):
        with patch.object(mesa, "_snapshot_publicado", return_value=False), patch.object(sala, "post") as post:
            with self.assertRaises(sala.SalaError):
                mesa.montar()
            post.assert_not_called()

    def test_valid_image_but_unpublished_tira_mounts_nothing(self):
        def proof(path):
            return str(path).startswith("laminas/")
        with patch.object(mesa, "_snapshot_publicado", side_effect=proof), patch.object(sala, "post") as post:
            with self.assertRaises(sala.SalaError):
                mesa.montar()
            post.assert_not_called()

    def test_valid_publication_proposes_without_editor_approval(self):
        with patch.object(mesa, "_snapshot_publicado", return_value=True), \
             patch.object(sala, "post", return_value={"ok": True}) as post:
            self.assertEqual(mesa.montar(), 0)
            post.assert_called_once_with("proponer", fecha="2026-10-11",
                                         propuestas=[self.card], familia="prueba")
            self.assertNotIn("aprobada", self.card)

    def test_rejected_gas_response_never_confirms_mount(self):
        with patch.object(mesa, "_snapshot_publicado", return_value=True), \
             patch.object(sala, "post", return_value={"ok": False}):
            with self.assertRaises(sala.SalaError):
                mesa.montar()

    def test_arranque_without_proof_mounts_nothing(self):
        with patch.object(mesa, "_snapshot_publicado", return_value=False), patch.object(sala, "post") as post:
            with self.assertRaises(sala.SalaError):
                arranque.montar()
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
