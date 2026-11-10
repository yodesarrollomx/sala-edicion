#!/usr/bin/env python3
"""Arma los dos grafos de proceso de la Sala (actual y 4.0) en el formato de Graphify.

Cada grafo es una lista de nodos (id, nombre, grupo) y de flechas (de, a, relación).
`python3 docs/grafos/construir.py` escribe sala-actual.json y sala-4.json y, si Graphify
está instalado (`pip install graphifyy`), rehace también las dos páginas interactivas.
"""
import json
import pathlib
import shutil
import subprocess
import tempfile

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
  ('consejo_wf', 'Workflow del Roast Room', 3), ('salida', 'Estación de salida (arma el paquete, 9-nov)', 3),
  ('cron', 'Horarios de GitHub (46 workflows)', 3),
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
  ('a_video', 'Video gratuito rechazado (zoom, voz fea)', 7),
  ('a_reloj', 'Los horarios llegan ~4 veces al día', 7), ('a_laminas', '44 % de láminas rechazadas', 7),
 ],
 'flechas': [
  ('correo', 'alejandro', 'avisa con la liga'), ('alejandro', 'sala', 'revisa y decide'), ('sayri', 'sala', 'revisa y decide'),
  ('lector', 'sala', 'sólo mira'), ('sala', 'borrador', 'guarda en el clic'), ('borrador', 'gas', 'envía decidir'),
  ('sala', 'gas', 'lee el día'), ('gas', 'respaldo', 'si no contesta, la Sala cae aquí'),
  ('gas', 'd_rol', 'valida'), ('d_rol', 'decisiones', 'editor: escribe'), ('d_rol', 'sala', 'agente o lector: «tu rol solo lee»'),
  ('gas', 'propuestas', 'lee/escribe'),
  ('decisiones', 'd_no', 'fusiona por pieza'), ('d_no', 'mesa', 'sí: la lámina se rehace'), ('d_no', 'd_eje', 'no: sigue'),
  ('d_eje', 'productor', 'cerrado: puede avanzar'), ('gas', 'correo', 'disparo diario'),
  ('cron', 'arranque', 'lanza'), ('cron', 'mesa', 'lanza'), ('cron', 'relevo', 'lanza'), ('cron', 'chinches', 'lanza'),
  ('cron', 'semaforo', 'lanza'), ('cron', 'consejo_wf', 'lanza'), ('cron', 'a_reloj', 'padece'),
  ('ideas', 'arranque', 'ideas elegidas'), ('arranque', 'gemini', 'pide guion'), ('arranque', 'imagen', 'pide lámina 1'),
  ('arranque', 'd_veto', 'pasa por'), ('d_veto', 'propuestas', 'limpia: entra a la mesa'), ('mesa', 'propuestas', 'monta cartas'),
  ('mesa', 'd_rehecha', 'si rehace'), ('d_rehecha', 'propuestas', 'sí: carta nueva que retira a la vieja'),
  ('mesa', 'imagen', 'rehace láminas con «no»'),
  ('relevo', 'decisiones', 'cosecha'), ('relevo', 'respaldo', 'reescribe'), ('relevo', 'd_peticion', 'revisa primero'),
  ('d_peticion', 'productor', 'sin petición abierta: puede producir'),
  ('productor', 'decisiones', 'lee aprobadas'), ('productor', 'cola', 'encola'), ('productor', 'reglas', 'lee umbrales'),
  ('cola', 'ejecutor', 'trabajos'), ('ejecutor', 'd_etapas', 'pregunta'), ('d_etapas', 'd_tope', 'sí: revisa el motor'),
  ('d_etapas', 'cola', 'no (así está hoy): el trabajo espera'),
  ('d_tope', 'ejecutor', 'sí: usa ese motor · no: prueba el siguiente'),
  ('motores_h', 'd_tope', 'define'), ('reglas', 'd_etapas', 'define'),
  ('ejecutor', 'wan', 'escena'), ('ejecutor', 'kokoro', 'voz'), ('ejecutor', 'gemini', 'voz de respaldo'),
  ('ejecutor', 'ffmpeg', 'corte'), ('ejecutor', 'drive', 'guarda producto'), ('ejecutor', 'produccion', 'reporta'),
  ('wan', 'a_video', 'no alcanza el estándar'), ('imagen', 'a_laminas', 'imagen no cuadra con el texto'),
  ('sala', 'produccion', 'chinches y recados'), ('produccion', 'chinches', 'cosecha'), ('chinches', 'verificar', 'abre issue'),
  ('consejo_wf', 'candados', 'juzga con'), ('consejo', 'consejo_wf', 'veredictos'), ('consejo_wf', 'decisiones', 'registra'),
  ('semaforo', 'sala', 'publica estado'), ('verificar', 'sala', 'publica'), ('expedientes', 'sala', 'historia de piezas'),
  ('consejo_wf', 'salida', 'con todas las láminas aprobadas'), ('salida', 'listas', 'deja imágenes en orden y texto'),
  ('salida', 'expedientes', 'anota el paquete'), ('listas', 'alejandro', 'publica él («Ya la publiqué»)'),
 ],
}

V4 = {
 'grupos': ['Personas', 'Pantalla nueva: Historias', 'Sheet (sin tocar Apps Script)', 'Nube: un solo flujo',
            'Motores', 'Drive', 'Decisiones lógicas', 'Lo que se conserva'],
 'nodos': [
  ('alejandro', 'Alejandro (edita y decide)', 0), ('sayri', 'Sayri (decide en la mesa de siempre)', 0),
  ('historias', 'historias.html · Series · Episodios · Universo · Ajustes', 1),
  ('universo_ui', 'Universo = el canon: temporada, personajes, lugares, objetos, encuadres, reglas', 1),
  ('serie_ui', 'Serie: su mundo y sus episodios (texto, encuadre, objetos, video, sí / pedir cambio / no va)', 1),
  ('ajustes_ui', 'Ajustes: tomas e imágenes por día, semillero, piloto primero', 1),
  ('gas', 'Apps Script /exec (acciones que ya existen)', 2),
  ('exp_u', 'EXPEDIENTES v4:universo y v4:mundo:<clase> (el canon: lo escribe el editor)', 2),
  ('exp_s', 'EXPEDIENTES v4:serie:<id> (texto de la historia)', 2),
  ('exp_d', 'EXPEDIENTES v4:dec:<id> (decisiones: sólo el editor)', 2),
  ('exp_p', 'EXPEDIENTES v4:prod:<id> (producción: sólo la nube)', 2),
  ('exp_c', 'EXPEDIENTES v4:canon (imágenes de referencia y fallos: sólo la nube)', 2),
  ('ideas', 'IDEAS pasadas (se leen, no se tocan)', 2), ('candados', 'CANDADOS de Dirección (se leen)', 2),
  ('flujo', 'sala-v4.yml (horario + botón)', 3), ('semillero', '1 · Semillero limpio: propone series', 3),
  ('referencias', '2 · Referencias: una imagen por personaje, lugar y objeto', 3),
  ('productor', '3 · Productor: genera episodios', 3), ('paquete', '4 · Paquete: une y deja listo', 3),
  ('estado', '5 · Estado: qué hizo y qué falta', 3),
  ('gemini', 'Gemini texto (historias y copy)', 4), ('omni', 'Gemini Omni Flash (video 15 s con voz)', 4),
  ('imagen', 'Gemini imagen (pinta las imágenes de referencia)', 4),
  ('ffmpeg', 'ffmpeg (último cuadro, unión)', 4),
  ('drive_h', 'Drive · _HISTORIAS/<serie>/E01-v1.mp4', 5),
  ('listas', 'Drive · _LISTAS PARA PUBLICAR/Historia · <título>', 5),
  ('canon_drive', 'Drive · _HISTORIAS/_CANON (pintadas, retratos de piloto, las de Dirección y CANON.txt)', 5),
  ('d_semillero', '¿Semillero encendido y faltan propuestas?', 6),
  ('d_temporada', '¿Queda una historia de la temporada sin escribir?', 6),
  ('d_cara', '¿El piloto se produjo sin imagen del protagonista? Su cara sale de ese piloto', 6),
  ('d_ficha', '¿Ya tiene imagen (la de Dirección, o la hecha con la ficha de hoy)?', 6),
  ('d_fallo', '¿Esa imagen ya falló hoy con la misma ficha?', 6),
  ('d_tope_img', '¿Queda tope de imágenes de referencia hoy?', 6),
  ('d_escalon', '¿Google rechazó las imágenes? La toma baja un escalón', 6),
  ('d_serie', '¿La serie está aprobada?', 6),
  ('d_tope', '¿Queda tope de clips hoy? (el gasto máximo)', 6),
  ('d_espera', '¿Lo que sale en el episodio ya tiene su imagen al día?', 6),
  ('d_gratis', '¿Se pudo preparar lo que no cuesta? (imágenes leídas, cuadro de arranque, texto sin veto)', 6),
  ('d_orden', '¿Cuál es el siguiente episodio sin video o con «cambio»?', 6),
  ('d_piloto', '¿El piloto (primer episodio en pie) ya tiene «sí»?', 6),
  ('d_fuera', '¿El episodio tiene «no va»? Queda fuera: ni se produce ni se publica', 6),
  ('d_bloque', '¿Episodio de 15 s o bloque de 30 s (dos tomas)?', 6),
  ('d_continua', '¿Misma escena que el anterior? Arranca en su último cuadro', 6),
  ('d_retrato', '¿Qué imágenes viajan con la toma? Hasta 4: quién sale, objetos y lugar', 6),
  ('d_cruce', '¿Cómo se cruza con las otras historias? Guiños e invitados del plan, o un conocido al final', 6),
  ('d_veto', '¿Trae ubicación vetada? Se rechaza', 6),
  ('d_cambio', '¿El editor pidió cambio? Versión nueva con su nota', 6),
  ('d_completa', '¿Cada episodio en pie tiene «sí» sobre su última versión?', 6),
  ('k_mesa', 'La Sala de siempre (láminas y carruseles)', 7), ('k_inviolables', 'Reglas inviolables y candados', 7),
  ('k_pausa', 'Video viejo en pausa (COLA, Wan, Kokoro)', 7), ('k_publicar', 'Publicar: siempre el clic de Dirección', 7),
 ],
 'flechas': [
  ('alejandro', 'historias', 'entra con su llave'), ('historias', 'universo_ui', 'puerta'), ('historias', 'serie_ui', 'puerta'),
  ('historias', 'ajustes_ui', 'puerta'), ('universo_ui', 'gas', 'guarda (accion expediente)'), ('ajustes_ui', 'gas', 'guarda'),
  ('serie_ui', 'gas', 'guarda texto y decisión'), ('gas', 'exp_u', 'escribe'), ('gas', 'exp_s', 'escribe'),
  ('gas', 'exp_d', 'escribe'), ('gas', 'historias', 'lee expedientes al instante'),
  ('flujo', 'semillero', 'paso 1'), ('flujo', 'referencias', 'paso 2'), ('flujo', 'productor', 'paso 3'), ('flujo', 'paquete', 'paso 4'),
  ('flujo', 'estado', 'paso 5'),
  ('semillero', 'd_semillero', 'pregunta'), ('exp_u', 'd_semillero', 'define'), ('ideas', 'semillero', 'nutren'),
  ('exp_u', 'semillero', 'el canon: mundo, reglas y encuadres'), ('d_semillero', 'd_temporada', 'sí'),
  ('exp_u', 'd_temporada', 'trae la temporada'),
  ('d_temporada', 'gemini', 'sí: escribe la historia planeada · no: una libre con cliente nuevo'),
  ('d_semillero', 'estado', 'no: lo dice y no propone'),
  ('semillero', 'd_veto', 'pasa por'), ('d_veto', 'estado', 'sí: no se propone ni se produce, y se avisa'),
  ('semillero', 'exp_s', 'propone serie'),
  ('referencias', 'd_serie', 'pregunta'), ('d_serie', 'd_cara', 'sí: primero su protagonista'),
  ('exp_p', 'd_cara', 'trae el piloto vigente'), ('d_cara', 'ffmpeg', 'sí: saca un cuadro del piloto (no cuesta)'),
  ('ffmpeg', 'canon_drive', 'guarda el retrato'), ('d_cara', 'd_ficha', 'no: por cada cosa que la serie usa'),
  ('exp_u', 'd_ficha', 'trae la ficha y la imagen de Dirección'), ('exp_c', 'd_ficha', 'trae lo ya pintado'),
  ('d_ficha', 'estado', 'sí: al día, no gasta'), ('d_ficha', 'd_fallo', 'no: hay que pintarla'),
  ('exp_c', 'd_fallo', 'recuerda los fallos'), ('d_fallo', 'estado', 'sí: espera a mañana o a que cambie la ficha'),
  ('d_fallo', 'd_tope_img', 'no'), ('imagen', 'exp_c', 'si falla, anota el motivo'),
  ('exp_c', 'd_tope_img', 'cuenta las pintadas hoy'), ('d_tope_img', 'imagen', 'sí: reserva y pinta'),
  ('d_tope_img', 'estado', 'no: espera a mañana'), ('imagen', 'canon_drive', 'guarda la imagen'),
  ('referencias', 'exp_c', 'anota imagen e índice'), ('referencias', 'canon_drive', 'deja CANON.txt'),
  ('exp_c', 'serie_ui', 'se ve en «El mundo de esta serie»'), ('canon_drive', 'universo_ui', 'liga para abrir las imágenes'),
  ('serie_ui', 'universo_ui', '«Guardar en el universo»'),
  ('exp_d', 'd_serie', 'responde'), ('productor', 'd_serie', 'pregunta'), ('d_serie', 'd_fuera', 'sí'),
  ('d_serie', 'serie_ui', 'no: espera a Dirección'), ('exp_d', 'd_fuera', 'responde'), ('d_fuera', 'd_orden', 'los que siguen en pie'),
  ('d_orden', 'd_piloto', 'elige'), ('exp_d', 'd_piloto', 'responde'), ('d_piloto', 'd_tope', 'sí, o es el piloto mismo'),
  ('d_piloto', 'serie_ui', 'no: espera el «sí» del piloto'),
  ('exp_u', 'd_tope', 'define el tope'), ('exp_p', 'd_tope', 'cuenta lo gastado hoy'), ('d_tope', 'd_espera', 'sí'),
  ('exp_c', 'd_espera', 'responde'), ('d_espera', 'd_gratis', 'sí, o las imágenes están apagadas'),
  ('d_espera', 'estado', 'no: espera su imagen y no gasta'), ('canon_drive', 'd_gratis', 'baja las imágenes'),
  ('d_gratis', 'd_bloque', 'sí: reserva y produce'), ('d_gratis', 'serie_ui', 'no: avisa en la serie y no gasta'),
  ('d_tope', 'estado', 'no: espera a mañana'),
  ('exp_d', 'd_cambio', 'trae la nota'), ('d_cambio', 'd_orden', 'vuelve a la fila'),
  ('d_bloque', 'd_continua', 'por toma'), ('d_continua', 'ffmpeg', 'sí: saca el último cuadro'), ('d_continua', 'd_retrato', 'con o sin primer cuadro'),
  ('d_retrato', 'omni', 'pide el clip con sus imágenes'), ('exp_u', 'd_retrato', '1º la imagen que pegó Dirección'),
  ('canon_drive', 'd_retrato', '2º la del canon: pintada o salida del piloto'),
  ('omni', 'd_escalon', 'contesta'), ('d_escalon', 'd_retrato', 'sí: reintenta con menos imágenes, hasta sólo texto'),
  ('d_escalon', 'drive_h', 'no: guarda el video'),
  ('ffmpeg', 'omni', 'primer cuadro'), ('candados', 'semillero', 'obligan al guion'), ('candados', 'paquete', 'obligan al texto'),
  ('semillero', 'd_cruce', 'pregunta'), ('exp_u', 'd_cruce', 'guiños e invitados del plan'),
  ('exp_c', 'd_cruce', 'personajes que ya tienen imagen'), ('d_cruce', 'exp_s', 'quedan en sus episodios; lo olvidado se coloca'),
  ('productor', 'd_veto', 'pasa por'), ('productor', 'exp_p', 'anota versión, liga e imágenes usadas'),
  ('exp_p', 'serie_ui', 'aparece para revisar'), ('drive_h', 'serie_ui', 'se ve ahí mismo'),
  ('exp_d', 'd_completa', 'responde'), ('paquete', 'd_completa', 'pregunta'), ('d_completa', 'ffmpeg', 'sí: une los aprobados'),
  ('d_completa', 'serie_ui', 'no: faltan decisiones'),
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


def pagina(nombre, g):
    """La página interactiva de Graphify (sala-actual.html, sala-4.html). Sin graphify
    instalado se quedan los JSON, que son la fuente; la página se rehace cuando lo haya."""
    if not shutil.which('graphify'):
        print('  (graphify no está instalado: no rehago %s.html)' % nombre)
        return
    with tempfile.TemporaryDirectory() as tmp:
        etiquetas = pathlib.Path(tmp) / 'etiquetas.json'
        etiquetas.write_text(json.dumps({str(n['community']): n['community_name'] for n in g['nodes']}, ensure_ascii=False),
                             encoding='utf-8')
        subprocess.run(['graphify', 'export', 'html', '--graph', str(AQUI / (nombre + '.json')), '--labels', str(etiquetas)],
                       check=True, capture_output=True)
    (AQUI / 'graph.html').replace(AQUI / (nombre + '.html'))


if __name__ == '__main__':
    for d, nombre in ((ACTUAL, 'sala-actual'), (V4, 'sala-4')):
        g = grafo(d, nombre)
        (AQUI / (nombre + '.json')).write_text(json.dumps(g, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        print(nombre, len(g['nodes']), 'nodos', len(g['links']), 'flechas')
        pagina(nombre, g)
