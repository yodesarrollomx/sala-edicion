#!/usr/bin/env python3
"""Siembra en REGLAS los números nuevos que trae esta fase — SIN tocar `gas/Code.gs`
(INVIOLABLE 1: el repo es espejo, sembrar ahí no cambia nada en vivo).

**Ojo real, no supuesto:** a diferencia de `accion:'hojas'` (que sólo agrega lo que falte y
lo dice en su propio comentario), `accion:'regla'` en `gas/Code.gs` SOBREESCRIBE sin
preguntar cualquier nombre que ya exista (`doPost`, rama `regla`: `hr.getRange(fila,
2).setValue(...)` corre siempre que la fila exista, sin comparar valores). Si este script
mandara todos sus defaults en cada corrida, la segunda vez que Alejandro editara uno de estos
números a mano en el Sheet, la siguiente siembra se lo pisaría — exactamente lo que «Sembrar
es agregar lo que falte, jamás pisar lo que tú ya editaste» prohíbe.

Por eso este script LEE `recurso=reglas` primero y sólo manda `accion:'regla'` con las
llaves que de verdad faltan (no existen, o existen vacías) — la comprobación de «ya existe»
vive aquí, no en el GAS.
"""

import sys

import sala_cliente as sala

# Las reglas nuevas de esta fase, con su valor de arranque y su descripción — la misma
# lista que el plan aprobado (Fase D). Ninguna se manda si YA existe en el Sheet.
NUEVAS = {
    'nube_ejecuta_etapas': ('', 'qué etapas EJECUTA de verdad la nube (escena,voz,corte); '
                            'vacío = sólo encola, igual que productor_ejecuta_etapas para la Mac'),
    'nube_tope_minutos': (15, 'minutos máximos que corre el ejecutor por invocación del workflow'),
    'drive_raiz': ('', 'el id de la carpeta «YOD Editorial» en Drive — sin esto, la nube no '
                   'sube nada, sólo produce local (y sala_ejecutor lo dice cada vez)'),
    'escena_segundos': (5, 'segundos fijos por escena de video (regla 98, 14-sep)'),
    'escena_aire_s': (0.34, 'segundos que se restan del cupo por cambio de voz (regla 98)'),
    'animacion_lamina_entera': (1, 'anima la lámina entera, sin recortar (regla 100, 14-sep)'),
    'voz_motor': ('kokoro', 'el motor de voz vigente — Alejandro lo eligió a oído el 14-sep'),
    'voz_narrador': ('af_heart', 'voz de Kokoro para el rol narrador (mujer, "ella")'),
    'voz_vecino': ('am_adam', 'voz de Kokoro para el rol vecino (hombre, "el")'),
    'voz_seg_por_palabra': (0.3125, 'segundos por palabra a ritmo Kokoro (~16 palabras en 5s, regla 98)'),
    'escena_respaldo_camara': (1, 'si wan_hf no puede, anima la lámina con un movimiento de '
                               'cámara (ffmpeg, gratis, siempre sale); 0 = esperar a wan_hf'),
    'imagen_motores': ('cloudflare,gemini', 'orden de los motores de imagen en la nube (gratis primero)'),
    'cerebro_modelo': ('gemini-2.5-flash-lite', 'modelo gratis que escribe las recetas de candidatas'),
    'cerebro_respaldo_modelo': ('gpt-4o-mini', 'respaldo de pago del cerebro, sólo si Gemini no contesta'),
    'cerebro_pago_tope_dia': (30, 'llamadas máximas al día al respaldo de pago (≈ centavos, < 1 USD)'),
    'escena_wan_hf_modelo': ('', 'el id del modelo en HuggingFace para animar con wan_hf — '
                             'vacío a propósito: no se adivina uno sin confirmar'),
}


def faltantes(reglas_actuales):
    return {k: v for k, (v, _desc) in NUEVAS.items()
           if k not in reglas_actuales or str(reglas_actuales[k]).strip() == ''}


def main():
    sala.enmascarar_en_actions()
    try:
        reglas_actuales = (sala.get('reglas') or {}).get('reglas') or {}
    except sala.SalaError as e:
        sala.avisar('✗ no pude leer REGLAS: %s' % e)
        return 2

    faltan = faltantes(reglas_actuales)
    if not faltan:
        sala.avisar('✓ las %d reglas de esta fase ya existen en el Sheet. Nada que sembrar.'
                    % len(NUEVAS))
        return 0

    sala.avisar('sembrando %d regla(s) que faltan: %s' % (len(faltan), ', '.join(sorted(faltan))))
    desc = {k: NUEVAS[k][1] for k in faltan}
    r = sala.post('regla', set=faltan, desc=desc)
    sala.avisar('✓ REGLAS: %s editada(s)/creada(s)' % r.get('editadas'))
    ya_estaban = set(NUEVAS) - set(faltan)
    if ya_estaban:
        sala.avisar('  (%d ya existían y NO se tocaron: %s)' % (len(ya_estaban), ', '.join(sorted(ya_estaban))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
