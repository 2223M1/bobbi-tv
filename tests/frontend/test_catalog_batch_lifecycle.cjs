'use strict';
// Execute the shipped browser script, not a copied lifecycle implementation.
// A minimal DOM and deterministic transport/clock exercise its real event handlers.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const filename=path.resolve(__dirname,'../../addons/plugin.video.bobbi/resources/web/manage.js');
const source=fs.readFileSync(filename,'utf8');
const flush=()=>new Promise(setImmediate);
class Element {
  constructor(tag) {
    this.tag=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.disabled=false;
    const classes=new Set();
    this.classList={add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name),
      toggle(name,force){const selected=force===undefined?!classes.has(name):!!force;selected?classes.add(name):classes.delete(name);}};
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  addEventListener(type,handler){this.listeners[type]=handler;}
  async fire(type='click') {
    if(type==='click'&&this.disabled)return;
    assert.equal(typeof this.listeners[type],'function',this.tag+' has no '+type+' handler');
    return this.listeners[type]({target:this,preventDefault(){},stopPropagation(){}});
  }
}
function text(root){return [root.textContent,...root.children.map(text)].join('\n');}
function find(root,label){if(root.textContent===label)return root;for(const child of root.children){const result=find(child,label);if(result)return result;}return null;}
function row(index=0,revision=0){return {file:{id:(index+1).toString(16).padStart(64,'0'),name:'Episode '+index+'.mkv',parent:'folder'},state:'unmatched',revision,mapping:null,candidates:[],available:true};}
function response(value,status=200){return {ok:status>=200&&status<300,status,json:async()=>value};}
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
async function boot(overrides={}) {
  const ids=new Map(),requests=[],timers=new Map();let timerId=0,now=100000;
  const element=id=>{if(!ids.has(id))ids.set(id,new Element(id));return ids.get(id);};
  element('workspace').classList.add('hidden');
  const api={element,requests,rows:[row()],handlers:{},now:()=>now,
    async tick(ms){now+=ms;const pending=[...timers.entries()].filter(([key,timer])=>timer.due<=now);pending.forEach(([key,timer])=>{timers.delete(key);timer.fn();});await flush();},
    async expire(){await api.tick(15001);},
    advance(ms){now+=ms;},text:id=>text(element(id)),
    click:id=>element(id).fire(),
    async add(index=0){const card=element('rows').children[index];await find(card,'加入本批修改').fire();},
    field(index,label){return find(element('rows').children[index],label).children[0];}};
  Object.assign(api,overrides);
  const document={getElementById:element,createElement:tag=>new Element(tag),hidden:false,listeners:{},addEventListener(name,handler){this.listeners[name]=handler;}};
  api.visibility=hidden=>{document.hidden=hidden;document.listeners.visibilitychange();};
  const context={document,crypto:webcrypto,AbortController,
    setTimeout(fn,ms){const key=++timerId;timers.set(key,{fn,due:now+ms});return key;},clearTimeout:key=>timers.delete(key),
    Date:{now:()=>now},location:{hash:'#pair-example',pathname:'/manage'},history:{replaceState(){}},confirm:()=>true,
    fetch:async(url,options)=>{
      const body=JSON.parse(options.body), action=body.action||url;
      requests.push({url,body,options});
      if(api.handlers[action])return api.handlers[action](body,options);
      if(url==='/manage/api/pair')return response({csrf:'test-csrf'});
      if(url==='/manage/api/revoke')return response({revoked:true});
      if(body.action==='catalog_preview')return response({items:body.params.commands.map(()=>({status:'ready',before:null,after:{kind:'custom'}}))});
      if(body.action==='catalog_apply')return response({items:body.params.commands.map(()=>({status:'applied',revision:1}))});
      if(body.action==='catalog_receipt')return response({status:'missing',items:[]});
      return response({items:api.rows,next_offset:null});
    }};
  vm.runInNewContext(source,context,{filename});await flush();return api;
}
function calls(api,action){return api.requests.filter(request=>request.body.action===action);}

for(const stage of ['preview','apply'])test(stage+' clear in flight cannot erase immutable batch or real receipt',async()=>{
  const ui=await boot();await ui.add();
  if(stage==='apply')await ui.click('preview');
  const delayed=deferred();ui.handlers['catalog_'+stage]=()=>delayed.promise;
  const pending=ui.click(stage);await flush();assert.equal(ui.element('clear').disabled,true);
  await ui.click('clear');
  ui.field(0,'显示名称').value='Changed only in editor';
  delayed.resolve(response({items:[{status:stage==='preview'?'ready':'applied',before:null,after:{title:'Original'},revision:1}]}));
  await pending;
  assert.match(ui.text('previewRows'),/Episode 0\.mkv/);
  assert.doesNotMatch(ui.text('status'),/Cannot read|TypeError/);
  if(stage==='apply'){
    assert.match(ui.text('previewRows'),/已保存/);
    assert.equal(calls(ui,'catalog_apply')[0].body.params.commands[0].mapping.title,'Episode 0.mkv');
    await ui.click('clear');await ui.add();
    assert.match(ui.text('receipts'),/Episode 0\.mkv.*已保存/);
  }
});

test('preview deadline releases busy; late preview cannot replace a newer preview',async()=>{
  const ui=await boot();await ui.add();const delayed=deferred();
  ui.handlers.catalog_preview=()=>delayed.promise;
  const pending=ui.click('preview');await flush();await ui.expire();await pending;
  assert.equal(ui.element('apply').disabled,true);assert.equal(ui.element('clear').disabled,false);
  await ui.click('clear');ui.field(0,'显示名称').value='New title';await ui.add();
  delete ui.handlers.catalog_preview;await ui.click('preview');const before=ui.text('previewRows');
  delayed.resolve(response({items:[{status:'ready',after:{title:'OLD LATE RESULT'}}]}));await flush();
  assert.equal(ui.text('previewRows'),before);assert.equal(ui.element('apply').disabled,false);
});

test('lost write stays unknown and retries identical request id/order/content only',async()=>{
  const ui=await boot({rows:[row(),row(1)]});await ui.add();await ui.add(1);await ui.click('preview');
  const delayed=deferred();ui.handlers.catalog_apply=()=>delayed.promise;
  const pending=ui.click('apply');await flush();await ui.expire();await pending;
  assert.match(ui.text('status'),/提交结果待核对/);assert.equal(ui.element('clear').disabled,true);
  await ui.add();assert.match(ui.text('status'),/上一批提交结果待核对/);
  delete ui.handlers.catalog_apply;await ui.click('retry');
  const writes=calls(ui,'catalog_apply');assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);
  assert.equal(calls(ui,'catalog_receipt')[0].body.params.request_id,writes[0].body.params.request_id);
  assert.match(ui.text('status'),/本批已保存/);
  delayed.resolve(response({items:[{status:'failed'},{status:'failed'}]}));await flush();
  assert.match(ui.text('status'),/本批已保存/);
});

test('receipt lookup uses original names and indices; never resubmits a found result',async()=>{
  const ui=await boot({rows:[row(),row(1)]});await ui.add();await ui.add(1);await ui.click('preview');
  ui.handlers.catalog_apply=()=>new Promise(()=>{});
  const pending=ui.click('apply');await flush();await ui.expire();await pending;
  ui.handlers.catalog_receipt=()=>response({status:'found',items:[{index:1,status:'conflict',revision:2},{index:0,status:'applied',revision:1}]});
  await ui.click('retry');assert.equal(calls(ui,'catalog_apply').length,1);
  assert.match(ui.text('receipts'),/Episode 0\.mkv.*已保存/);assert.match(ui.text('receipts'),/Episode 1\.mkv.*版本冲突/);
  await ui.click('clear');await ui.add();await ui.click('preview');
  assert.match(ui.text('receipts'),/Episode 0\.mkv.*已保存/);
});

test('expired/missing receipt cannot become new blind write; reload requires manual reconciliation',async()=>{
  const ui=await boot();await ui.add();await ui.click('preview');ui.handlers.catalog_apply=()=>new Promise(()=>{});
  const pending=ui.click('apply');await flush();await ui.expire();await pending;ui.advance(120000);
  await ui.click('retry');assert.equal(calls(ui,'catalog_apply').length,1);
  assert.match(ui.text('status'),/原回执不可用/);assert.equal(ui.element('reviewAgain').disabled,false);
  ui.rows=[row(0,2)];await ui.click('reviewAgain');assert.equal(calls(ui,'catalog_items').length,2);
  assert.match(ui.text('status'),/修订变化不证明原提交成功/);
  await ui.add();await ui.click('preview');
  assert.equal(calls(ui,'catalog_preview').at(-1).body.params.commands[0].expected_revision,2);
  assert.equal(calls(ui,'catalog_apply').length,1);
});

test('partial receipt stays visible when missing indices expire',async()=>{
  const ui=await boot({rows:[row(),row(1)]});await ui.add();await ui.add(1);await ui.click('preview');
  ui.handlers.catalog_apply=()=>response({items:[{status:'applied',revision:1}]});
  await ui.click('apply');ui.advance(120000);
  ui.handlers.catalog_receipt=()=>response({status:'found',items:[{index:0,status:'applied',revision:1}]});
  await ui.click('retry');await ui.click('reviewAgain');
  assert.match(ui.text('receipts'),/Episode 0\.mkv.*已保存/);
  assert.match(ui.text('receipts'),/Episode 1\.mkv.*提交结果待核对/);
});

test('independent revoke interrupts hung read and isolates all late results',async()=>{
  const ui=await boot();const delayed=deferred();ui.handlers.catalog_items=()=>delayed.promise;
  const reading=ui.click('refresh');await flush();await ui.click('revoke');await reading;
  assert.equal(ui.requests.filter(request=>request.url==='/manage/api/revoke').length,1);
  assert.equal(ui.element('workspace').classList.contains('hidden'),true);
  assert.match(ui.text('status'),/电视已确认授权结束/);
  delayed.resolve(response({items:[row(4)],next_offset:null}));await flush();
  assert.doesNotMatch(ui.text('rows'),/Episode 4/);assert.match(ui.text('status'),/电视已确认授权结束/);
  const count=ui.requests.length;await ui.click('refresh');assert.equal(ui.requests.length,count);
});

test('late pairing cannot restore csrf/workspace after revoke; timeout never claims remote cancellation',async()=>{
  const delayed=deferred();const ui=await boot({handlers:{'/manage/api/pair':()=>delayed.promise,'/manage/api/revoke':()=>new Promise(()=>{})}});
  const revoking=ui.click('revoke');await flush();await ui.expire();await revoking;
  delayed.resolve(response({csrf:'late-csrf'}));await flush();
  assert.equal(ui.element('workspace').classList.contains('hidden'),true);
  assert.match(ui.text('status'),/电视端撤销尚未确认/);assert.equal(calls(ui,'catalog_items').length,0);
});

test('account/session expiration closes workspace and blocks old callbacks',async()=>{
  const ui=await boot();await ui.add();ui.handlers.catalog_preview=()=>response({error:'ACCOUNT_OR_SERVICE_CHANGED'},401);
  await ui.click('preview');assert.equal(ui.element('workspace').classList.contains('hidden'),true);
  assert.match(ui.text('status'),/账号已变化/);const count=ui.requests.length;
  await ui.click('apply');await ui.click('refresh');assert.equal(ui.requests.length,count);
});

test('expired preview rejected before a first write requires preview again rather than an uncertain retry',async()=>{
  const ui=await boot();await ui.add();await ui.click('preview');
  ui.handlers.catalog_apply=()=>response({error:'PREVIEW_REQUIRED'},409);
  await ui.click('apply');assert.match(ui.text('status'),/预览已过期.*重新预览/);
  assert.equal(ui.element('retry').disabled,true);assert.equal(ui.element('clear').disabled,false);
  assert.equal(ui.element('apply').disabled,true);
});

test('oversized editor payload is split by complete UTF-8 envelope, not just item count',async()=>{
  const ui=await boot({rows:Array.from({length:5},(_,index)=>row(index))});
  for(let index=0;index<5;index++){
    ui.field(index,'显示名称').value='影'.repeat(240);
    ui.field(index,'版本备注（可选，不作为同源续播证明）').value='版'.repeat(240);
    await ui.add(index);
  }
  await ui.click('preview');assert.equal(calls(ui,'catalog_preview').length,2);
  await ui.click('apply');
  for(const request of calls(ui,'catalog_apply'))assert.ok(Buffer.byteLength(JSON.stringify(request.body),'utf8')<=8192);
});

const candidate={media_kind:'tv',tmdb_id:123,title:'Show',original_title:'Show',year:2020,poster_path:'/poster.jpg',basis:'TMDb 搜索建议，尚未确认',mismatch:false};
function episode(index,season=1){return {...row(index),file:{...row(index).file,name:'Show.2020.S'+String(season).padStart(2,'0')+'E'+String(index+1).padStart(2,'0')+'.mkv'},
  state:'proposed',candidates:[{origin:'filename',season,episode:index+1,year:2020}]};}
async function seasonPlan(size=12,changes={}) {
  const items=Array.from({length:size},(_,index)=>episode(index));
  Object.entries(changes).forEach(([index,value])=>Object.assign(items[index],value));
  const ui=await boot({rows:[items[0]]});
  ui.handlers.catalog_candidates=()=>response({items:[candidate]});
  ui.handlers.catalog_group=body=>{const start=body.params.offset;return response({items:items.slice(start,start+5),next_offset:start+5<size?start+5:null,
    group_id:'a'.repeat(64),anchor_id:items[0].file.id,source_id:'b'.repeat(32),projection_revision:4});};
  await find(ui.element('rows'),'搜索作品候选').fire();
  await find(ui.element('rows'),'采用此候选（尚未保存）').fire();
  await find(ui.element('rows'),'查看同目录逐集整理建议').fire();
  return {ui,items};
}
async function acceptGroup(ui){await find(ui.element('groupRows'),'将勾选项加入分批预览').fire();await ui.click('preview');}

test('12 real selected files are previewed completely and written as 5/5/2 independent snapshots',async()=>{
  const {ui}=await seasonPlan();await acceptGroup(ui);
  assert.equal((ui.text('batchPreview').match(/修改前/g)||[]).length,12);
  await ui.click('apply');const writes=calls(ui,'catalog_apply');
  assert.deepEqual(writes.map(request=>request.body.params.commands.length),[5,5,2]);
  assert.equal(new Set(writes.map(request=>request.body.params.request_id)).size,3);
  writes.forEach(request=>assert.ok(Buffer.byteLength(JSON.stringify(request.body),'utf8')<=8192));
  assert.match(ui.text('planStatus'),/已保存 12\/12，待核对 0.*未开始 0/);
  assert.equal((ui.text('receipts').match(/已保存/g)||[]).length,12);
  const groupCalls=calls(ui,'catalog_group');assert.equal(groupCalls.length,3);
  assert.equal(groupCalls[1].body.params.projection_revision,4);assert.equal(groupCalls[1].body.params.source_id,'b'.repeat(32));
});

test('cancel during a real write stops only unstarted chunks and retains the first receipt',async()=>{
  const {ui}=await seasonPlan();await acceptGroup(ui);const delayed=deferred();ui.handlers.catalog_apply=()=>delayed.promise;
  const saving=ui.click('apply');await flush();await ui.click('cancelPlan');
  delayed.resolve(response({items:Array.from({length:5},()=>({status:'applied',revision:1}))}));await saving;
  assert.equal(calls(ui,'catalog_apply').length,1);assert.match(ui.text('planStatus'),/已保存 5\/12.*未开始 7/);
  assert.equal((ui.text('receipts').match(/已保存/g)||[]).length,5);
});

test('second-chunk conflict leaves first saved and never starts the third',async()=>{
  const {ui}=await seasonPlan();await acceptGroup(ui);let writes=0;
  ui.handlers.catalog_apply=body=>response({items:body.params.commands.map(()=>({status:++writes<=5?'applied':'conflict',revision:2}))});
  await ui.click('apply');assert.equal(calls(ui,'catalog_apply').length,2);
  assert.match(ui.text('planStatus'),/已保存 5\/12.*未保存 5，未开始 2/);
  assert.match(ui.text('receipts'),/版本冲突/);
});

test('unknown second chunk pauses later chunks; lookup resumes only with an explicit user click',async()=>{
  const {ui}=await seasonPlan();await acceptGroup(ui);let count=0;
  ui.handlers.catalog_apply=body=>++count===2?new Promise(()=>{}):response({items:body.params.commands.map(()=>({status:'applied',revision:1}))});
  const saving=ui.click('apply');await flush();await ui.expire();await saving;
  assert.equal(calls(ui,'catalog_apply').length,2);assert.match(ui.text('planStatus'),/已保存 5\/12，待核对 5.*未开始 2/);
  ui.handlers.catalog_receipt=()=>response({status:'found',items:Array.from({length:5},(_,index)=>({index,status:'applied',revision:1}))});
  await ui.click('retry');assert.equal(calls(ui,'catalog_apply').length,2);assert.equal(ui.element('apply').disabled,false);
  await ui.click('apply');assert.equal(calls(ui,'catalog_apply').length,3);assert.match(ui.text('planStatus'),/已保存 12\/12/);
});

test('S00 survives group selection; remakes, multiple episodes and type conflicts default to excluded',async()=>{
  const {ui}=await seasonPlan(5,{
    0:{candidates:[{origin:'filename',season:0,episode:1,year:2020}]},
    1:{candidates:[{origin:'filename',season:1,episode:2,year:1990}]},
    2:{state:'ambiguous',candidates:[{origin:'filename',season:null,episode:null,year:2020}]},
    3:{mapping:{kind:'movie',tmdb_id:123,title:'Same numeric ID, wrong type'}}
  });
  await acceptGroup(ui);const commands=calls(ui,'catalog_preview')[0].body.params.commands;
  assert.equal(commands.length,2);assert.equal(commands[0].mapping.season,0);assert.equal(commands[0].mapping.episode,1);
  assert.equal(calls(ui,'catalog_apply').length,0);
});

test('candidate response after switching page cannot populate or select another file',async()=>{
  const ui=await boot();const delayed=deferred();ui.handlers.catalog_candidates=()=>delayed.promise;
  const searching=find(ui.element('rows'),'搜索作品候选').fire();await flush();
  ui.rows=[row(3)];await ui.click('itemsTab');
  delayed.resolve(response({items:[candidate]}));await searching;
  assert.equal(find(ui.element('rows'),'采用此候选（尚未保存）'),null);
  assert.equal(calls(ui,'catalog_apply').length,0);
});

test('candidate typing is debounced and stale earlier query never overwrites newer results',async()=>{
  const ui=await boot();const delayed=deferred();let count=0;
  ui.handlers.catalog_candidates=()=>++count===1?delayed.promise:response({items:[{...candidate,title:'New match'}]});
  const old=find(ui.element('rows'),'搜索作品候选').fire();await flush();
  const query=ui.field(0,'候选搜索关键词（仅发送此关键词）');query.value='New';await query.fire('input');
  query.value='New match';await query.fire('input');await ui.tick(349);assert.equal(count,1);
  await ui.tick(1);assert.equal(count,2);
  delayed.resolve(response({items:[{...candidate,title:'Old match'}]}));await old;
  assert.match(ui.text('rows'),/New match/);assert.doesNotMatch(ui.text('rows'),/Old match/);
});

test('job polling is single-flight, hidden-aware, bounded, and stops on a terminal state',async()=>{
  const ui=await boot();let state='running';ui.handlers.catalog_jobs=()=>response({items:[{task_id:'a'.repeat(32),state,counts:{scanned:2,discovered:1}}],next_offset:null});
  await ui.click('jobsTab');assert.equal(calls(ui,'catalog_jobs').length,1);
  ui.visibility(true);await ui.tick(10000);assert.equal(calls(ui,'catalog_jobs').length,1);
  ui.visibility(false);await ui.tick(5000);assert.equal(calls(ui,'catalog_jobs').length,2);
  const delayed=deferred();ui.handlers.catalog_jobs=()=>delayed.promise;await ui.tick(5000);
  await ui.tick(5000);assert.equal(calls(ui,'catalog_jobs').length,3);
  delayed.resolve(response({items:[{task_id:'a'.repeat(32),state:'completed',counts:{scanned:3,discovered:1}}],next_offset:null}));await flush();
  await ui.tick(30000);assert.equal(calls(ui,'catalog_jobs').length,3);assert.match(ui.text('rows'),/扫描完成/);
  assert.equal(calls(ui,'catalog_cancel').length,0);
});

test('job polling failures back off and total deadline prevents endless retries',async()=>{
  const ui=await boot();ui.handlers.catalog_jobs=()=>response({items:[{state:'running',counts:{}}],next_offset:null});
  await ui.click('jobsTab');ui.handlers.catalog_jobs=()=>response({error:'OFFLINE'},502);
  await ui.tick(5000);assert.equal(calls(ui,'catalog_jobs').length,2);
  await ui.tick(5000);assert.equal(calls(ui,'catalog_jobs').length,2);
  await ui.tick(5000);assert.equal(calls(ui,'catalog_jobs').length,3);
  await ui.tick(10000);assert.equal(calls(ui,'catalog_jobs').length,3);
  await ui.tick(10000);assert.equal(calls(ui,'catalog_jobs').length,4);
  ui.advance(120000);await ui.tick(30000);const end=calls(ui,'catalog_jobs').length;
  await ui.tick(300000);assert.equal(calls(ui,'catalog_jobs').length,end);
  assert.equal(calls(ui,'catalog_cancel').length,0);
});
