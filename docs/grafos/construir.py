#!/usr/bin/env python3
"""Arma los dos grafos de proceso de la Sala (actual y 4.0) en el formato de Graphify.

Cada grafo es una lista de nodos (id, nombre, grupo) y de flechas (de, a, relación).
`python3 docs/grafos/construir.py` escribe sala-actual.json y sala-4.json; después
`graphify export html --graph <json>` los vuelve página interactiva.
"""
import json
import pathlib

AQUI = pathlib.Path(__file__).resolve().parent

ACTUAL = {
 'grupos': ['Personas', 'Pantalla (GitHub Pages)', 'Sheet + Apps Script', 'Nube (GitHub Actions)',
            'Motores externos', 'Drive', 'Decisiones lógicas', 'Atorones medidos'],
 'nodos': [
  ('alejandro', 'Alejandro (editor)', 0), ('sayri', 'Sayri (editor2)', 0), ('lector', 'Cliente / socio (lector)', 0),
  ('consejo', 'Roast Room (consejo virtual)', 0),
  ('sala', 'La Sala · index.html (Hoy · Publicaciones · Ajustes)', 1), ('borrador', 'Borrador local y cola de envíos', 1),
  ('respaldo', 'Respaldo espejo datos/manifiesto.json', 1),
  ('gas', 'Apps Script /exec', 2), ('propuestas', 'PROPUESTAS (la mesa)', 2), ('decisiones', 'DECISIONES', 2),
  ('produccion', 'PRODUCCION + BITACORA', 2), ('reglas', 'REGLAS', 2), ('motores_h', 'MOTORES', 2),
  ('cola', 'COLA de trabajos', 2), ('candados', 'CANDADOS (21)', 2), ('expedientes', 'EXPEDIENTES', 2),
  ('ideas', 'IDEAS / ÁRBOL (641 ideas)', 2), ('correo', 'Correo de las 7:00', 2),
  ('arranque', 'Semillero y arranque (ideas, guion, lámina 1)', 3), ('mesa', 'Montador de la mesa', 3),
  ('relevo', 'Relevo (cosecha el día)', 3), ('productor', 'Productor (abre compuertas, encola)', 3),
  ('ejecutor', 'Ejecutor (escena, voz, corte)', 3), ('chinches', 'Puente de chinches', 3),
  ('semaforo', 'Semáforo de máquinas', 3), ('verificar', 'Verificar + publicar Pages', 3),
  ('consejo_wf', 'Workflow del Roast Room', 3), ('cron', 'Horarios de GitHub (46 workflows)', 3),
  ('gemini', 'Gemini (texto, voz)', 4), ('wan', 'Wan en HuggingFace (escena gratis ≤5 s)', 4),
  ('kokoro', 'Kokoro (voz local)', 4), ('imagen', 'Motores de imagen', 4), ('ffmpeg', 'ffmpeg (corte)', 4),
  ('drive', 'Drive · unidad compartida (_producidos)', 5), ('listas', 'YOD Editorial/_LISTAS PARA PUBLICAR', 5),
  ('d_rol', '¿Qué rol tiene la llave? (editor decide, agente no)', 6),
  ('d_no', '¿Algún editor dijo «no»? El «no» manda', 6),
  ('d_eje', '¿Es un eje? Se cierra con un solo sí', 6),
  ('d_peticion', '¿La pieza tiene petición abierta? Nada avanza', 6),
  ('d_etapas', '¿nube_ejecuta_etapas incluye la etapa?', 6),
  ('d_tope', '¿Queda tope diario del motor?', 6),
  ('d_veto', '¿Trae ubicación vetada? Se rechaza entera', 6),
  ('d_rehecha', '¿Es rehecha? id nuevo + origen', 6),
  ('a_video', 'Video gratuito rechazado (zoom, voz fea)', 7), ('a_salida', 'Sin copy ni publicador', 7),
  ('a_reloj', 'Los horarios llegan ~4 veces al día', 7), ('a_laminas', '44 % de láminas rechazadas', 7),
 ],
 'flechas': [
  ('correo', 'alejandro', 'avisa con la liga'), ('alejandro', 'sala', 'revisa y decide'), ('sayri', 'sala', 'revisa y decide'),
  ('lector', 'sala', 'sólo mira'), ('sala', 'borrador', 'guarda en el clic'), ('borrador', 'gas', 'envía decidir'),
  ('sala', 'gas', 'lee el día'), ('gas', 'respaldo', 'si no contesta, la Sala cae aquí'),
  ('gas', 'd_rol', 'valida'), ('d_rol', 'decisiones', 'editor: escribe'), ('gas', 'propuestas', 'lee/escribe'),
  ('decisiones', 'd_no', 'fusiona por pieza'), ('d_no', 'd_eje', 'luego'), ('gas', 'correo', 'disparo diario'),
  ('cron', 'arranque', 'lanza'), ('cron', 'mesa', 'lanza'), ('cron', 'relevo', 'lanza'), ('cron', 'chinches', 'lanza'),
  ('cron', 'semaforo', 'lanza'), ('cron', 'consejo_wf', 'lanza'), ('cron', 'a_reloj', 'padece'),
  ('ideas', 'arranque', 'ideas elegidas'), ('arranque', 'gemini', 'pide guion'), ('arranque', 'imagen', 'pide lámina 1'),
  ('arranque', 'd_veto', 'pasa por'), ('arranque', 'propuestas', 'propone'), ('mesa', 'propuestas', 'monta cartas'),
  ('mesa', 'd_rehecha', 'si rehace'), ('mesa', 'imagen', 'rehace láminas con «no»'),
  ('relevo', 'decisiones', 'cosecha'), ('relevo', 'respaldo', 'reescribe'), ('relevo', 'd_peticion', 'revisa primero'),
  ('productor', 'decisiones', 'lee aprobadas'), ('productor', 'cola', 'encola'), ('productor', 'reglas', 'lee umbrales'),
  ('cola', 'ejecutor', 'trabajos'), ('ejecutor', 'd_etapas', 'pregunta'), ('ejecutor', 'd_tope', 'pregunta'),
  ('motores_h', 'd_tope', 'define'), ('reglas', 'd_etapas', 'define'),
  ('ejecutor', 'wan', 'escena'), ('ejecutor', 'kokoro', 'voz'), ('ejecutor', 'gemini', 'voz de respaldo'),
  ('ejecutor', 'ffmpeg', 'corte'), ('ejecutor', 'drive', 'guarda producto'), ('ejecutor', 'produccion', 'reporta'),
  ('wan', 'a_video', 'no alcanza el estándar'), ('imagen', 'a_laminas', 'imagen no cuadra con el texto'),
  ('sala', 'produccion', 'chinches y recados'), ('produccion', 'chinches', 'cosecha'), ('chinches', 'verificar', 'abre issue'),
  ('consejo_wf', 'candados', 'juzga con'), ('consejo', 'consejo_wf', 'veredictos'), ('consejo_wf', 'decisiones', 'registra'),
  ('semaforo', 'sala', 'publica estado'), ('verificar', 'sala', 'publica'), ('expedientes', 'sala', 'historia de piezas'),
  ('propuestas', 'listas', 'paquete a mano (9-nov)'), ('listas', 'alejandro', 'publica él'), ('listas', 'a_salida', 'no existía'),
 ],
}

V4 = {
 'grupos': ['Personas', 'Pantalla nueva: Historias', 'Sheet (sin tocar Apps Script)', 'Nube: un solo flujo',
            'Motores', 'Drive', 'Decisiones lógicas', 'Lo que se conserva'],
 'nodos': [
  ('alejandro', 'Alejandro (edita y decide)', 0), ('sayri', 'Sayri (decide en la mesa de siempre)', 0),
  ('historias', 'historias.html · Series · Episodios · Universo · Ajustes', 1),
  ('universo_ui', 'Universo: personajes, lugares, vértices, formato', 1),
  ('serie_ui', 'Serie: 10 episodios (texto editable, video, sí / cambio / no)', 1),
  ('ajustes_ui', 'Ajustes: tope diario, semillero, duración', 1),
  ('gas', 'Apps Script /exec (acciones que ya existen)', 2),
  ('exp_u', 'EXPEDIENTES v4:universo (lo escribe el editor)', 2),
  ('exp_s', 'EXPEDIENTES v4:serie:<id> (texto de la historia)', 2),
  ('exp_d', 'EXPEDIENTES v4:dec:<id> (decisiones: sólo el editor)', 2),
  ('exp_p', 'EXPEDIENTES v4:prod:<id> (producción: sólo la nube)', 2),
  ('ideas', 'IDEAS pasadas (se leen, no se tocan)', 2),
  ('flujo', 'sala-v4.yml (horario + botón)', 3), ('semillero', '1 · Semillero limpio: propone series', 3),
  ('productor', '2 · Productor: genera episodios', 3), ('paquete', '3 · Paquete: une y deja listo', 3),
  ('estado', '4 · Estado: qué hizo y qué falta', 3),
  ('gemini', 'Gemini texto (historias y copy)', 4), ('omni', 'Gemini Omni Flash (video 15 s con voz)', 4),
  ('ffmpeg', 'ffmpeg (último cuadro, unión)', 4),
  ('drive_h', 'Drive · _HISTORIAS/<serie>/E01-v1.mp4', 5), ('listas', 'YOD Editorial/_LISTAS PARA PUBLICAR/<serie>', 5),
  ('d_semillero', '¿Semillero encendido y faltan propuestas?', 6),
  ('d_serie', '¿La serie está aprobada?', 6),
  ('d_tope', '¿Queda tope de clips hoy? (el gasto máximo)', 6),
  ('d_orden', '¿Cuál es el siguiente episodio sin video o con «cambio»?', 6),
  ('d_bloque', '¿Episodio de 15 s o bloque de 30 s (dos tomas)?', 6),
  ('d_continua', '¿Misma escena que el anterior? Arranca en su último cuadro', 6),
  ('d_veto', '¿Trae ubicación vetada? Se rechaza', 6),
  ('d_cambio', '¿El editor pidió cambio? Versión nueva con su nota', 6),
  ('d_completa', '¿Los 10 episodios tienen «sí»?', 6),
  ('k_mesa', 'La Sala de siempre (láminas y carruseles)', 7), ('k_inviolables', 'Reglas inviolables y candados', 7),
  ('k_pausa', 'Video viejo en pausa (COLA, Wan, Kokoro)', 7), ('k_publicar', 'Publicar: siempre el clic de Dirección', 7),
 ],
 'flechas': [
  ('alejandro', 'historias', 'entra con su llave'), ('historias', 'universo_ui', 'puerta'), ('historias', 'serie_ui', 'puerta'),
  ('historias', 'ajustes_ui', 'puerta'), ('universo_ui', 'gas', 'guarda (accion expediente)'), ('ajustes_ui', 'gas', 'guarda'),
  ('serie_ui', 'gas', 'guarda texto y decisión'), ('gas', 'exp_u', 'escribe'), ('gas', 'exp_s', 'escribe'),
  ('gas', 'exp_d', 'escribe'), ('gas', 'historias', 'lee expedientes al instante'),
  ('flujo', 'semillero', 'paso 1'), ('flujo', 'productor', 'paso 2'), ('flujo', 'paquete', 'paso 3'), ('flujo', 'estado', 'paso 4'),
  ('semillero', 'd_semillero', 'pregunta'), ('exp_u', 'd_semillero', 'define'), ('ideas', 'semillero', 'nutren'),
  ('exp_u', 'semillero', 'personajes, lugares, vértices'), ('semillero', 'gemini', 'pide 10 episodios'),
  ('semillero', 'd_veto', 'pasa por'), ('semillero', 'exp_s', 'propone serie'),
  ('exp_d', 'd_serie', 'responde'), ('productor', 'd_serie', 'pregunta'), ('d_serie', 'd_tope', 'sí'),
  ('exp_u', 'd_tope', 'define el tope'), ('exp_p', 'd_tope', 'cuenta lo gastado hoy'), ('d_tope', 'd_orden', 'sí'),
  ('exp_d', 'd_cambio', 'trae la nota'), ('d_cambio', 'd_orden', 'vuelve a la fila'), ('d_orden', 'd_bloque', 'elige'),
  ('d_bloque', 'd_continua', 'por toma'), ('d_continua', 'ffmpeg', 'saca el último cuadro'), ('d_continua', 'omni', 'pide el clip'),
  ('productor', 'd_veto', 'pasa por'), ('omni', 'drive_h', 'guarda el video'), ('productor', 'exp_p', 'anota versión y liga'),
  ('exp_p', 'serie_ui', 'aparece para revisar'), ('drive_h', 'serie_ui', 'se ve ahí mismo'),
  ('exp_d', 'd_completa', 'responde'), ('paquete', 'd_completa', 'pregunta'), ('d_completa', 'ffmpeg', 'une los 10'),
  ('paquete', 'gemini', 'escribe el copy'), ('paquete', 'listas', 'deja el paquete'), ('listas', 'k_publicar', 'espera'),
  ('k_publicar', 'alejandro', 'su clic'), ('estado', 'exp_p', 'deja el resumen'), ('sayri', 'k_mesa', 'sigue igual'),
  ('k_mesa', 'historias', 'liga en el menú'), ('k_inviolables', 'productor', 'siguen mandando'),
  ('k_pausa', 'productor', 'no se reactiva: es otro camino'),
 ],
}


def grafo(d, nombre):
    nodos = [{'id': i, 'label': l, 'norm_label': l.lower(), 'community': g, 'community_name': d['grupos'][g],
              'file_type': 'doc', 'source_file': 'docs/grafos/construir.py', 'source_location': nombre}
             for i, l, g in d['nodos']]
    ids = {n['id'] for n in nodos}
    for a, b, _ in d['flechas']:
        assert a in ids and b in ids, (nombre, a, b)
    sueltos = ids - {x for a, b, _ in d['flechas'] for x in (a, b)}
    assert not sueltos, (nombre, sueltos)
    return {'directed': True, 'multigraph': False, 'graph': {'name': nombre}, 'nodes': nodos,
            'links': [{'source': a, 'target': b, 'relation': r, 'confidence': 'EXTRACTED',
                       'confidence_score': 1.0, 'weight': 1.0, 'source_file': 'docs/grafos/construir.py'}
                      for a, b, r in d['flechas']], 'hyperedges': []}


if __name__ == '__main__':
    for d, nombre in ((ACTUAL, 'sala-actual'), (V4, 'sala-4')):
        g = grafo(d, nombre)
        (AQUI / (nombre + '.json')).write_text(json.dumps(g, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(nombre, len(g['nodes']), 'nodos', len(g['links']), 'flechas')
