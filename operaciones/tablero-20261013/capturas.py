import json, os, pathlib, shutil, subprocess, time
from PIL import Image
source=os.environ["SOURCE_SHA"]
for i in range(24):
    runs=json.loads(subprocess.check_output(["gh","run","list","--workflow","sala-tablero-pruebas.yml","--branch","codex/sala-tablero-20261013","--limit","8","--json","databaseId,headSha,status,conclusion"],text=True))
    rows=[r for r in runs if r["headSha"]==source]
    good=next((r for r in rows if r["conclusion"]=="success"),None)
    if good:break
    if rows and all(r["status"]=="completed" for r in rows):raise SystemExit("La última versión aún requiere corrección")
    time.sleep(10)
else:raise SystemExit("Recorrido todavía en curso")
dest=pathlib.Path(os.environ["RUNNER_TEMP"])/"capturas-tablero"
subprocess.run(["gh","run","download",str(good["databaseId"]),"--name","tablero-sala-recorrido","--dir",str(dest)],check=True)
out=pathlib.Path("operaciones/tablero-20261013")
for p in dest.glob("*.png"):
    im=Image.open(p).convert("RGB")
    im.save(out/(p.stem+".jpg"),quality=90)
r=json.loads((dest/"resultado.json").read_text());r.update(code_sha=source,run=good["databaseId"])
(out/"recorrido.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n")
print(json.dumps(r))
