import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
const repo='yodesarrollomx/sala-edicion',root='evidencia-cuatro-ciclos';
fs.mkdirSync(root,{recursive:true});
const report={scope:'cuatro_ejecuciones_reales_secuenciales_con_verificacion_de_entregables',produccion_inicial:{run_id:'39073909910',tomas:8,laminas:4,corte:'apodo:48s'},nota:'Las repeticiones conservan aprobaciones y entregables. Trabajo nuevo y reutilizado se registran por separado; no se generan versiones para inflar el contador.',cycles:[],ok:false};
const save=()=>fs.writeFileSync(root+'/bitacora.json',JSON.stringify(report,null,2));
const gh=args=>execFileSync('gh',args,{encoding:'utf8',maxBuffer:30*1024*1024});
const api=path=>JSON.parse(gh(['api','repos/'+repo+'/'+path]));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function finished(id){
 for(let k=0;k<180;k++){
  const r=api('actions/runs/'+id);
  if(r.status==='completed')return r;
  if(k%3===0)console.log('ESPERANDO '+JSON.stringify({run:id,status:r.status}));
  await sleep(20000);
 }
 throw Error('La ejecución no terminó en el plazo: '+id);
}
async function dispatch(){
 const before=api('actions/workflows/sala-recorrido.yml/runs?event=workflow_dispatch&branch=main&per_page=100').workflow_runs;
 const ids=new Set(before.map(r=>r.id));
 gh(['workflow','run','sala-recorrido.yml','--ref','main','-f','pasadas_restantes=0']);
 for(let k=0;k<20;k++){
  const fresh=api('actions/workflows/sala-recorrido.yml/runs?event=workflow_dispatch&branch=main&per_page=100').workflow_runs.filter(r=>!ids.has(r.id));
  if(fresh.length>1)throw Error('Más de una ejecución nueva: requiere conciliación, no se elige por orden');
  if(fresh.length===1)return fresh[0].id;
  await sleep(3000);
 }
 throw Error('Dispatch sin ejecución identificada; no se repite');
}
try{
 const calibration=await finished(39073909910);
 report.produccion_inicial.conclusion=calibration.conclusion;save();
 for(let cycle=1;cycle<=4;cycle++){
  const id=cycle===1?39075517796:await dispatch(),start=new Date().toISOString();report.actual={cycle,run:id,inicio:start};save();console.log('CICLO_INICIADO '+JSON.stringify(report.actual));
  const r=await finished(id),jobs=api('actions/runs/'+id+'/jobs?per_page=100').jobs;
  if(r.conclusion!=='success')throw Error('El recorrido completo falló: '+id+' '+r.conclusion);
  for(const name of ['mesa / mesa','productor / productor','ejecutor / ejecutor','revision / revision']){
   if(!jobs.some(j=>j.name===name&&j.conclusion==='success'))throw Error('Etapa no acreditada: '+name);
  }
  const dir=root+'/ciclo-'+cycle;
  const env={...process.env,SALA_EVIDENCE_DIR:dir,SALA_CYCLE_RUN:String(id),SALA_PASSES:'1',SALA_MOBILE:cycle%2===0?'1':'0'};
  execFileSync('node',['operaciones/verificar-ciclo.cjs'],{env,stdio:'inherit',timeout:15*60*1000});
  execFileSync('python3',['operaciones/verificar-video-real.py'],{env,stdio:'inherit',timeout:5*60*1000});
  const view=JSON.parse(fs.readFileSync(dir+'/resultado.json')),video=JSON.parse(fs.readFileSync(dir+'/video-verificado.json'));
  if(!view.ok||!video.ok)throw Error('Falta prueba de entregables');
  const item={cycle,run:id,code_sha:r.head_sha,inicio:start,fin:new Date().toISOString(),etapas:jobs.map(j=>({name:j.name,conclusion:j.conclusion})),laminas_preparadas:view.lote.laminas_preparadas,tiras_reutilizadas:view.lote.tiras_reutilizadas,tomas_obtenidas:view.lote.tomas_obtenidas,imagenes_verificadas:view.lote.assets.length,publicaciones:view.passes[0].columnas,laminas_recorridas:view.passes[0].laminas_recorridas,video,ok:true};
  report.cycles.push(item);save();console.log('CICLO_COMPLETO '+JSON.stringify(item));
 }
 report.ok=true;report.cuatro_consecutivos=true;delete report.actual;save();
}catch(e){report.error=e.message;save();console.error('CICLO_FALLIDO '+e.message);process.exitCode=1;}
