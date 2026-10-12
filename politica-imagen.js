/* Generado desde politica-imagen.json; cambiar la fuente y verificar ambas representaciones. */
(function(root,factory){const api=factory({"schema":1,"revision":"2026-10-12.sin-tiny-sd.1","retirados":[{"motor":"cpu","modelo":"segmind/tiny-sd","aliases":["cpu_pequeno","tiny-sd"],"motivo":"Retirado por Dirección de la generación y revisión de nuevas tomas."}]});if(typeof module==="object"&&module.exports)module.exports=api;else root.SalaPoliticaImagen=api;})(typeof globalThis!=="undefined"?globalThis:this,function(policy){
"use strict";
const denied=new Set(policy.retirados.flatMap(x=>[x.motor,x.modelo,...(x.aliases||[])]).map(x=>String(x).trim().toLowerCase()));
function vetada(c){return !!c&&[c.motor,c.modelo].some(x=>denied.has(String(x||"").trim().toLowerCase()));}
function tomas(l){return (Array.isArray(l&&l.candidatas)?l.candidatas:[]).map((c,i)=>({...c,indiceOriginal:i})).filter(c=>!vetada(c));}
function srcLamina(l,src,aprobada=false){
 if(!l||aprobada||l.estado==="aprobada")return src||"";
 const raw=Array.isArray(l.candidatas)?l.candidatas:[];
 if(!raw.length)return vetada(l)?"":(src||"");
 const allowed=tomas(l);if(!allowed.length)return "";
 const match=raw.find(c=>c.src===src||c.original===src);
 return match&&!vetada(match)?src:(allowed[0].src||allowed[0].original||"");
}
return Object.freeze({policy,vetada,tomas,srcLamina});
});
