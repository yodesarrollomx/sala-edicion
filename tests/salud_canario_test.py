import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"nube"))
import tempfile
import unittest
import salud_canario as canario

class CanaryTests(unittest.TestCase):
    def test_no_green_video_missing_audio(self):
        meta={"format":{"duration":"2"},"streams":[{"codec_type":"video","codec_name":"h264","width":1080,"height":1920}]}
        with self.assertRaises(ValueError):
            canario.video_correcto(meta,audio=True)

    def test_no_green_wrong_resolution_or_nonfinite(self):
        for duration,width in (("NaN",1080),("2",640)):
            with self.subTest(duration=duration,width=width):
                with self.assertRaises(ValueError):
                    canario.video_correcto({"format":{"duration":duration},"streams":[{"codec_type":"video","codec_name":"h264","width":width,"height":1920}]})

    def test_mismatch_cleans_only_new_file_and_fails(self):
        events=[]
        class Client:
            def asegurar_carpeta(self,*args): return "synthetic-folder"
            def subir(self,*args): return "new-probe-only"
            def bajar(self,fid,path):
                path.write_bytes(b"different");return path
            def retirar(self,fid): events.append(fid)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(canario.DriveProbeError):
                canario.probar_drive(Path(tmp),"synthetic-parent",Client())
        self.assertEqual(events,["new-probe-only"])

    def test_cleanup_failure_is_not_success(self):
        class Client:
            def asegurar_carpeta(self,*args): return "synthetic-folder"
            def subir(self,*args): return "new-probe-only"
            def bajar(self,fid,path):
                path.write_bytes(b"SALA canario aislado\n");return path
            def retirar(self,fid): raise RuntimeError("synthetic cleanup rejection")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(canario.DriveProbeError):
                canario.probar_drive(Path(tmp),"synthetic-parent",Client())

if __name__=="__main__":
    unittest.main()
