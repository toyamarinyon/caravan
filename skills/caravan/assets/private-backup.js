// Local file import only. Never restore scripts, assets, or browser storage.
const initialView=JSON.parse(document.getElementById('report-data').textContent);
// Capture the trusted, unmounted page; never serialize imported HTML or live drafts.
const reportTemplate=document.documentElement?.cloneNode?.(true);
const pristineRoots=['report-shell','summary-mode'].map(id=>[id,document.getElementById(id).cloneNode?.(true)]);
let restoreGeneration=0;
function validateBackup(value){
 let nodes=0;
 function walk(item,depth=0){
  if(++nodes>150000||depth>30)throw Error('データが複雑すぎます。');
  if(typeof item==='number'&&!Number.isFinite(item))throw Error('数値が不正です。');
  if(item&&typeof item==='object')for(const [key,child] of Object.entries(item)){
   if(['__proto__','prototype','constructor'].includes(key))throw Error('未対応の項目があります。');
   walk(child,depth+1);
  }
 }
 walk(value);
 const fail=()=>{throw Error('このファイルからは結果を復元できません。「詳しい結果をJSONで保存」（旧版では「本人用バックアップを保存」）で保存したファイルを選んでください。共有用プロフィールは比較用のため、復元には使えません。');};
 if(!value||value.schema!=='caravan-private-backup-v1'||Object.keys(value).sort().join(',')!=='execution_audit,report,schema')fail();
 const r=value.report;
 if(!r||!['semantic-18-v1','semantic-26-v2','semantic-38-v3','semantic-38-v4'].includes(r.method))fail();
 const ids=r.perspectives?.map(p=>p?.id),known=new Set(initialView.viewer_definitions.map(p=>p.id));
 if(!ids||ids.length<18||ids.length>38||new Set(ids).size!==ids.length||ids.some(id=>!known.has(id)))fail();
 if(['sessions','messages','days'].some(k=>!Number.isInteger(r[k])||r[k]<(k==='days'?1:0))||typeof r.generated_at!=='string')fail();
 if(r.portrait&&!['portrait-v1','portrait-v2'].includes(r.portrait.schema))fail();
 if('practices' in r)validatePractices(r.practices,r,fail);
 if(['journey','rendered_at','private_backup','execution_audit','material_checks'].some(k=>k in r))fail();
 if(value.execution_audit!==null&&value.execution_audit?.schema!=='execution-events-v1')fail();
 return value;
}
function validatePractices(value,report,fail){
 const text=(v,n=400)=>typeof v==='string'&&v.trim().length>0&&[...v].length<=n;
 if(!value||!['practice-v1','practice-v2','practice-v3'].includes(value.schema)||!text(value.sample_key,80)||value.sample_key!==report.sample_key||!text(value.generated_at,80)||value.reviewed_sessions!==report.sessions||!Array.isArray(value.items)||value.items.length>report.sessions)fail();
 const seen=new Set();let featured=0;
 for(const item of value.items){
  if(!item||Object.keys(item).sort().join(',')!=='case,featured,session'||!text(item.session,80)||seen.has(item.session)||typeof item.featured!=='boolean')fail();
  seen.add(item.session);featured+=item.featured;
  const c=item.case;
  const fields=['ai_role','human_action','limitation','question','response','situation','stage','title','try_next'];
  if(value.schema!=='practice-v1')fields.push('decision');
  if(value.schema==='practice-v3')fields.push('collaboration');
  if(!c||Object.keys(c).sort().join(',')!==fields.sort().join(',')||!text(c.title,80)||!['request','adjustment','review'].includes(c.stage)||['limitation','question','try_next'].some(k=>!text(c[k],300)))fail();
  for(const field of ['situation','human_action','ai_role','response']){
   const claim=c[field];
   if(!claim||Object.keys(claim).sort().join(',')!==(field==='response'?'refs,status,text':'refs,text')||!text(claim.text)||!Array.isArray(claim.refs)||claim.refs.some(r=>typeof r!=='string')||new Set(claim.refs).size!==claim.refs.length||(field!=='response'&&!claim.refs.length))fail();
  }
  if(!['not_visible','assistant_report','user_report'].includes(c.response.status)||Boolean(c.response.refs.length)!==(c.response.status!=='not_visible'))fail();
  if(value.schema!=='practice-v1'){
   const d=c.decision;
   if(!d||Object.keys(d).sort().join(',')!=='alternative,condition,kind,steps'||!['generic','sequence','tradeoff','conditional'].includes(d.kind)||!Array.isArray(d.steps)||d.steps.length>4||(item.featured&&d.kind==='generic'))fail();
   function claim(q,states){
    if(!q||Object.keys(q).sort().join(',')!==(states?'refs,status,text':'refs,text')||!text(q.text,240)||!Array.isArray(q.refs)||q.refs.some(r=>typeof r!=='string')||new Set(q.refs).size!==q.refs.length||(states&&!states.includes(q.status))||Boolean(q.refs.length)!==(!states||q.status!=='unknown'))fail();
   }
   claim(d.condition,['stated','context','unknown']);claim(d.alternative,['observed','unknown']);for(const step of d.steps)claim(step);
   if(d.kind==='sequence'&&(d.steps.length<2||d.condition.status==='unknown'))fail();
   if(['tradeoff','conditional'].includes(d.kind)&&(d.condition.status!=='stated'||d.alternative.status!=='observed'))fail();
   if(value.schema==='practice-v3'){
    if(item.featured&&c.collaboration===null)fail();
    if(c.collaboration!==null){
     if(!c.collaboration||Object.keys(c.collaboration).sort().join(',')!=='boundary,pattern')fail();
     claim(c.collaboration.pattern);claim(c.collaboration.boundary);
    }
   }
  }
 }
 if(featured>3||(value.schema==='practice-v1'&&featured!==Math.min(3,value.items.length)))fail();
}
function currentBackup(value){
 const result=JSON.parse(JSON.stringify(value)),r=result.report;
 if(['portrait-v1','portrait-v2'].includes(r.portrait?.schema)){
  for(const key of ['type_code','type_name','profile','type_status','candidate_codes','alternatives','type_catalog','repeated_dimensions','evidence_ready'])delete r[key];
  const names=Object.fromEntries(initialView.viewer_assets.types.map(t=>[t.code,t])),style=r.portrait.classification;
  for(const item of [...(style.type_catalog||[]),...(style.alternatives||[]),...(style.profile?[style.profile]:[])]){
   const entry=names[item.code];if(!entry)continue;
   item.name=entry.name;if('description' in item)item.description=entry.summary;
  }
  if(style.profile&&names[style.profile.code])style.type_name=names[style.profile.code].name;
 }
 return result;
}
function backupView(value){
 validateBackup(value);
 const view=JSON.parse(JSON.stringify(value.report)),present=new Set(view.perspectives.map(p=>p.id));
 for(const p of initialView.viewer_definitions)if(!present.has(p.id))view.perspectives.push({...p,not_assessed:true,count:null,sessions:null,assessed_sessions:null,uncertain_sessions:null,not_applicable_sessions:null,session_rate:null,status:'未評価',findings:[],observed_forms:[]});
 view.private_backup=currentBackup(value);view.execution_audit=value.execution_audit;view.rendered_at=initialView.rendered_at;
 view.journey=initialView.viewer_assets;view.material_checks={};
 if(view.portrait?.rules){
  const rules=view.portrait.rules;
  const state=c=>{const n=(c.left||0)+(c.right||0)+(c.both||0),f=n?((c.left||0)+.5*(c.both||0))/n:0;return n<rules.min_sessions?'insufficient':f>=rules.dominance?'left':1-f>=rules.dominance?'right':'mixed';};
  for(const a of view.portrait.axes){
   if(state(a.counts)!==a.state)continue;
   let changed=0,tested=0;const states=new Set();
   for(const side of ['left','right','both'])if(a.counts[side]){const c={...a.counts};c[side]--;const after=state(c);states.add(after);tested+=a.counts[side];if(after!==a.state)changed+=a.counts[side];}
   view.material_checks[a.id]={changed,tested,states:[...states].sort()};
  }
 }
 return view;
}
function resetReport(){
 for(const [id,original] of pristineRoots){const target=document.getElementById(id);target.replaceChildren(...original.cloneNode(true).childNodes);target.hidden=original.hidden;}
 document.getElementById('skip-content').setAttribute('href','#report-main');
}
function bindBackup(view){
 if(view!==initialView)for(const link of document.querySelectorAll('a[href^="developer.html"]'))link.hidden=true;
 document.getElementById('export-private').onclick=()=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(currentBackup(view.private_backup),null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='caravan-private.backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 document.getElementById('export-result-html').onclick=()=>{
  const saved=reportTemplate.cloneNode(true);
  const data={...view,viewer_definitions:initialView.viewer_definitions,viewer_assets:initialView.viewer_assets};
  // JSON is inside a script element. Escape '<' so imported prose cannot close it.
  saved.querySelector('#report-data').textContent=JSON.stringify(data).replace(/</g,'\\u003c');
  // A downloaded result has no corresponding developer.html beside it.
  for(const link of saved.querySelectorAll('a[href^="developer.html"]'))link.remove();
  const notice=saved.querySelector('#backup-status');notice.hidden=false;
  notice.textContent='保存した詳しい結果を表示しています。根拠の説明や具体例を含むため、他の人に渡す前に内容を確認してください。';
  const url=URL.createObjectURL(new Blob(['<!DOCTYPE html>\n'+saved.outerHTML],{type:'text/html;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download='index.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  document.getElementById('result-save-status').textContent='結果画面のダウンロードを開始しました。保存したHTMLを開くと、同じ詳しい結果を表示できます。';
 };
 document.getElementById('private-file').onchange=async function(){
  const generation=++restoreGeneration,file=this.files[0];if(!file)return;
  try{
   if(file.size>8*1024*1024)throw Error('8 MiB以下の本人用バックアップを選んでください。');
   const restored=backupView(JSON.parse(await file.text()));
   if(generation!==restoreGeneration)return;
   resetReport();
   try{app=mountReport(restored);}catch(error){resetReport();app=mountReport(view);throw Error('必要な分析項目が欠けています。元の表示を保持しました。');}
   const status=document.getElementById('backup-status');status.hidden=false;
   status.textContent='詳しい結果を読み込みました。元のファイルは変更していません。「結果の保存・復元」から「結果画面をHTMLで保存」を選ぶと、後からそのまま開けます。';
   document.getElementById('view-result').scrollIntoView?.({block:'start'});
  }catch(error){
   if(generation!==restoreGeneration)return;
   const status=document.getElementById('backup-status');status.hidden=false;
   status.textContent=error instanceof SyntaxError?'ファイルを読み取れませんでした。元の表示は変わりません。「詳しい結果をJSONで保存」（旧版では「本人用バックアップを保存」）で保存したファイルを選び直してください。':error.message;
  }
 };
}
