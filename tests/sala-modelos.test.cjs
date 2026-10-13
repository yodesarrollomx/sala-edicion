const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs");
const p=require("../politica-imagen.js"),j=JSON.parse(fs.readFileSync("politica-imagen.json","utf8"));
test("política usada en revisión coincide con fuente de generación",()=>assert.deepEqual(p.policy,j));
test("filtro preserva índice original, sin ofrecer CPU",()=>{
 const l={candidatas:[{motor:"cpu",src:"bad.jpg"},{motor:"cloudflare",src:"good.jpg"},{motor:"gemini_pro",src:"other.jpg"}]};
 assert.deepEqual(p.tomas(l).map(c=>c.indiceOriginal),[1,2]);
 assert.equal(p.srcLamina(l,"bad.jpg"),"good.jpg");
 assert.equal(l.candidatas.length,3);
});
test("sin toma permitida se muestra espera, sin usar foto vetada",()=>{
 const l={estado:"rehecha",src:"bad.jpg",candidatas:[{motor:"cpu",src:"bad.jpg"}]};
 assert.equal(p.srcLamina(l,"bad.jpg"),"");
 assert.deepEqual(p.tomas(l),[]);
});
test("referencia ya aprobada se conserva exactamente",()=>{
 const l={estado:"aprobada",src:"old.png",candidatas:[{motor:"cpu",src:"old.png"}]};
 assert.equal(p.srcLamina(l,"old.png"),"old.png");
});
test("selección de una fila filtrada usa el índice original y su miniatura",()=>{
 const html=fs.readFileSync("index.html","utf8");
 assert.match(html,/data-cand="\$\{o\.indiceOriginal\}"/);
 assert.match(html,/b\.closest\('\.cand-item'\)\.querySelector\('img'\)/);
 assert.match(html,/\(k\+1\).*?avanzar\('si'\)/);
 assert.ok(html.indexOf('src="politica-imagen.js?')<html.indexOf("const POLITICA_IMAGEN"));
});

test("fuente retirada exige reemplazo incluso si tuvo aprobación anterior",()=>{
 const src=p.policy.fuentes_retiradas[0];
 const l={estado:"aprobada",src,candidatas:[{motor:"pollinations",src}]};
 assert.equal(p.srcLamina(l,src,true),"");
 assert.deepEqual(p.tomas(l),[]);
 assert.equal(l.src,src);
});
test("una fuente aprobada sana conserva su selección y el índice original",()=>{
 const bad=p.policy.fuentes_retiradas[0];
 const l={estado:"aprobada",src:"healthy.png",candidatas:[{motor:"cloudflare",src:"healthy.png"},{motor:"pollinations",src:bad}]};
 assert.equal(p.srcLamina(l,l.src),"healthy.png");
 assert.deepEqual(p.tomas(l).map(x=>x.indiceOriginal),[0]);
 assert.equal(l.candidatas.length,2);
});
test("miniatura sin tira y URL absoluta tampoco muestran una fuente retirada",()=>{
 const src=p.policy.fuentes_retiradas[0];
 assert.equal(p.srcLamina(null,"https://yodesarrollomx.github.io/sala-edicion/"+src+"?v=1"),"");
 assert.match(p.mensajeEspera({src},src),/retirada/);
});

test("árbol de producción oculta modelos retirados sin cambiar la elección histórica",()=>{
 const html=fs.readFileSync("index.html","utf8");
 const start=html.indexOf("function ramaLaminas("),end=html.indexOf("\nfunction ramaEtapaCola",start);
 assert.ok(start>=0&&end>start);
 const render=new Function("POLITICA_IMAGEN","laminaAbierta","esc","ligera","evidenciaSrc","colorPunto","fuenteLamina",
   html.slice(start,end)+";return ramaLaminas;")(p,()=>null,String,x=>x,f=>f.src,()=> "gris",(l,src)=>p.srcLamina(l,src));
 const retired=p.policy.fuentes_retiradas[0];
 const tira={laminas:[{n:2,version:1,estado:"aprobada",src:"healthy.png",
   candidatas:[{motor:"cpu",src:"retired-cpu.jpg"},{motor:"cloudflare",src:"healthy.jpg"}]}]};
 const before=JSON.stringify(tira);
 const out=render(tira,[{item:"2-1",motor:"pollinations",src:retired,estado:"hecho"},
   {item:"2-2",motor:"cloudflare",src:"queue-healthy.jpg",estado:"hecho"}]);
 assert.ok(!out.includes("retired-cpu.jpg"));
 assert.ok(!out.includes(retired));
 assert.ok(out.includes("healthy.jpg")&&out.includes("queue-healthy.jpg"));
 assert.ok(out.includes("candidata 2"));
 assert.equal(p.tomas(tira.laminas[0])[0].indiceOriginal,1);
 assert.equal(JSON.stringify(tira),before);
});
