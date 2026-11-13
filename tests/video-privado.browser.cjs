/* Reproducción real y fallos con MP4 sintético; ningún endpoint de negocio recibe escrituras. */
const {chromium,webkit}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..'),fixture=process.env.SALA_VIDEO_FIXTURE||path.join(require('node:os').tmpdir(),'sala-video-sintetico.mp4');
if(!fs.existsSync(fixture))require('node:child_process').execFileSync('ffmpeg',['-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=180x320:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=24000','-t','6','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',fixture]);
const bytes=fs.readFileSync(fixture);
const src='https://drive.google.com/file/d/syntheticvideo123/preview';
const key=crypto.randomBytes(32),iv=crypto.randomBytes(12),enc=crypto.createCipheriv('aes-256-gcm',key,iv);
const cipher=Buffer.concat([enc.update(bytes),enc.final(),enc.getAuthTag()]),cipherSha=crypto.createHash('sha256').update(cipher).digest('hex');
const cipherUrl='https://raw.githubusercontent.com/yodesarrollomx/sala-edicion/'+'c'.repeat(40)+'/video-revision-cifrado/'+cipherSha+'.bin';
const server=http.createServer((req,res)=>{const name=new URL(req.url,'http://localhost').pathname;if(name==='/qa-embed'){res.setHeader('Content-Type','text/html');res.end('<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><style>html,body{margin:0;width:100%;height:100%}iframe{border:0;width:100%;height:100%}</style><iframe id=embudoFrame title="Sala QA aislada" src="/" allow="fullscreen; autoplay; picture-in-picture" allowfullscreen></iframe>');return;}try{const file=path.join(root,name==='/'?'index.html':name);res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.css')?'text/css':'text/html');res.end(fs.readFileSync(file));}catch(e){res.writeHead(404);res.end();}});
function day(){return {fecha:'2026-10-20',rol:'editor',quien:'Editor sintético',propuestas:[0,1].map(i=>({id:'corte-'+i,tipo:'eje',titulo:'Corte '+i,video:src,laminas:[],opciones:{candidatas:[{titulo:'Conservar'}]}})),decisiones:{editores:[],propuestas:{}}};}
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{for(const [name,engine] of [['chromium',chromium],['webkit',webkit]].filter(([n])=>!process.env.SALA_VIDEO_ENGINE||n===process.env.SALA_VIDEO_ENGINE)){
  const browser=await engine.launch({headless:true,...(name==='chromium'?{args:['--no-sandbox'],...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})}: {})});
  try{for(const embedded of [false,true])for(const width of [390,844,1280]){
   const context=await browser.newContext({viewport:{width,height:width===844?390:844},hasTouch:width<1000}),surface=await context.newPage(),errors=[],writes=[];let page=surface;let requests=0,assets=0,fail=false;
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{localStorage.setItem('sala_clave','synthetic');localStorage.setItem('sala_rol','editor');localStorage.setItem('sala_guia','1');localStorage.setItem('sala_guia_v3','1');});
   await page.route('**/*',async route=>{
    const req=route.request(),u=new URL(req.url());
    if(u.protocol==='blob:'||u.protocol==='data:')return route.continue();
    if(req.method()==='POST'){
     const d=JSON.parse(req.postData()||'{}');
     if(d.accion!=='video_revision'){writes.push(d.accion);return route.fulfill({json:{ok:true}});}
     requests++;if(fail)return route.fulfill({json:{ok:false,error:'video_no_disponible'}});
     return route.fulfill({json:{ok:true,prop_id:d.prop_id,file_id:'syntheticvideo123',mime:'video/mp4',bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),cifrado:{url:cipherUrl,sha256:cipherSha,bytes:cipher.length,key:key.toString('base64'),iv:iv.toString('base64')}}});
    }
    if(req.url()===cipherUrl){assets++;return route.fulfill({body:cipher,contentType:'application/octet-stream',headers:{'Access-Control-Allow-Origin':'*'}});}
    if(u.hostname==='script.google.com')return route.fulfill({json:u.searchParams.get('recurso')==='dia'?day():{ok:true,cola:[],reglas:{}}});
    if(u.hostname!=='127.0.0.1')return route.fulfill({body:'',contentType:'application/javascript'});
    if(u.pathname==='/datos/manifiesto.json')return route.fulfill({json:day()});
    if(u.pathname==='/version-online.json')return route.fulfill({json:{}});
    if(u.pathname.startsWith('/datos/'))return route.fulfill({json:u.pathname.endsWith('/index.json')?[]:{}});
    return route.continue();
   });
   await surface.goto('http://127.0.0.1:'+server.address().port+(embedded?'/qa-embed':''));if(embedded){await surface.locator('#embudoFrame').waitFor();page=surface.frames().find(f=>f.parentFrame());assert.ok(page);}
   try{await page.waitForFunction(()=>document.querySelector('.video-nativo video')?.readyState>=2);}
   catch(e){console.error(JSON.stringify({engine:name,requests,errors,state:await page.evaluate(()=>{const v=document.querySelector('#zona video');return {video:v&&{state:v.readyState,error:v.error&&{code:v.error.code,message:v.error.message},source:!!v.src},aviso:document.querySelector('.video-aviso')?.textContent};})}));throw e;}
   assert.equal(await page.locator('#zona iframe').count(),0);
   const video=page.locator('#zona video');assert.equal(await video.getAttribute('playsinline'),'');
   assert.equal(requests,1);assert.equal(assets,1);await video.evaluate(v=>{v.muted=true;return v.play();});
   await page.waitForFunction(()=>document.querySelector('#zona video').currentTime>.5);
   await video.evaluate(v=>{v.pause();v.currentTime=3;});await page.waitForFunction(()=>document.querySelector('#zona video').currentTime>=3);
   await page.locator('[data-video-fullscreen]').click();assert.match(page.url(),/^http:\/\/127/);await page.waitForFunction(()=>!!document.fullscreenElement||!!document.webkitFullscreenElement||!!document.querySelector('#zona video')?.webkitDisplayingFullscreen||!!document.querySelector('.video-ampliado'));
   if(await page.evaluate(()=>!!document.fullscreenElement))await page.evaluate(()=>document.exitFullscreen());
   await surface.keyboard.press('Escape');if(await page.locator('.video-ampliado').count())await page.locator('.video-cerrar').click();assert.equal(await page.locator('.video-ampliado').count(),0);
   const old=await video.getAttribute('src');fail=true;
   await page.evaluate(()=>{idx=1;pintarCartas();});
   await page.waitForSelector('.video-reintentar:not([hidden])');assert.equal(requests,3);assert.equal(await page.locator('#zona video').getAttribute('src'),null);
   assert.equal(await page.evaluate(async u=>{try{const r=await fetch(u);return r.ok;}catch(e){return false;}},old),false);
   fail=false;await page.locator('.video-reintentar').click();await page.waitForFunction(()=>document.querySelector('#zona video')?.readyState>=2);
   assert.equal(requests,4);assert.equal(assets,2);assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
   await surface.screenshot({path:'/tmp/sala-video-'+name+'-'+width+'-'+embedded+'.png'});await surface.reload();if(embedded)page=surface.frames().find(f=>f.parentFrame());await page.waitForFunction(()=>document.querySelector('#zona video')?.readyState>=2);await page.locator('#zona video').evaluate(v=>{v.muted=true;return v.play();});await page.waitForFunction(()=>document.querySelector('#zona video').currentTime>.5);assert.deepEqual(writes,[]);
   console.log(JSON.stringify({engine:name,width,embedded,reopen:true,fullscreenEnteredAndReturned:true,playback:true,seek:true,retry:true,blobReleased:true,privateReads:requests,businessWrites:0}));
   await context.close();
  }}finally{await browser.close();}
 }}finally{server.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
