import sys,os,json,hashlib,tempfile,pathlib,subprocess
sys.path.insert(0,str(pathlib.Path("app/nube").resolve()))
import sala_cliente as sala
import sala_drive as drive
try:
    sala.enmascarar_en_actions()
    rows=(sala.get("cola") or {}).get("cola") or []
    found=[r for r in rows if r.get("id")=="apodo:corte:completo:36a02f99"]
    assert len(found)==1 and found[0].get("estado")=="hecho","corte no confirmado"
    e=found[0].get("evidencia") or {}
    if isinstance(e,str): e=json.loads(e)
    assert e.get("durable") is True and e.get("drive_id") and e.get("md5")
    with tempfile.TemporaryDirectory() as tmp:
        p=drive.bajar(e["drive_id"],pathlib.Path(tmp)/"corte.mp4")
        raw=p.read_bytes()
        assert hashlib.md5(raw).hexdigest()==e["md5"],"bytes distintos"
        info=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(p)],text=True))
        streams=info.get("streams",[])
        assert any(s.get("codec_type")=="video" and s.get("width",0)>0 and s.get("height",0)>0 for s in streams)
        assert any(s.get("codec_type")=="audio" for s in streams)
        duration=float(info["format"]["duration"])
        assert abs(duration-float(e["duracion_s"]))<0.2
        out={"ok":True,"corte":"apodo:corte:completo:36a02f99","bytes":len(raw),"md5":e["md5"],"sha256":hashlib.sha256(raw).hexdigest(),"duracion_s":duration,"video_y_audio":True,"fuente":"Drive real, descarga completa","mutaciones":0}
        target=pathlib.Path(os.environ["SALA_EVIDENCE_DIR"])/"video-verificado.json"
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps(out))
except Exception as exc:
    print(json.dumps({"ok":False,"error_type":type(exc).__name__,"scope":"video_real_descargado"}))
    sys.exit(1)
