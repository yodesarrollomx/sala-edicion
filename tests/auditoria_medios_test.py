"""La auditoría hidrata medios mediante el mismo transporte protegido sólo GET."""
import types
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
import auditar_fallos as auditoria
import snapshots_medios_test as mediafixture


class AuditoriaIntegracionMedios(unittest.TestCase):
    def test_snapshot_con_medios_se_hidrata_sin_ampliar_escrituras(self):
        fixture = mediafixture.MediaSnapshots()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        output = fixture.prepare()
        fixture.publish(output)
        fixture.s.release()
        def mutations():
            return len([c for c in fixture.api.media.calls
                        if c[1] is not None or c[2] not in (None, "GET")])
        writes = mutations()
        fixture.env["GITHUB_RUN_ID"] = "13"
        fixture.new_snapshot()
        delegate = types.SimpleNamespace(
            repo=fixture.api.repo,
            request=lambda path, method=None, raw=False: fixture.api.request(path, method=method),
            asset=fixture.api.asset,
        )
        fixture.s.api = auditoria.ReadOnlyGitHub(delegate)
        fixture.s.bootstrap(lock=False)
        self.assertEqual((fixture.root / "laminas/new/L1.png").read_bytes(),
                         mediafixture.public.PNG)
        self.assertEqual(mutations(), writes)
        with self.assertRaises(auditoria.AuditoriaError):
            fixture.s.api.request("releases", {"draft": False})

    def test_fuente_historica_solo_es_get_fresco_y_no_abre_recursos_arbitrarios(self):
        with patch.object(auditoria.sala, "get", return_value={"ok": True}) as get:
            self.assertEqual(auditoria.fresh("produccion"), {"ok": True})
            get.assert_called_once_with("produccion", fresco="1")
            with self.assertRaises(auditoria.AuditoriaError):
                auditoria.fresh("guardar")
            self.assertEqual(get.call_count, 1)
