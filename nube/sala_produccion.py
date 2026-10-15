#!/usr/bin/env python3
"""Lectura de producción independiente de las tarjetas visibles al editor.

Reutiliza exclusivamente lecturas del GAS existente. No escribe decisiones ni
reconstruye propuestas retiradas desde un archivo local.
"""
import copy
from datetime import date, datetime
import json
import os
from pathlib import Path
import re
import sala_cliente as sala

ROOT = Path(__file__).resolve().parent.parent
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PID = re.compile(r"^[A-Za-z0-9_.-]+$")
CONTRATO_PRODUCCION = 'produccion-historica-v1'
VERSION_PRODUCCION = 'produccion-historica-2026-10-15'
VERSIONES_LEGADAS = frozenset({'dos-compuertas-2026-09-12'})


def contrato_invalido():
    raise sala.SalaError('producción sin contrato histórico confirmado', codigo='sala_contrato_lectura')


def fecha_valida(value):
    if not isinstance(value, str) or not DATE.fullmatch(value): return False
    try: date.fromisoformat(value)
    except ValueError: return False
    return True


def sello_valido(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z', value): return False
    try: datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: return False
    return True


def id_valido(value):
    return isinstance(value, str) and 1 <= len(value) <= 256 and PID.fullmatch(value) is not None


def validar_historica(value):
    """No acepta un día limitado disfrazado de historial ni una aprobación sin firmas."""
    if (not isinstance(value, dict) or value.get('ok') is not True or value.get('error')
            or value.get('contrato') != CONTRATO_PRODUCCION or value.get('version') != VERSION_PRODUCCION
            or value.get('alcance') != 'historial_completo' or not fecha_valida(value.get('fecha'))):
        contrato_invalido()
    try: size = len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
    except (TypeError, ValueError): contrato_invalido()
    if size > 4 * 1024 * 1024: contrato_invalido()
    props, dec, sources = value.get('propuestas'), value.get('decisiones'), value.get('fuentes')
    if (not isinstance(props, list) or len(props) > 10000 or not isinstance(dec, dict)
            or not isinstance(dec.get('propuestas'), dict) or len(dec['propuestas']) > 10000
            or not isinstance(dec.get('editores'), list) or len(dec['editores']) > 2
            or not all(isinstance(x, str) and 0 < len(x) <= 256 for x in dec['editores'])
            or not isinstance(sources, dict)):
        contrato_invalido()
    for field, limit in (('leidas', 10000), ('activas', 10000), ('retiradas', 10000), ('decisiones_leidas', 50000)):
        if type(sources.get(field)) is not int or not 0 <= sources[field] <= limit: contrato_invalido()
    if sources['activas'] != len(props) or sources['activas'] + sources['retiradas'] > sources['leidas']:
        contrato_invalido()
    ids = []
    for prop in props:
        if (not isinstance(prop, dict) or not id_valido(prop.get('id'))
                or not fecha_valida(prop.get('fecha_fuente')) or prop['fecha_fuente'] > value['fecha']
                or not isinstance(prop.get('laminas'), list) or len(prop['laminas']) > 1000
                or not all(isinstance(x, (str, dict)) for x in prop['laminas'])
                or not isinstance(prop.get('opciones'), (list, dict))
                or not isinstance(prop.get('tipo'), str) or len(prop['tipo']) > 64
                or not isinstance(prop.get('titulo'), str) or len(prop['titulo']) > 32768
                or not (prop.get('video') is None or isinstance(prop.get('video'), str))
                or not isinstance(prop.get('estado'), str)
                or prop['estado'].lower().startswith('retirada')
                or not (prop.get('origen') is None or isinstance(prop.get('origen'), str))
                or str(prop.get('origen') or '').lower().startswith('retirada')):
            contrato_invalido()
        ids.append(prop['id'])
    if len(set(ids)) != len(ids): contrato_invalido()
    max_stamp = None
    for pid, decision in dec['propuestas'].items():
        if not id_valido(pid) or not isinstance(decision, dict): contrato_invalido()
        marks, signatures, notes = decision.get('laminas'), decision.get('firmas'), decision.get('notas')
        proposal_signatures = decision.get('firmas_nota')
        if (not isinstance(marks, list) or len(marks) > 1000
                or not isinstance(signatures, list) or len(signatures) != len(marks)
                or not isinstance(notes, list) or len(notes) != len(marks)
                or not all(isinstance(x, str) and len(x) <= 32768 for x in notes)
                or not isinstance(decision.get('nota'), str) or len(decision['nota']) > 65536
                or not isinstance(proposal_signatures, list) or len(proposal_signatures) > 2):
            contrato_invalido()
        for i, (mark, group) in enumerate(zip(marks, signatures)):
            if mark not in (None, 'si', 'no') or not isinstance(group, list) or len(group) > 2:
                contrato_invalido()
            roles = []
            for sig in group:
                if (not isinstance(sig, dict) or sig.get('rol') not in ('editor', 'editor2')
                        or sig.get('marca') not in (None, 'si', 'no')
                        or not isinstance(sig.get('quien'), str) or not 0 < len(sig['quien']) <= 256
                        or not isinstance(sig.get('nota'), str) or len(sig['nota']) > 16384
                        or not sello_valido(sig.get('guardado'))):
                    contrato_invalido()
                roles.append(sig['rol'])
                stamp = datetime.fromisoformat(sig['guardado'].replace('Z', '+00:00'))
                max_stamp = max(max_stamp, stamp) if max_stamp else stamp
            if len(set(roles)) != len(roles): contrato_invalido()
            merged = 'no' if any(s['marca'] == 'no' for s in group) else 'si' if any(s['marca'] == 'si' for s in group) else None
            if mark != merged: contrato_invalido()
            signed_notes = [s for s in group if s['nota']]
            expected_note = signed_notes[0]['nota'] if len(signed_notes) == 1 else ' | '.join(s['quien'] + ': ' + s['nota'] for s in signed_notes)
            if notes[i] != expected_note: contrato_invalido()
        note_roles = []
        for sig in proposal_signatures:
            if (not isinstance(sig, dict) or sig.get('rol') not in ('editor', 'editor2')
                    or not isinstance(sig.get('quien'), str) or not 0 < len(sig['quien']) <= 256
                    or not isinstance(sig.get('nota'), str) or not 0 < len(sig['nota']) <= 16384
                    or not sello_valido(sig.get('guardado'))):
                contrato_invalido()
            note_roles.append(sig['rol'])
            stamp = datetime.fromisoformat(sig['guardado'].replace('Z', '+00:00'))
            max_stamp = max(max_stamp, stamp) if max_stamp else stamp
        if len(set(note_roles)) != len(note_roles) or decision['nota'] != ' | '.join(s['quien'] + ': ' + s['nota'] for s in proposal_signatures):
            contrato_invalido()
    if 'guardado' in dec and not sello_valido(dec['guardado']): contrato_invalido()
    if max_stamp and ('guardado' not in dec or datetime.fromisoformat(dec['guardado'].replace('Z', '+00:00')) < max_stamp):
        contrato_invalido()
    return value


def leer_tira(pid):
    if not PID.fullmatch(str(pid or "")):
        raise sala.SalaError("identidad de propuesta inválida")
    try:
        value = json.loads((ROOT / "datos" / "tiras" / (pid + ".json")).read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def validar_dia(value, fecha=None):
    if (not isinstance(value, dict) or value.get("ok") is False or value.get("error")
            or not isinstance(value.get("propuestas"), list)
            or not isinstance(value.get("decisiones"), dict)
            or not isinstance(value["decisiones"].get("propuestas"), dict)
            or not DATE.fullmatch(str(value.get("fecha", "")))
            or (fecha and value["fecha"] != fecha)):
        raise sala.SalaError("lectura del día sin contrato de producción")
    for prop in value["propuestas"]:
        if not isinstance(prop, dict) or not PID.fullmatch(str(prop.get("id", ""))):
            raise sala.SalaError("fuente de propuesta inválida")
    return value


def fechas_fuente(pid, tira, dia):
    candidates = []
    if isinstance(tira, dict):
        candidates.append(str(tira.get("fecha") or ""))
    candidates += re.findall(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", pid)
    # El historial sólo localiza una lectura; nunca acredita vigencia ni marcas.
    try:
        old = json.loads((ROOT / "datos" / "manifiesto.json").read_text())
    except (OSError, ValueError):
        old = {}
    candidates += [f for f, h in (old.get("historial") or {}).items()
                   if any(p.get("id") == pid for p in (h or {}).get("propuestas", []))]
    if not any(DATE.fullmatch(f) for f in candidates):
        candidates += sorted([f for f in dia.get("dias", []) if DATE.fullmatch(str(f))],
                             reverse=True)
    return list(dict.fromkeys(f for f in candidates
                if DATE.fullmatch(f) and f <= dia["fecha"]))[:16]


def cargar(getter=None, tira_reader=None, *, historica=None):
    """Prefiere el contrato canónico sólo tras habilitarlo con backend ya verificado.

    Durante el despliegue SALA_PRODUCCION_HISTORICA=0 conserva el lector limitado
    y declara su alcance. El fallback sólo reconoce una versión legada conocida;
    una falla de red, autenticación o contrato nunca se convierte en un día vacío.
    """
    getter = getter or sala.get
    tira_reader = tira_reader or leer_tira
    if historica is None:
        flag = os.environ.get('SALA_PRODUCCION_HISTORICA', '0')
        if flag not in ('0', '1'): contrato_invalido()
        historica = flag == '1'
    if not isinstance(historica, bool): contrato_invalido()
    if not historica:
        return cargar_legacy(getter, tira_reader, motivo='habilitacion_pendiente')
    try:
        value = getter('produccion', fresco='1')
    except sala.SalaError as error:
        if error.codigo != 'sala_recurso_no_disponible': raise
        return cargar_legacy(getter, tira_reader, motivo='recurso_no_disponible')
    if isinstance(value, dict) and 'contrato' not in value and 'alcance' not in value and value.get('version') in VERSIONES_LEGADAS:
        # El GAS antiguo ignora un recurso desconocido y devuelve su día normal.
        return cargar_legacy(getter, tira_reader, inicial=value, motivo='gas_legacy_reconocido')
    value = copy.deepcopy(validar_historica(value))
    active = {p['id'] for p in value['propuestas']}
    live_decisions = [d for pid, d in value['decisiones']['propuestas'].items() if pid in active]
    value['_produccion'] = {
        'alcance': 'historial_completo', 'fuente': 'gas_produccion', 'cuenta_historial': 'exacta',
        'visibles': len(value['propuestas']),
        'recuperadas': sum(p['fecha_fuente'] < value['fecha'] for p in value['propuestas']),
        'fuentes_no_vigentes': value['fuentes']['retiradas'], 'fuentes_sin_acreditar': 0,
        'decisiones_sin_fuente_activa': len(value['decisiones']['propuestas']) - len(live_decisions),
        'si': sum(m == 'si' for d in live_decisions for m in d['laminas']),
        'no': sum(m == 'no' for d in live_decisions for m in d['laminas']),
    }
    return value


def cargar_legacy(getter, tira_reader, *, inicial=None, motivo):
    day = validar_dia(inicial if inicial is not None else getter("dia", fresco="1"))
    out = copy.deepcopy(day)
    props = {p["id"]: copy.deepcopy(p) for p in day["propuestas"]
             if not str(p.get("origen") or "").lower().startswith("retirada")}
    decisions = day["decisiones"]["propuestas"]
    wanted = [pid for pid, d in decisions.items()
              if isinstance(d, dict) and any(m in ("si", "no") for m in d.get("laminas", []))
              and pid not in props]
    cache = {day["fecha"]: day}
    inactive = 0
    for pid in wanted:
        tira = tira_reader(pid)
        found = None
        for date in fechas_fuente(pid, tira, day):
            if date not in cache:
                cache[date] = validar_dia(getter("dia", f=date, fresco="1"), date)
            same = [p for p in cache[date]["propuestas"] if p["id"] == pid
                    and not str(p.get("origen") or "").lower().startswith("retirada")]
            if len(same) > 1:
                raise sala.SalaError("fuente de propuesta duplicada")
            if same:
                found = copy.deepcopy(same[0])
                break
        if found:
            props[pid] = found
        else:
            # Puede ser una versión retirada. No se inventa su tarjeta desde la tira.
            inactive += 1
    out["propuestas"] = list(props.values())
    out["_produccion"] = {
        'alcance': 'legacy_ventana_limitada', 'fuente': 'gas_dia', 'cuenta_historial': 'no_confirmada',
        'motivo_legacy': motivo,
        "visibles": len(day["propuestas"]), "recuperadas": len(props) - len(day["propuestas"]),
        "fuentes_no_vigentes": None, 'fuentes_sin_acreditar': inactive,
        "si": sum(m == "si" for d in decisions.values() if isinstance(d, dict)
                  for m in d.get("laminas", [])),
        "no": sum(m == "no" for d in decisions.values() if isinstance(d, dict)
                  for m in d.get("laminas", [])),
    }
    return out


def resolver_tira(tira, decision, prop=None):
    """Aplica sólo lo que la fusión del Sheet acredita, sin modificar el original."""
    from motores._comun import toma_elegida
    result = copy.deepcopy(tira)
    mapa = result.get("mapa") or {
        str(i + 1): n for i, n in enumerate(result.get("decidir") or [])}
    marks = (decision or {}).get("laminas") or []
    notes = (decision or {}).get("notas") or (decision or {}).get("notas_laminas") or []
    firms = (decision or {}).get("firmas") or []
    by_n = {str(l.get("n")): l for l in result.get("laminas") or []}
    for i, mark in enumerate(marks):
        n = str(mapa.get(str(i + 1), i + 1))
        lam = by_n.get(n)
        if lam is None:
            if mark in ("si", "no"):
                raise sala.SalaError("decisión sin lámina en su tira")
            continue
        note = str(notes[i] or "") if i < len(notes) else ""
        note = note or str((decision or {}).get("nota") or "")
        if mark == "no":
            displayed = (prop or {}).get("laminas") or []
            image = displayed[i] if i < len(displayed) else ""
            if isinstance(image, dict):
                image = image.get("src") or ""
            # La nota corrige lo que el editor vio, no la foto anterior sustituida.
            shown = next((c for c in lam.get("candidatas") or []
                          if image and image in (c.get("src"), c.get("original"))), None)
            if shown:
                lam["src"] = str(shown.get("original") or shown.get("src"))
                lam["dice"] = str(shown.get("dice") or lam.get("dice") or "")
                if shown.get("ve"):
                    lam["ve"] = str(shown["ve"])
            lam.update(estado="rechazada", marca_previa="no", nota_previa=note)
        elif mark == "si":
            candidates = lam.get("candidatas") or []
            if len(set(re.findall(r'\[toma elegida:\s*(\d+)\]', note))) > 1:
                raise sala.SalaError("aprobación con tomas elegidas contradictorias")
            selected = toma_elegida(note)
            if candidates:
                if not 0 < selected <= len(candidates):
                    raise sala.SalaError("aprobación sin toma elegida válida")
                chosen = candidates[selected - 1]
                src = str(chosen.get("original") or chosen.get("src") or "")
                if not src:
                    raise sala.SalaError("toma elegida sin imagen")
                lam["src"] = src
                lam["dice"] = str(chosen.get("dice") or lam.get("dice") or "")
                if chosen.get("ve"):
                    lam["ve"] = str(chosen["ve"])
                lam["seleccion"] = {"toma": selected, "src": src,
                                    "huella": str(chosen.get("huella") or "")}
            elif selected:
                raise sala.SalaError("toma elegida ausente de su versión")
            lam.update(estado="aprobada", marca_previa="si")
        elif i < len(firms) and firms[i]:
            # La fusión representa un BORRAR explícito como marca nula firmada.
            lam.update(estado="pendiente", marca_previa="")
    from motores.politica_imagen import depurar_tira, requiere_reemplazo
    # El retiro explícito afecta sólo sus fuentes; la depuración ordinaria
    # de candidatas pendientes la conserva Mesa con su registro de cambios.
    cleaned, _ = depurar_tira(result)
    for i, lam in enumerate(result.get('laminas') or []):
        if requiere_reemplazo(lam):
            result['laminas'][i] = cleaned['laminas'][i]
    return result


def guion_faltante(tira):
    """Láminas del guion que aún no tienen propuesta visual; nunca aprobaciones."""
    guion = tira.get("guion") or []
    if not isinstance(guion, list):
        raise sala.SalaError("guion sin lista de láminas")
    numbers = [str(l.get("n", "")) for l in guion if isinstance(l, dict)]
    if (len(numbers) != len(guion) or len(set(numbers)) != len(numbers)
            or any(not n.isdigit() or int(n) < 1 for n in numbers)):
        raise sala.SalaError("guion con identidad de láminas inválida")
    present = {str(l.get("n")) for l in tira.get("laminas", [])}
    return [copy.deepcopy(l) for l in guion if str(l["n"]) not in present]


def es_video(tira):
    """Formato explícito; para piezas históricas sin formato conserva el contrato."""
    return str(tira.get("formato") or "").strip().lower() not in {
        "carrusel", "lamina", "lámina", "imagen"}


def peticiones_abiertas(path=None):
    path = path or ROOT / "datos" / "manifiesto.json"
    try:
        m = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        raise sala.SalaError("peticiones sin lectura válida")
    return any(isinstance(p, dict) and p.get("estado") != "cumplida"
               for p in m.get("peticiones", []))
