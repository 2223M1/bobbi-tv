'use strict';
// Actual browser handlers -> actual PhoneManagement -> actual SQLite. Only DOM,
// IPC transport, clock and private directory rows are synthetic; no network IO.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const readline=require('node:readline');
const {boot,calls,deferred,response,find}=require('./catalog_test_dom.cjs');
const repo=path.resolve(process.env.BOBBI_FRONTEND_REPO||path.join(__dirname,'../..'));
const expectBug=process.env.BOBBI_EXPECT_BASELINE_BUG==='1';

async function waitUntil(predicate) {
  const deadline=Date.now()+5000;
  while(!predicate()) {
    assert.ok(Date.now()<deadline,'Actual browser/phone exchange did not complete');
    await new Promise(done=>setTimeout(done,5));
  }
}

async function backend(count) {
  const child=spawn(process.env.BOBBI_TEST_PYTHON||'python3',['-u',path.join(__dirname,'phone_management_bridge.py'),
    '--repo',repo,'--count',String(count)],{stdio:['pipe','pipe','pipe']});
  const pending=new Map();let sequence=0,errors='',readyResolve,readyReject;
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject;});
  const exit=new Promise(resolve=>child.once('exit',resolve));
  child.stderr.on('data',data=>errors+=String(data));
  child.on('error',error=>{readyReject(error);for(const waiter of pending.values())waiter.reject(error);});
  child.on('exit',code=>{
    const error=new Error('Phone bridge ended ('+code+'): '+errors);
    readyReject(error);for(const waiter of pending.values())waiter.reject(error);
  });
  readline.createInterface({input:child.stdout}).on('line',line=>{
    const message=JSON.parse(line);
    if(message.ready){readyResolve(message);return;}
    const waiter=pending.get(message.id);
    if(waiter){pending.delete(message.id);waiter.resolve(message.result);}
  });
  const initial=await ready;
  const request=(op,body={})=>new Promise((resolve,reject)=>{
    const id=++sequence;pending.set(id,{resolve,reject});child.stdin.write(JSON.stringify({id,op,...body})+'\n');
  });
  let cookie='';
  return {request,code:initial.pairing_code,
    async fetch(url,body,options) {
      const result=await request('handle',{path:url,body,headers:{...options.headers,Cookie:cookie}});
      if(result.cookie)cookie=result.cookie.split(';')[0];
      return response(result.value,result.status);
    },
    async close(){await request('close');child.stdin.end();assert.equal(await exit,0,errors);}
  };
}

async function scene(count) {
  const server=await backend(count);
  let interceptor=null;
  const ui=await boot({filename:path.join(repo,'addons/plugin.video.bobbi/resources/web/manage.js'),hash:'#'+server.code,
    transport:(url,body,options)=>interceptor?interceptor(url,body,options):server.fetch(url,body,options)});
  await waitUntil(()=>ui.element('rows').children.length===Math.min(count,32));
  let selected=0;
  while(selected<count) {
    for(let index=0;index<ui.element('rows').children.length;index++){await ui.add(index);selected++;}
    if(selected<count){assert.equal(ui.element('next').disabled,false);await ui.click('next');}
  }
  await ui.click('preview');assert.equal(ui.element('apply').disabled,false);
  return {ui,server,setTransport:handler=>{interceptor=handler;}};
}

test(expectBug?'baseline: 41 files lose the first authorization in the real eight-preview cache':
  '41 files cross the real eight-preview cache without losing the first authorization',async()=>{
  const {ui,server}=await scene(41);
  try {
    const before=await server.request('state');assert.equal(before.preview_cache,8);
    assert.equal(calls(ui,'catalog_preview').length,9);assert.equal(before.saved,0);
    await ui.click('apply');const after=await server.request('state');
    if(expectBug) {
      assert.equal(after.saved,0);assert.equal(after.writes.length,0);
      assert.match(ui.text('status'),/预览已过期/);
      assert.equal(calls(ui,'catalog_apply').length,1);
    } else {
      assert.equal(after.saved,41);assert.equal(after.writes.length,9);
      assert.deepEqual(after.writes.map(row=>row.commands.length),[5,5,5,5,5,5,5,5,1]);
      assert.equal(new Set(after.writes.map(row=>row.request_id)).size,9);
      assert.match(ui.text('planStatus'),/已保存 41\/41，待核对 0.*未开始 0/);
    }
  } finally {await server.close();}
});

if(!expectBug) {
  test('reachable filters keep source and hierarchy through actual browser phone and SQLite queries',async()=>{
    const server=await backend(3);
    try {
      const originals=(await server.request('query')).items;
      for(const [number,row] of originals.entries())await server.request('mutate',{command:{file_id:row.entity_id,
        expected_revision:0,action:'confirm',mapping:{kind:number<2?'tv':'movie',title:number<2?'Show':'Movie',
          tmdb_id:number<2?123:456,season:number<2?1:null,episode:number<2?number+1:null,version:'版本 '+number}}});
      const ui=await boot({filename:path.join(repo,'addons/plugin.video.bobbi/resources/web/manage.js'),hash:'#'+server.code,transport:server.fetch});
      await waitUntil(()=>ui.element('rows').children.length===2);
      await ui.click('sourcesTab');await find(ui.element('rows'),'查看此来源').fire();
      ui.element('mediaKind').value='tv';await ui.element('mediaKind').fire('change');
      ui.element('availability').value='observed_present';await ui.element('availability').fire('change');
      ui.element('sort').value='recent_edited';await ui.element('sort').fire('change');
      ui.element('keyword').value='Show';await ui.click('search');
      await find(ui.element('rows'),'查看季').fire();await find(ui.element('rows'),'查看分集').fire();
      await find(ui.element('rows').children[0],'查看具体文件').fire();
      const parent=calls(ui,'catalog_query').at(-1).body.params.query.parent_entity_id;
      ui.element('sort').value='name';await ui.element('sort').fire('change');
      let query=calls(ui,'catalog_query').at(-1).body.params;
      assert.equal(query.query.view,'files');assert.equal(query.query.parent_entity_id,parent);assert.equal(query.cursor,null);
      assert.equal(query.query.source_id,'a'.repeat(32));assert.equal(query.query.media_kind,'tv');
      assert.equal(query.query.availability,'observed_present');assert.equal(query.query.text,'Show');
      assert.equal(query.query.sort,'name');assert.equal(ui.element('rows').children.length,1);
      assert.match(ui.text('scopeStatus'),/测试收藏目录.*剧集.*已收录.*按名称/);
      ui.element('availability').value='observed_absent';await ui.element('availability').fire('change');
      assert.match(ui.text('rows'),/此范围暂无作品/);
      assert.equal(calls(ui,'catalog_query').at(-1).body.params.query.parent_entity_id,parent);
      await ui.click('clearFilters');query=calls(ui,'catalog_query').at(-1).body.params;
      assert.equal(query.query.view,'works');assert.equal(query.cursor,null);assert.equal(query.query.source_id,'a'.repeat(32));
      assert.equal(query.query.availability,null);assert.equal(query.query.media_kind,null);
      assert.equal(ui.element('rows').children.length,2);assert.match(ui.text('scopeStatus'),/测试收藏目录/);
      ui.element('keyword').value='中'.repeat(160);await ui.click('search');
      assert.equal(calls(ui,'catalog_query').at(-1).body.params.query.text.length,160);
      assert.equal(ui.element('status').classList.contains('error'),false);
      await ui.click('clearFilters');assert.equal(ui.element('rows').children.length,2);
      assert.equal(calls(ui,'catalog_apply').length,0);assert.equal(calls(ui,'catalog_item').length,0);
    } finally {await server.close();}
  });

  test('filter requests lock editable controls and late results stay hidden after authorization ends',async()=>{
    const server=await backend(2), delayed=deferred();let hold=false,waiting=false;
    try {
      const ui=await boot({filename:path.join(repo,'addons/plugin.video.bobbi/resources/web/manage.js'),hash:'#'+server.code,
        transport:async(url,body,options)=>{
          const result=await server.fetch(url,body,options);
          if(hold&&body.action==='catalog_query'){waiting=true;await delayed.promise;}
          return result;
        }});
      await waitUntil(()=>ui.element('rows').children.length===2);
      const previous=ui.element('rows').children;hold=true;
      ui.element('availability').value='observed_absent';const request=ui.element('availability').fire('change');
      await waitUntil(()=>waiting);
      for(const name of ['keyword','state','mediaKind','availability','sort','search','clearFilters'])assert.equal(ui.element(name).disabled,true);
      await ui.click('revoke');delayed.resolve();await request;
      assert.equal(ui.element('workspace').classList.contains('hidden'),true);
      assert.equal(ui.element('rows').children,previous);assert.equal(calls(ui,'catalog_apply').length,0);
    } finally {delayed.resolve();await server.close();}
  });

  test('file version descriptions survive actual SQLite -> PhoneManagement -> browser rendering',async()=>{
    const server=await backend(3);
    try {
      const originals=(await server.request('query')).items;
      for(const [number,row] of originals.entries())await server.request('mutate',{command:{file_id:row.entity_id,
        expected_revision:0,action:'confirm',mapping:{kind:'movie',title:'Movie',tmdb_id:123,season:null,episode:null,version:'手工版本 '+number}}});
      const ui=await boot({hash:'#'+server.code,transport:server.fetch});
      await waitUntil(()=>ui.element('rows').children.length===1);
      await find(ui.element('rows'),'查看具体文件').fire();
      assert.equal(ui.element('rows').children.length,3);
      for(let number=0;number<3;number++)assert.match(ui.text('rows'),new RegExp('手工版本 '+number));
      assert.match(ui.text('rows'),/Show\.S01E001\.mkv/);
      assert.match(ui.text('rows'),/1,024 字节/);
      assert.match(ui.text('rows'),/测试收藏目录/);
      assert.equal(calls(ui,'catalog_item').length,0);
      assert.equal(calls(ui,'catalog_apply').length,0);
    } finally {await server.close();}
  });

  test('real work -> season -> episode -> file -> review returns to the same filtered work',async()=>{
    const server=await backend(3);
    try {
      const originals=(await server.request('query')).items;
      for(const [number,row] of originals.entries())await server.request('mutate',{command:{file_id:row.entity_id,
        expected_revision:0,action:'confirm',mapping:{kind:'tv',title:'Show',tmdb_id:123,season:0,episode:number+1,version:null}}});
      const ui=await boot({hash:'#'+server.code,transport:server.fetch});
      await waitUntil(()=>ui.element('rows').children.length===1);
      assert.equal(calls(ui,'catalog_items').length,0);assert.equal(calls(ui,'catalog_item').length,0);
      assert.equal(calls(ui,'catalog_query')[0].body.params.limit,32);
      ui.element('keyword').value='Show';await ui.click('search');
      await find(ui.element('rows'),'查看季').fire();
      const work=calls(ui,'catalog_query').at(-1).body.params.query.parent_entity_id;
      await find(ui.element('rows'),'查看分集').fire();
      await find(ui.element('rows').children[0],'查看具体文件').fire();
      const originalQuery=calls(ui,'catalog_query').at(-1).body.params.query;
      await ui.edit(0);assert.equal(calls(ui,'catalog_item').length,1);
      ui.field(0,'显示名称').value='Show reviewed';await ui.add();
      await ui.click('preview');await ui.click('apply');await ui.click('refresh');
      assert.deepEqual(calls(ui,'catalog_query').at(-1).body.params.query,originalQuery);
      assert.equal(ui.element('keyword').value,'Show');
      assert.match(ui.text('receipts'),/已保存/);
      await ui.click('back');await ui.click('back');
      assert.equal(calls(ui,'catalog_query').at(-1).body.params.query.parent_entity_id,work);
      await ui.click('back');
      const same=(await server.request('query')).items;
      assert.equal(same.length,1);assert.equal(same[0].entity_id,work);
      assert.equal(calls(ui,'catalog_items').length,0);
    } finally {await server.close();}
  });

  test('100 files keep twenty original chunks after all initial previews expire',async()=>{
    const {ui,server}=await scene(100);
    try {
      const original=calls(ui,'catalog_preview').map(row=>row.body.params.commands);
      assert.equal(original.length,20);
      await server.request('advance',{seconds:121});ui.advance(121000);
      await ui.click('apply');const after=await server.request('state');
      assert.equal(after.saved,100);assert.equal(after.writes.length,20);
      assert.deepEqual(after.writes.map(row=>row.commands),original);
      assert.equal(new Set(after.writes.map(row=>row.request_id)).size,20);
      assert.match(ui.text('planStatus'),/已保存 100\/100，待核对 0.*未开始 0/);
    } finally {await server.close();}
  });

  test('real second-chunk CAS conflict preserves the first receipt and leaves later chunks unsent',async()=>{
    const state=await scene(41),{ui,server}=state;
    try {
      const second=calls(ui,'catalog_preview')[1].body.params.commands[0];let writes=0;
      state.setTransport(async(url,body,options)=>{
        const reply=await server.fetch(url,body,options);
        if(body.action==='catalog_apply'&&++writes===1) {
          const changed=await server.request('mutate',{command:{...second,mapping:{...second.mapping,title:'Other reviewer'}}});
          assert.equal(changed.items[0].status,'applied');
        }
        return reply;
      });
      await ui.click('apply');const after=await server.request('state');
      assert.equal(after.writes.length,1);assert.equal(after.saved,6);
      assert.match(ui.text('status'),/本批修订已变化/);
      assert.match(ui.text('receipts'),/已保存/);
      assert.equal(calls(ui,'catalog_apply').length,1);
    } finally {await server.close();}
  });

  test('cancel during the refreshed first preview sends no mutation to the real index',async()=>{
    const state=await scene(41),{ui,server}=state;
    try {
      const delayed=deferred();let previewFinished=false;
      state.setTransport(async(url,body,options)=>{
        const reply=await server.fetch(url,body,options);
        if(body.action==='catalog_preview'){previewFinished=true;await delayed.promise;}
        return reply;
      });
      const saving=ui.click('apply');await waitUntil(()=>previewFinished);await ui.click('cancelPlan');
      delayed.resolve();await saving;const after=await server.request('state');
      assert.equal(after.saved,0);assert.equal(after.writes.length,0);
      assert.match(ui.text('planStatus'),/已保存 0\/41.*未开始 41.*已停止后续批次/);
    } finally {await server.close();}
  });

  test('lost committed response stays unknown and receipt recovery never remints the original write',async()=>{
    const state=await scene(41),{ui,server}=state;
    try {
      let drop=true,committed=false;
      state.setTransport(async(url,body,options)=>{
        const reply=await server.fetch(url,body,options);
        if(body.action==='catalog_apply'&&drop){drop=false;committed=true;return new Promise(()=>{});}
        return reply;
      });
      const saving=ui.click('apply');await waitUntil(()=>committed);await ui.expire();await saving;
      let actual=await server.request('state');assert.equal(actual.saved,5);assert.equal(actual.writes.length,1);
      const original=actual.writes[0];assert.match(ui.text('planStatus'),/已保存 0\/41，待核对 5/);
      await ui.click('retry');actual=await server.request('state');assert.equal(actual.writes.length,1);
      assert.equal(calls(ui,'catalog_receipt')[0].body.params.request_id,original.request_id);
      await ui.click('apply');actual=await server.request('state');
      assert.equal(actual.saved,41);assert.equal(actual.writes.length,9);
      assert.deepEqual(actual.writes[0],original);
      assert.equal(new Set(actual.writes.map(row=>row.request_id)).size,9);
    } finally {await server.close();}
  });
}
