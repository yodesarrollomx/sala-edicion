const test=require("node:test"),assert=require("node:assert/strict"),fs=require("node:fs");
const p=require("../politica-imagen.js"),j=JSON.parse(fs.readFileSync("politica-imagen.json","utf8"));
test("política usada en revisión coincide con fuente de generación",()=>assert.deepEqual(p.policy,j));
test("filtro preserva índice original, sin ofrecer CPU",()=>{
 const l={candidatas:[{motor:"cpu",src:"bad.jpg"},{motor:"cloudflare",src:"good.jpg"},{motor:"pollinations",src:"other.jpg"}]};
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
