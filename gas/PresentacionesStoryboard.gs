/* Typed, data-only storyboard contract. Shared with the existing private service. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.YODStoryboard=api;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const SCHEMA='yod.storyboard.v1',VERSION='YOD-SB-1.0.0';
 const roles={problem:{label:'Problema',color:'#b54745'},solution:{label:'Solución',color:'#785696'},plan:{label:'Plan',color:'#936e44'},risk:{label:'Riesgo evitado',color:'#a27d16'},outcome:{label:'Resultado',color:'#38788e'},action:{label:'Siguiente acción',color:'#50764b'},context:{label:'Contexto',color:'#65756c'}};
 const kinds=['land','building','unit','money','person','document'];
 const diagrams=['site','comparison','program','cashflow','phases','decision'];
 const statuses=['verified','calculated','assumption','pending'];
 const statusLabels={verified:'Documentado',calculated:'Calculado en PPP',assumption:'Supuesto',pending:'Pendiente'};
 const fail=code=>{throw Error(code);};
 function object(x,allowed){if(!x||typeof x!=='object'||Array.isArray(x)||Object.keys(x).some(k=>!allowed.includes(k)))fail('invalid_storyboard');return x;}
 function text(v,max=600,empty=false){if(typeof v!=='string'||v.length>max||(!empty&&!v.trim())||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(v))fail('invalid_storyboard');return v.trim();}
 function id(v){if(typeof v!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(v)||['__proto__','constructor','prototype'].includes(v))fail('invalid_storyboard');return v;}
 function list(v,min,max){if(!Array.isArray(v)||v.length<min||v.length>max)fail('invalid_storyboard');return v;}
 function unique(rows){const ids=new Set();for(const r of rows){if(ids.has(r.id))fail('invalid_storyboard');ids.add(r.id);}return ids;}
 function normalize(input){
  object(input,['schema','title','audience','decision','objects','facts','scenes']);if(input.schema!==SCHEMA)fail('invalid_storyboard');
  const result={schema:SCHEMA,title:text(input.title,160),audience:text(input.audience,300),decision:text(input.decision,500)};
  result.objects=list(input.objects,1,24).map(o=>{object(o,['id','kind','label','schematic']);if(!kinds.includes(o.kind)||typeof o.schematic!=='boolean')fail('unsupported_visual');return {id:id(o.id),kind:o.kind,label:text(o.label,80),schematic:o.schematic};});
  const objects=unique(result.objects);
  result.facts=list(input.facts,0,100).map(f=>{object(f,['id','label','value','unit','source_ref','status','condition']);if(!statuses.includes(f.status)||f.status==='pending'&&f.value!==null)fail('invalid_fact');const source=text(f.source_ref,400);if(!/^snapshot\.[A-Za-z0-9_.\[\]-]+$/.test(source))fail('invalid_fact');return {id:id(f.id),label:text(f.label,80),value:f.value===null?null:text(f.value,100),unit:text(f.unit,40,true),source_ref:source,status:f.status,condition:text(f.condition,500,true)};});
  const facts=unique(result.facts);
  result.scenes=list(input.scenes,1,24).map(s=>{
   object(s,['id','title','question','takeaway','role','diagram','condition','moments']);if(!Object.prototype.hasOwnProperty.call(roles,s.role)||!diagrams.includes(s.diagram))fail('unsupported_visual');
   const out={id:id(s.id),title:text(s.title,100),question:text(s.question,300),takeaway:text(s.takeaway,350),role:s.role,diagram:s.diagram,condition:text(s.condition,500,true)};
   out.moments=list(s.moments,1,6).map(m=>{
    object(m,['id','label','spoken','visible_objects','annotations','relations','camera']);
    const visible=list(m.visible_objects,1,6).map(id);if(new Set(visible).size!==visible.length||visible.some(x=>!objects.has(x)))fail('invalid_object_reference');
    const annotations=list(m.annotations,0,4).map(a=>{object(a,['object_id','fact_id','label']);if(!visible.includes(a.object_id)||(a.fact_id!==null&&!facts.has(a.fact_id)))fail('invalid_fact_reference');return {object_id:a.object_id,fact_id:a.fact_id,label:text(a.label,100,true)};});
    const relations=list(m.relations,0,6).map(r=>{object(r,['from','to','label']);if(!visible.includes(r.from)||!visible.includes(r.to)||r.from===r.to)fail('invalid_object_reference');return {from:r.from,to:r.to,label:text(r.label,90)};});
    object(m.camera,['focus']);const focus=list(m.camera.focus,1,6).map(id);if(focus.some(x=>!visible.includes(x))||new Set(focus).size!==focus.length)fail('invalid_object_reference');
    return {id:id(m.id),label:text(m.label,120),spoken:text(m.spoken,2000),visible_objects:visible,annotations,relations,camera:{focus}};
   });unique(out.moments);if(new Set(out.moments.flatMap(m=>m.visible_objects)).size>6)fail('unsupported_visual');return out;
  });unique(result.scenes);
  if(JSON.stringify(result).length>240000)fail('storyboard_too_large');return result;
 }
 function timeline(story){const frames=[];story.scenes.forEach((scene,scene_index)=>scene.moments.forEach((moment,moment_index)=>frames.push({scene,scene_index,moment,moment_index,index:frames.length})));return frames;}
 function at(story,position){const frames=timeline(story),p=Math.max(0,Math.min(frames.length-1,Number(position)||0)),i=Math.floor(p);return {...frames[i],position:p,fraction:p-i,max:frames.length-1,next:frames[Math.min(i+1,frames.length-1)]};}
 function factLabel(f){return f.value===null?'No definido':f.value+(f.unit?' '+f.unit:'');}
 function project(input){
  const s=normalize(input),used=new Set(s.scenes.flatMap(scene=>scene.moments.flatMap(m=>m.annotations.map(a=>a.fact_id).filter(Boolean))));
  return {schema:'yod.presentation.projection.v1',title:s.title,decision:s.decision,objects:s.objects,facts:s.facts.filter(f=>used.has(f.id)).map(({source_ref,...f})=>f),scenes:s.scenes.map(({question,...scene})=>({...scene,moments:scene.moments.map(({spoken,...m})=>m)}))};
 }
 return {SCHEMA,VERSION,roles,kinds,diagrams,statuses,statusLabels,normalize,project,timeline,at,factLabel};
});
