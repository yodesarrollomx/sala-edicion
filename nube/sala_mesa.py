#!/usr/bin/env python3
"""El montador de la mesa: lo que antes hacía `sala_publicar.py` en la Mac, ahora en la nube.

Para cada pieza viva toma su tira MÁS RECIENTE, le encima lo que los editores decidieron en el
Sheet (el Sheet manda: marcas y notas de `recurso=dia` del día en que se montó), y a cada lámina
que quedó en «no» (o que se quedó sin decidir) le prepara tomas nuevas que obedecen la nota:

  nota + texto + promesa → cerebro (Gemini; OpenAI con tope) → receta y, si la nota lo pide,
  texto nuevo → imagen (Cloudflare FLUX → Gemini) → compositor (texto de la casa) → tomas.

Luego escribe la tira nueva (la pieza COMPLETA, invariante 9: una carta nunca llega sola),
con `decidir`/`mapa` y las tomas en `candidatas`, y la carta con id NUEVO y
`origen: rehecha-de <tira anterior>` (invariante 16). Montar va aparte (`--montar`) para que
el workflow publique primero y la carta nunca llegue a la mesa sin su tira.

Lo que NO hace: decidir (INVIOLABLE 3), tocar una lámina aprobada, montar una pieza publicada.

Uso:
  python3 sala_mesa.py --simular          # dice qué haría; no gasta ni escribe
  python3 sala_mesa.py --producir         # genera tomas y escribe tiras/plan (no monta)
  python3 sala_mesa.py --montar           # lee el plan y hace accion:proponer
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys
import tempfile

import sala_cliente as sala
import sala_produccion as produccion
from motores import cerebro, imagen
from motores._comun import MotorError
from contenido_reglas import ContenidoVetado, exigir, normalizar, prohibidas, ubicaciones

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / 'datos'
TIRAS = DATOS / 'tiras'
PLAN = RAIZ / 'nube' / '.producido' / 'plan-mesa.json'
NO_PIEZA = re.compile(r'(corte|video|prueba|coherencia)', re.I)
DINERO = re.compile(r'(\$\s*\d|\d[\d.,]*\s*(pesos|mil|mdp|millones)\b|\bgratis\b)', re.I)


def _leer(p, defecto=None):
    try:
        return json.loads(pathlib.Path(p).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defecto


def fecha_de(t):
    fechas = [str(t.get('fecha') or '')]
    for lam in t.get('laminas') or []:
        fechas.append(str(lam.get('fecha') or ''))
        fechas += [str(v.get('fecha') or '') for v in lam.get('versiones') or []]
    return max(f for f in fechas if f) if any(fechas) else ''


def tiras_por_pieza():
    """{slug: (id, tira)} con la tira más reciente de cada pieza."""
    mejores = {}
    for ruta in TIRAS.glob('*.json'):
        if ruta.stem == 'index' or NO_PIEZA.search(ruta.stem):
            continue
        t = _leer(ruta, {})
        if not isinstance(t, dict) or not t.get('laminas'):
            continue
        slug = str(t.get('pieza_slug') or ruta.stem.split('-')[0])
        montada = (fechas_montada(ruta.stem) or [''])[-1]
        clave = (max(montada, fecha_de(t)), montada, ruta.stem)
        if slug not in mejores or clave > mejores[slug][0]:
            mejores[slug] = (clave, ruta.stem, t)
    return {s: (i, t) for s, (_, i, t) in mejores.items()}


def publicadas():
    """Slugs/títulos de piezas que ya salieron: «una publicada no vuelve»."""
    p = _leer(DATOS / 'piezas.json', {}) or {}
    e = _leer(DATOS / 'embudo.json', {}) or {}
    salieron = {str(x.get('pieza') or '').lower() for x in p.get('piezas') or []
                if str(x.get('etapa')) == 'publicada'}
    return salieron | {str(x.get('pieza') or '').lower() for x in e.get('piezas') or []}


def vetadas(slug):
    v = _leer(DATOS / 'vetados.json', {}) or {}
    out = []
    for clave in ('global', slug.upper()):
        for x in v.get(clave) or []:
            out.append(str(x.get('palabra') if isinstance(x, dict) else x))
    return list(dict.fromkeys(ubicaciones() + [x for x in out if x]))


def fechas_montada(pid):
    m = _leer(DATOS / 'manifiesto.json', {}) or {}
    return sorted(d for d, h in (m.get('historial') or {}).items()
                  if any(str(p.get('id')) == pid for p in (h or {}).get('propuestas') or []))


_contexto_produccion = None


def contexto_produccion():
    global _contexto_produccion
    if _contexto_produccion is None:
        _contexto_produccion = produccion.cargar()
    return _contexto_produccion


def decision_del_sheet(pid, fecha_tira):
    """La decisión vigente, aunque la carta ya no figure en la mesa visual."""
    dia = contexto_produccion()
    prop = next((p for p in dia["propuestas"] if p["id"] == pid), None)
    if prop is None:
        return None, None
    dec = dia["decisiones"]["propuestas"].get(pid) or {}
    return dec, prop.get("laminas")


from motores.politica_imagen import depurar_tira, para_revision, vetada, POLITICA


def abiertas(tid, t, leer_sheet=True):
    """Correcciones vigentes y continuación del guion tras aprobar la primera."""
    dec, srcs = decision_del_sheet(tid, fecha_de(t)) if leer_sheet else ({}, None)
    if leer_sheet and dec is None:
        raise sala.SalaError("la tira no tiene fuente vigente en el Sheet")
    work, retiradas = depurar_tira(produccion.resolver_tira(t, dec, {'laminas': srcs or []}))
    mapa = work.get("mapa") or {str(i + 1): n for i, n in
                                enumerate(work.get("decidir") or [])}
    marks = (dec or {}).get("laminas") or []
    notes = (dec or {}).get("notas") or []
    por_n = {int(mapa.get(str(i + 1), i + 1)): (str(mark or ""),
             str(notes[i] or "") if i < len(notes) else str((dec or {}).get("nota") or ""))
             for i, mark in enumerate(marks)}
    salida = []
    for lam in work["laminas"]:
        n = int(lam.get("n") or 0)
        mark, note = por_n.get(n, ("", ""))
        if lam.get("estado") == "aprobada":
            continue
        if lam.get("reemplazo_modelo") == POLITICA["revision"]:
            note = (note + " La imagen no cuadra con el texto. Sustituir el modelo retirado; conservar exactamente el texto visible.").strip()
            salida.append((lam, "reemplazar_modelo", note))
            continue
        # La nota del rechazo pertenece a su versión; no rechaza también
        # las nuevas candidatas que aún nadie ha revisado.
        if not mark and lam.get("candidatas"):
            if n in retiradas:
                salida.append((lam, "depurar_modelo", note))
            continue
        note = note or str(lam.get("nota_previa") or "")
        salida.append((lam, mark or "pendiente", note))
    first = next((l for l in work["laminas"] if str(l.get("n")) == "1"), None)
    if first and first.get("estado") == "aprobada":
        for lam in produccion.guion_faltante(work):
            lam.update(estado="pendiente", version=1, src="")
            salida.append((lam, "pendiente", ""))
    return salida


def portada(lam):
    """Lo que la carta enseña arriba: la toma A si la lámina trae tomas nuevas; si no, la
    versión vigente. Nunca la versión rechazada como si fuera la propuesta."""
    nuevas = [c for c in lam.get('candidatas') or [] if c.get('motor')]
    return (nuevas or [{}])[0].get('src') or lam['src']


def guardia(texto, veto):
    lugares = prohibidas(texto)
    if lugares:
        return 'usa ubicación vetada: %s' % ', '.join(lugares)
    lugares = {normalizar(v) for v in ubicaciones()}
    malas = [v for v in veto if v and normalizar(v) not in lugares and v.lower() in texto.lower()]
    if malas:
        return 'usa palabra vetada: %s' % ', '.join(malas)
    if DINERO.search(texto):
        return 'trae dinero o «gratis»'
    return ''


def validar_nuevas_tomas(tira, reglas=None):
    """Veta el contenido NUEVO sin alterar guiones, aprobaciones ni notas históricas.

    Solo las láminas indicadas en `decidir` son candidatas recién generadas.
    Revisar el guion entero bloquearía imágenes nuevas por texto antiguo ya
    guardado como historia (la Ley prohíbe modificar retrospectivamente ese dato).
    """
    numeros = {str(n) for n in tira.get('decidir') or []}
    if not numeros:
        raise sala.SalaError('la tira no trae láminas para revisión')
    encontradas = set()
    for lam in tira.get('laminas') or []:
        n = str(lam.get('n') or '')
        if n not in numeros:
            continue
        encontradas.add(n)
        candidatas = [c for c in lam.get('candidatas') or [] if c.get('motor')]
        if not candidatas:
            raise sala.SalaError('lámina %s sin tomas nuevas verificables' % n)
        if any(vetada(c) for c in candidatas):
            raise sala.SalaError('lámina %s contiene un modelo retirado' % n)
        exigir(candidatas, reglas, 'tomas nuevas L%s' % n)
    if numeros != encontradas:
        raise sala.SalaError('el mapa de láminas nuevas no coincide con la tira')
    return True


def referencia(t):
    """La lámina aprobada más temprana de la pieza: el mundo al que las demás se parecen
    (invariante 105: «todas tienen que parecerse a la primera lámina que aprobemos»)."""
    for lam in sorted(t.get('laminas') or [], key=lambda x: int(x.get('n') or 0)):
        if lam.get('estado') == 'aprobada':
            return lam
    return None


def contexto_visual(texto):
    """Una referencia histórica no vuelve a introducir ubicaciones o dinero vetados."""
    value = str(texto or '')
    for location in prohibidas(value):
        value = re.sub(re.escape(location), 'el lugar del proyecto', value, flags=re.I)
    return '' if prohibidas(value) or DINERO.search(value) else value

def producir_tomas(slug, t, lam, nota, reglas, cola, carpeta, n_tomas, solo_recibo=False):
    from sala_compositor import componer, avisos as avisos_comp
    veto = vetadas(slug)
    tomas, avisos = [], []
    ref = referencia(t)
    ref_txt = ('Lámina %s aprobada — referencia visual: %s' % (ref.get('n'), contexto_visual(ref.get('ve')))
               if ref and ref.get('n') != lam.get('n') else '')
    if not nota and ref_txt:
        nota = 'Que se parezca a la lámina %s aprobada: mismos personajes, mismo lugar, misma luz.' % ref.get('n')
    for k in range(1, n_tomas + 1):
        try:
            if 'hidream_demo' in str(reglas.get('imagen_motores') or 'hidream_demo').split(','):
                d, quien, av = cerebro.fotografia_guion(
                    str(lam.get('dice') or ''), contexto_visual(lam.get('ve')),
                    contexto_visual(nota), ref_txt, reglas, k)
            elif lam.get('reemplazo_modelo') == POLITICA['revision'] or solo_recibo:
                # Cambiar el generador no requiere reescribir el guion ni otra inferencia.
                # El modelo de imagen recibe el mensaje visible como autoridad de la escena.
                receta = (
                    "Create a high-end architectural editorial photograph for this existing Spanish caption: "
                    + json.dumps(str(lam.get('dice') or ''), ensure_ascii=False)
                    + ". Show the caption's meaning literally with a concrete action and physical objects: "
                    "site plans, architectural models, materials or the described work. "
                    "People must interact with those objects; a generic couple posing or looking at each other is insufficient. "
                    "Mexican architectural context, coherent professional full-frame 35mm photography, warm natural daylight, "
                    "restrained beige and terracotta palette, accurate perspective and anatomically correct faces and hands. "
                    "Keep all important subjects inside the central 4:5 region with space for the separate caption overlay. "
                    "The approved reference below guides characters, lighting and style, not an unrelated pose. "
                    + (ref_txt or "Consistent contemporary architectural documentary style.")
                    + " Context from the original description: " + contexto_visual(lam.get('ve'))
                    + ". Editor visual correction notes, for composition only: " + contexto_visual(nota)
                    + ". Output only the photograph, absolutely no text, letters, captions, signs, logos or watermarks.")
                d = {'texto': str(lam.get('dice') or ''), 'receta': receta,
                     'porque': 'Nueva fotografía desde el guion vigente; conserva exactamente el texto visible.'}
                quien, av = 'guion-vigente', []
            else:
                d, quien, av = cerebro.lamina(t.get('pieza') or slug, t.get('promesa'), lam.get('dice'),
                                              lam.get('ve'), nota, veto, reglas, cola, k, ref_txt,
                                              numero=lam.get('n'))
            avisos += av
            exigir(d, reglas, 'candidata')
            # Un desacuerdo explícito entre imagen y texto corrige la imagen;
            # no convierte la nota en permiso para reescribir el texto mostrado.
            solo_imagen = 'la imagen no cuadra con el texto' in normalizar(nota)
            texto = str(lam.get('dice') or '') if solo_imagen else d['texto']
            problema = guardia(texto, veto)
            if problema:
                avisos.append('toma %d: el texto propuesto %s; se queda el de la tira' % (k, problema))
                texto = str(lam.get('dice') or '')
                if guardia(texto, veto):
                    avisos.append('toma %d: el texto de la tira también %s — no se monta' % (k, guardia(texto, veto)))
                    continue
            exigir({'texto': texto}, reglas, 'texto elegido')
            reglas_imagen = dict(reglas, _imagen_request_id=hashlib.sha256(
                (str(carpeta.relative_to(RAIZ)) + ':L%d-%d' % (lam['n'], k)).encode()).hexdigest(),
                _imagen_solo_recibo=solo_recibo)
            datos, ext, motor, av2 = imagen.generar(d['receta'], reglas_imagen)
            avisos += av2
            with tempfile.NamedTemporaryFile(suffix='.' + ext) as tmp:
                tmp.write(datos)
                tmp.flush()
                png, jpg = componer(tmp.name, texto, carpeta / ('L%d-%d.png' % (lam['n'], k)))
            tomas.append({'src': str(jpg.relative_to(RAIZ)), 'original': str(png.relative_to(RAIZ)),
                          'titulo': chr(64 + k), 'texto': str(d.get('porque') or '')[:160],
                          'dice': texto, 'motor': motor, 'modelo': imagen.modelo_de(motor, reglas), 'cerebro': quien,
                          'generado_en': dt.datetime.now(dt.timezone.utc).isoformat(),
                          'run_id': __import__('os').environ.get('GITHUB_RUN_ID'),
                          'workflow': __import__('os').environ.get('GITHUB_WORKFLOW'),
                          'receta_sha256': reglas_imagen.get('_receta_proveedor_sha256') or hashlib.sha256(d['receta'].encode()).hexdigest(),
                          'recibo_imagen': reglas_imagen.get('_imagen_recibo_id'),
                          'huella': hashlib.md5(png.read_bytes()).hexdigest()})
        except imagen.ReciboNoConfirmado:
            avisos.append('RECIBO_NO_CONFIRMADO: toma aún pendiente, sin nueva generación')
            break
        except imagen.ServicioImagen as e:
            avisos.append('SERVICIO_IMAGEN_NO_DISPONIBLE: %s' % e)
            break
        except imagen.CupoImagen as e:
            avisos.append('CUPO_IMAGEN_AGOTADO: %s' % e)
            break
        except (MotorError, ContenidoVetado) as e:
            avisos.append('toma %d: %s' % (k, e))
    return tomas, avisos + avisos_comp




def hidratar_tiras_activas(dia, lector=None):
    """Recupera sólo fuentes publicadas que el backend vigente mantiene activas."""
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import PurePosixPath
    def remoto(path):
        req=urllib.request.Request('https://yodesarrollomx.github.io/sala-edicion/'+path,
                                   headers={'Cache-Control':'no-cache'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                raw=r.read(8*1024*1024+1)
            if len(raw)>8*1024*1024:
                raise ValueError('fuente demasiado grande')
            return raw
        except Exception as exc:
            raise sala.SalaError('fuente publicada sin confirmar') from exc
    lector=lector or remoto
    faltan=[p['id'] for p in dia.get('propuestas',[])
            if p.get('laminas') and not (TIRAS/(p['id']+'.json')).is_file()]
    if not faltan:
        return 0
    index=json.loads(lector('datos/tiras/index.json'))
    if not isinstance(index,list):
        raise sala.SalaError('índice publicado sin contrato')
    drafts={}
    paths=set()
    hashes={}
    for pid in faltan:
        if not produccion.PID.fullmatch(pid) or pid not in index:
            continue
        path='datos/tiras/'+pid+'.json'
        raw=lector(path)
        t=json.loads(raw)
        if (not isinstance(t,dict) or not isinstance(t.get('laminas'),list)
                or not t.get('laminas') or not t.get('pieza_slug')):
            raise sala.SalaError('tira publicada sin contrato')
        numbers=[l.get('n') for l in t['laminas']]
        if len(numbers)!=len(set(numbers)) or any(not isinstance(n,int) or n<1 for n in numbers):
            raise sala.SalaError('identidades de lámina inválidas')
        for lam in t['laminas']:
            candidates=lam.get('candidatas') or []
            refs=[lam.get('src')]+[c.get(k) for c in candidates for k in ('src','original')]
            for ref in refs:
                if not ref:
                    continue
                pp=PurePosixPath(str(ref))
                if (not str(ref).startswith('laminas/') or pp.is_absolute()
                        or '..' in pp.parts or pp.suffix.lower() not in ('.png','.jpg','.jpeg','.webp')):
                    raise sala.SalaError('ruta de imagen publicada no autorizada')
                paths.add(str(ref))
            for c in candidates:
                if c.get('original') and c.get('huella'):
                    hashes[c['original']]=str(c['huella'])
        drafts[path]=raw
    existing={p:(RAIZ/p).read_bytes() for p in paths if (RAIZ/p).is_file()}
    missing=sorted(paths-set(existing))
    with ThreadPoolExecutor(max_workers=6) as pool:
        downloaded=dict(zip(missing,pool.map(lector,missing)))
    files={**existing,**downloaded}
    for path,raw in files.items():
        if not raw.startswith((b'\x89PNG',b'\xff\xd8',b'RIFF')):
            raise sala.SalaError('archivo publicado sin formato de imagen')
        if path in hashes and hashlib.md5(raw).hexdigest()!=hashes[path]:
            raise sala.SalaError('huella de original publicado no coincide')
    for path,raw in {**downloaded,**drafts}.items():
        target=RAIZ/path
        if not target.resolve().is_relative_to(RAIZ.resolve()):
            raise sala.SalaError('ruta local no autorizada')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw)
    sala.avisar('fuentes publicadas activas recuperadas: %d tira(s)' % len(drafts))
    return len(drafts)


def tiras_vigentes(piezas, dia):
    """Seleccionar la fuente del Sheet, incluso si ya hay una versión sin montar."""
    live = {p["id"] for p in dia.get("propuestas", [])}
    result = {}
    for slug, (pid, t) in piezas.items():
        if pid in live:
            result[slug] = (pid, t)
            continue
        alternatives = []
        for source in live:
            raw = _leer(TIRAS / (source + ".json"), {}) or {}
            if str(raw.get("pieza_slug") or "") == slug:
                alternatives.append((source, raw))
        if alternatives:
            result[slug] = max(alternatives, key=lambda x: (fecha_de(x[1]), x[0]))
    return result


def referencias_aprobadas(tira):
    return sorted((str(l.get("n")), str(l.get("src") or ""), str(l.get("dice") or ""))
                  for l in tira.get("laminas", []) if l.get("estado") == "aprobada")


def piezas_por_prioridad(piezas, dia):
    """Primero decisiones recientes y la continuación de sus versiones."""
    decisions = (dia.get("decisiones") or {}).get("propuestas") or {}
    def priority(item):
        slug, (pid, t) = item
        date, seen = "", set()
        while pid and pid not in seen:
            seen.add(pid)
            d = decisions.get(pid) or {}
            if any(m in ("si", "no") for m in d.get("laminas", [])):
                date = max(date, str(d.get("heredada") or dia.get("fecha") or ""))
            pid = str(t.get("base") or "")
            if not pid or not produccion.PID.fullmatch(pid):
                break
            t = _leer(TIRAS / (pid + ".json"), {}) or {}
        return date, slug
    # Fecha descendente; desempate estable por slug, para no priorizar el alfabeto viejo.
    return sorted(piezas.items(), key=lambda x: x[0]) if not dia else sorted(
        sorted(piezas.items(), key=lambda x: x[0]),
        key=lambda x: priority(x)[0], reverse=True)


TIPOS_DIAGNOSTICO = ('idea', 'guion', 'eje', 'lamina', 'laminas', 'voz', 'escena',
                    'video', 'corte', 'copy', 'otros')
CAMPOS_SELECCION = ('propuestas_vivas', 'propuestas_con_laminas', 'fuentes_recuperadas',
                    'tiras_locales', 'tiras_vigentes', 'tiras_sin_fuente_vigente',
                    'tiras_con_fuente_reemplazada', 'tiras_fuera_filtro_pieza',
                    'tiras_excluidas_publicadas', 'tiras_sin_fuente_al_procesar',
                    'tiras_sin_laminas_abiertas', 'tiras_con_laminas_abiertas',
                    'laminas_abiertas', 'tiras_sin_laminas_listas',
                    'tiras_con_validacion_pendiente', 'tiras_preparadas')


def conteos_seleccion(dia, antes, vigentes, recuperadas=0, sin_sheet=False):
    """Sólo cantidades y categorías fijas: ningún ID, título o texto del backend."""
    report = {key: 0 for key in CAMPOS_SELECCION}
    props = dia.get('propuestas') or []
    types = {key: 0 for key in TIPOS_DIAGNOSTICO}
    for prop in props:
        tipo = prop.get('tipo')
        key = tipo if isinstance(tipo, str) and tipo in types else 'otros'
        types[key] += 1
    report.update({'fuente': 'sin_sheet' if sin_sheet else 'backend',
                   'propuestas_vivas': len(props),
                   'propuestas_por_tipo': types,
                   'propuestas_con_laminas': sum(bool(p.get('laminas')) for p in props),
                   'fuentes_recuperadas': recuperadas,
                   'tiras_locales': len(antes), 'tiras_vigentes': len(vigentes),
                   'tiras_sin_fuente_vigente': len(antes) - len(vigentes),
                   'tiras_con_fuente_reemplazada': sum(
                       antes[slug][0] != value[0] for slug, value in vigentes.items())})
    return report


def seleccion_publica(seleccion):
    """La salida admite únicamente contadores enteros y nombres definidos aquí."""
    def cantidad(value):
        return value if type(value) is int and value >= 0 else 0
    tipos = seleccion.get('propuestas_por_tipo')
    tipos = tipos if isinstance(tipos, dict) else {}
    return {**{key: cantidad(seleccion.get(key)) for key in CAMPOS_SELECCION},
            'fuente': seleccion.get('fuente') if seleccion.get('fuente') in ('backend', 'sin_sheet') else 'sin_confirmar',
            'propuestas_por_tipo': {key: cantidad(tipos.get(key)) for key in TIPOS_DIAGNOSTICO}}


def guardar_estado_mesa(generadas, fallidas, limitadas, cartas, reutilizadas=0, causa='', modelo_imagen=None, seleccion=None):
    state = "bloqueado" if fallidas and not generadas else (
        "parcial" if fallidas or limitadas else "al_dia")
    report = {"schema": 1, "estado": state,
              "revisado_en": dt.datetime.now(dt.timezone.utc).isoformat(),
              "code_sha": __import__("os").environ.get("GITHUB_SHA"),
              "run_id": __import__("os").environ.get("GITHUB_RUN_ID"),
              "generadas": generadas, "reutilizadas": reutilizadas, "fallidas": fallidas,
              "causa": causa, "modelo_imagen": modelo_imagen or imagen.MODELO_FLUX2,
              "limite_pendiente": limitadas, "cartas": cartas}
    if seleccion is not None:
        report['seleccion'] = seleccion_publica(seleccion)
    dest = RAIZ / "datos" / "mesa-estado.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    sala.avisar("estado Mesa:", json.dumps(report, ensure_ascii=False))
    return state


def main():
    ap = argparse.ArgumentParser(description='El montador de la mesa de la Sala.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--simular', action='store_true')
    g.add_argument('--producir', action='store_true')
    g.add_argument('--montar', action='store_true')
    g.add_argument('--montar-commit', action='store_true', help='nuevas tiras del commit que ya publicó Pages')
    ap.add_argument('--pieza', help='sólo esta pieza (slug)')
    ap.add_argument('--sin-sheet', action='store_true', help='no leer el Sheet (pruebas locales)')
    args = ap.parse_args()
    sala.enmascarar_en_actions()
    global _contexto_produccion
    _contexto_produccion = None
    if produccion.peticiones_abiertas():
        sala.avisar('PASO 0: peticiones abiertas; Mesa no produce ni monta.')
        return 0

    if args.montar:
        return montar()
    if args.montar_commit:
        return montar_desde_commit()

    reglas, cola = {}, []
    if not args.sin_sheet:
        try:
            reglas = (sala.get('reglas') or {}).get('reglas') or {}
            cola = (sala.get('cola') or {}).get('cola') or []
        except sala.SalaError as e:
            sala.avisar('✗ no pude leer REGLAS/COLA: %s — «no contestó» no es «no hay nada»' % e)
            return 2
    if not args.sin_sheet:
        try:
            contexto_produccion()
        except sala.SalaError:
            sala.avisar('fuente de decisiones sin confirmar; Mesa no produce.')
            return 2
    n_tomas = int(float(str(reglas.get('mesa_tomas_por_lamina') or 2)))
    tope = int(float(str(reglas.get('mesa_tope_laminas') or 8)))
    ya_salieron = publicadas()
    hoy = sala.hoy_hermosillo()
    plan, gastadas = [], 0
    generadas = fallidas = limitadas = reutilizadas = 0
    cupo_bloqueado = False
    servicio_bloqueado = False

    recuperadas = 0
    if not args.sin_sheet:
        recuperadas = hidratar_tiras_activas(contexto_produccion())
    piezas = tiras_por_pieza()
    piezas_antes = piezas
    if not args.sin_sheet:
        piezas = tiras_vigentes(piezas, contexto_produccion())
    dia_orden = contexto_produccion() if not args.sin_sheet else {}
    orden = piezas_por_prioridad(piezas, dia_orden)
    seleccion = conteos_seleccion(dia_orden, piezas_antes, piezas, recuperadas, args.sin_sheet)
    for slug, (tid, t) in orden:
        if args.pieza and slug != args.pieza:
            seleccion['tiras_fuera_filtro_pieza'] += 1
            continue
        nombre = str(t.get('pieza') or slug)
        if nombre.lower() in ya_salieron:
            seleccion['tiras_excluidas_publicadas'] += 1
            sala.avisar('· %s: ya publicada, no vuelve a la mesa' % nombre)
            continue
        if not args.sin_sheet:
            live = {p['id'] for p in contexto_produccion()['propuestas']}
            if tid not in live:
                seleccion['tiras_sin_fuente_al_procesar'] += 1
                continue
        pend = abiertas(tid, t, leer_sheet=not args.sin_sheet)
        if not pend:
            seleccion['tiras_sin_laminas_abiertas'] += 1
            sala.avisar('· %s (%s): todas sus láminas aprobadas — nada que rehacer' % (nombre, tid))
            continue
        seleccion['tiras_con_laminas_abiertas'] += 1
        seleccion['laminas_abiertas'] += len(pend)
        sala.avisar('▶ %s · tira %s · %d lámina(s) abiertas' % (nombre, tid, len(pend)))
        nueva_id = '%s-nube-%s-%s' % (slug, hoy, hashlib.md5(
            json.dumps({'base': tid, 'laminas': [(l['n'], m, n, l.get('src'), l.get('dice'))
                        for l, m, n in pend]}, ensure_ascii=False).encode()).hexdigest()[:6])
        carpeta = RAIZ / 'laminas' / nueva_id
        hecha = TIRAS / (nueva_id + '.json')
        dec_vigente, mostradas = decision_del_sheet(tid, fecha_de(t)) if not args.sin_sheet else ({}, None)
        vigente, _ = depurar_tira(produccion.resolver_tira(t, dec_vigente, {'laminas': mostradas or []}))
        if hecha.is_file() and referencias_aprobadas(_leer(hecha, {}) or {}) != referencias_aprobadas(vigente):
            # La referencia cambió después de generar: versión nueva, sin pisar la anterior.
            nueva_id += '-' + hashlib.sha256(json.dumps(referencias_aprobadas(vigente)).encode()).hexdigest()[:6]
            carpeta = RAIZ / 'laminas' / nueva_id
            hecha = TIRAS / (nueva_id + '.json')
        if hecha.is_file() and not para_revision(_leer(hecha, {}) or {}):
            nueva_id += '-' + hashlib.sha256(POLITICA['revision'].encode()).hexdigest()[:6]
            carpeta = RAIZ / 'laminas' / nueva_id
            hecha = TIRAS / (nueva_id + '.json')
        if hecha.is_file() and not args.simular:
            # Idempotente: la tira de hoy con estas mismas notas ya se produjo (y se revisó);
            # montar no vuelve a gastar cuota ni cambia las tomas que el editor va a ver.
            previa = _leer(hecha, {}) or {}
            validar_nuevas_tomas(previa, reglas)
            reutilizadas += 1
            limitadas += len(produccion.guion_faltante(previa))
            sala.avisar('   ↺ la tira %s ya existe: se reusa sin volver a producir' % nueva_id)
            plan.append({'familia': slug, 'tira_id': nueva_id, 'carta': {
                'id': nueva_id, 'titulo': previa.get('titulo'), 'tipo': 'laminas',
                'laminas': [portada(next(l for l in previa['laminas'] if l['n'] == n))
                            for n in previa.get('decidir') or []],
                'opciones': [], 'video': None, 'origen': previa.get('origen')}})
            continue
        tira = vigente
        decidir = []
        for lam, marca, nota in pend:
            sala.avisar('   L%s · %s · nota vigente de %d caracteres' %
                        (lam.get('n'), marca, len(nota or '')))
            destino = next((l for l in tira['laminas'] if l.get('n') == lam.get('n')), None)
            if destino is None:
                destino = dict(lam)
            destino['marca_previa'], destino['nota_previa'] = marca, nota
            if args.simular:
                decidir.append(lam['n'])
                continue
            if marca == 'depurar_modelo':
                destino['candidatas'] = lam['candidatas']
                destino['src'] = lam.get('src') or lam['candidatas'][0]['src']
                destino['estado'] = 'rehecha'
                destino['produccion_guardados'] = 1
                destino['fecha'] = hoy
                decidir.append(lam['n'])
                sala.avisar('   ↺ modelo retirado depurado; se conservan las tomas permitidas')
                continue
            solo_recibo = cupo_bloqueado
            if gastadas >= tope:
                limitadas += 1
                sala.avisar('   ⏸ tope de %d láminas por corrida; ésta queda para mañana' % tope)
                continue
            if marca != 'no' and str(reglas.get('mesa_remontar_sin_decidir') or '0') == '1' \
                    and destino.get('candidatas'):
                sala.avisar('   ↺ nunca se decidió: se vuelve a montar con sus tomas')
                decidir.append(lam['n'])
                continue
            if solo_recibo:
                tomas, avisos = producir_tomas(slug, tira, lam, nota, reglas, cola, carpeta, n_tomas, solo_recibo=True)
            else:
                tomas, avisos = producir_tomas(slug, tira, lam, nota, reglas, cola, carpeta, n_tomas)
            gastadas += 1
            servicio_bloqueado = servicio_bloqueado or any(str(a).startswith('SERVICIO_IMAGEN_NO_DISPONIBLE:') for a in avisos)
            cupo_bloqueado = cupo_bloqueado or servicio_bloqueado or any(str(a).startswith('CUPO_IMAGEN_AGOTADO:') for a in avisos)
            for a in avisos:
                sala.avisar('     ⚠ %s' % a)
            if not tomas:
                if solo_recibo:
                    limitadas += 1
                    sala.avisar('   ⏸ sin recibo confirmado para L%s; permanece pendiente' % lam['n'])
                    continue
                fallidas += 1
                sala.avisar('   ✗ sin tomas para L%s: se queda pendiente' % lam['n'])
                continue
            if destino not in tira['laminas']:
                tira['laminas'].append(destino)
            destino['src'] = tomas[0]['src']
            destino.pop('reemplazo_modelo', None)
            destino['estado'] = 'rehecha'
            generadas += 1
            destino['produccion_guardados'] = 1
            destino['candidatas'] = tomas
            destino['fecha'] = hoy
            decidir.append(lam['n'])
        if not decidir:
            seleccion['tiras_sin_laminas_listas'] += 1
            continue
        # Un lote parcial no oculta las candidatas aún sin responder del lote anterior.
        decidir = sorted(set(decidir) | {l['n'] for l in tira['laminas']
                         if l.get('estado') != 'aprobada' and l.get('candidatas')
                         and l.get('produccion_guardados') == 1})
        tira.update({'decidir': decidir, 'mapa': {str(i + 1): n for i, n in enumerate(decidir)},
                     'titulo': '%s · láminas para revisión (%d)' % (nombre, len(decidir)),
                     'nota': 'La tira conserva lo aprobado. Revisa las láminas señaladas: muestran '
                             'su continuación y las correcciones con tus notas. Elige con «Ésta».',
                     'origen': 'rehecha-de %s' % tid, 'fecha': hoy, 'base': tid})
        # Los textos anteriores se conservan como historia; la compuerta revisa
        # exclusivamente las tomas recién producidas y sus textos visibles.
        try:
            validar_nuevas_tomas(tira, reglas)
        except (ContenidoVetado, sala.SalaError) as e:
            seleccion['tiras_con_validacion_pendiente'] += 1
            sala.avisar('⏸ %s: las tomas nuevas requieren corrección; %s' % (nombre, e))
            continue
        carta = {'id': nueva_id, 'titulo': tira['titulo'], 'tipo': 'laminas',
                 'laminas': [portada(next(l for l in tira['laminas'] if l['n'] == n)) for n in decidir],
                 'opciones': [], 'video': None, 'origen': 'rehecha-de %s' % tid}
        plan.append({'familia': slug, 'tira_id': nueva_id, 'carta': carta})
        if not args.simular:
            (TIRAS / (nueva_id + '.json')).write_text(json.dumps(tira, ensure_ascii=False, indent=1),
                                                     encoding='utf-8')
            idx = _leer(TIRAS / 'index.json', []) or []
            if nueva_id not in idx:
                (TIRAS / 'index.json').write_text(json.dumps([nueva_id] + idx, ensure_ascii=False),
                                                  encoding='utf-8')

    seleccion['tiras_preparadas'] = len(plan)
    sala.avisar('selección Mesa:', json.dumps(seleccion_publica(seleccion), ensure_ascii=False))
    sala.avisar('resumen: %d carta(s) %s' % (len(plan), 'que se montarían' if args.simular else 'listas para montar'))
    if not args.simular:
        PLAN.parent.mkdir(parents=True, exist_ok=True)
        PLAN.write_text(json.dumps({'fecha': hoy, 'cartas': plan}, ensure_ascii=False, indent=1),
                        encoding='utf-8')
        guardar_estado_mesa(generadas, fallidas, limitadas, len(plan), reutilizadas,
                            causa='servicio_imagen_no_disponible' if servicio_bloqueado else ('cupo_imagen_agotado' if cupo_bloqueado else ''),
                            modelo_imagen=imagen.modelo_de(str(reglas.get('imagen_motores') or 'hidream_demo').split(',')[0].strip(), reglas),
                            seleccion=seleccion)
    # Preparación que falló por completo es un fallo real, no una mesa «al día».
    return 2 if fallidas and not plan and not args.simular else 0


_snapshot_verifier = None


def _snapshot_publicado(ruta):
    global _snapshot_verifier
    from snapshots_online import Snapshots, OnlineError
    try:
        if _snapshot_verifier is None:
            _snapshot_verifier = Snapshots(RAIZ)
        return _snapshot_verifier.file_is_published(RAIZ / str(ruta))
    except OnlineError:
        raise sala.SalaError('no se pudo leer o acreditar el snapshot privado de publicación') from None
    except (ValueError, OSError):
        return False


def _existe_en_commit_publicado(ruta):
    """Solo rutas del repositorio, contenidas en el HEAD ya desplegado."""
    import subprocess
    from pathlib import PurePosixPath
    p = PurePosixPath(str(ruta or ''))
    if (p.is_absolute() or '..' in p.parts
            or not str(p).startswith('laminas/')
            or p.suffix.lower() not in ('.jpg', '.jpeg', '.png', '.webp')):
        return False
    import os
    if os.environ.get('SALA_PUBLICADOR_MODO') == 'snapshots':
        return _snapshot_publicado(str(p))
    run = subprocess.run(['git', 'ls-tree', '-r', '--name-only', 'HEAD', '--', str(p)],
                         cwd=RAIZ, capture_output=True, text=True, timeout=10, check=False)
    return run.returncode == 0 and str(p) in run.stdout.splitlines()


def montar():
    plan = _leer(PLAN, None)
    if not plan or not plan.get('cartas'):
        sala.avisar('nada que montar (no hay plan de esta corrida)')
        return 0
    # Todos los JPG de cada carta DEBEN estar en el commit ya publicado.
    # Los archivos del runner pueden existir en disco aunque su PR no se haya
    # integrado; ese era el origen de las fotos rotas en los teléfonos.
    sin_publicar = [(c.get('tira_id'), ruta) for c in plan['cartas']
                   for ruta in (c.get('carta') or {}).get('laminas') or []
                   if not _existe_en_commit_publicado(ruta)]
    if sin_publicar:
        raise sala.SalaError(
            '%d lámina(s) sin hash confirmado en la versión publicada; no se monta ninguna carta de '
            'este lote y se conservan las decisiones previas' % len(sin_publicar))
    for c in plan['cartas']:
        tira = _leer(TIRAS / (c['tira_id'] + '.json'), None)
        if not isinstance(tira, dict):
            raise sala.SalaError('no se monta una carta sin su tira')
        import os
        if os.environ.get('SALA_PUBLICADOR_MODO') == 'snapshots' and not _snapshot_publicado(
                'datos/tiras/' + c['tira_id'] + '.json'):
            raise sala.SalaError('la tira no coincide con la versión publicada')
        try:
            validar_nuevas_tomas(tira)
        except ContenidoVetado as e:
            raise sala.SalaError(str(e)) from e
        r = sala.post('proponer', fecha=plan['fecha'], propuestas=[c['carta']], familia=c['familia'])
        if not isinstance(r, dict) or not r.get('ok'):
            raise sala.SalaError('GAS no confirmó el montaje; conservar plan')
        sala.avisar('✓ montada %s · retiradas: %s' % (c['tira_id'], ', '.join(r.get('retiradas_familia') or []) or '—'))
    return 0


def montar_desde_commit():
    """Montar tarjetas de tiras NUEVAS tras despliegue confirmado de Pages.

    La salida efímera del productor ya desapareció al terminar aquel runner.
    Git conserva qué tiras creó el commit publicado; los originales y la
    historia anteriores no cambian. Se usa la misma puerta de GAS (proponer).
    """
    import subprocess
    proc = subprocess.run(
        ['git', 'diff', '--name-status', 'HEAD^', 'HEAD'],
        cwd=RAIZ, capture_output=True, text=True, timeout=25, check=False)
    if proc.returncode:
        raise sala.SalaError('no se pudo comprobar cuáles tiras agregó el commit publicado')
    rutas = []
    for linea in proc.stdout.splitlines():
        tipo, _, nombre = linea.partition('\t')
        if tipo != 'A' or not re.fullmatch(r'datos/tiras/[A-Za-z0-9_.-]+\.json', nombre):
            continue
        if '-nube-' not in nombre and '-arranque-' not in nombre:
            continue
        rutas.append(nombre)
    if not rutas:
        sala.avisar('✓ publicación sin tiras nuevas que montar')
        return 0
    # Una ficha no autorizada no debe bloquear el resto de publicaciones.
    fallas = 0
    for nombre in rutas:
        tira = _leer(RAIZ / nombre, None)
        if not isinstance(tira, dict):
            sala.avisar('⏸ tira inexistente o inválida: %s' % nombre)
            fallas += 1
            continue
        try:
            validar_nuevas_tomas(tira)
            mapa = {str(l.get('n')): l for l in tira.get('laminas') or []}
            elegidas = [mapa[str(n)] for n in tira['decidir']]
            srcs = [portada(l) for l in elegidas]
            if not all((RAIZ / src).is_file() for src in srcs):
                raise sala.SalaError('alguna imagen aprobable no está en el sitio publicado')
            tid = pathlib.Path(nombre).stem
            slug = str(tira.get('pieza_slug') or '').strip()
            if not slug:
                raise sala.SalaError('tira sin familia de pieza')
            carta = {
                'id': tid, 'titulo': str(tira.get('titulo') or tira.get('pieza') or slug),
                'tipo': 'laminas', 'laminas': srcs,
                'opciones': [], 'video': None,
                'origen': str(tira.get('origen') or 'nueva propuesta'),
            }
            respuesta = sala.post('proponer', fecha=str(tira.get('fecha') or sala.hoy_hermosillo()),
                                  propuestas=[carta], familia=slug)
            if not respuesta.get('ok'):
                raise sala.SalaError('GAS no confirmó el montaje de la pieza')
            sala.avisar('✓ tarjeta lista para editores: %s (%s tomas)' % (tid, len(srcs)))
        except (sala.SalaError, ContenidoVetado, KeyError, ValueError) as e:
            fallas += 1
            sala.avisar('⏸ no se montó %s: %s' % (nombre, e))
    if fallas:
        raise sala.SalaError('%d de %d tiras requieren atención (resto conservado)' %
                             (fallas, len(rutas)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
