"""Pintarrón tipográfico animado, render CPU en Actions. No es video generativo."""
import hashlib
import math
import pathlib
import subprocess
import textwrap
from PIL import Image, ImageDraw, ImageFont
from ._comun import MotorError, lamina_de

W, H, FPS = 720, 1280, 24


def frame(texto, t, duracion, variante=0):
    im = Image.new('RGB', (W, H), '#102523')
    d = ImageDraw.Draw(im)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    font = ImageFont.truetype(font_path, 36)
    small = ImageFont.truetype(font_path, 20)
    d.text((52, 65), 'YO DESARROLLO', font=small, fill='#a6bcb0')
    d.text((52, 103), 'PINTARRÓN · ANIMACIÓN', font=small, fill='#d8e6df')
    all_lines = textwrap.wrap(texto, width=29)
    pages = max(1, math.ceil(len(all_lines)/12))
    page = min(pages-1, int(t/duracion*pages))
    lines = all_lines[page*12:(page+1)*12]
    # Trazo y nodos progresivos; ningún dato ni volumen comercial se inventa.
    progress = min(1, t / max(.1, duracion * .65))
    points = [(70, 1050), (220, 970), (365, 1040), (520, 910), (650, 985)]
    if variante:
        points = [(x, 2000-y) for x,y in points]
    length = progress * (len(points)-1)
    for i in range(len(points)-1):
        f = max(0, min(1, length-i))
        a,b = points[i:i+2]
        end = (a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f)
        if f:
            d.line([a,end], fill='#dbb777', width=6)
            d.ellipse((a[0]-8,a[1]-8,a[0]+8,a[1]+8), fill='#dbb777')
    for i,line in enumerate(lines):
        alpha = max(0, min(1, (t-i*.09)*3))
        color = tuple(int(a+(b-a)*alpha) for a,b in zip((16,37,35),(240,237,225)))
        d.text((52, 260+i*48+int(12*(1-alpha))), line, font=font, fill=color)
    # Movimiento durante toda la voz, sin congelación de cola.
    x = 52 + int(616 * t / duracion)
    d.line((52, 1188, x, 1188), fill='#dbb777', width=4)
    d.ellipse((x-5,1183,x+5,1193), fill='#f0ede1')
    return im


def producir(trabajo, reglas, cat, salida, segundos):
    texto = lamina_de(trabajo).get('dice', '').strip()
    if not texto:
        raise MotorError('animación por código sin texto aprobado')
    salida = pathlib.Path(salida); salida.mkdir(parents=True, exist_ok=True)
    huella = hashlib.sha256(str(trabajo['id']).encode()).hexdigest()[:16]
    archivo = salida / ('codigo-' + huella + '.mp4')
    cmd = ['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
           '-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264',
           '-preset','veryfast','-crf','22','-pix_fmt','yuv420p','-movflags','+faststart',str(archivo)]
    try:
        with subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE) as p:
            for n in range(math.ceil(segundos*FPS)):
                p.stdin.write(frame(texto,n/FPS,segundos,int(huella,16)%2).tobytes())
            p.stdin.close()
            error = p.stderr.read()
            if p.wait(timeout=60):
                raise MotorError('ffmpeg no pudo renderizar animación por código')
    except (OSError, subprocess.SubprocessError) as e:
        raise MotorError('render de animación por código falló') from e
    return archivo
