import datetime as dt
import importlib.util
from pathlib import Path
import unittest

ruta = Path(__file__).resolve().parents[1] / "nube/cola_salud.py"
spec = importlib.util.spec_from_file_location("cola_salud", ruta)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
AHORA = dt.datetime(2026, 10, 8, 3, 0, tzinfo=dt.timezone.utc)

def t(id, fecha, etapa="corte", estado="corriendo", evidencia='{}'):
    return dict(id=id, actualizado=fecha, estado=estado, etapa=etapa,
                evidencia=evidencia)

class ColaSaludTests(unittest.TestCase):
    def test_formats_real_google_sheets(self):
        for f in ("2026-09-30 9:12:28", "2026-09-30T09:12:28",
                  "2026-09-30 09:12:28",
                  "Sat Sep 12 2026 15:30:53 GMT-0700 (hora de México)"):
            with self.subTest(fecha=f):
                self.assertIsNotNone(mod.fecha_utc(f))
        self.assertEqual(mod.fecha_utc("2026-09-30 9:12:28").hour, 16)
        self.assertIsNone(mod.fecha_utc("ilegible"))

    def test_siete_abandonos_no_se_reproducen(self):
        fechas = [("apodo:prospectos:3:v1","prospectos","2026-09-12 20:56:53"),
                  ("apodo:prospectos:5:v1","prospectos","2026-09-12 21:09:01"),
                  ("apodo:escena:2:v1","escena","2026-09-14 14:26:28"),
                  ("apodo:corte:completo:a","corte","2026-09-22 21:27:57"),
                  ("apodo:corte:completo:b","corte","2026-09-30 9:12:28"),
                  ("dato-servilleta-3:corte:completo:a","corte","2026-09-27 18:00:57"),
                  ("tu-terreno-tus-reglas:corte:completo:a","corte","2026-09-28 13:58:47")]
        cambios, ilegibles = mod.propuestas_rescate(
            [t(i,f,e) for i,e,f in fechas], {"escena","corte","voz","prospecto"}, AHORA)
        self.assertEqual(len(cambios), 7)
        self.assertEqual(ilegibles, [])
        self.assertTrue(all(c["estado"] == "fallo"
                            and c["evidencia"]["requiere_revision"] for c in cambios))

    def test_conserva_evidencia_y_nota(self):
        cambios,_ = mod.propuestas_rescate(
            [t("x:voz:1:a","2026-10-07 12:00:00",evidencia='{"md5":"abc","nota":"revisar"}')],
            {"voz"}, AHORA)
        self.assertEqual(cambios[0]["evidencia"]["md5"], "abc")
        self.assertEqual(cambios[0]["evidencia"]["nota"], "revisar")

    def test_no_toca_trabajos_vivos_ni_terminados(self):
        cambios,_=mod.propuestas_rescate(
            [t("vivo","2026-10-07 19:00:00"),
             t("hecho","2026-09-20 10:00:00",estado="hecho")],
            {"corte"},AHORA)
        self.assertEqual(cambios, [])

    def test_no_inventa_fecha_ni_identidad(self):
        cambios,ilegibles=mod.propuestas_rescate(
            [t("x","fecha rota"),t("","2026-09-20 10:00:00")],{"corte"},AHORA)
        self.assertFalse(cambios)
        self.assertEqual(len(ilegibles),2)

    def test_no_reanuda_aunque_estaba_autorizada(self):
        cambios,_=mod.propuestas_rescate(
            [t("x","2026-10-07 12:00:00")],{"corte"},AHORA)
        self.assertEqual(cambios[0]["estado"],"fallo")
        self.assertTrue(cambios[0]["evidencia"]["requiere_revision"])

if __name__=="__main__":
    unittest.main()
