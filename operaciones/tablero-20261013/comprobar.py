import hashlib, json, os, pathlib, shutil, subprocess, sys, time
root=pathlib.Path.cwd()
out=root/"operaciones/tablero-20261013";out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(root/"_codigo-temporal/nube"))
from motores import imagen
rid=hashlib.sha256(b"sala-tablero-canario-hidream-20261013-v1").hexdigest()
rules={"imagen_motores":"hidream_demo","_imagen_request_id":rid}
prompt="Three adult architects compare three distinct small architectural scale models around a spacious wooden worktable, realistic natural warm daylight, contemporary beige studio, professional editorial documentary photograph, accurate anatomy, no printed text or lettering."
start=time.monotonic()
try:
    data,ext,motor,avisos=imagen.generar(prompt,rules)
    assert motor=="hidream_demo"
    assert imagen.generar(prompt,rules)[0]==data
    (out/"hidream-canario.png").write_bytes(data)
    result={"ok":True,"modelo":imagen.modelo_de(motor),"motor":motor,"segundos":round(time.monotonic()-start,2),"cache_verificada":True,"sha256":hashlib.sha256(data).hexdigest(),"costo_monetario":0,"prueba_sintetica":True,"decisiones_escritas":0}
except Exception as e:
    from sala_cliente import redactar
    result={"ok":False,"modelo":"HiDream-I1-Dev","causa":redactar(str(e))[:250],"prueba_sintetica":True,"decisiones_escritas":0}
(out/"hidream-canario.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(result,ensure_ascii=False))
for attempt in range(18):
    listing=json.loads(subprocess.check_output(["gh","run","list","--repo",os.environ["GITHUB_REPOSITORY"],"--workflow","sala-tablero-pruebas.yml","--branch","codex/sala-tablero-20261013","--limit","6","--json","databaseId,headSha,status,conclusion"],text=True))
    rows=[r for r in listing if r["headSha"]==os.environ["SOURCE_SHA"]]
    good=next((r for r in rows if r["conclusion"]=="success"),None)
    if good:
        dest=root/"_capturas-temporales"
        subprocess.run(["gh","run","download",str(good["databaseId"]),"--repo",os.environ["GITHUB_REPOSITORY"],"--name","tablero-sala-recorrido","--dir",str(dest)],check=True)
        from PIL import Image
        for photo in dest.glob("*.png"):
            im=Image.open(photo).convert("RGB")
            if im.width>1440:im.thumbnail((1440,3200))
            im.save(out/(photo.stem+".jpg"),quality=90)
        if (dest/"resultado.json").exists():shutil.copyfile(dest/"resultado.json",out/"recorrido.json")
        print("Recorrido y capturas confirmadas:",good["databaseId"])
        break
    if rows and all(r["status"]=="completed" for r in rows):
        print("Recorrido aún requiere corrección; se conserva sólo el canario")
        break
    time.sleep(10)
