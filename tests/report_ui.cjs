// Behavior tests using a small DOM double, not a browser layout test. No packages required.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2] || 'output/index.html', 'utf8');
class Element {
  constructor(tag) {this.tag=tag;this.children=[];this.dataset={};this.style={};this.attrs={};this.className='';this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(k,v){this.attrs[k]=v;}
  getAttribute(k){return this.attrs[k];}
  click(){return this.onclick?.();}
  scrollIntoView(options){this.lastScroll=options;}
  focus(options){this.lastFocus=options;}
  matches(q){
    if(q.startsWith('.'))return this.className.split(' ').includes(q.slice(1));
    const attr=q.match(/^\[data-perspective="(.+)"\]$/);
    if(attr)return this.dataset.perspective===attr[1];
    return this.tag===q;
  }
  querySelectorAll(q){return this.children.flatMap(c=>c instanceof Element?[...(c.matches(q)?[c]:[]),...c.querySelectorAll(q)]:[]);}
  querySelector(q){return this.querySelectorAll(q)[0]||null;}
}
const ids=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new Element('div')]));
ids['report-data'].textContent=html.match(/<script id="report-data" type="application\/json">(.*?)<\/script>/s)[1];
const events={};
const doc={querySelectorAll:q=>[],getElementById:id=>ids[id],createElement:tag=>new Element(tag),querySelector:q=>Object.values(ids).flatMap(e=>e.querySelectorAll(q))[0],addEventListener:(name,handler)=>events[name]=handler};
let reloads=0;
const context=vm.createContext({document:doc,Blob,URL,setTimeout,location:{reload:()=>reloads++}});
vm.runInContext(html.match(/<script>(.*?)<\/script>/s)[1],context);
async function main(){
  if(ids['reload-report']){
    assert.match(ids.updated.textContent,/表示の更新日時/);
    assert.ok(!ids.updated.textContent.includes('Invalid Date'));
    ids['reload-report'].click();assert.equal(reloads,1);
  }
  const rendered=JSON.parse(ids['report-data'].textContent);
  if(rendered.portrait?.purpose_context){
    const rows=ids['purpose-context'].children.map(x=>x.textContent);
    assert.ok(rows.some(x=>x.includes('定型操作')));
    assert.ok(rows.some(x=>x.includes('感度確認')));
    assert.ok(rows.some(x=>x.includes('材料不足')));
  }else assert.equal(ids['purpose-context'].children.length,0);
  const practices=rendered.practices?.items||[];
  assert.equal(ids['practice-cases'].querySelectorAll('.practice').length,practices.filter(p=>p.featured).length);
  assert.equal(ids['practice-more'].querySelectorAll('.practice').length,practices.filter(p=>!p.featured).length);
  if(practices.some(p=>p.featured)){
    assert.equal(ids['practice-picks'].querySelectorAll('button').length,practices.filter(p=>p.featured).length);
    ids['practice-picks'].querySelector('button').click();
    assert.ok(ids['practice-cases'].querySelector('.practice').lastScroll);
    const sample=practices.find(p=>p.featured);
    ids['practice-cases'].querySelector('button').click();
    assert.equal(ids['view-comparison'].hidden,false);
    assert.ok(ids['practice-draft'].value.includes(sample.case.question));
    if(sample.case.collaboration){
      const article=ids['practice-cases'].querySelector('.practice');
      const account=article.querySelector('.practice-collaboration');
      assert.deepEqual(account.querySelectorAll('p').map(e=>e.textContent),[sample.case.collaboration.pattern.text,sample.case.collaboration.boundary.text]);
      assert.ok(article.children.indexOf(account)<article.children.indexOf(article.querySelector('.practice-layout')));
      assert.ok(ids['practice-draft'].value.includes(sample.case.collaboration.pattern.text));
      assert.ok(ids['practice-draft'].value.includes(sample.case.situation.text));
    }
    assert.ok(!ids['practice-draft'].value.includes(sample.session));
    ids['discard-practice-text'].click();
    assert.equal(ids['practice-draft'].value,'');
    assert.equal(ids['practice-draft-panel'].hidden,true);
    ids['nav-result'].click();
  }
  const grouped=['portrait-v1','portrait-v2'].includes(rendered.portrait?.schema);
  const catalogEntries=grouped?ids['type-grid'].querySelectorAll('.catalog-traveler'):ids['type-grid'].children;
  assert.equal(catalogEntries.length,16);
  if(grouped){
    assert.equal(ids['type-grid'].children.length,4);
    for(const group of ids['type-grid'].children){
      const entries=group.querySelectorAll('.catalog-traveler');
      assert.equal(entries.length,4);
      assert.ok(entries.every(t=>t.dataset.code.startsWith(group.dataset.prefix)));
      const types=rendered.portrait.classification.type_catalog.filter(t=>t.code.startsWith(group.dataset.prefix));
      assert.equal(group.querySelector('.catalog-common').textContent,types[0].tagline.split(' / ').slice(0,2).join(' ／ '));
      for(const entry of entries){
        const type=types.find(t=>t.code===entry.dataset.code);
        assert.deepEqual(entry.querySelectorAll('dd').map(e=>e.textContent),type.tagline.split(' / ').slice(2));
      }
    }
  }
  assert.equal(ids['reflection-questions'].children.length,4);
  assert.ok(ids['material-overview'].textContent.includes('会話'));
  assert.ok(ids['material-overview'].textContent.includes('表'));
  ids['material-evidence'].click();
  assert.equal(ids['view-observations'].hidden,false);
  ids['nav-result'].click();
  // Screenshot mode preserves the diagnosis and can be left by button or Escape.
  const summaryName=ids['summary-name'].textContent;
  ids['open-summary'].click();
  assert.equal(ids['summary-mode'].hidden,false);
  assert.equal(ids['report-shell'].hidden,true);
  assert.equal(ids['skip-content'].getAttribute('href'),'#summary-sheet');
  assert.equal(ids['open-summary'].getAttribute('aria-expanded'),'true');
  assert.equal(ids['close-summary'].lastFocus.preventScroll,true);
  doc.onkeydown({key:'Escape'});
  assert.equal(ids['summary-mode'].hidden,true);
  assert.equal(ids['report-shell'].hidden,false);
  assert.equal(ids['skip-content'].getAttribute('href'),'#report-main');
  ids['open-summary'].click();ids['close-summary'].click();
  assert.equal(ids['summary-mode'].hidden,true);
  assert.equal(ids['open-summary'].getAttribute('aria-expanded'),'false');
  assert.equal(ids['open-summary'].lastFocus.preventScroll,true);
  assert.equal(ids['summary-name'].textContent,summaryName);
  assert.equal(summaryName,ids.name.textContent);
  assert.deepEqual(ids['summary-examples'].children.map(e=>e.textContent),rendered.perspectives.filter(p=>!p.not_assessed&&p.sessions>0).slice(0,3).map(p=>p.title));
  if(rendered.portrait){
    const axes=ids['summary-axes'].querySelectorAll('article');
    assert.equal(axes.length,4);
    rendered.portrait.axes.forEach((a,i)=>{
      assert.equal(axes[i].querySelectorAll('.axis-track').length,Number(a.state!=='insufficient'&&Number.isFinite(a.left_percent)));
      assert.equal(axes[i].querySelectorAll('details').length,0,'summary does not copy conversation evidence');
    });
  }else{assert.ok(ids['summary-axes'].children[0].textContent.includes('未評価'));}
  assert.equal(ids.perspectives.querySelectorAll('article').length,rendered.perspectives.length);
  assert.equal(rendered.perspectives.length,38);
  const views=['result','observations','comparison','catalog'];
  const checkView=active=>{
    for(const view of views){
      assert.equal(ids['view-'+view].hidden,view!==active);
      assert.equal(ids['nav-'+view].getAttribute('aria-pressed'),String(view===active));
    }
  };
  checkView('result');
  for(const view of views){
    ids['nav-'+view].click();checkView(view);
    assert.equal(ids['view-'+view].lastScroll.block,'start','view changes reveal the new content from the start');
    assert.equal(ids['view-'+view].lastFocus.preventScroll,true);
    assert.equal(ids['view-'+view].getAttribute('tabindex'),'-1');
  }
  ids['nav-result'].click();
  const cards=ids.perspectives.querySelectorAll('article');
  const cardPerspectives=cards.map(card=>rendered.perspectives.find(p=>p.id===card.querySelector('.example-text').dataset.perspective));
  assert.ok(cards.every(card=>card.querySelector('details')&&!card.querySelector('details').open),'long explanations start collapsed');
  const checkFilter=predicate=>{
    assert.deepEqual(cards.map(card=>!card.hidden),cardPerspectives.map(predicate));
    const count=rendered.perspectives.filter(predicate).length;
    assert.equal(ids['observation-count'].textContent,count+' / 38観点');
    assert.equal(ids['observation-empty'].hidden,count!==0);
    for(const grid of ids.perspectives.querySelectorAll('.lens-grid')){
      assert.equal(grid.hidden,grid.children.every(card=>card.hidden));
    }
  };
  ids['observation-search'].value='no-matching-observation-xyz';
  ids['observation-search'].oninput();checkFilter(()=>false);
  ids['observation-search'].value='';
  for(const mode of ['observed','unknown','all']){
    ids['observation-filter'].value=mode;ids['observation-filter'].onchange();
    checkFilter(p=>mode==='all'||mode==='observed'&&p.sessions>0||mode==='unknown'&&Boolean(p.not_assessed||p.uncertain_sessions>0));
  }
  const query=rendered.perspectives[0].id.toUpperCase();
  ids['observation-search'].value='  '+query+'  ';ids['observation-search'].oninput();
  checkFilter(p=>[p.title,p.id,p.description,p.group].join(' ').toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  ids['nav-observations'].click();checkView('observations');
  assert.equal(ids['observation-search'].value,'  '+query+'  ','switching views preserves filters');
  ids['observation-search'].value='';ids['observation-search'].oninput();checkFilter(()=>true);
  ids['nav-result'].click();
  if(rendered.portrait){
    assert.equal(ids['portrait-axes'].querySelectorAll('article').length,4);
    assert.equal(ids['portrait-tones'].querySelectorAll('article').length,7);
    assert.equal(ids['portrait-discoveries'].querySelectorAll('article').length,rendered.portrait.discoveries.length);
    const current=rendered.portrait.classification;
    const art=rendered.journey?.types.find(t=>t.code===(current.profile?.code||rendered.representative?.code));
    const candidates=!art&&current.evidence_ready?current.candidate_codes:[];
    assert.equal(ids['journey-candidates'].querySelectorAll('img').length,candidates.length);
    assert.equal(ids['representative-note'].hidden, !rendered.representative);
    if(rendered.representative)assert.ok(ids['representative-note'].textContent.includes(rendered.representative.reason));
    assert.equal(ids.name.textContent,art?.name||current.type_name);
    assert.equal(ids['journey-hero'].hidden,!art?.image);
    if(art?.image){
      assert.equal(ids['journey-hero'].getAttribute('src'),art.image);
      assert.equal(ids['journey-hero'].getAttribute('alt'),art.alt);
    }
    if(rendered.journey){
      assert.equal(rendered.journey.types.length,16);
      for(const button of catalogEntries){
        const item=rendered.journey.types.find(t=>t.code===button.dataset.code);
        assert.equal(button.querySelector(grouped?'h3':'strong').textContent,item.name);
        assert.equal(button.querySelector('img').getAttribute('src'),item.image);
        assert.equal(button.querySelector('img').getAttribute('alt'),item.alt);
        assert.equal(button.querySelector('.type-summary').textContent,item.summary);
        assert.equal(button.querySelectorAll('.type-axis').length,grouped?2:4);
      }
      // Missing evidence must not select a cute illustration as an implicit diagnosis.
      const mixed=structuredClone(rendered);
      Object.assign(mixed.portrait.classification,{profile:null,type_code:'????',type_name:'タイプは保留',candidate_codes:[],evidence_ready:false});
      mixed.portrait.axes.forEach(a=>{a.state='insufficient';a.left_percent=100;});
      const alternateIds=Object.fromEntries(Object.keys(ids).map(id=>[id,new Element('div')]));
      alternateIds['report-data'].textContent=JSON.stringify(mixed);
      const alternateDoc={getElementById:id=>alternateIds[id],createElement:tag=>new Element(tag),querySelector:q=>Object.values(alternateIds).flatMap(e=>e.querySelectorAll(q))[0]};
      vm.runInNewContext(html.match(/<script>(.*?)<\/script>/s)[1],{document:alternateDoc,Blob,URL,setTimeout,location:{reload:()=>{}}});
      assert.equal(alternateIds['journey-hero'].hidden,true);
      assert.equal(alternateIds['summary-image'].children.length,0,'a held type has no arbitrary illustration');
      assert.equal(alternateIds['summary-axes'].querySelectorAll('.axis-track').length,0,'partial evidence must not position an insufficient axis');
      assert.equal(alternateIds['summary-name'].textContent,'タイプは保留');
      assert.equal(alternateIds.name.textContent,'タイプは保留');
    }
    const mismatch=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));mismatch.method=rendered.method;
    context.input=mismatch;assert.equal(vm.runInContext('app.validShare(input)',context),false);
  }else{assert.ok(ids['portrait-axes'].textContent.includes('まだ分析していません'));assert.equal(ids['journey-hero'].hidden,true);assert.equal(ids['type-grid'].querySelectorAll('img').length,0);}
  const coverage=rendered.sampling.source_coverage;
  if(coverage){
    assert.equal(ids['source-coverage'].children.length,coverage.length+1);
    for(const row of coverage){
      assert.ok(ids['source-coverage'].children.some(c=>c.textContent.includes(row.reason)&&c.textContent.includes('分析 '+row.selected_sessions+'会話')));
    }
  }else{assert.ok(ids['source-coverage'].children[0].textContent.includes('内訳がありません'));}
  const original=ids.name.textContent;
  for(const entry of catalogEntries){
    assert.ok(entry.querySelector('.type-summary').textContent);
    if(grouped){assert.equal(entry.tag,'article');assert.ok(entry.querySelector('.catalog-differences'));}
    else{
      assert.equal(entry.tag,'details');assert.ok(entry.querySelector('summary'));
      assert.ok(entry.querySelector('.type-detail'));
      assert.equal(entry.open,undefined,'legacy explanations start collapsed');
    }
  }
  assert.equal(ids.name.textContent,original,'browsing does not alter the diagnosis');
  ids['example-role'].value='designer';ids['example-role'].onchange();
  const profile=JSON.parse(fs.readFileSync(process.argv[3] || 'output/share-profile.json','utf8'));
  const exported=JSON.parse(vm.runInContext('JSON.stringify(app.share())',context));
  assert.deepEqual(exported,profile,'HTML and file export must agree, including legacy omissions and process forms');
  const runValid=p=>{context.input=p;return vm.runInContext('app.validShare(input)',context);};
  assert.equal(runValid(profile),true);
  for(const edit of [p=>p.method='old',p=>p.metrics[0]=null,p=>p.metrics[0].id='__proto__',p=>p.metrics[0].session_rate=101,p=>p.metrics.push(p.metrics[0])]){
    const invalid=structuredClone(profile);edit(invalid);assert.equal(runValid(invalid),false);
  }
  if(profile.method==='semantic-38-v3'){
    const invalid=structuredClone(profile);invalid.metrics.find(m=>'forms' in m).forms=['unknown'];assert.equal(runValid(invalid),false);
  }
  ids['peer-files'].files=[{size:2000,text:async()=>JSON.stringify(profile)}];
  await ids['peer-files'].onchange();
  assert.equal(ids['peer-error'].textContent,'');
  assert.equal(ids.comparison.querySelectorAll('tbody')[0].children.length,profile.metrics.length);
  ids['clear-peers'].click();assert.equal(ids.comparison.querySelector('table'),null);
  ids['peer-files'].files=[{size:4,text:async()=>'{bad'}];await ids['peer-files'].onchange();assert.ok(ids['peer-error'].textContent);
  if(rendered.portrait?.purpose_context){
    const legacy=structuredClone(rendered);delete legacy.portrait.purpose_context;delete legacy.purpose_summary;
    legacy.method='semantic-38-v3';legacy.portrait.schema='portrait-v1';context.legacy=legacy;
    vm.runInContext('mountReport(legacy)',context);
    assert.equal(ids['purpose-context'].children.length,0,'old import clears new purpose details');
  }
  console.log('Report behavior passed: view navigation, observation filters, collapsed details, 38 metrics, 16 styles and versioned sharing.');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
