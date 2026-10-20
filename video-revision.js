/* Visor autenticado de Drive o archivo de video. Nunca admite iframes arbitrarios. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.VIDEO_REVISION=api;})(typeof self!=='undefined'?self:this,function(){
 'use strict';
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function resolver(src){
  if(typeof src!=='string'||!src||/[\s\\<>"']/.test(src))return null;
  const d=src.match(/^https:\/\/drive\.google\.com\/file\/d\/([A-Za-z0-9_-]{10,128})\/preview$/);
  if(d)return {tipo:'drive',src,enlace:`https://drive.google.com/file/d/${d[1]}/view`};
  if(src.startsWith('//')||src.split(/[?#]/)[0].split('/').some(x=>x==='..'||/%2e/i.test(x)))return null;
  if(!/\.(mp4|webm|mov)(?:[?#][^\s]*)?$/i.test(src))return null;
  if(/^[a-z][a-z0-9+.-]*:/i.test(src)&&!src.startsWith('https://'))return null;
  return {tipo:'archivo',src,enlace:src};
 }
 function html(src,privado){const v=resolver(src);if(!v)return '';
  if(v.tipo==='drive'&&!privado)return `<div class="lienzo conVideo"><iframe loading="lazy" src="${esc(v.src)}" title="Corte completo para revisar" allow="fullscreen" allowfullscreen referrerpolicy="no-referrer"></iframe></div>`;
  return `<div class="lienzo conVideo video-nativo"><video ${v.tipo==='archivo'?`src="${esc(v.src)}"`:''} controls playsinline webkit-playsinline preload="auto" aria-label="Corte completo para revisar"></video><button type="button" class="video-cerrar" aria-label="Cerrar video ampliado">Cerrar</button>${v.tipo==='drive'?'<div class="video-aviso"><span role="status">Preparando tu video…</span><button type="button" class="secund video-reintentar" hidden>Reintentar video</button></div>':''}</div>`;
 }
 async function decodificar(j,pid,src,signal){
  const v=resolver(src),id=v&&v.tipo==='drive'&&v.src.split('/')[5];
  if(!j||j.ok!==true||j.prop_id!==pid||j.file_id!==id||j.mime!=='video/mp4'||
   !Number.isSafeInteger(j.bytes)||j.bytes<12||j.bytes>12*1024*1024||
   !/^[a-f0-9]{64}$/.test(j.sha256||''))throw Error('video_incompleto');
  let bytes;
  if(j.cifrado){
   const c=j.cifrado;
   if(j.bytes>4*1024*1024||c.bytes!==j.bytes+16||!/^[a-f0-9]{64}$/.test(c.sha256||'')||
    !/^[A-Za-z0-9+/]{43}=$/.test(c.key||'')||!/^[A-Za-z0-9+/]{16}$/.test(c.iv||'')||
    !(new RegExp('^https://raw\\.githubusercontent\\.com/yodesarrollomx/sala-edicion/[a-f0-9]{40}/video-revision-cifrado/'+c.sha256+'\\.bin$')).test(c.url||''))throw Error('video_incompleto');
   const ctl=new AbortController(),cancel=()=>ctl.abort(),timer=setTimeout(cancel,8000);
   if(signal){if(signal.aborted)ctl.abort();else signal.addEventListener('abort',cancel,{once:true});}
   try{
    const r=await fetch(c.url,{signal:ctl.signal,credentials:'omit',referrerPolicy:'no-referrer'});
    if(!r.ok||Number(r.headers.get('content-length')||0)>c.bytes)throw Error('video_incompleto');
    const payload=new Uint8Array(await r.arrayBuffer());
    const sum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',payload)),n=>n.toString(16).padStart(2,'0')).join('');
    if(payload.length!==c.bytes||sum!==c.sha256)throw Error('video_incompleto');
    const from64=s=>Uint8Array.from(atob(s),x=>x.charCodeAt(0));
    const key=await crypto.subtle.importKey('raw',from64(c.key),'AES-GCM',false,['decrypt']);
    bytes=new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:from64(c.iv)},key,payload));
   }finally{clearTimeout(timer);if(signal)signal.removeEventListener('abort',cancel);}
  }else{
   if(typeof j.base64!=='string'||j.base64.length!==4*Math.ceil(j.bytes/3)||!/^[A-Za-z0-9+/]*={0,2}$/.test(j.base64))throw Error('video_incompleto');
   const raw=atob(j.base64);bytes=new Uint8Array(raw.length);
   for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  }
  if(bytes.length!==j.bytes||String.fromCharCode(...bytes.slice(4,8))!=='ftyp')throw Error('video_incompleto');
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==j.sha256)throw Error('video_incompleto');
  return new Blob([bytes],{type:j.mime});
 }
 let activo=null,trabajo=null;
 function desmontar(){if(activo){activo();activo=null;}}
 function montar(el,{pid,src,cargar,sesion=''}){
  desmontar();const host=el.querySelector('.video-nativo'),video=host&&host.querySelector('video');
  if(!video)return;
  const aviso=host.querySelector('.video-aviso'),status=aviso&&aviso.querySelector('[role="status"]'),retry=host.querySelector('.video-reintentar');
  let cancelado=false,url=null,ocupado=false;
  const key=pid+'\n'+src+'\n'+sesion;
  let job=null;
  if(aviso){
   if(!trabajo||trabajo.key!==key){if(trabajo)trabajo.ctl.abort();trabajo={key,ctl:new AbortController(),refs:0,promise:null};}
   job=trabajo;job.refs++;
  }
  const salir=()=>host.classList.remove('video-ampliado'),escape=e=>{if(e.key==='Escape')salir();};
  host.querySelector('.video-cerrar').onclick=salir;document.addEventListener('keydown',escape);
  const cleanup=()=>{cancelado=true;if(job){job.refs--;queueMicrotask(()=>{if(job.refs===0){job.ctl.abort();if(trabajo===job)trabajo=null;}});}document.removeEventListener('keydown',escape);video.pause();video.removeAttribute('src');video.load();if(url)URL.revokeObjectURL(url);};
  activo=cleanup;
  function informar(texto,fallo){if(!aviso)return;aviso.hidden=false;status.textContent=texto;retry.hidden=!fallo;}
  video.addEventListener('loadeddata',()=>{if(aviso)aviso.hidden=true;});
  video.addEventListener('error',()=>informar('No se pudo abrir el video. Puedes reintentarlo aquí.',true));
  video.addEventListener('loadedmetadata',()=>{try{if(video.currentTime===0)video.currentTime=Math.min(.01,video.duration/2);}catch(e){}});
  async function abrir(){
   if(ocupado||cancelado)return;ocupado=true;informar('Preparando tu video…',false);
   try{
    if(!job.promise)job.promise=cargar(pid,src,job.ctl.signal).then(j=>decodificar(j,pid,src,job.ctl.signal)).catch(e=>{job.promise=null;throw e;});
    const blob=await job.promise;if(cancelado)return;
    if(url)URL.revokeObjectURL(url);url=URL.createObjectURL(blob);video.src=url;video.load();
   }catch(e){if(!cancelado)informar('El video no llegó. Reintenta sin salir de la Sala.',true);}
   finally{ocupado=false;}
  }
  if(retry)retry.onclick=abrir;
  const full=el.querySelector('[data-video-fullscreen]');
  if(full)full.onclick=()=>{
   if(video.readyState<1){informar('El video se está preparando. Amplíalo cuando aparezca.',false);return;}
   try{
    if(typeof video.webkitEnterFullscreen==='function')video.webkitEnterFullscreen();
    else if(video.requestFullscreen){const p=video.requestFullscreen();if(p&&p.catch)p.catch(()=>host.classList.toggle('video-ampliado'));}
    else host.classList.toggle('video-ampliado');
   }catch(e){host.classList.toggle('video-ampliado');}
  };
  if(aviso)queueMicrotask(()=>{if(!cancelado)abrir();});
 }
 return {resolver,html,decodificar,montar,desmontar};
});
