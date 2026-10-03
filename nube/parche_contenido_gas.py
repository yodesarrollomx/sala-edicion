"""Añade sólo la guardia revisada al código privado vigente, sin copiar el espejo."""
from pathlib import Path
import argparse


def aplicar(vigente, espejo):
    if 'function contenidoVetado_' in vigente or 'validarContenidoEntrada_' in vigente:
        raise ValueError('La fuente ya tiene una guardia: conciliar, no sobrescribir.')
    inicio = espejo.index('/* Chinche #49: contenido NUEVO.')
    fin = espejo.index('var _FECHAS = {};', inicio)
    funciones = espejo[inicio:fin]
    inicio = espejo.index('  // #49: validar antes de cachés')
    fin = espejo.index('  if (d && d.accion', inicio)
    compuerta = espejo[inicio:fin]
    ancla = "  var d; try { d = JSON.parse(e.postData.contents); } catch (err) { return json({ error: 'cuerpo ilegible' }); }\n"
    if vigente.count(ancla) != 1 or vigente.count('function doPost(e) {') != 1:
        raise ValueError('La fuente cambió; revisar anclas antes de aplicar.')
    resultado = vigente.replace(ancla, ancla + compuerta, 1)
    resultado = resultado.replace('function doPost(e) {', funciones + 'function doPost(e) {', 1)
    if resultado.replace(funciones, '', 1).replace(compuerta, '', 1) != vigente:
        raise ValueError('Cambios fuera de la guardia.')
    return resultado


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fuente', type=Path)
    parser.add_argument('salida', type=Path)
    args = parser.parse_args()
    espejo = Path(__file__).resolve().parents[1] / 'gas/Code.gs'
    resultado = aplicar(args.fuente.read_text(), espejo.read_text())
    with args.salida.open('x') as f:
        args.salida.chmod(0o600)
        f.write(resultado)
