(function(){
"use strict";
function fotoKey(v){return String(v&& (v.original||v.src)||"").split(/[?#]/)[0].replace(/\.jpe?g$/i,".png");}
function intentos(l){
 const paths=new Set();const receipts=new Set();
 for(const v of [...(l.versiones||[]),...(l.candidatas||[]),l]){
  const k=fotoKey(v);if(k)paths.add(k);
  if(v.recibo_imagen)receipts.add(v.recibo_imagen);
 }
 return Math.max(paths.size,receipts.size,Number(l.version)||0,1);
}
function estado(l,marks){
 if((marks||[]).includes("no"))return "rojo";
 if((marks||[]).includes("si")||l.estado==="aprobada")return "verde";
 if(/rechaz|cancel/.test(l.estado||""))return "rojo";
 if(!l.src&&!(l.candidatas||[]).length)return "produccion";
 return "amarillo";
}
const labels={amarillo:"Por revisar",verde:"Aprobada",rojo:"Cambio pedido",produccion:"En producción"};
const api={intentos,estado,fotoKey};
if(typeof module==="object"&&module.exports)module.exports=api;
if(typeof document==="undefined")return;
const root=document.getElementById("tableroHoy");if(!root)return;
window.SalaTablero=api;
const S={groups:[],focus:null,choice:null,filter:"todas",busy:false,loaded:false,last:null,notice:"",pinch:null};
const tones=["184,137,86","116,157,142","130,148,186","177,135,157","162,163,112","164,138,190","110,167,180"];
const eligible=()=>DECIDE()&&(!D||!D._respaldo||VISTA_DOC);
function group(){return S.groups.find(g=>g.id===S.focus);}
function tone(g){let h=0;for(const c of g.id)h=(h*31+c.charCodeAt(0))>>>0;return tones[h%tones.length];}
function markData(g,l){
 const key=Object.keys(mapaDe(g.t)).find(k=>Number(mapaDe(g.t)[k])===Number(l.n));
 const i=key===undefined?-1:Number(key)-1;
 const f=((D&&D.decisiones&&D.decisiones.propuestas)||{})[g.pid]||{};
 const local=dec[g.pid];const mine=local&&i>=0?local.laminas[i]:"";
 const fs=i>=0&&f.firmas&&f.firmas[i]||[];
 const own=fs.find(x=>x.quien===YO());
 const marks=fs.filter(x=>x.quien!==YO()).map(x=>x.marca);
 if(mine)marks.push(mine);else if(own)marks.push(own.marca);else if(!fs.length&&i>=0)marks.push((f.laminas||[])[i]||"");
 if(g.t.base&&dec[g.t.base]&&dec[g.t.base].laminas[l.n-1]==="no")marks.push("no");
 return {i,marks,mine,fs,nota:local&&i>=0?local.notas[i]||"":(f.notas||[])[i]||""};
}
function status(g,l){const md=markData(g,l);
 // El voto de otro editor no cierra tu revisión; el rechazo de cualquiera manda.
 const marks=eligible()&&md.i>=0&&dec[g.pid]&&!md.mine&&l.estado!=="aprobada"?md.marks.filter(m=>m==="no"):md.marks;
 return estado(l,marks);
}
function options(l){
 const c=POLITICA_IMAGEN.tomas(l);
 if(c.length)return c;
 const src=fuenteLamina(l,l.src);return src?[{src,original:l.original,indiceOriginal:null,titulo:"Actual",modelo:l.modelo}]:[];
}
function phase(g){
 const q=(COLA||[]).filter(f=>normSlug(f.pieza)===normSlug(g.t.pieza_slug||g.t.pieza)&&!/barrida|hecho|cancel|retirad/i.test(f.estado||""));
 const running=q.find(f=>/corriendo|proceso/i.test(f.estado||""));
 const bad=q.find(f=>/fallo|error/i.test(f.estado||""));
 return running?{text:"Produciendo "+(running.etapa||""),kind:"produccion"}:bad?{text:"Producción necesita atención",kind:"rojo"}:q.length?{text:q.length+" trabajos en fila",kind:"produccion"}:null;
}
function visible(){return S.groups.filter(g=>S.filter==="todas"||(g.t.laminas||[]).some(l=>S.filter==="atencion"?status(g,l)==="amarillo"||status(g,l)==="rojo":status(g,l)==="produccion")||(S.filter==="produccion"&&phase(g)));}
function img(src,alt,cls=""){
 return src?`<img class="${cls}" src="${esc(ligera(src))}" alt="${esc(alt)}" loading="lazy" decoding="async">`:`<div class="bt-sin-foto">Preparando fotografía</div>`;
}
function counts(g){const c={amarillo:0,rojo:0,verde:0,produccion:0};(g.t.laminas||[]).forEach(l=>c[status(g,l)]++);return c;}
function header(g){
 const c=counts(g),p=phase(g);
 return `<header class="bt-col-head"><span class="bt-eyebrow">PUBLICACIÓN ${S.groups.indexOf(g)+1}</span>
 <button class="bt-topic" data-open="${esc(g.id)}"><h2>${esc(g.t.pieza||g.p.titulo||g.id)}</h2><span aria-hidden="true">↗</span></button>
 <div class="bt-counts">${c.amarillo?`<span class="bt-dot amarillo">${c.amarillo} por revisar</span>`:""}${c.rojo?`<span class="bt-dot rojo">${c.rojo} con cambios</span>`:""}${c.verde?`<span class="bt-dot verde">${c.verde} aprobadas</span>`:""}${p?`<span class="bt-dot ${p.kind}">${esc(p.text)}</span>`:""}</div>
 <div class="bt-tools"><button data-info="guion" data-group="${esc(g.id)}">Guion</button><button data-info="intencion" data-group="${esc(g.id)}">Intención</button><button data-info="historial" data-group="${esc(g.id)}">Historial</button></div></header>`;
}
function card(g,l){
 const st=status(g,l),src=fuenteLamina(l,l.src),v=intentos(l),md=markData(g,l);
 return `<article class="bt-frame ${st}" data-frame="${l.n}" data-group="${esc(g.id)}">
 <button class="bt-photo" data-lamina="${l.n}" data-group="${esc(g.id)}" aria-label="Lámina ${l.n}, ${labels[st]}, ${v} intentos. Abrir">
 ${img(src,"Lámina "+l.n)}<span class="bt-lamina">L${l.n}</span><span class="bt-light ${st}" aria-hidden="true"></span></button>
 <div class="bt-frame-meta"><span class="bt-dot ${st}">${labels[st]}</span><button class="bt-attempts" data-history="${l.n}" data-group="${esc(g.id)}" aria-label="Ver historial de ${v} intentos">↺ <b>${v}</b></button></div>
 <p class="bt-caption">${esc(l.dice||"Lámina "+l.n)}</p>${md.fs.length?`<small class="bt-signatures">${md.fs.map(f=>esc(f.quien)+": "+(f.marca==="si"?"✓":f.marca==="no"?"cambio":"pendiente")).join(" · ")}</small>`:""}
 </article>`;
}
function render(){
 if(!D)return;
 const previousLevel=root.dataset.level;
 document.body.classList.add("sala-tablero");
 const f=group(),cg=S.choice&&S.groups.find(g=>g.id===S.choice.group),cl=cg&&(cg.t.laminas||[]).find(l=>Number(l.n)===S.choice.n);
 const vg=f?[f]:visible(),pending=S.groups.reduce((n,g)=>n+counts(g).amarillo,0);
 const oldX=root.querySelector(".bt-pan")?.scrollLeft||0;
 root.dataset.level=S.choice?"opciones":f?"publicacion":"tablero";
 root.dataset.transition=String(previousLevel!==root.dataset.level);
 root.innerHTML=`<div class="bt-heading"><div><span class="bt-eyebrow">SALA DE EDICIÓN</span><h1>${f?esc(f.t.pieza||f.p.titulo):"Tus publicaciones, de un vistazo"}</h1><p>${f?"Tira completa · toca una lámina para comparar sus opciones.":S.groups.length+" publicaciones · "+pending+" láminas por revisar"}</p></div>
 <div class="bt-heading-actions"><button data-refresh ${S.busy?"disabled":""}>${S.busy?"Actualizando…":"↻ Actualizar"}</button><button data-legacy>Revisión paso a paso</button></div></div>
 <div class="bt-bar"><div class="bt-legend"><span class="bt-dot amarillo">Revisar</span><span class="bt-dot verde">Aprobada</span><span class="bt-dot rojo">Cambio pedido</span><span class="bt-dot produccion">Producción</span></div>
 <div class="bt-levels"><button data-back ${!f?"disabled":""} aria-label="Alejar, volver al tablero">−</button><span>${S.choice?"3 · Opciones":f?"2 · Publicación":"1 · Tablero"}</span><button data-zoom aria-label="Acercar">${S.choice?"↗":"+"}</button></div></div>
 <div class="bt-nav">${f?`<button data-back>← Todas las publicaciones</button><button data-next>Ir a la siguiente por revisar →</button>`:
 `<div class="bt-filters">${["todas","atencion","produccion"].map(k=>`<button data-filter="${k}" class="${S.filter===k?"on":""}" aria-pressed="${S.filter===k}">${k==="todas"?"Todas":k==="atencion"?"Necesitan atención":"En producción"}</button>`).join("")}</div><span class="bt-hint">Toca una columna para acercarte · doble clic en una lámina para elegir</span>`}</div>
 <div class="bt-pan" tabindex="0" aria-label="Tablero de publicaciones"><div class="bt-columns">${vg.map((g,i)=>`<section class="bt-column" style="--bt-tone:${tone(g)}" data-column="${esc(g.id)}">${header(g)}<div class="bt-frames">${(g.t.laminas||[]).map(l=>card(g,l)).join("")}${g.ejes.map(p=>`<button class="bt-other" data-eje="${esc(p.id)}">${esc(p.titulo||"Revisión de guion o producción")} →</button>`).join("")}</div></section>`).join("")||`<div class="bt-empty"><h2>${S.loaded?"No hay publicaciones en este filtro":"Cargando las publicaciones…"}</h2><p>${S.loaded?"Las decisiones y el historial siguen guardados. Elige Todas para volver.":"Leyendo la tira completa de cada publicación."}</p></div>`}</div></div>
 <p class="bt-bottom">El número ↺ cuenta los intentos de cada lámina. Amarillo pide tu revisión; azul indica trabajo en la nube. Usa +/−, la rueda sobre una imagen o dos dedos para acercar y alejar.</p>
 <p class="bt-notice" role="status" aria-live="polite">${esc(S.notice)}</p>`;
 root.querySelector(".bt-pan").scrollLeft=oldX;
 if(cl)renderChoice(cg,cl);
 bind();if(S.choice){root.querySelector(".bt-carousel")?.focus({preventScroll:true});}
}
function info(g,n,kind){
 const l=(g.t.laminas||[]).find(x=>Number(x.n)===n);
 if(kind==="guion"){verGuia(g.t);return;}
 if(kind==="intencion"){
 const d=g.t.direccion||{};
 hoja(`<h3>Intención · ${esc(g.t.pieza||g.id)}</h3><p>${esc(d.promesa||g.t.promesa||g.p.porque||"Sin intención registrada todavía.")}</p>${(d.escenas||g.t.laminas||[]).map(e=>`<p><b>L${e.n}</b> · ${esc(e.entiende||e.por_que||e.ve||e.dice||"")}</p>`).join("")}`,"tablero-intencion");return;
 }
 const rows=l?[l]:g.t.laminas||[];
 hoja(`<h3>${l?"Lámina "+n:"Historial"} · ${esc(g.t.pieza||g.id)}</h3><p>Intentos anteriores y opciones actuales. Tus votos y notas se conservan.</p>${rows.map(x=>{const candidates=[...(x.versiones||[]),...(x.candidatas||[])],seen=new Set();if(!candidates.length)candidates.push(x);return `<h4>L${x.n} · ${intentos(x)} intentos</h4><div class="bt-history">${candidates.filter(v=>{const k=fotoKey(v)||JSON.stringify(v);if(seen.has(k))return false;seen.add(k);return true;}).map((v,i)=>{const retired=POLITICA_IMAGEN.vetada(v);return `<article>${retired?`<div class="bt-sin-foto">Modelo retirado</div>`:img(v.src||v.original,"Intento "+(i+1))}<b>${esc(v.titulo||"Intento "+(v.v||i+1))}</b><small>${esc(v.fecha||v.generado_en||"")}</small><small>${esc(v.modelo||v.motor||"")}</small><p>${v.marca==="si"?"Aprobada":v.marca==="no"?"Cambio pedido":"Versión guardada"}${v.nota?" · "+esc(v.nota):""}</p></article>`}).join("")}</div>`}).join("")}`,"tablero-historial");
}
function open(g,n,choose=false){
 if(!g)return;
 if(!S.focus){document.body.classList.remove("sala-turno");S.focus=g.id;abrirCapa("tablero-publicacion",()=>{S.focus=null;S.choice=null;render();},null,root);}
 else S.focus=g.id;
 render();
 if(choose&&n)chooseFrame(g,n);
 else {root.querySelector(`[data-frame="${n||1}"] button`)?.focus({preventScroll:true});}
}
function chooseFrame(g,n){
 const l=(g.t.laminas||[]).find(x=>Number(x.n)===Number(n));if(!l)return;
 const opts=options(l),md=markData(g,l),selected=/\[toma elegida: (\d+)\]/.exec(md.nota||"");
 let k=selected?opts.findIndex(o=>o.indiceOriginal===Number(selected[1])-1):0;
 if(k<0)k=0;
 S.choice={group:g.id,n:Number(n),k};
 if(!CAPAS.some(c=>c.id==="tablero-opciones"))abrirCapa("tablero-opciones",()=>{S.choice=null;render();},null,root);
 render();
}
function back(){
 if(S.choice){cerrarCapa("tablero-opciones");return;}
 if(S.focus)cerrarCapa("tablero-publicacion");
}
function next(){
 const list=S.groups.flatMap(g=>(g.t.laminas||[]).filter(l=>status(g,l)==="amarillo").map(l=>({g,l})));
 if(!list.length){S.notice="No quedan láminas amarillas. Puedes ver aprobadas, cambios y producción.";render();return;}
 const i=S.choice?list.findIndex(x=>x.g.id===S.choice.group&&Number(x.l.n)===S.choice.n):-1;
 const x=list[(i+1)%list.length];open(x.g,x.l.n,true);
}
function renderChoice(g,l){
 const os=options(l),c=S.choice,k=Math.min(c.k,Math.max(0,os.length-1)),o=os[k],md=markData(g,l),st=status(g,l);
 c.k=k;
 const writable=eligible()&&md.i>=0&&!!dec[g.pid]&&l.estado!=="aprobada";
 const box=document.createElement("div");box.className="bt-choice";box.setAttribute("role","dialog");box.setAttribute("aria-modal","true");box.setAttribute("aria-label","Elegir fotografía de lámina "+l.n);
 box.innerHTML=`<div class="bt-choice-top"><button data-back>← Tira completa</button><span>${esc(g.t.pieza||g.id)} · L${l.n}</span><button data-close-choice aria-label="Cerrar opciones">×</button></div>
 <div class="bt-choice-content"><div class="bt-carousel" tabindex="0" aria-label="Opciones; flechas para cambiar, botón para aprobar">
 <div class="bt-hero">${o?img(o.src||o.original,"Opción "+(k+1),"bt-main-photo"):`<div class="bt-sin-foto">No hay una toma disponible todavía</div>`}<span class="bt-lamina">L${l.n}</span></div>
 <div class="bt-pager"><button data-prev-option aria-label="Opción anterior" ${k<=0?"disabled":""}>←</button><span>${os.length?"Opción "+(k+1)+" de "+os.length:"En producción"}</span><button data-next-option aria-label="Opción siguiente" ${k>=os.length-1?"disabled":""}>→</button></div>
 <div class="bt-thumbs">${os.map((x,i)=>`<button data-option="${i}" aria-label="Ver opción ${i+1}" aria-pressed="${i===k}" class="${i===k?"on":""}">${img(x.src,"Opción "+(i+1))}</button>`).join("")}</div></div>
 <div class="bt-choice-copy"><span class="bt-dot ${st}">${labels[st]}</span><h2>${esc(l.dice||"Lámina "+l.n)}</h2><p>${esc(o&&o.texto||l.ve||"")}</p>
 <div class="bt-tools"><button data-info="guion" data-group="${esc(g.id)}">Guion</button><button data-info="intencion" data-group="${esc(g.id)}">Intención</button><button data-history="${l.n}" data-group="${esc(g.id)}">↺ ${intentos(l)} intentos</button><button data-full-photo ${!o?"disabled":""}>Ampliar</button></div>
 <small>${esc(o&&(o.modelo||o.motor)||"")}</small>${md.nota?`<p class="bt-editor-note">Tu nota: ${esc(md.nota.replace(/\s*\[toma elegida: \d+\]/g,""))}</p>`:""}
 <div class="bt-decisions"><button class="bt-approve" data-vote="si" ${!writable||!o?"disabled":""}>↑ Aprobar esta opción</button><button class="bt-reject" data-vote="no" ${!writable?"disabled":""}>× Pedir cambio</button></div>
 <p class="bt-gesture-hint">${writable?"Desliza la foto a los lados para comparar. Hacia arriba aprueba la opción visible.":l.estado==="aprobada"?"Esta lámina ya está aprobada. Su historia queda conservada.":"Vista de lectura: aquí puedes comparar sin cambiar decisiones."}</p>
 ${l.estado==="aprobada"&&eligible()&&g.t.base?`<button data-reopen>Pedir una nueva revisión</button>`:""}
 <button class="bt-next-review" data-next>Siguiente por revisar →</button><p class="bt-notice" role="status">${esc(S.notice)}</p></div></div>`;
 root.appendChild(box);
}
function moveOption(delta){if(!S.choice)return;const g=S.groups.find(x=>x.id===S.choice.group),l=g.t.laminas.find(x=>Number(x.n)===S.choice.n);S.choice.k=Math.min(Math.max(0,S.choice.k+delta),Math.max(0,options(l).length-1));render();}
function ampliarOpciones(){
 if(!S.choice)return;
 const {group:gid,n,k}=S.choice,g=S.groups.find(x=>x.id===gid),l=g&&g.t.laminas.find(x=>Number(x.n)===n);
 if(!l)return;
 const os=options(l),md=markData(g,l),writable=eligible()&&md.i>=0&&!!dec[g.pid]&&l.estado!=="aprobada";
 const galeria=os.map((o,i)=>({src:o.original||o.src,titulo:"Opción "+(i+1),...(writable?{elegir:photo=>{
  if(!S.choice||S.choice.group!==gid||S.choice.n!==n||!eligible())return;
  const live=S.groups.find(x=>x.id===gid),frame=live&&live.t.laminas.find(x=>Number(x.n)===n);
  if(!frame||fotoKey(options(frame)[i]||{})!==fotoKey(o))return;
  S.choice.k=i;vote("si",photo);
 }}:{})}));
 if(galeria[k])abrirZoom(galeria[k].src,{galeria,i:k});
}
function vote(m,zoomPhoto){
 if(!S.choice||!eligible())return;
 const g=S.groups.find(x=>x.id===S.choice.group),l=g.t.laminas.find(x=>Number(x.n)===S.choice.n),md=markData(g,l),d=dec[g.pid],o=options(l)[S.choice.k];
 if(!d||md.i<0||l.estado==="aprobada")return;
 const image=zoomPhoto||root.querySelector(".bt-main-photo");
 if(m==="si"&&(!mediosDisponibles()||!o||!image||!image.complete||!image.naturalWidth)){S.notice="Espera a que cargue esta fotografía antes de aprobarla.";render();return;}
 const apply=note=>{
  S.last={pid:g.pid,i:md.i,marca:d.laminas[md.i],nota:d.notas[md.i]};
  const before=String(note??d.notas[md.i]??"").replace(/\s*\[toma elegida: \d+\]/g,"").trim();
  d.laminas[md.i]=m;d.notas[md.i]=m==="si"?before+(o.indiceOriginal===null?"":(before?" ":"")+"[toma elegida: "+(o.indiceOriginal+1)+"]"):before;
  if(d._borrar)delete d._borrar[md.i];
  if(!pasos.some(x=>x.tipo==="lamina"&&x.pid===g.pid&&x.i===md.i)){pasos.push({tipo:"lamina",pid:g.pid,i:md.i,p:g.p});lockeadas=lockeadas.filter(x=>!(x.pid===g.pid&&x.i===md.i));}
  guardarBorrador();programarSubida();subir();
  S.notice=m==="si"?"Opción elegida. El indicador de guardado confirma su envío al Sheet.":"Cambio pedido. La nota viaja con tu revisión.";render();
 };
 if(m==="no"){pedirNota(note=>{apply(note);},md.nota.replace(/\s*\[toma elegida: \d+\]/g,""));}else apply();
}
async function reintentarFoto(im){
 if(typeof SalaMedios!=="undefined"&&!mediosDisponibles()){await SalaMedios.cargar();render();return;}
 im.removeAttribute("data-failed");im.parentElement.querySelector(".bt-retry-label")?.remove();
 im.src=typeof SalaMedios!=="undefined"?SalaMedios.reintentar(im.src):im.src.split("?")[0]+"?reintentar="+Date.now();
}
function bind(){
 const gs=id=>S.groups.find(x=>x.id===id);
 root.querySelectorAll("[data-open]").forEach(b=>b.onclick=()=>open(gs(b.dataset.open)));
 root.querySelectorAll("[data-lamina]").forEach(b=>{
  b.onclick=()=>{const failed=b.querySelector("img[data-failed]");if(failed){reintentarFoto(failed);return;}const g=gs(b.dataset.group);if(!S.focus)open(g,Number(b.dataset.lamina));else chooseFrame(g,Number(b.dataset.lamina));};
  b.ondblclick=e=>{e.preventDefault();const g=gs(b.dataset.group);open(g,Number(b.dataset.lamina),true);};
 });
 root.querySelectorAll("[data-info]").forEach(b=>b.onclick=()=>info(gs(b.dataset.group),0,b.dataset.info));
 root.querySelectorAll("[data-history]").forEach(b=>b.onclick=()=>info(gs(b.dataset.group),Number(b.dataset.history),"historial"));
 root.querySelectorAll("[data-back],[data-close-choice]").forEach(b=>b.onclick=back);
 root.querySelectorAll("[data-next]").forEach(b=>b.onclick=next);
 root.querySelectorAll("[data-filter]").forEach(b=>b.onclick=()=>{S.filter=b.dataset.filter;render();});
 root.querySelectorAll("[data-option]").forEach(b=>b.onclick=()=>{S.choice.k=Number(b.dataset.option);render();});
 root.querySelector("[data-prev-option]")?.addEventListener("click",()=>moveOption(-1));
 root.querySelector("[data-next-option]")?.addEventListener("click",()=>moveOption(1));
 root.querySelectorAll("[data-vote]").forEach(b=>b.onclick=()=>vote(b.dataset.vote));
 root.querySelector("[data-full-photo]")?.addEventListener("click",ampliarOpciones);
 root.querySelector("[data-reopen]")?.addEventListener("click",()=>{const g=gs(S.choice.group),l=g.t.laminas.find(l=>Number(l.n)===S.choice.n);pedirNota(note=>{reabrirAprobada(g.t,l,note);S.focus=null;S.choice=null;render();});});
 root.querySelector("[data-zoom]")?.addEventListener("click",()=>{if(S.choice)root.querySelector("[data-full-photo]")?.click();else if(S.focus){const g=group();chooseFrame(g,g.t.laminas[0]?.n);}else open(visible()[0]);});
 root.querySelector("[data-refresh]")?.addEventListener("click",()=>refresh(true));
 root.querySelector("[data-legacy]")?.addEventListener("click",()=>{cerrarCapas();document.body.classList.remove("sala-tablero");document.body.classList.add("sala-turno");pintarCartas();});
 root.querySelectorAll("[data-eje]").forEach(b=>b.onclick=()=>{cerrarCapas();document.body.classList.remove("sala-tablero");document.body.classList.add("sala-turno");const k=pasos.findIndex(x=>x.pid===b.dataset.eje);if(k>=0){idx=k;irVista("hoy");pintarCartas();}});
 root.querySelectorAll(".bt-photo img,.bt-main-photo").forEach(im=>{im.onerror=()=>{
  im.dataset.failed="1";const parent=im.parentElement;if(parent.querySelector(".bt-retry-label"))return;
  const label=document.createElement(parent.classList.contains("bt-hero")?"button":"span");label.className="bt-retry-label";label.textContent="Foto sin cargar · reintentar";parent.appendChild(label);
  if(label.tagName==="BUTTON")label.onclick=()=>reintentarFoto(im);
 };});
 const hero=root.querySelector(".bt-hero");if(hero){
  let p=null;hero.addEventListener("pointerdown",e=>{if(e.target.closest("button,a,input,textarea,select,[role=button]"))return;if(e.isPrimary){p={x:e.clientX,y:e.clientY,id:e.pointerId};hero.setPointerCapture(e.pointerId);}});
  hero.addEventListener("pointercancel",()=>{p=null;});
  hero.addEventListener("pointerup",e=>{if(!p||p.id!==e.pointerId)return;const dx=e.clientX-p.x,dy=e.clientY-p.y;p=null;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.3)moveOption(dx<0?1:-1);else if(dy< -95&&Math.abs(dx)<45)vote("si");});
 }
}
async function refresh(live=false){
 if(S.busy)return;S.busy=true;render();
 try{
  if(live&&ENTRADO()){_tCola=0;traerCola();const d=await traer(fecha,1,20000,true);if(d&&!d._respaldo&&!d.error)aplicarDia(d);else S.notice="No se confirmó una lectura nueva del Sheet; conservé lo que ya tenías.";}
  const props=(D&&(D._todas||D.propuestas))||[];
  if(live){for(const p of props)delete TIRAS[p.id];}
  const all=await Promise.all(props.map(async p=>({p,t:await cargarTira(p.id)}))),map=new Map();
  for(const {p,t}of all){if(!t||!(t.laminas||[]).length)continue;const id=t.pieza_slug||normSlug(t.pieza||p.pieza||p.titulo);let g=map.get(id);if(!g){g={id,pid:p.id,p,t,ejes:[]};map.set(id,g);}else if((D.propuestas||[]).some(x=>x.id===p.id)&&!dec[g.pid])map.set(id,{id,pid:p.id,p,t,ejes:g.ejes});}
  for(const {p,t}of all){if(t&&(t.laminas||[]).length)continue;const id=p.pieza_slug||normSlug(p.pieza||String(p.titulo||"").split(" · ")[0]);const g=map.get(id)||[...map.values()].find(x=>normSlug(x.t.pieza)===id);if(g)g.ejes.push(p);else map.set(id,{id,pid:p.id,p,t:{pieza:p.pieza||p.titulo,pieza_slug:id,laminas:[]},ejes:[p]});}
  S.groups=[...map.values()];S.loaded=true;if(S.focus&&!group()){S.focus=null;S.choice=null;}
 }catch(e){S.notice="No pude actualizar el tablero. Tu revisión sigue conservada. Usa Actualizar.";}
 finally{S.busy=false;render();}
}
api.refresh=refresh;api.render=render;api.produccionActualizada=()=>{if(!S.choice)render();};
const returnButton=document.createElement("button");returnButton.className="bt-return";returnButton.textContent="← Volver al tablero";returnButton.onclick=()=>{document.body.classList.remove("sala-turno");render();};document.getElementById("vHoy").prepend(returnButton);
let wheelTotal=0,lastWheel=0;
root.addEventListener("wheel",e=>{
 if(CAPAS.some(c=>!["tablero-publicacion","tablero-opciones"].includes(c.id)))return;
 const photo=e.target.closest(".bt-photo,.bt-hero");
 if(!photo&&!e.ctrlKey&&!e.metaKey)return;
 if(Date.now()-lastWheel>400)wheelTotal=0;lastWheel=Date.now();wheelTotal+=e.deltaY;
 if(e.ctrlKey||e.metaKey||photo)e.preventDefault();
 if(wheelTotal< -100){wheelTotal=0;if(!S.focus){const g=S.groups.find(g=>g.id===photo?.dataset.group)||visible()[0];open(g);}else if(!S.choice){const n=Number(photo?.dataset.lamina)||group().t.laminas[0]?.n;chooseFrame(group(),n);}}
 else if(wheelTotal>100){wheelTotal=0;back();}
},{passive:false});
root.addEventListener("touchstart",e=>{if(e.touches.length===2){S.pinch={d:Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY),g:e.target.closest("[data-group],[data-column]")?.dataset.group||e.target.closest("[data-column]")?.dataset.column};e.preventDefault();}},{passive:false});
root.addEventListener("touchmove",e=>{if(e.touches.length!==2||!S.pinch)return;e.preventDefault();const d=Math.hypot(e.touches[0].clientX-e.touches[1].clientX,e.touches[0].clientY-e.touches[1].clientY),r=d/S.pinch.d;if(r<.78){S.pinch=null;back();}else if(r>1.25){const id=S.pinch.g;S.pinch=null;if(!S.focus)open(S.groups.find(g=>g.id===id)||visible()[0]);else if(!S.choice)chooseFrame(group(),group().t.laminas[0]?.n);}},{passive:false});
root.addEventListener("touchend",()=>{S.pinch=null;});
document.addEventListener("keydown",e=>{
 if(!document.body.classList.contains("sala-tablero")||document.body.dataset.vista!=="hoy"||e.target.closest("textarea,input")||CAPAS.some(c=>!["tablero-publicacion","tablero-opciones"].includes(c.id)))return;
 if(S.choice&&(e.key==="ArrowLeft"||e.key==="ArrowRight")){e.preventDefault();e.stopImmediatePropagation();moveOption(e.key==="ArrowLeft"?-1:1);}
 if(e.key==="Tab"&&S.choice){const buttons=[...root.querySelectorAll(".bt-choice button:not(:disabled),.bt-choice [tabindex]")];if(e.shiftKey&&document.activeElement===buttons[0]){e.preventDefault();buttons[buttons.length-1]?.focus();}else if(!e.shiftKey&&document.activeElement===buttons[buttons.length-1]){e.preventDefault();buttons[0]?.focus();}}
},true);
setInterval(()=>{if(D&&!document.hidden&&document.body.dataset.vista==="hoy"&&!S.choice)render();},30000);
if(D)refresh();
})();
