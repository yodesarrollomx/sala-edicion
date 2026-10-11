import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nube"))
import medios_reconexion as m

AUDIO = b"RIFF" + (48).to_bytes(4, "little") + b"WAVE" + b"fixture-audio" * 4

def fixture():
    c = {"job_id": "demo:voz:1:abcdef12", "source_drive_id": "fixture-source-123",
         "source_revision_id": "fixture-revision-123", "new_drive_id": "fixture-copy-one",
         "md5": hashlib.md5(AUDIO).hexdigest(), "sha256": hashlib.sha256(AUDIO).hexdigest(),
         "bytes": len(AUDIO), "storage_verified": True, "queue_reconnected": False}
    row = {"id": c["job_id"], "pieza": "demo", "etapa": "voz", "item": "1",
           "motor": "kokoro", "estado": "hecho", "prioridad": 5, "bloqueado_por": "",
           "creado": "2026-01-01", "actualizado": "2026-01-02", "pidio": "productor",
           "evidencia": {"md5": c["md5"], "drive_id": c["source_drive_id"],
                         "duracion_s": 2.5, "ruta_local": "/tmp/fixture.wav",
                         "version": "fixture-version", "durable": True,
                         "metadatos": {"conservar": ["uno", "dos"]}}}
    return c, row

def report():
    c, _ = fixture()
    other = dict(c, job_id="demo:voz:1:abcdef34", new_drive_id="fixture-copy-two")
    return {"queue_writes": 0, "decisions_changed": False, "social_publications": 0,
            "copies": [c, other],
            "retained_revisions": [{"file_id": c["source_drive_id"],
                "revision_id": c["source_revision_id"], "md5": c["md5"], "keep_forever": True}]}

class FakeQueue:
    def __init__(self, row):
        self.row = copy.deepcopy(row)
        self.calls = []
    def read(self, job):
        if self.row["id"] != job:
            raise AssertionError("wrong identity")
        return copy.deepcopy(self.row)
    def write(self, **kw):
        self.calls.append(copy.deepcopy(kw))
        self.row["evidencia"] = json.dumps(kw["filas"][0]["evidencia"])
        self.row["actualizado"] = "2026-01-03"
        return {"ok": True, "actualizadas": 1, "creadas": 0, "ignoradas": []}

class ReconexionTest(unittest.TestCase):
    def setUp(self):
        self.c, self.row = fixture()

    def test_report_requires_two_original_verified_copies(self):
        self.assertEqual(len(m.validate_report(report())), 2)

    def test_report_duplicate_identity_is_rejected(self):
        r = report(); r["copies"][1]["job_id"] = r["copies"][0]["job_id"]
        with self.assertRaisesRegex(m.ReconexionError, "objetivo_duplicado"):
            m.validate_report(r)

    def test_revision_must_be_retained_with_original_md5(self):
        r = report(); r["retained_revisions"][0]["md5"] = "0" * 32
        with self.assertRaisesRegex(m.ReconexionError, "revision_original_no_acreditada"):
            m.validate_report(r)

    def test_report_does_not_expand_to_other_targets(self):
        r = report(); r["copies"].append(dict(r["copies"][0]))
        with self.assertRaisesRegex(m.ReconexionError, "objetivos_ambiguos"):
            m.validate_report(r)

    def test_corrupt_audio_cannot_be_linked(self):
        bad = AUDIO[:-1] + b"x"
        with self.assertRaisesRegex(m.ReconexionError, "archivo_hash_diferente"):
            m.prepare(self.row, self.c, bad)

    def test_same_length_other_file_cannot_be_linked(self):
        with self.assertRaisesRegex(m.ReconexionError, "archivo_hash_diferente"):
            m.prepare(self.row, self.c, b"x" * len(AUDIO))

    def test_matching_digest_still_requires_wav_format(self):
        data = b"x" * len(AUDIO)
        c = dict(self.c, md5=hashlib.md5(data).hexdigest(), sha256=hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(m.ReconexionError, "archivo_no_es_wav"):
            m.verify_audio(c, data)

    def test_original_job_md5_must_match_recovered_revision(self):
        self.row["evidencia"]["md5"] = "0" * 32
        with self.assertRaisesRegex(m.ReconexionError, "evidencia_original_hash_diferente"):
            m.prepare(self.row, self.c, AUDIO)

    def test_active_job_is_never_relinked(self):
        self.row["estado"] = "corriendo"
        with self.assertRaisesRegex(m.ReconexionError, "trabajo_no_terminado"):
            m.prepare(self.row, self.c, AUDIO)

    def test_unknown_original_reference_is_rejected(self):
        self.row["evidencia"]["drive_id"] = "fixture-unrelated-123"
        with self.assertRaisesRegex(m.ReconexionError, "referencia_original_diferente"):
            m.prepare(self.row, self.c, AUDIO)

    def test_malformed_evidence_is_never_replaced(self):
        self.row["evidencia"] = "{broken"
        with self.assertRaisesRegex(m.ReconexionError, "evidencia_invalida"):
            m.prepare(self.row, self.c, AUDIO)

    def test_duplicate_queue_row_is_ambiguous(self):
        with self.assertRaisesRegex(m.ReconexionError, "fila_no_unica"):
            m.unique_row([self.row, copy.deepcopy(self.row)], self.c["job_id"])

    def test_only_file_reference_and_provenance_change(self):
        original = copy.deepcopy(self.row["evidencia"])
        self.row["evidencia"] = json.dumps(original)
        p = m.prepare(self.row, self.c, AUDIO)
        q = FakeQueue(self.row)
        after = m.apply(p, q.read, q.write)
        self.assertEqual(len(q.calls), 1)
        self.assertEqual(set(q.calls[0]), {"op", "filas"})
        self.assertEqual(q.calls[0]["op"], "estado")
        self.assertEqual(set(q.calls[0]["filas"][0]), {"id", "evidencia"})
        ev = m.evidence(after)
        self.assertEqual(ev["drive_id"], self.c["new_drive_id"])
        for key, value in original.items():
            if key != "drive_id":
                self.assertEqual(ev[key], value)
        self.assertEqual(after["estado"], "hecho")
        self.assertEqual(after["motor"], "kokoro")

    def test_already_linked_original_is_idempotent(self):
        self.row["evidencia"]["drive_id"] = self.c["new_drive_id"]
        p = m.prepare(self.row, self.c, AUDIO)
        q = FakeQueue(self.row)
        self.assertEqual(m.apply(p, q.read, q.write), self.row)
        self.assertEqual(q.calls, [])

    def test_changed_row_prevents_write(self):
        p = m.prepare(self.row, self.c, AUDIO)
        q = FakeQueue(self.row); q.row["actualizado"] = "concurrent-update"
        with self.assertRaisesRegex(m.ReconexionError, "fila_cambio_antes_de_escribir"):
            m.apply(p, q.read, q.write)
        self.assertEqual(q.calls, [])

    def test_http_success_with_error_is_not_an_ack(self):
        p = m.prepare(self.row, self.c, AUDIO)
        q = FakeQueue(self.row)
        with self.assertRaisesRegex(m.ReconexionError, "escritura_sin_acuse"):
            m.apply(p, q.read, lambda **kw: {"ok": False, "error": "fixture"})

    def test_wrong_ack_count_is_not_confirmed(self):
        p = m.prepare(self.row, self.c, AUDIO)
        q = FakeQueue(self.row)
        with self.assertRaisesRegex(m.ReconexionError, "escritura_sin_acuse"):
            m.apply(p, q.read, lambda **kw: {"ok": True, "actualizadas": 0, "creadas": 0, "ignoradas": []})

    def test_changed_operational_field_after_write_is_reported(self):
        p = m.prepare(self.row, self.c, AUDIO); q = FakeQueue(self.row)
        def write(**kw):
            r = q.write(**kw); q.row["motor"] = "another-engine"; return r
        with self.assertRaisesRegex(m.ReconexionError, "fila_cambio_despues_de_escribir"):
            m.apply(p, q.read, write)

    def test_reference_without_matching_readback_is_not_confirmed(self):
        p = m.prepare(self.row, self.c, AUDIO); q = FakeQueue(self.row)
        def write(**kw):
            r = q.write(**kw); q.row["evidencia"] = "{}"; return r
        with self.assertRaisesRegex(m.ReconexionError, "evidencia_no_confirmada"):
            m.apply(p, q.read, write)

    def test_json_serialization_only_is_not_a_conflict(self):
        other = copy.deepcopy(self.row); other["evidencia"] = json.dumps(other["evidencia"])
        self.assertEqual(m.signature(other), m.signature(self.row))

if __name__ == "__main__":
    unittest.main()
