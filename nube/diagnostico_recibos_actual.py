import json,urllib.request
from gradio_client import Client
for sid in ("HiDream-ai/HiDream-O1-Image-Dev","HiDream-ai/HiDream-O1-Image-Dev-2604"):
 try:
  c=Client(sid,verbose=False)
  info=c.view_api(return_format="dict",print_info=False)
  print("API",sid,json.dumps(info))
 except Exception as e: print("ERROR",sid,type(e).__name__)
