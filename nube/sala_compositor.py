#!/usr/bin/env python3
"""El compositor: pone el texto de la lámina sobre la imagen, con el estilo de la casa.

1080×1350 (4:5) · foto a sangre · degradado negro abajo · texto blanco en Playfair Display
centrado · UNA palabra en dorado · «Yodesarrollo presenta» en itálica dorada arriba.
Reglas de lámina que aplica (docs/CRITERIOS-LAMINA.md): el texto nunca se come la lámina
(se parte en renglones y baja de tamaño antes de invadir la foto), y siempre sale la versión
ligera .jpg junto al .png (LA-LEY §3: al teléfono jamás le viaja un original).

La tipografía la baja el workflow (nube/.cache/fuentes); si no está, cae a una serif del
sistema y lo dice — nunca revienta por una fuente.
"""

import os
import pathlib
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ANCHO, ALTO = 1080, 1350
TINTA = (255, 255, 255)
ORO = (214, 184, 122)
CACHE = pathlib.Path(__file__).resolve().parent / '.cache' / 'fuentes'
RESPALDOS = ['/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
             '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf']
VACIAS = {'que', 'qué', 'como', 'cómo', 'para', 'pero', 'desde', 'hasta', 'sobre', 'entre',
          'este', 'esta', 'esos', 'esas', 'ellos', 'tiene', 'sabes', 'dicen', 'puede',
          'llegar', 'tienes', 'hacer', 'sabías', 'cuando', 'porque', 'todos', 'nadie'}
avisos = []


def _fuente(tam, italica=False):
    nombre = 'PlayfairDisplay-Italic[wght].ttf' if italica else 'PlayfairDisplay[wght].ttf'
    ruta = CACHE / nombre
    if ruta.is_file():
        f = ImageFont.truetype(str(ruta), tam)
        try:
            f.set_variation_by_name('Italic' if italica else 'Bold')
        except (OSError, ValueError):
            pass
        return f
    for r in RESPALDOS:
        if os.path.isfile(r):
            if 'sin Playfair' not in avisos:
                avisos.append('sin Playfair')
            return ImageFont.truetype(r, tam)
    return ImageFont.load_default()


def palabra_de_oro(texto):
    """La palabra que va en dorado: la última con peso (≥5 letras, no vacía) — así cae en
    «esquina», «negocio», «terreno», como en las láminas aprobadas."""
    palabras = re.findall(r"[\wáéíóúñüÁÉÍÓÚÑÜ]+", texto)
    for p in reversed(palabras):
        if len(p) >= 5 and p.lower() not in VACIAS:
            return p
    return palabras[-1] if palabras else ''


def _renglones(dib, texto, fuente, ancho_max):
    palabras, lineas, actual = texto.split(), [], ''
    for p in palabras:
        prueba = (actual + ' ' + p).strip()
        if dib.textlength(prueba, font=fuente) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def cubrir(imagen):
    """Llena 1080×1350 sin deformar (recorta lo que sobra, centrado un poco arriba: las
    caras y el terreno suelen estar en el tercio medio)."""
    im = imagen.convert('RGB')
    esc = max(ANCHO / im.width, ALTO / im.height)
    im = im.resize((round(im.width * esc), round(im.height * esc)), Image.LANCZOS)
    x = (im.width - ANCHO) // 2
    y = max(0, min(im.height - ALTO, int((im.height - ALTO) * 0.4)))
    return im.crop((x, y, x + ANCHO, y + ALTO))


def componer(imagen_origen, texto, destino_png, firma='Yodesarrollo presenta'):
    """Devuelve (ruta_png, ruta_jpg)."""
    base = cubrir(Image.open(imagen_origen))
    # degradado negro en el 45 % de abajo
    capa = Image.new('L', (1, ALTO), 0)
    inicio = int(ALTO * 0.52)
    for y in range(ALTO):
        a = 0 if y < inicio else min(235, int(235 * ((y - inicio) / (ALTO - inicio)) ** 0.8))
        capa.putpixel((0, y), a)
    negro = Image.new('RGB', (ANCHO, ALTO), (8, 8, 8))
    base = Image.composite(negro, base, capa.resize((ANCHO, ALTO)))
    dib = ImageDraw.Draw(base)

    margen = 90
    for tam in (64, 58, 52, 47, 42):
        f = _fuente(tam)
        lineas = _renglones(dib, texto, f, ANCHO - 2 * margen)
        if len(lineas) <= 3:
            break
    alto_linea = int(tam * 1.28)
    y = ALTO - 120 - alto_linea * len(lineas)
    oro = palabra_de_oro(texto)
    ya_oro = False
    for linea in lineas:
        ancho = dib.textlength(linea, font=f)
        x = (ANCHO - ancho) / 2
        for token in re.split(r'(\s+)', linea):
            limpio = re.sub(r"[^\wáéíóúñüÁÉÍÓÚÑÜ]", '', token)
            color = ORO if (not ya_oro and oro and limpio == oro and linea == _ultima_con(lineas, oro)) else TINTA
            if color == ORO:
                ya_oro = True
            dib.text((x, y), token, font=f, fill=color)
            x += dib.textlength(token, font=f)
        y += alto_linea
    dib.text((56, 52), firma, font=_fuente(30, italica=True), fill=ORO)

    destino_png = pathlib.Path(destino_png)
    destino_png.parent.mkdir(parents=True, exist_ok=True)
    base.save(destino_png, optimize=True)
    ligera = destino_png.with_suffix('.jpg')
    base.resize((720, 900), Image.LANCZOS).filter(ImageFilter.SHARPEN).save(ligera, quality=82)
    return destino_png, ligera


def _ultima_con(lineas, palabra):
    for linea in reversed(lineas):
        if palabra in linea:
            return linea
    return None


if __name__ == '__main__':
    import sys
    print(componer(sys.argv[1], sys.argv[2], sys.argv[3]), avisos)
