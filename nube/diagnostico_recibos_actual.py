import json,urllib.request,concurrent.futures
def get(url):
 with urllib.request.urlopen(url,timeout=25) as r:return json.load(r)
rows=get("https://huggingface.co/api/spaces?search=HiDream&limit=40&sort=likes&direction=-1")
def check(row):
 sid=row["id"]
 try:
  r=get("https://huggingface.co/api/spaces/"+sid)
  print(json.dumps({"id":sid,"runtime":r.get("runtime"),"sdk":r.get("sdk"),"likes":r.get("likes"),"sha":r.get("sha")}))
 except Exception as e:print(json.dumps({"id":sid,"error":type(e).__name__}))
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(check,rows))
