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
function textoToma(l,o){return o&&o.dice||l.dice||"Lámina "+l.n;}
function preseleccion(storage,context,opciones){
 const ids=opciones.map(o=>JSON.stringify([o.indiceOriginal,fotoKey(o),o.recibo_imagen||"",o.dice||""]));
 const key="sala_finalistas_v1:"+JSON.stringify([context.quien,context.pid,context.n,context.version,context.dice||"",ids]);
 function leer(){
  const raw=storage.getItem(key),a=raw===null?[]:JSON.parse(raw);
  if(!Array.isArray(a)||a.length>2||a.some(x=>!ids.includes(x))||new Set(a).size!==a.length)throw Error("Preselección inválida");
  return a;
 }
 function cambiar(i){
  if(!["editor","editor2"].includes(context.quien)||!ids[i])throw Error("No disponible");
  const a=leer(),id=ids[i],next=a.includes(id)?a.filter(x=>x!==id):[...a,id];
  if(next.length>2)return {ok:false,limite:true,indices:a.map(x=>ids.indexOf(x))};
  storage.setItem(key,JSON.stringify(next));
  if(JSON.stringify(leer())!==JSON.stringify(next))throw Error("Guardado sin confirmar");
  return {ok:true,indices:next.map(x=>ids.indexOf(x))};
 }
 return {leer:()=>leer().map(x=>ids.indexOf(x)),cambiar};
}
function proyectarPublicacion(t,registro){
 const copia=JSON.parse(JSON.stringify(t));
 const frames=new Map((registro.laminas||[]).map(l=>[Number(l.n),l]));
 if(frames.size!==(copia.laminas||[]).length)throw Error("Proyección incompleta");
 for(const l of copia.laminas||[]){
  const f=frames.get(Number(l.n));if(!f||!["aprobada","rechazada","pendiente"].includes(f.estado))throw Error("Estado sin confirmar");
  if(f.toma!==undefined){
   if(!Number.isInteger(f.toma)||f.toma<1)throw Error("Toma inválida");
   const c=(l.candidatas||[])[f.toma-1];if(!c||!(c.original||c.src))throw Error("Toma ausente");
   l.src=c.original||c.src;l.original=l.src;l.dice=c.dice||l.dice;
   l.seleccion={toma:f.toma};
  }
  l.estado=f.estado;
 }
 return copia;
}
// Cortes se relacionan por fuente exacta, nunca por el prefijo del título.
function grupoDeCorte(p,groups){
 const source=/^corte-de ([A-Za-z0-9_-]+)$/.exec(String(p.origen||""));
 if(!source)return null;
 const matches=groups.filter(g=>g.pid===source[1]);
 return matches.length===1?matches[0]:null;
}
const api={grupoDeCorte,intentos,estado,fotoKey,textoToma,preseleccion,proyectarPublicacion};
if(typeof module==="object"&&module.exports)module.exports=api;
if(typeof document==="undefined")return;
const root=document.getElementById("tableroHoy");if(!root)return;
window.SalaTablero=api;
const S={groups:[],focus:null,choice:null,filter:"todas",busy:false,loaded:false,last:null,notice:"",pinch:null};
api.contexto=function(el){
 const card=el&&el.closest&&el.closest('[data-group]');
 const gid=card&&card.dataset.group||(S.choice&&S.choice.group)||S.focus;
 const g=S.groups.find(x=>x.id===gid);if(!g)return null;
 const frame=el&&el.closest&&el.closest('[data-frame]');
 const n=frame?Number(frame.dataset.frame):(S.choice&&S.choice.group===gid?S.choice.n:null);
 const l=(g.t.laminas||[]).find(x=>Number(x.n)===n);
 const k=S.choice&&S.choice.group===gid&&S.choice.n===n?S.choice.k:null;
 const zoom=document.querySelector('.zoom[data-fuente]');
 const z=zoom&&l?options(l).find(o=>fotoKey(o)===fotoKey({src:zoom.dataset.fuente})):null;
 const o=z||(l&&k!==null?options(l)[k]:null);
 return {pid:g.pid,pieza:g.t.pieza||g.id,tipo:'lamina',lamina:n,version:l&&l.version||null,
  src:o&&(o.original||o.src)||l&&(l.original||l.src)||null,toma:o?o.indiceOriginal:null,
  recibo:o&&o.recibo_imagen||l&&l.recibo_imagen||null};
};
const tones=["184,137,86","116,157,142","130,148,186","177,135,157","162,163,112","164,138,190","110,167,180"];
const eligible=()=>!S.cached&&DECIDE()&&(!D||!D._respaldo||VISTA_DOC);
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
 const q=(COLA||[]).filter(f=>normSlug(f.pieza)===normSlug(g.t.pieza_slug||g.t.pieza)&&!/barrida|hecho|cancel|retirad|obsoleto/i.test(f.estado||""));
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
 // Una lectura de cola o el reloj no interrumpen una revisión de video/eje.
 if(document.body.classList.contains("sala-turno"))return;
 if(!D)return;
 const previousLevel=root.dataset.level;
 document.body.classList.add("sala-tablero");
 const f=group(),cg=S.choice&&S.groups.find(g=>g.id===S.choice.group),cl=cg&&(cg.t.laminas||[]).find(l=>Number(l.n)===S.choice.n);
 const vg=f?[f]:visible(),pending=S.groups.reduce((n,g)=>n+counts(g).amarillo,0);
 const oldX=root.querySelector(".bt-pan")?.scrollLeft||0;
 root.dataset.level=S.choice?"opciones":f?"publicacion":"tablero";
 root.dataset.transition=String(previousLevel!==root.dataset.level);
 root.innerHTML=`${S.cached?`<p class="bt-notice bt-local" role="status">Copia guardada el ${esc(new Date(S.savedAt).toLocaleString('es-MX'))} · Actualizando. Puedes consultar; las decisiones se habilitan al confirmar la mesa vigente.</p>`:''}<div class="bt-heading"><div><span class="bt-eyebrow">SALA DE EDICIÓN</span><h1>${f?esc(f.t.pieza||f.p.titulo):"La mesa editorial"}</h1><p>${f?"Lee la secuencia completa. Abre una página para revisar sus tomas.":S.groups.length+" "+(S.groups.length===1?"publicación":"publicaciones")+" en mesa · "+pending+" páginas por revisar"}</p></div>
 <div class="bt-heading-actions"><button data-refresh ${S.busy?"disabled":""}>${S.busy?"Actualizando…":"↻ Actualizar"}</button><button data-legacy ${S.cached?"disabled":""}>Otras revisiones</button></div></div>
 ${!f&&!S.cached?`<div class="bt-editorial-intro"><div><span class="bt-eyebrow">TU CRITERIO, ANTES DE PRODUCIR</span><h2>Una historia. Cada detalle.</h2><p>Revisa el mensaje, compara las tomas y deja una decisión clara. Tus notas acompañan cada página.</p></div><button class="bt-start" data-next ${pending?"":"disabled"}>${pending?"Empezar revisión ↗":"Sin páginas por revisar"}</button></div>`:""}
 <div class="bt-bar"><div class="bt-legend"><span class="bt-dot amarillo">Revisar</span><span class="bt-dot verde">Aprobada</span><span class="bt-dot rojo">Cambio pedido</span><span class="bt-dot produccion">Producción</span></div>
 <div class="bt-levels"><button data-back ${!f?"disabled":""} aria-label="Alejar, volver al tablero">−</button><span>${S.choice?"Revisión":f?"Libro abierto":"Vista general"}</span><button data-zoom aria-label="Acercar">${S.choice?"↗":"+"}</button></div></div>
 <div class="bt-nav">${f?`<button data-back>← Todas las publicaciones</button><button data-next>Ir a la siguiente por revisar →</button>`:
 `<div class="bt-filters">${["todas","atencion","produccion"].map(k=>`<button data-filter="${k}" class="${S.filter===k?"on":""}" aria-pressed="${S.filter===k}">${k==="todas"?"Todas":k==="atencion"?"Necesitan atención":"En producción"}</button>`).join("")}</div><span class="bt-hint">Cada publicación conserva su secuencia y sus decisiones</span>`}</div>
 <div class="bt-pan" tabindex="0" aria-label="Tablero de publicaciones"><div class="bt-columns">${vg.map((g,i)=>`<section class="bt-column" style="--bt-tone:${tone(g)}" data-column="${esc(g.id)}">${header(g)}<div class="bt-frames">${(g.t.laminas||[]).map(l=>card(g,l)).join("")}${g.ejes.map(p=>`<button class="bt-other" data-eje="${esc(p.id)}">${esc(p.titulo||"Revisión de guion o producción")} →</button>`).join("")}</div></section>`).join("")||`<div class="bt-empty"><h2>${S.loaded?(S.filter==="todas"?"No se han cargado publicaciones":"No hay publicaciones en este filtro"):"Cargando las publicaciones…"}</h2><p>${S.loaded?(S.filter==="todas"?"Consulta el estado de actualización abajo. Un tablero vacío no confirma que no exista producción.":"Elige Todas para ver las demás publicaciones."):"Leyendo la tira completa de cada publicación."}</p></div>`}</div></div>
 <p class="bt-bottom">Aprobar una toma registra tu elección. Producción y publicación tienen sus propios comprobantes.</p>
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
 let k=selected?opts.findIndex(o=>o.indiceOriginal===Number(selected[1])-1):l.seleccion?opts.findIndex(o=>o.indiceOriginal===l.seleccion.toma-1):0;
 if(k<0)k=0;
 S.choice={group:g.id,n:Number(n),k,compare:false};
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
 const writable=eligible()&&!g.p?._consulta&&md.i>=0&&!!dec[g.pid]&&l.estado!=="aprobada";
 const box=document.createElement("div");box.className="bt-choice";box.setAttribute("role","dialog");box.setAttribute("aria-modal","true");box.setAttribute("aria-label","Elegir fotografía de lámina "+l.n);
 let finalistas=[],finalistasError=false;
 try{finalistas=preseleccion(localStorage,{quien:ROL(),pid:g.pid,n:l.n,version:l.version||null,dice:l.dice},os).leer();}catch(e){finalistasError=true;}
 const frames=g.t.laminas||[],pos=frames.findIndex(x=>Number(x.n)===Number(l.n));
 const otherIndex=finalistas.length===2&&finalistas.includes(k)?finalistas.find(i=>i!==k):(k===0?1:0),other=os[otherIndex];
 const intention=l.entiende||l.por_que||g.t.direccion?.promesa||g.t.promesa||g.p.porque||"";
 const chosen=/\[toma elegida: (\d+)\]/.exec(md.nota||"");
 box.innerHTML=`<div class="bt-choice-top"><button data-back>← Tira completa</button><div class="bt-book-title"><span class="bt-eyebrow">LIBRO DE REVISIÓN</span><strong>${esc(g.t.pieza||g.id)}</strong></div><button data-close-choice aria-label="Cerrar opciones">×</button></div>
 <nav class="bt-page-rail" aria-label="Páginas de esta publicación">${frames.map(x=>`<button data-page="${x.n}" aria-label="Revisar lámina ${x.n}" aria-current="${Number(x.n)===Number(l.n)?"page":"false"}" class="${Number(x.n)===Number(l.n)?"on":""}"><span class="bt-dot ${status(g,x)}">${String(x.n).padStart(2,"0")}</span></button>`).join("")}<span>Página ${pos+1} de ${frames.length}</span></nav>
 <div class="bt-choice-content"><div class="bt-carousel" tabindex="0" aria-label="Opciones; flechas para cambiar, botón para aprobar">
 <div class="bt-image-heading"><span class="bt-eyebrow">${c.compare?"COMPARACIÓN DE TOMAS":"LA IMAGEN"}</span>${os.length>1?`<button data-compare aria-pressed="${!!c.compare}">${c.compare?"Ver una toma":"Comparar lado a lado"}</button>`:""}</div>
 <div class="bt-image-stage ${c.compare&&other?"is-comparing":""}"><figure><div class="bt-hero">${o?img(o.src||o.original,"Opción "+(k+1),"bt-main-photo"):`<div class="bt-sin-foto">No hay una toma disponible todavía</div>`}<span class="bt-lamina">L${l.n}</span></div><figcaption>${os.length?"Toma "+(k+1)+" · En revisión":"Esperando imagen"}${chosen&&o&&Number(chosen[1])===o.indiceOriginal+1?" · Tu elección":""}</figcaption></figure>${c.compare&&other?`<figure class="bt-comparison"><div>${img(other.src||other.original,"Toma de referencia")}</div><figcaption>Toma ${otherIndex+1} · Referencia</figcaption></figure>`:""}</div>
 <div class="bt-pager"><button data-prev-option aria-label="Opción anterior" ${k<=0?"disabled":""}>←</button><span>${os.length?"Opción "+(k+1)+" de "+os.length:"En producción"}</span><button data-next-option aria-label="Opción siguiente" ${k>=os.length-1?"disabled":""}>→</button></div>
 <div class="bt-thumbs">${os.map((x,i)=>`<button data-option="${i}" aria-label="Ver opción ${i+1}" aria-pressed="${i===k}" class="${i===k?"on":""}">${img(x.src||x.original,"Opción "+(i+1))}<span>${i+1}</span></button>`).join("")}</div>
 <button class="bt-enlarge" data-full-photo ${!o?"disabled":""}>Ampliar</button></div>
 <div class="bt-choice-copy"><span class="bt-dot ${st}">${labels[st]}</span><span class="bt-eyebrow bt-section-label">EL MENSAJE DE ESTA TOMA</span><h2>${esc(textoToma(l,o))}</h2>
 ${writable&&os.length>1?`<section class="bt-finalistas" aria-label="Preselección de finalistas"><span class="bt-eyebrow">CONSERVA HASTA DOS FINALISTAS</span><div class="bt-tools">${os.map((x,i)=>`<button data-finalista="${i}" aria-pressed="${finalistas.includes(i)}">${finalistas.includes(i)?"✓ ":""}Toma ${i+1}</button>`).join("")}</div><p>${finalistasError?"No pude recuperar la preselección local.":finalistas.length+" de 2 guardadas en este navegador."} Preseleccionar no aprueba ni produce.</p></section>`:""}
 ${intention?`<div class="bt-intention"><span class="bt-eyebrow">QUÉ DEBE TRANSMITIR</span><p>${esc(intention)}</p></div>`:""}
 ${(o&&o.texto)||l.ve?`<details class="bt-scene"><summary>Dirección de la imagen</summary><p>${esc(o&&o.texto||l.ve)}</p></details>`:""}
 <div class="bt-tools"><button data-info="guion" data-group="${esc(g.id)}">Guion completo</button><button data-info="intencion" data-group="${esc(g.id)}">Intención</button><button data-history="${l.n}" data-group="${esc(g.id)}">↺ ${intentos(l)} intentos</button></div>
 ${md.nota.replace(/\s*\[toma elegida: \d+\]/g,"")?`<blockquote class="bt-editor-note"><span class="bt-eyebrow">TU NOTA AL MARGEN</span><p>${esc(md.nota.replace(/\s*\[toma elegida: \d+\]/g,""))}</p></blockquote>`:""}
 <div class="bt-decision-panel"><span class="bt-eyebrow">TU DECISIÓN · ${os.length?"TOMA "+(k+1):"SIN TOMA"}</span><div class="bt-decisions"><button class="bt-approve" data-vote="si" ${!writable||!o?"disabled":""}>Aprobar esta toma</button><button class="bt-reject" data-vote="no" ${!writable?"disabled":""}>Pedir cambio</button></div>
 <p class="bt-gesture-hint">${writable?"Comparar no decide. Aprueba esta toma o pide un cambio con una nota.":l.estado==="aprobada"?"Esta página ya está aprobada. Su historia se conserva.":"Vista de lectura: puedes comparar sin cambiar decisiones."}</p>
 ${l.estado==="aprobada"&&eligible()&&!g.p?._consulta&&g.t.base?`<button data-reopen>Pedir una nueva revisión</button>`:""}
 <p class="bt-notice" role="status">${esc(S.notice)}</p></div>
 <button class="bt-next-review" data-next>Siguiente por revisar →</button></div></div>`;
 root.appendChild(box);
}
function moveOption(delta){if(!S.choice)return;const g=S.groups.find(x=>x.id===S.choice.group),l=g.t.laminas.find(x=>Number(x.n)===S.choice.n);S.choice.k=Math.min(Math.max(0,S.choice.k+delta),Math.max(0,options(l).length-1));render();}
function conservarFinalista(i){
 if(!S.choice||!eligible())return;
 const g=S.groups.find(x=>x.id===S.choice.group),l=g&&g.t.laminas.find(x=>Number(x.n)===S.choice.n);
 if(!l||g.p?._consulta||l.estado==="aprobada"||markData(g,l).i<0||!dec[g.pid])return;
 try{
  const r=preseleccion(localStorage,{quien:ROL(),pid:g.pid,n:l.n,version:l.version||null,dice:l.dice},options(l)).cambiar(i);
  S.notice=r.ok?"Preselección guardada en este navegador. Aún no has aprobado esta toma.":"Ya conservaste dos finalistas. Quita una antes de añadir otra.";
 }catch(e){S.notice="No pude guardar la preselección. No quedó confirmada; tus decisiones siguen conservadas.";}
 render();
}
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
 if(g.p?._consulta||!d||md.i<0||l.estado==="aprobada")return;
 const image=zoomPhoto||root.querySelector(".bt-main-photo");
 if(m==="si"&&(!mediosDisponibles()||!o||!image||!image.complete||!image.naturalWidth)){S.notice="Espera a que cargue esta fotografía antes de aprobarla.";render();return;}
 const identity=JSON.stringify(api.contexto()),owner=ROL();
 const apply=note=>{
  if(!eligible()||ROL()!==owner||JSON.stringify(api.contexto())!==identity||dec[g.pid]!==d){S.notice="La versión o sesión cambió. Abre de nuevo la lámina antes de decidir.";render();return;}
  if(m==='no'&&!String(note||'').trim()){S.notice="Escribe qué debe cambiar.";render();return;}

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
 root.querySelectorAll("[data-finalista]").forEach(b=>b.onclick=()=>conservarFinalista(Number(b.dataset.finalista)));
 root.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>chooseFrame(gs(S.choice.group),Number(b.dataset.page)));
 root.querySelector("[data-compare]")?.addEventListener("click",()=>{
  S.choice.compare=!S.choice.compare;
  if(S.choice.compare){
   const g=gs(S.choice.group),l=g.t.laminas.find(x=>Number(x.n)===S.choice.n);
   try{const picks=preseleccion(localStorage,{quien:ROL(),pid:g.pid,n:l.n,version:l.version||null,dice:l.dice},options(l)).leer();if(picks.length===2&&!picks.includes(S.choice.k))S.choice.k=picks[0];}catch(e){}
  }
  render();
 });
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
  hero.addEventListener("pointerup",e=>{if(!p||p.id!==e.pointerId)return;const dx=e.clientX-p.x,dy=e.clientY-p.y;p=null;if(Math.abs(dx)>55&&Math.abs(dx)>Math.abs(dy)*1.3)moveOption(dx<0?1:-1);});
 }
}
async function refresh(live=false){
 if(_mesaLocal&&!live){render();return;}
 if(S.busy){S.refreshPending=true;return;}S.busy=true;S.notice="";render();
 try{
  if(live&&ENTRADO()){_tCola=0;traerCola();const d=await traer(_mesaLocal?'':fecha,1,20000,true);if(d&&!d._respaldo&&!d.error)aplicarDia(normalizarDia(d));else S.notice="No se confirmó una lectura nueva del Sheet; conservé lo que ya tenías.";}
  if(_mesaLocal)return;
  const sourceDay=D, cacheDay=_diaParaCache;
  const props=[...((D&&(D._todas||D.propuestas))||[])];
  let inventario=[], inventarioConfirmado=false;
  try{
   const response=await fetch("datos/mesa-estado.json?v="+Date.now(),{cache:"no-store",signal:AbortSignal.timeout(20000)});
   if(!response.ok)throw Error("Sin inventario");
   const report=await response.json();
   if(!Array.isArray(report.publicaciones)||!report.revisado_en)throw Error("Sin proyección");
   inventario=report.publicaciones; inventarioConfirmado=true;
   const ids=new Set(props.map(p=>p.id));
   for(const p of inventario){
    if(!/^[A-Za-z0-9_-]+$/.test(p.id)||!Array.isArray(p.laminas))throw Error("Inventario inválido");
    if(!ids.has(p.id)){props.push({id:p.id,tipo:"laminas",_consulta:true});ids.add(p.id);}
   }
   S.notice="Inventario consultado: "+new Date(report.revisado_en).toLocaleString()+". Las publicaciones sin revisión activa se muestran sólo para consulta.";
   if(Date.now()-Date.parse(report.revisado_en)>3*60*60*1000)S.notice+=" La actualización tiene más de tres horas; sus estados pueden haber cambiado.";
  }catch(e){S.notice="No se confirmó el inventario de publicaciones. Se muestran únicamente las revisiones disponibles; esto no significa que no haya trabajo guardado.";}
  const porId=new Map(inventario.map(p=>[p.id,p]));
  if(live){for(const p of props)delete TIRAS[p.id];}
  const all=await Promise.all(props.map(async p=>{
   let t=await cargarTira(p.id);
   if(p._consulta){if(!t)throw Error("Falta una tira vigente");t=proyectarPublicacion(t,porId.get(p.id));}
   return {p,t};
  })),map=new Map();
  for(const {p,t}of all){if(!t||!(t.laminas||[]).length)continue;const id=t.pieza_slug||normSlug(t.pieza||p.pieza||p.titulo);let g=map.get(id);if(!g){g={id,pid:p.id,p,t,ejes:[]};map.set(id,g);}else if((D.propuestas||[]).some(x=>x.id===p.id)&&!dec[g.pid])map.set(id,{id,pid:p.id,p,t,ejes:g.ejes});}
  for(const {p,t}of all){if(t&&(t.laminas||[]).length)continue;
   if(String(p.origen||"").startsWith("corte-de ")){
    const g=grupoDeCorte(p,[...map.values()]);
    if(g)g.ejes.push(p);
    else map.set("corte:"+p.id,{id:"corte:"+p.id,pid:p.id,p,t:{pieza:p.pieza||p.titulo,pieza_slug:"corte:"+p.id,laminas:[]},ejes:[p]});
    continue;
   }
   const id=p.pieza_slug||normSlug(p.pieza||String(p.titulo||"").split(" · ")[0]);const g=map.get(id)||[...map.values()].find(x=>normSlug(x.t.pieza)===id);if(g)g.ejes.push(p);else map.set(id,{id,pid:p.id,p,t:{pieza:p.pieza||p.titulo,pieza_slug:id,laminas:[]},ejes:[p]});}
  if(D!==sourceDay){S.refreshPending=true;return;}
  S.groups=[...map.values()];S.loaded=true;S.cached=false;
  if(inventarioConfirmado&&all.every(({p,t})=>!(p.laminas||[]).length||!!t)) guardarMesaLocal(S.groups,cacheDay);if(S.focus&&!group()){S.focus=null;S.choice=null;}
 }catch(e){S.notice="No pude actualizar el tablero. Tu revisión sigue conservada. Usa Actualizar.";}
 finally{S.busy=false;render();if(S.refreshPending){S.refreshPending=false;queueMicrotask(()=>refresh());}}
}
api.restore=cache=>{S.groups=cache.groups;S.loaded=true;S.cached=true;S.savedAt=cache.savedAt;render();requestAnimationFrame(()=>requestAnimationFrame(()=>performance.mark("sala-mesa-local-visible")));};
api.clear=()=>{S.groups=[];S.focus=S.choice=null;S.cached=false;S.loaded=false;root.innerHTML="";document.body.classList.remove("sala-tablero");};
api.refresh=refresh;api.render=render;api.produccionActualizada=()=>{if(!S.choice)render();};
const returnButton=document.createElement("button");returnButton.className="bt-return";returnButton.textContent="← Volver al tablero";returnButton.onclick=()=>{document.body.classList.remove("sala-turno");render();};document.getElementById("vHoy").prepend(returnButton);
let wheelTotal=0,lastWheel=0;
root.addEventListener("wheel",e=>{
 if(CAPAS.some(c=>!["tablero-publicacion","tablero-opciones"].includes(c.id)))return;
 const photo=e.target.closest(".bt-photo,.bt-hero");
 if(!e.ctrlKey&&!e.metaKey)return;
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
if(_cacheMesa)api.restore(_cacheMesa);else if(D)refresh();
})();
