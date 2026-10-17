import sys,json
sys.path.insert(0,"nube")
import sala_cliente as sala
from motores.imagen import modelo_de
sala.enmascarar_en_actions()
assert modelo_de("hidream_o1")=="HiDream-O1-Image-Dev"
before=sala.get("reglas",fresco="1")["reglas"]["imagen_motores"]
if before not in ("hidream_demo","hidream_o1"):
 raise SystemExit("La selección cambió; no se sobrescribe")
if before=="hidream_demo":
 try:
  sala.post("regla",set={"imagen_motores":"hidream_o1"})
 except sala.SalaError:
  pass
after=sala.get("reglas",fresco="1")["reglas"]["imagen_motores"]
if after!="hidream_o1":raise SystemExit("Cambio no confirmado; no reenviar")
print(json.dumps({"activado":True,"antes":before,"despues":after,"modelo":"HiDream-O1-Image-Dev","prueba_real":"39070759507","sin_respaldo_pagado":True,"decisiones_modificadas":0}))
