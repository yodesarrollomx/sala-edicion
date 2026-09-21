#!/usr/bin/env python3
"""La cascada de motores (regla 47), leída desde la hoja MOTORES y ejecutada desde la nube
para lo que SÍ es una API — nunca para lo que corre local en la Mac.

Columnas de MOTORES: `etapa · motor · encendido · tope_dia · costo · orden · nota`
(`gas/Code.gs`, `recurso=reglas`). Apagar un motor o cambiar su tope es un 1 por un 0 en el
Sheet: no se toca código ni se redespliega nada — la nube sólo LEE esa hoja.

**Motores locales, la nube los salta siempre**, no los apaga en el Sheet: `mflux` (imagen,
~6.5 min en la Mac) y `ltx_local` (escena, ~17 min, respaldo de wan_hf). Apagarlos ahí los
apagaría también PARA LA MAC, que es justo lo que no se quiere — la Mac los sigue necesitando.

**Kokoro no tiene fila en MOTORES todavía.** El GAS sólo expone `accion:'regla'` (edita
REGLAS) y `accion:'hojas'` (siembra MOTORES una vez, sin pisar lo editado) — no hay ninguna
acción que agregue una fila a MOTORES desde afuera, y agregarla exigiría tocar `gas/Code.gs`
y redesplegar el Apps Script, que es justo lo que INVIOLABLE 1 prohíbe hacer desde CI. Mientras
Alejandro no agregue esa fila a mano en el Sheet, Kokoro se gobierna aparte, por la REGLA
`voz_motor` (`docs/SALA-SISTEMA.md`, regla 99: «voz_motor=kokoro»): si dice «kokoro» (su valor
de fábrica aquí), se intenta PRIMERO, antes que la cascada de MOTORES para la etapa `voz`.
"""

import pathlib

import sala_cliente as sala

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Motores que sólo corren en la Mac. La nube los ve en la hoja, los respeta como encendidos
# (no los toca), pero nunca los ejecuta ella misma.
LOCALES = {'mflux', 'ltx_local'}

DEFAULTS = {
    'voz_motor': 'kokoro',      # lo que Alejandro eligió a oído el 14-sep, tras oír 5 motores
}


def _regla(reglas, nombre):
    if nombre in reglas and str(reglas[nombre]).strip() != '':
        return reglas[nombre]
    return DEFAULTS.get(nombre)


def _hoy_prefijo():
    return sala.hoy_hermosillo()               # 'YYYY-MM-DD', mismo formato que ahora() del GAS


def _tope_gastado(cola, etapa, motor):
    """Cuenta trabajos de HOY, de esa etapa y ese motor, en 'hecho' O 'corriendo' — un
    trabajo empezado ya gastó la cuota (regla 47), aunque no haya terminado."""
    hoy = _hoy_prefijo()
    n = 0
    for t in cola:
        if str(t.get('etapa')) != etapa:
            continue
        if str(t.get('motor') or '') != motor:
            continue
        if str(t.get('estado')) not in ('hecho', 'corriendo'):
            continue
        creado = str(t.get('creado') or '')
        if creado.startswith(hoy):
            n += 1
    return n


def motores_de(motores_resp, etapa, saltar_locales=True):
    """Los motores encendidos de una etapa, ordenados por `orden`. `saltar_locales=True`
    (el default para todo lo que la nube va a EJECUTAR) excluye mflux/ltx_local sin tocar el
    Sheet — se documenta con `nota` por qué se saltó."""
    filas = [m for m in (motores_resp or []) if str(m.get('etapa')) == etapa]
    filas = [m for m in filas if str(m.get('encendido')) not in ('0', '', 'False', 'false')]
    filas.sort(key=lambda m: m.get('orden', 99))
    if saltar_locales:
        filas = [m for m in filas if str(m.get('motor')) not in LOCALES]
    return filas


def elegir_motor(etapa, motores_resp, cola):
    """El primer motor encendido, no local, CON CUPO, en orden. `(motor, razon)` o
    `(None, razon)` si ninguno califica — nunca falla en silencio."""
    candidatos = motores_de(motores_resp, etapa)
    if not candidatos:
        locales = motores_de(motores_resp, etapa, saltar_locales=False)
        if locales:
            return None, ('sólo hay motores LOCALES encendidos para «%s» (%s): eso lo hace '
                          'la Mac, no la nube' % (etapa, ', '.join(m['motor'] for m in locales)))
        return None, 'ningún motor encendido para «%s» en la hoja MOTORES' % etapa
    for m in candidatos:
        tope = int(m.get('tope_dia') or 0)
        if tope <= 0:
            return m, 'sin tope diario'
        gastado = _tope_gastado(cola, etapa, m['motor'])
        if gastado < tope:
            return m, 'cupo %d/%d hoy' % (gastado, tope)
    return None, ('todos los motores de «%s» agotaron su tope_dia hoy (%s)'
                  % (etapa, ', '.join('%s %d/%d' % (m['motor'], _tope_gastado(cola, etapa, m['motor']),
                                                     int(m.get('tope_dia') or 0)) for m in candidatos)))


def elegir_motor_voz(reglas, motores_resp, cola):
    """Caso especial: Kokoro no vive en MOTORES (ver docstring del módulo). Se intenta primero
    si `voz_motor` lo pide; si no, o si Kokoro ya se descartó, cae a la cascada normal de
    MOTORES para `voz` (hoy: `gemini_tts`)."""
    preferido = str(_regla(reglas, 'voz_motor') or '').strip().lower()
    if preferido == 'kokoro':
        return {'motor': 'kokoro', 'etapa': 'voz', 'tope_dia': 0}, \
               'voz_motor=kokoro (REGLA, no vive en la hoja MOTORES — ver docstring)'
    return elegir_motor('voz', motores_resp, cola)


if __name__ == '__main__':                          # prueba de humo contra el /exec vivo
    import sys
    sala.enmascarar_en_actions()
    try:
        r = sala.get('reglas')
        cola = (sala.get('cola') or {}).get('cola') or []
    except sala.SalaError as e:
        sala.avisar('✗', e)
        sys.exit(2)
    reglas, motores = r.get('reglas') or {}, r.get('motores') or []
    # 'corte' no pasa por aquí: no es un menú de motores, es ffmpeg (sala_montador.py) — su
    # gobierno es `nube_ejecuta_etapas` + el horario quieto, no una fila de MOTORES.
    m, razon = elegir_motor('escena', motores, cola)
    sala.avisar('escena   -> %s (%s)' % ((m or {}).get('motor', '—'), razon))
    m, razon = elegir_motor_voz(reglas, motores, cola)
    sala.avisar('voz      -> %s (%s)' % ((m or {}).get('motor', '—'), razon))
