/* Salida de la Sala corta (9-nov-2026).
   Dirección: «quiero el proceso de creación de inicio a final completo… sólo quiero orden para
   poderlas desatorar». Lo que faltaba al final de la línea: ver qué quedó LISTO PARA PUBLICAR,
   tener a un toque sus imágenes y su texto, y poder decir «ya la publiqué».

   De dónde sale cada cosa:
   · el paquete (imágenes en orden + texto) lo arma la nube y lo anota en el expediente de la
     pieza (`nube/sala_salida.py` → EXPEDIENTES); aquí sólo se lee;
   · «Ya la publiqué» agrega UNA fila a PRODUCCION con el transporte de siempre
     (`SalaCorrecciones`: se guarda en el aparato antes de mandar y no se repite). La nube cierra
     el expediente en su siguiente sesión; mientras, este aparato ya la da por publicada.
   Publicar es siempre el clic de Dirección: nada de aquí publica por su cuenta. */
(function(root){
'use strict';
const LLAVE='sala_publicadas_v1', BORRADOR='sala_salida_texto_v1';

/* ── puro (sin pantalla): se prueba en Node ─────────────────────────────────────────────── */
function paquete(e){ return e&&typeof e==='object'&&e.paquete&&typeof e.paquete==='object'&&Array.isArray(e.paquete.imagenes)&&e.paquete.imagenes.length?e.paquete:null }
/* las piezas con paquete que todavía no salen, en el orden de sus carpetas */
function listas(expedientes,publicada){
  return Object.entries(expedientes||{}).filter(([n,e])=>paquete(e)&&!publicada(n))
    .map(([nombre,e])=>({nombre,e,p:e.paquete})).sort((a,b)=>(a.p.orden||1e9)-(b.p.orden||1e9)||a.nombre.localeCompare(b.nombre));
}
/* el texto común y lo que va después en cada red (el cierre de IG, la liga de FB) */
function partes(copy){
  const c=copy||{}, t=String(c.texto||''), cola=x=>{ x=String(x||''); return t&&x.startsWith(t)?x.slice(t.length):'' };
  return {texto:t, ig:cola(c.instagram), fb:cola(c.facebook), comentario:String(c.comentario||''), revision:Array.isArray(c.revision)?c.revision.filter(x=>typeof x==='string'&&x.trim()):[]};
}
function ligaValida(v){ v=String(v||'').trim(); return !v||/^https:\/\/[^\s"<>]{4,300}$/.test(v) }
/* en qué va una pieza de la línea: publicada · lista (paquete hecho) · texto (imágenes aprobadas,
   falta el texto) · video (le faltan etapas de video) · laminas · guion */
function estado(nombre,hechas,etapas,expedientes,publicada){
  if(publicada) return 'publicada';
  if(!hechas.has('laminas')) return hechas.has('guion')?'laminas':'guion';
  if(paquete((expedientes||{})[nombre])) return 'lista';
  return (etapas||[]).some(k=>['voz','escenas','corte'].includes(k)&&!hechas.has(k))?'video':'texto';
}
function cuantas(n,uno,varios){ return n+' '+(n===1?uno:varios) }
const puro={paquete,listas,partes,ligaValida,estado,cuantas};
if(typeof module==='object'&&module.exports){ module.exports=puro; return }

/* ── pantalla ───────────────────────────────────────────────────────────────────────────── */
const leer=(k,d)=>{ try{ const v=JSON.parse(localStorage.getItem(k)||'null'); return v&&typeof v==='object'?v:d }catch(e){ return d } };
const guardar=(k,v)=>{ try{ localStorage.setItem(k,JSON.stringify(v)); return true }catch(e){ return false } };
function publicadaAqui(n){ const m=leer(LLAVE,{}); return !!(m[n]&&m[n].fecha) }
function paqueteDe(n){ return paquete((typeof EXP!=='undefined'&&EXP[n])||null) }
function deHoy(){ return (typeof fecha!=='undefined'&&fecha)||new Date(Date.now()-7*36e5).toISOString().slice(0,10) }
const miniatura=src=>typeof ligera==='function'?ligera(src):src;
function pendientes(){ return listas(typeof EXP!=='undefined'?EXP:{},n=>esPublicada(n)) }

/* las que tienen todas sus imágenes aprobadas y todavía no tienen paquete: unas esperan su texto y
   otras están guardadas por regla (REGLAS salida_excluir) hasta que Dirección decida */
async function sinPaquete(){
  try{ const piezas=(typeof LINEA_PIEZAS!=='undefined'&&LINEA_PIEZAS)||await armarPiezas();
    const l=piezas.filter(z=>z.tira&&!esPublicada(z.nombre)&&!paqueteDe(z.nombre)&&hechasDe(z,false).has('laminas'));
    const guardada=z=>typeof salidaGuardada==='function'&&salidaGuardada(z.slug);
    return {espera:l.filter(z=>!guardada(z)).length, guardadas:l.filter(guardada).map(z=>z.nombre)} }catch(e){ return {espera:0,guardadas:[]} }
}
function tarjeta(x,k){
  const img=x.e.portada||(x.p.imagenes[0]||{}).src||'', n=x.p.imagenes.length;
  return `<button class="sal-carta" type="button" data-publicar="${esc(x.nombre)}">
    <span class="sal-foto">${miniatura(img)?`<img src="${esc(miniatura(img))}" alt="" loading="lazy" decoding="async">`:''}<span class="sal-n">${esc(x.p.orden||k+1)}</span></span>
    <b>${esc(x.nombre)}</b><small>${esc(x.p.formato||'Publicación')} · ${cuantas(n,'imagen','imágenes')} · texto listo</small>
    <span class="sal-ir">${DECIDE()?'Publicar →':'Ver →'}</span></button>`;
}
async function pintar(){
  const hoy=$('#salidaHoy'); if(!hoy) return;
  if(!ENTRADO()){ hoy.innerHTML=''; return }
  if(!Object.keys(EXP).length){ try{ await (_expP=_expP||cargarExpedientes()) }catch(e){} }
  if(typeof traerReglasSala==='function'){ try{ await traerReglasSala() }catch(e){} }
  conciliar();
  const l=pendientes(), {espera,guardadas}=await sinPaquete();
  const html=!l.length&&!espera&&!guardadas.length?'':`<section class="sal" aria-label="Listas para publicar">
    <header><span class="bt-eyebrow">${l.length?'TE TOCA PUBLICAR':'LA SALIDA'}</span>
      <h2>${l.length?cuantas(l.length,'lista para publicar','listas para publicar'):'Todavía no hay nada listo para publicar'}</h2>
      <p>${l.length?'Imágenes aprobadas, en orden, con su texto. Tú das el clic de publicar.':'En cuanto una pieza tenga sus imágenes aprobadas y su texto, aparece aquí.'}</p></header>
    ${l.length?`<div class="sal-fila">${l.map(tarjeta).join('')}</div>`:''}
    ${espera?`<p class="sal-pie"><b>${cuantas(espera,'pieza más','piezas más')}</b> ya ${espera===1?'tiene':'tienen'} sus imágenes aprobadas y ${espera===1?'espera':'esperan'} su texto. Es el paso del consejo; cuando lo escriba, ${espera===1?'aparece':'aparecen'} aquí.</p>`:''}
    ${guardadas.length?`<p class="sal-pie"><b>${cuantas(guardadas.length,'pieza guardada','piezas guardadas')}</b> hasta que tú decidas: ${esc(guardadas.join(' · '))}.</p>`:''}
  </section>`;
  if(hoy._html!==html){ hoy._html=html; hoy.innerHTML=html; hoy.querySelectorAll('[data-publicar]').forEach(b=>b.onclick=()=>abrir(b.dataset.publicar)) }   // sin cambios no se repinta: no se pierde el desplazamiento
  if(typeof avisarPuerta==='function') avisarPuerta('hoy',l.length>0&&DECIDE());
}
async function copiar(texto,boton){
  let ok=false;
  try{ await navigator.clipboard.writeText(texto); ok=true }catch(e){
    try{ const t=document.createElement('textarea'); t.value=texto; t.setAttribute('readonly',''); t.style.cssText='position:fixed;opacity:0'; document.body.appendChild(t); t.select(); ok=document.execCommand('copy'); t.remove() }catch(_){ ok=false } }
  if(boton){ const antes=boton.dataset.txt||boton.textContent; boton.dataset.txt=antes; boton.textContent=ok?'Copiado ✓':'No se pudo copiar: selecciónalo a mano'; boton.classList.toggle('ok',ok);
    clearTimeout(boton._t); boton._t=setTimeout(()=>{ boton.textContent=antes; boton.classList.remove('ok') },2200) }
  return ok;
}
function abrir(nombre){
  const e=EXP[nombre], p=paquete(e); if(!p) return;
  const c=partes(e.copy), borr=leer(BORRADOR,{}), sello=String(p.sello||''), mio=borr[nombre]&&borr[nombre].sello===sello?String(borr[nombre].texto||''):'';
  const n=p.imagenes.length, puede=DECIDE()&&!esPublicada(nombre);
  const v=hoja(`<div class="sal-hoja">
    <h3>${esc(nombre)}</h3>
    <p class="sal-sub">${esc(p.formato||'Publicación')} · ${cuantas(n,'imagen','imágenes')}${p.nota_formato?' · '+esc(p.nota_formato):''}</p>
    <div class="sal-tira" role="list">${p.imagenes.map((im,i)=>`<button type="button" role="listitem" class="sal-img" data-zoom="${esc(im.src)}" aria-label="Imagen ${i+1} de ${n}: ${esc(im.dice||'')}. Ampliar">${miniatura(im.src)?`<img src="${esc(miniatura(im.src))}" alt="" loading="lazy">`:''}<i>${i+1}</i></button>`).join('')}</div>
    ${c.revision.length?`<div class="sal-ojo"><b>Antes de publicar, mira esto</b><ul>${c.revision.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`:''}
    <div class="sal-paso"><h4><i>1</i>Las imágenes</h4>
      <p>Están en Drive, numeradas en el orden en que van.</p>
      ${/^https:\/\/drive\.google\.com\//.test(p.url||'')?`<a class="secund sal-liga" href="${esc(p.url)}" target="_blank" rel="noopener">Abrir la carpeta en Drive ↗</a>`:''}</div>
    <div class="sal-paso"><h4><i>2</i>El texto</h4>
      <p>Cámbialo aquí si quieres; se copia tal como lo dejes.</p>
      <textarea id="salTexto" rows="9" spellcheck="true" aria-label="Texto de la publicación">${esc(mio||c.texto)}</textarea>
      ${mio&&mio!==c.texto?`<button type="button" class="sal-mini" id="salOriginal">Volver al texto del consejo</button>`:''}
      <div class="sal-botones"><button type="button" class="secund" id="salIg">Copiar para Instagram</button><button type="button" class="secund" id="salFb">Copiar para Facebook</button></div></div>
    <div class="sal-paso"><h4><i>3</i>La liga (primer comentario en Instagram)</h4>
      <p class="sal-url">${esc(c.comentario)}</p>
      <button type="button" class="secund" id="salCom">Copiar la liga</button></div>
    ${puede?`<div class="sal-paso fin"><h4><i>4</i>Cuando ya esté publicada</h4>
      <label class="sal-lab" for="salPost">Liga de la publicación (si la tienes a la mano)</label>
      <input id="salPost" type="url" inputmode="url" autocomplete="off" placeholder="https://www.instagram.com/p/…">
      <button type="button" class="listo" id="salYa">Ya la publiqué</button>
      <p class="aviso" id="salAviso" role="status" aria-live="polite"></p></div>`
      :`<p class="nota-pie">${esPublicada(nombre)?'Esta pieza ya está anotada como publicada.':'Publicar y anotar la publicación corresponde a los editores.'}</p>`}
  </div>`,'publicar-'+normSlug(nombre));
  const q=s=>v.querySelector(s), txt=q('#salTexto');
  v.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{ if(typeof abrirZoom==='function') abrirZoom(b.dataset.zoom) });
  txt.oninput=()=>{ const b=leer(BORRADOR,{}); if(txt.value===c.texto) delete b[nombre]; else b[nombre]={sello,texto:txt.value}; guardar(BORRADOR,b) };
  const orig=q('#salOriginal'); if(orig) orig.onclick=()=>{ txt.value=c.texto; txt.oninput(); orig.remove() };
  q('#salIg').onclick=ev=>copiar(txt.value.trim()+c.ig,ev.currentTarget);
  q('#salFb').onclick=ev=>copiar(txt.value.trim()+c.fb,ev.currentTarget);
  q('#salCom').onclick=ev=>copiar(c.comentario,ev.currentTarget);
  const ya=q('#salYa'); if(!ya) return;
  ya.onclick=async()=>{
    const av=q('#salAviso'), liga=q('#salPost').value.trim();
    if(!ligaValida(liga)){ av.textContent='Esa liga no parece una dirección completa (empieza con https://). Corrígela o déjala vacía.'; return }
    ya.disabled=true; av.textContent='Anotando…';
    const final=txt.value.trim(), det={texto:'Publicada desde la Sala'}; if(final&&final!==c.texto) det.texto_final=final.slice(0,2200);
    let r; try{ r=await correcciones().enviar({accion:'produccion',fecha:deHoy(),pieza:nombre,estado:'publicada',detalle:JSON.stringify(det),enlace:liga,quien:ROL()}) }catch(err){ r={estado:'local'} }
    if(r.estado==='rechazado'||r.estado==='local'){ ya.disabled=false; av.textContent=r.estado==='rechazado'?'La Sala no aceptó la anotación con tu acceso. No se anotó nada.':'No se pudo guardar en este aparato. Inténtalo otra vez.'; return }
    const m=leer(LLAVE,{}); m[nombre]={fecha:deHoy(),liga,sello}; guardar(LLAVE,m);
    if(D&&Array.isArray(D.produccion)) D.produccion.unshift({fecha:deHoy(),pieza:nombre,estado:'publicada',detalle:'',enlace:liga});
    const b=leer(BORRADOR,{}); delete b[nombre]; guardar(BORRADOR,b);
    cerrarCapa('publicar-'+normSlug(nombre));
    if(typeof LINEA_PIEZAS!=='undefined') _lineaHoyT=0;
    await pintar();
    if(document.body.dataset.vista==='prod'&&typeof pintarProduccion==='function') pintarProduccion();
    hoja(`<h3>Anotada como publicada</h3><p><b>${esc(nombre)}</b> sale de tu lista.${r.estado==='recibido'?'':' Se guardó en este aparato y sube sola en cuanto haya conexión.'}</p>
      <p>Su paquete se guarda en «_PUBLICADAS» y su historia queda en la Sala.</p><button class="listo" type="button" id="salOk">Entendido</button>`,'publicada-ok');
    const ok=document.getElementById('salOk'); if(ok) ok.onclick=()=>cerrarCapa('publicada-ok');
  };
}
/* lo anotado aquí deja de recordarse cuando el expediente ya lo trae como publicado */
function conciliar(){
  const m=leer(LLAVE,{}); let cambio=false;
  for(const n of Object.keys(m)){ const e=EXP[n]; if(e&&e.estado==='publicada'){ delete m[n]; cambio=true } }
  if(cambio) guardar(LLAVE,m);
}
root.SalaSalida=Object.assign({pintar,abrir,publicadaAqui,paqueteDe,pendientes,conciliar},puro);
})(globalThis);
