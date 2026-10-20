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
 function html(src){const v=resolver(src);if(!v)return '';
  return v.tipo==='drive'?`<div class="lienzo conVideo"><iframe loading="lazy" src="${esc(v.src)}" title="Corte completo para revisar" allow="fullscreen" allowfullscreen referrerpolicy="no-referrer"></iframe></div>`:`<div class="lienzo conVideo"><video src="${esc(v.src)}" controls playsinline preload="none"></video></div>`;
 }
 return {resolver,html};
});
