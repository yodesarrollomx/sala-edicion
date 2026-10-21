/* Presentaciones YOD v1. Pure contract shared by the browser and the existing GAS. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.YODPresentationsDomain=api;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const VERSION='PMD-1.0.0',clone=x=>JSON.parse(JSON.stringify(x));
 const fail=code=>{throw Error(code);}, id=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(v);
 const stable=x=>JSON.stringify(x,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.keys(v).sort().reduce((a,k)=>(a[k]=v[k],a),{}):v);
 function text(v,max=6000){if(typeof v!=='string'||v.length>max||/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(v))fail('invalid_field');return v.trim();}
 function safeURL(v){if(typeof v!=='string'||!/^https:\/\/(?:yodesarrollomx\.github\.io|docs\.google\.com|drive\.google\.com|gaston-madrid-pintarron\.sayri-fraijo\.chatgpt\.site)(?:\/[^#\s\\]*)?$/.test(v))return '';return v;}
 function patch(input,spec){
  if(!input||typeof input!=='object'||Array.isArray(input))fail('invalid_patch');
  const out={scenes:{}};for(const k of Object.keys(input))if(!['title','scenes'].includes(k))fail('invalid_patch');
  if(input.title!==undefined)out.title=text(input.title,200);
  const ss=input.scenes||{};if(!ss||typeof ss!=='object'||Array.isArray(ss)||Object.keys(ss).length>128)fail('invalid_patch');
  for(const [sid,s] of Object.entries(ss)){
   if(!id(sid)||!s||typeof s!=='object'||Array.isArray(s)||['__proto__','constructor','prototype'].includes(sid))fail('invalid_scene');
   const known=spec.scenes?.find(x=>x.id===sid);if(spec.scenes?.length&&!known)fail('invalid_scene');
   const v={};for(const k of Object.keys(s))if(!['title','question','understand','moments'].includes(k))fail('invalid_patch');
   for(const k of ['title','question','understand'])if(s[k]!==undefined)v[k]=text(s[k],k==='title'?240:3000);
   if(s.moments!==undefined){if(!s.moments||typeof s.moments!=='object'||Array.isArray(s.moments)||Object.keys(s.moments).length>128)fail('invalid_moment');v.moments={};
    for(const [mi,m] of Object.entries(s.moments)){
     if(!/^\d{1,3}$/.test(mi)||Number(mi)>127||(known&&Number(mi)>=known.moments)||!m||typeof m!=='object'||Array.isArray(m))fail('invalid_moment');
     const mm={};for(const k of Object.keys(m)){if(!['spoken','change','label'].includes(k))fail('invalid_patch');mm[k]=text(m[k],k==='label'?240:6000);}v.moments[mi]=mm;
    }
   }out.scenes[sid]=v;
  }if(stable(out).length>240000)fail('patch_too_large');return out;
 }
 function mergePatch(base,add){const r=clone(base||{scenes:{}});if(add.title!==undefined)r.title=add.title;r.scenes=r.scenes||{};for(const [sid,s] of Object.entries(add.scenes||{})){const prior=r.scenes[sid]||{};r.scenes[sid]={...prior,...s,moments:{...(prior.moments||{})}};for(const [i,m] of Object.entries(s.moments||{}))r.scenes[sid].moments[i]={...(prior.moments?.[i]||{}),...m};}return r;}
 function normalizeCatalog(raw){if(raw?.schema!==1||!Array.isArray(raw.presentations)||raw.presentations.length>500)fail('invalid_catalog');const seen=new Set();return {schema:1,version:String(raw.version||VERSION),presentations:raw.presentations.map(x=>{if(!id(x.id)||seen.has(x.id)||!safeURL(x.url))fail('invalid_catalog');seen.add(x.id);return {...x,title:text(x.title,200),url:safeURL(x.url),aliases:(x.aliases||[]).filter(safeURL),tags:(x.tags||[]).map(s=>text(s,80))};})};}
 function createRecord(meta,now){return {schema:1,id:meta.id,metadata:clone(meta),revision:1,draft:{scenes:{}},releases:[{id:meta.baseVersion,patch:{scenes:{}},at:now,baseVersion:meta.baseVersion}],releaseRevision:meta.baseVersion,receipts:[],updatedAt:now,links:{opportunityIds:[],pppIds:[],terrainIds:[]}};}
 function publicRelease(r,release){const v=r.releases.find(x=>x.id===(release||r.releaseRevision));if(!v)fail('release_not_found');return {id:r.id,baseVersion:v.baseVersion,revision:r.revision,releaseRevision:v.id,patch:clone(v.patch),stage:r.metadata.stage};}
 function publicSession(s,now){if(!s)return {mode:'summary',epoch:0,sequence:0};return {mode:s.until>now&&s.mode==='guided'?'guided':'summary',presentationId:s.presentationId,sessionId:s.sessionId,releaseRevision:s.releaseRevision,epoch:s.epoch,sequence:s.sequence,position:s.position,sceneId:s.sceneId,momentId:s.momentId,updatedAt:s.updatedAt,expiresAt:s.until};}
 function privateView(r){return {...publicRelease(r),metadata:clone(r.metadata),links:clone(r.links),draft:clone(r.draft),releases:r.releases.map(x=>({id:x.id,at:x.at,baseVersion:x.baseVersion}))};}
 function createService(a){

 function normalizeLayout(value, allowed){
  if(!value||value.schema!==1||!Array.isArray(value.items)||!Array.isArray(value.groups)||value.items.length>500||value.groups.length>100)fail('invalid_layout');
  const seen=new Set(),gs=new Set();const point=n=>{if(typeof n!=='number'||!Number.isFinite(n)||n<0||n>12000)fail('invalid_layout');return Math.round(n);};
  const groups=value.groups.map(g=>{if(!g||!id(g.id)||gs.has(g.id)||!['stack','folder'].includes(g.kind)||typeof g.name!=='string'||!g.name.trim()||g.name.length>100)fail('invalid_layout');gs.add(g.id);return {id:g.id,name:g.name.trim(),kind:g.kind,x:point(g.x),y:point(g.y)};});
  const items=value.items.map(i=>{if(!i||!id(i.id)||seen.has(i.id)||(allowed&&!allowed.has(i.id))||(i.group&&!gs.has(i.group)))fail('invalid_layout');seen.add(i.id);return {id:i.id,x:point(i.x),y:point(i.y),group:i.group||''};});
  return {schema:1,items,groups};
 }
 function layoutHandle(a,p,actor){
  if(!a.readLayout||!a.writeLayout)fail('backend_not_ready');
  const allowed=new Set(a.catalog().filter(m=>actor.owner||m.shared===true||a.read(m.id).links.opportunityIds.some(id=>(actor.opportunityIds||[]).includes(id))).map(m=>m.id));
  const empty=()=>({revision:0,layout:{schema:1,items:[],groups:[]},receipts:[]});
  const view=r=>({revision:r.revision,layout:{schema:1,items:r.layout.items.filter(i=>allowed.has(i.id)),groups:r.layout.groups}});
  if(p.op==='layout_read')return {ok:true,version:VERSION,data:view(a.readLayout(actor.id)||empty())};
  if(p.op!=='layout_save')fail('unknown_action');
  if(!id(p.requestId)||p.requestId.length<8)fail('invalid_request_id');
  const d=p.data||{};const layout=normalizeLayout(d.layout,allowed);
  if(!Number.isInteger(d.expectedRevision)||d.expectedRevision<0)fail('invalid_layout');
  return a.lock(function(){const r=a.readLayout(actor.id)||empty(),hash=a.hash(stable(d));const receipt=r.receipts.find(x=>x.id===p.requestId);
   if(receipt){if(receipt.hash!==hash)fail('idempotency_mismatch');return {ok:true,requestId:p.requestId,data:view(r),appliedRevision:receipt.revision};}
   if(d.expectedRevision!==r.revision)fail('conflict');
   const revision=r.revision+1;const next={revision,layout,receipts:r.receipts.slice(-49).concat({id:p.requestId,hash,revision}),updatedAt:a.now()};
   a.writeLayout(actor.id,next);return {ok:true,requestId:p.requestId,data:view(next),appliedRevision:revision};
  });
 }

  function handle(p){try{
   if(!p||typeof p.op!=='string')fail('invalid_request');
   if(p.op==='public_catalog'){return {ok:true,version:VERSION,data:a.catalog().filter(x=>x.public===true).map(x=>{const {links,owner,brokerIds,...v}=x;return v;})};}
   if(!id(p.id)&&p.op!=='catalog'&&!p.op.startsWith('layout_'))fail('invalid_id');
   if(['public_release','public_session'].includes(p.op)){
    const meta=a.catalog().find(x=>x.id===p.id&&x.public===true);if(!meta)fail('not_found');
    return p.op==='public_session'?{ok:true,version:VERSION,data:publicSession(a.session(p.id),a.now())}:{ok:true,version:VERSION,data:publicRelease(a.read(p.id),p.release)};
   }
   const actor=a.auth(p.token);if(!actor||actor.ok!==true||!actor.id)fail('unauthorized');
   if(p.op.startsWith('layout_'))return layoutHandle(a,p,actor);
   if(p.op==='catalog'){
    const records=a.catalog().map(x=>a.read(x.id));const allowed=actor.owner?records:records.filter(r=>r.metadata.shared===true||r.links.opportunityIds.some(x=>(actor.opportunityIds||[]).includes(x)));
    return {ok:true,version:VERSION,actor:{id:actor.id,name:actor.name,owner:actor.owner===true},data:allowed.map(r=>actor.owner?privateView(r):{...publicRelease(r),metadata:clone(r.metadata),links:{opportunityIds:r.links.opportunityIds.filter(x=>(actor.opportunityIds||[]).includes(x)),pppIds:[],terrainIds:[]}})};
   }
   if(actor.owner!==true)fail('forbidden');
   const meta=a.catalog().find(x=>x.id===p.id);if(!meta)fail('not_found');
   if(p.op==='pins'){if(!a.pins)fail('backend_not_ready');return {ok:true,version:VERSION,data:a.pins(meta,p.cursor)};}
   if(p.op==='pin_read'){if(!/^CHN-\d{8}-\d{4}-[a-f0-9]{4}$/.test(p.pinId||''))fail('invalid_id');if(!a.pin)fail('backend_not_ready');return {ok:true,version:VERSION,data:a.pin(meta,p.pinId)};}
   if(p.op==='inspect')return {ok:true,version:VERSION,data:privateView(a.read(p.id)),session:publicSession(a.session(p.id),a.now())};
   if(p.op==='receipt'){if(!id(p.requestId))fail('invalid_request_id');const r=a.read(p.id),found=r.receipts.find(x=>x.id===p.requestId&&x.actor===actor.id);return {ok:true,version:VERSION,found:!!found,receipt:found?{id:found.id,hash:found.hash,revision:found.revision}:null,data:privateView(r)};}
   if(!id(p.requestId)||p.requestId.length<8)fail('invalid_request_id');
   return a.lock(function(){
    let r=a.read(p.id),now=a.now();const hash=a.hash(stable({op:p.op,id:p.id,data:p.data||{}}));
    if(p.op.startsWith('session_')){
     const d=p.data||{},old=a.session(p.id);const receipt=old?.receipts?.find(x=>x.id===p.requestId&&x.actor===actor.id);if(receipt){if(receipt.hash!==hash)fail('idempotency_mismatch');return {ok:true,requestId:p.requestId,data:publicSession(old,now)};}
     if(!id(d.controllerId)||d.controllerId.length<8)fail('invalid_controller');let s;
     if(p.op==='session_start'){
      if(old&&old.until>now&&old.mode==='guided'&&old.controllerId!==d.controllerId&&d.takeover!==true)fail('controller_active');
      if(old&&old.until>now&&old.mode==='guided'&&old.controllerId===d.controllerId&&d.takeover!==true)s=old;
      else s={presentationId:p.id,sessionId:a.uuid(),controllerId:d.controllerId,actor:actor.id,epoch:(old?.epoch||0)+1,sequence:0,position:0,sceneId:'',momentId:'',releaseRevision:r.releaseRevision,mode:'guided',receipts:[]};
     }else{
      if(!old||old.mode!=='guided'||old.until<=now)fail('session_expired');if(old.actor!==actor.id||old.controllerId!==d.controllerId||old.epoch!==d.epoch)fail('controller_changed');s=old;
      if(p.op==='session_update'){
       if(!Number.isSafeInteger(d.sequence)||d.sequence<=s.sequence)fail('stale_sequence');if(typeof d.position!=='number'||!Number.isFinite(d.position)||d.position<0||d.position>Number(meta.maxPosition||2048))fail('invalid_position');
       if(typeof d.sceneId!=='string'||d.sceneId.length>100||typeof d.momentId!=='string'||d.momentId.length>100)fail('invalid_position');
       s.sequence=d.sequence;s.position=Math.round(d.position*1000)/1000;s.sceneId=d.sceneId;s.momentId=d.momentId;
      }else if(p.op==='session_end'){s.mode='summary';s.sequence++;}else if(p.op!=='session_renew')fail('unknown_action');
     }
     s.updatedAt=now;s.until=s.mode==='guided'?now+45000:0;s.receipts=(s.receipts||[]).slice(-9);s.receipts.push({id:p.requestId,hash,actor:actor.id});a.writeSession(p.id,s);
     return {ok:true,version:VERSION,requestId:p.requestId,data:publicSession(s,now)};
    }
    const receipt=r.receipts.find(x=>x.id===p.requestId&&x.actor===actor.id);if(receipt){if(receipt.hash!==hash)fail('idempotency_mismatch');return {ok:true,version:VERSION,requestId:p.requestId,data:privateView(r),receipt:{id:receipt.id,hash:receipt.hash,revision:receipt.revision}};}
    const d=p.data||{};if(d.expectedRevision!==r.revision)fail('conflict');
    if(p.op==='save_draft')r.draft=mergePatch(r.draft,patch(d.patch,meta));
    else if(p.op==='publish'){
     const chosen=d.release?r.releases.find(x=>x.id===d.release):null;if(d.release&&!chosen)fail('release_not_found');
     if(chosen)r.draft=clone(chosen.patch);
     const version='R'+(r.revision+1)+'-'+a.uuid().slice(0,8);r.releases.push({id:version,at:now,baseVersion:meta.baseVersion,patch:clone(r.draft)});r.releaseRevision=version;
    }else if(p.op==='link'){
     const links={};for(const k of ['opportunityIds','pppIds','terrainIds']){const v=d.links?.[k]||[];if(!Array.isArray(v)||v.length>30||v.some(x=>typeof x!=='string'||!x||x.length>200))fail('invalid_link');links[k]=[...new Set(v)];}
     if(!a.validateLinks(links,actor,p.token))fail('unknown_case');r.links=links;
    }else fail('unknown_action');
    r.revision++;r.updatedAt=now;const receiptOut={id:p.requestId,hash,actor:actor.id,revision:r.revision,at:now};r.receipts.push(receiptOut);r.receipts=r.receipts.slice(-100);a.write(r);
    return {ok:true,version:VERSION,requestId:p.requestId,data:privateView(r),receipt:{id:p.requestId,hash,revision:r.revision}};
   });
  }catch(e){return {ok:false,version:VERSION,error:['invalid_layout','invalid_request','invalid_id','not_found','integrity','unauthorized','forbidden','invalid_request_id','invalid_controller','controller_active','session_expired','controller_changed','stale_sequence','invalid_position','unknown_action','idempotency_mismatch','conflict','invalid_patch','invalid_scene','invalid_moment','invalid_field','patch_too_large','invalid_link','unknown_case','release_not_found','busy','backend_not_ready'].includes(e.message)?e.message:'service_unavailable'};}}
  return {handle};
 }
 function filtered(rows,filters={}){const norm=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();const q=norm(filters.query);return rows.filter(r=>(!q||norm([r.title,r.site,r.location,r.type,...(r.tags||[])].join(' ')).includes(q))&&(!filters.site||r.site===filters.site)&&(!filters.type||r.type===filters.type)&&(!filters.stage||r.stage===filters.stage)&&(!filters.ppp||r.links?.pppIds?.includes(filters.ppp))).sort((a,b)=>(a.order||0)-(b.order||0)||a.title.localeCompare(b.title,'es'));}
 return {VERSION,stable,patch,mergePatch,normalizeCatalog,createRecord,publicRelease,publicSession,privateView,createService,filtered,safeURL};
});
