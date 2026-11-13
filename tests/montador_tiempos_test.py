"""Comprueba sobre media real que el audio siga a su escena y no se corte."""
import array
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"nube"))
import sala_montador as m
import sala_guion as g

@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"ffmpeg no disponible")
class TimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.job={"pieza":"prueba","evidencia":{"laminas":[{"item":"1","huella":"a"},{"item":"2","huella":"b"}]}}
        self.queue=[]
        for n,dur,huella in (("1",.6,"a"),("2",.1,"b")):
            scene=self.root/(n+".mp4")
            subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i",
                "color=c=red:s=32x48:r=30:d="+str(dur),"-c:v","libx264","-pix_fmt","yuv420p",str(scene)],check=True)
            voice=self.root/(n+".wav")
            samples=array.array("h",(int(12000*math.sin(2*math.pi*800*i/24000)) for i in range(4800)))
            with wave.open(str(voice),"wb") as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(24000)
                output.writeframes(samples.tobytes())
            for stage,path in (("escena",scene),("voz",voice)):
                self.queue.append({"id":"prueba:"+stage+":"+n+":"+huella,"estado":"hecho",
                                   "evidencia":{"ruta_local":str(path)}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_voice_joins_its_visual_scene_and_long_scene_is_not_extended(self):
        with patch.object(m,"ANCHO",64),patch.object(m,"ALTO",96),\
             patch("motores._comun.lamina_de",return_value={"dice":"Texto sintético"}),\
             patch.object(g,"cargar",return_value={}),\
             patch.object(g,"desde_lamina",return_value={"escenas":[]}),\
             patch.object(g,"partes_de",return_value=[("narrador","Texto sintético")]):
            path=m.ensamblar(self.job,{"audio_margen_s":.05,"audio_cola_s":.1},{},self.root,self.queue)
        self.assertAlmostEqual(m._duracion(path),.967,delta=.08)
        pcm=self.root/"resultado.wav"
        subprocess.run(["ffmpeg","-v","error","-y","-i",str(path),"-ac","1",
                        "-ar","24000","-c:a","pcm_s16le",str(pcm)],check=True)
        with wave.open(str(pcm),"rb") as w:
            samples=array.array("h",w.readframes(w.getnframes()))
        def rms(a,b):
            block=samples[int(a*24000):int(b*24000)]
            return math.sqrt(sum(x*x for x in block)/len(block))
        self.assertGreater(rms(.08,.15),2000)
        self.assertLess(rms(.4,.5),150)
        self.assertGreater(rms(.64,.74),2000)
        self.assertLess(rms(.84,.89),150)

    def test_real_video_is_trimmed_to_voice_and_never_freezes(self):
        long=self.root/'1.mp4'
        short=self.root/'2.mp4'
        with patch.object(m,'ANCHO',64),patch.object(m,'ALTO',96):
            duration=m._escena_a_cuadro(long,self.root/'trim.mp4',.3,video_real=True)
            self.assertAlmostEqual(.3,duration,delta=.04)
            with self.assertRaisesRegex(m.MontadorError,'sin congelar'):
                m._escena_a_cuadro(short,self.root/'bad.mp4',1.0,video_real=True)

    def test_negative_margins_stop_before_render(self):
        with self.assertRaises(m.MontadorError):
            m.ensamblar(self.job,{"audio_margen_s":-1},{},self.root,self.queue)

    def test_missing_source_media_never_builds_partial_cut(self):
        with self.assertRaises(m.MontadorError):
            m.ensamblar(self.job,{}, {},self.root,[])

if __name__=="__main__":
    unittest.main()
