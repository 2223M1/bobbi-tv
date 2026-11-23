'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {boot,calls,response,flush,deferred,find}=require('./catalog_test_dom.cjs');
const expected={boot_id:'a'.repeat(32),epoch:1,request_id:'b'.repeat(32),native_instance:'c'.repeat(36),
  file_sha256:'d'.repeat(64),selection_epoch:1,expected_sequence:2,user_intent:0,subtitle_intent:0,audio_intent:0};
const playback={available:true,expected,position_ms:2000,duration_ms:100000,can_seek:true,
  subtitle_visible:true,subtitle_status:'字幕已由你手动控制',audio_status:'原声优先',
  audio:[{index:0,stream_key:'e'.repeat(64),name:'音轨一',selected:true}],
  subtitles:[{index:0,stream_key:'f'.repeat(64),name:'字幕一',selected:true}],chapters:[]};
async function scene(scopes=['playback_read','playback_control'],handlers={}){
  const ui=await boot({filename:process.env.BOBBI_FRONTEND_REPO&&path.join(process.env.BOBBI_FRONTEND_REPO,'addons/plugin.video.bobbi/resources/web/manage.js'),
    handlers:{'/manage/api/pair':()=>response({csrf:'test',scopes}),
    playback_presentation:()=>response(playback),playback_command:()=>response({status:'queued'}),
    playback_receipt:()=>response({status:'applied'}),playback_forget:()=>response({status:'forgotten'}),...handlers}});
  await ui.click('playbackTab');return ui;
}
function slider(ui){return ui.element('rows').children[0].children.find(row=>row.type==='range');}
test('catalog-only permission has no playback tab and read-only does not enable controls',async()=>{
  const old=await boot();assert.equal(old.element('playbackTab').classList.contains('hidden'),true);
  const ui=await scene(['playback_read']);assert.equal(slider(ui).disabled,true);
  assert.equal(find(ui.element('rows'),'关闭字幕').disabled,true);
  assert.equal(calls(ui,'playback_command').length,0);
});
test('drag previews and duplicate change events submit exactly one original-instance command',async()=>{
  const ui=await scene(),range=slider(ui);range.value='42000';
  await range.fire('input');await range.fire('input');assert.equal(calls(ui,'playback_command').length,0);
  const pending=range.fire('change');await flush();await range.fire('change');
  assert.equal(calls(ui,'playback_command').length,1);assert.match(ui.text('rows'),/等待原生播放器确认/);
  await ui.tick(500);await pending;
  const command=calls(ui,'playback_command')[0].body.params;
  assert.equal(command.params.position_ms,42000);assert.deepEqual(command.expected,expected);
  assert.match(ui.text('status'),/原生播放器已执行/);
  await range.fire('change');assert.equal(calls(ui,'playback_command').length,1);
});
test('lost connection does not replay an old action after refresh',async()=>{
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('offline');}}),range=slider(ui);
  range.value='12000';await range.fire('change');assert.match(ui.text('status'),/不会自动重发/);
  await range.fire('change');await ui.click('refresh');assert.equal(calls(ui,'playback_command').length,1);
});
test('capability missing does not render a global seek fallback',async()=>{
  const ui=await scene(undefined,{playback_presentation:()=>response({available:false})});
  assert.equal(slider(ui),undefined);assert.match(ui.text('rows'),/内核不支持安全控制/);
  assert.equal(calls(ui,'playback_command').length,0);
});

test('review13 lost playback response preserves its original receipt and locks same-instance commands after refresh',async()=>{
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('offline');}});
  slider(ui).value='22000';await slider(ui).fire('change');
  const command=calls(ui,'playback_command')[0].body.params;
  await ui.click('refresh');assert.equal(slider(ui).disabled,true);
  await find(ui.element('rows'),'核对这次播放操作').fire();
  assert.deepEqual(calls(ui,'playback_receipt').at(-1).body.params,{expected:command.expected,command_id:command.command_id});
  assert.equal(calls(ui,'playback_command').length,1);assert.equal(slider(ui).disabled,false);
  assert.match(ui.text('rows'),/原生播放器已执行/);
});

test('review13 queued playback retains the same command until a final rejected receipt',async()=>{
  let reads=0;
  const ui=await scene(undefined,{playback_receipt:()=>response({status:++reads<=6?'queued':'rejected'})});
  slider(ui).value='23000';const sending=slider(ui).fire('change');await flush();
  for(let i=0;i<6;i++)await ui.tick(500);
  await sending;await ui.click('refresh');assert.equal(slider(ui).disabled,true);
  await find(ui.element('rows'),'核对这次播放操作').fire();
  assert.equal(calls(ui,'playback_command').length,1);assert.equal(slider(ui).disabled,false);
  assert.match(ui.text('rows'),/未执行/);
  assert.equal(new Set(calls(ui,'playback_receipt').map(row=>row.body.params.command_id)).size,1);
});

test('review13 missing receipt and a newer sequence never unlock the same playback instance',async()=>{
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('offline');},playback_receipt:()=>response({status:'unknown'})});
  await slider(ui).fire('change');
  ui.handlers.playback_presentation=()=>response({...playback,expected:{...expected,expected_sequence:99}});
  await ui.click('refresh');await find(ui.element('rows'),'核对这次播放操作').fire();
  assert.equal(slider(ui).disabled,true);await slider(ui).fire('change');
  assert.equal(calls(ui,'playback_command').length,1);assert.match(ui.text('rows'),/结果未知/);
});

test('review13 timed-out receipt remains readable for the old instance without binding its action to a new movie',async()=>{
  const delayed=deferred();
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('offline');},playback_receipt:()=>delayed.promise});
  await slider(ui).fire('change');const command=calls(ui,'playback_command')[0].body.params;
  await ui.click('refresh');const reading=find(ui.element('rows'),'核对这次播放操作').fire();await flush();
  await ui.expire();await reading;assert.equal(slider(ui).disabled,true);
  const next={...expected,request_id:'9'.repeat(32),native_instance:'8'.repeat(36),selection_epoch:2};
  ui.handlers.playback_presentation=()=>response({...playback,expected:next});
  await ui.click('refresh');assert.equal(slider(ui).disabled,false);
  assert.deepEqual(calls(ui,'playback_receipt').at(-1).body.params.expected,command.expected);
  delayed.resolve(response({status:'applied'}));await flush();
  assert.match(ui.text('rows'),/结果未知/);assert.equal(calls(ui,'playback_command').length,1);
});

test('review13 revoke during original playback receipt lookup discards late UI publication',async()=>{
  const delayed=deferred();
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('offline');},playback_receipt:()=>delayed.promise});
  await slider(ui).fire('change');await ui.click('refresh');
  const reading=find(ui.element('rows'),'核对这次播放操作').fire();await flush();
  await ui.click('revoke');await reading;const before=ui.text('rows');
  delayed.resolve(response({status:'applied'}));await flush();
  assert.equal(ui.element('workspace').classList.contains('hidden'),true);assert.equal(ui.text('rows'),before);
  assert.equal(calls(ui,'playback_command').length,1);
});

test('review13 catalog unknown batch and playback unknown command keep independent original receipts',async()=>{
  const ui=await scene(undefined,{catalog_apply:()=>{throw new Error('catalog offline');},
    playback_command:()=>{throw new Error('playback offline');},
    catalog_receipt:()=>response({status:'found',items:[{index:0,status:'applied',revision:1}]})});
  await ui.click('itemsTab');await ui.add();await ui.click('preview');await ui.click('apply');
  const catalog=calls(ui,'catalog_apply')[0].body.params;assert.equal(ui.element('retry').disabled,false);
  await ui.click('playbackTab');await slider(ui).fire('change');await ui.click('refresh');
  await find(ui.element('rows'),'核对这次播放操作').fire();
  assert.equal(ui.element('retry').disabled,false);assert.equal(ui.element('preview').disabled,true);
  await ui.click('retry');assert.equal(calls(ui,'catalog_receipt').at(-1).body.params.request_id,catalog.request_id);
  assert.equal(calls(ui,'catalog_apply').length,1);assert.equal(calls(ui,'playback_command').length,1);
});

test('review13 bounded playback records allow explicit removal of an old unknown operation before controlling a new instance',async()=>{
  let current=expected;
  const ui=await scene(undefined,{playback_presentation:()=>response({...playback,expected:current}),
    playback_command:()=>{throw new Error('offline');},playback_receipt:()=>response({status:'unknown'})});
  for(let index=0;index<8;index++){
    assert.equal(slider(ui).disabled,false);await slider(ui).fire('change');
    current={...expected,request_id:(index+1).toString(16).padStart(32,'0'),
      native_instance:(index+1).toString(16).padStart(36,'0'),selection_epoch:index+2};
    await ui.click('refresh');
  }
  assert.equal(slider(ui).disabled,true);assert.equal(calls(ui,'playback_command').length,8);
  const original=calls(ui,'playback_command')[0].body.params;
  const remove=find(ui.element('rows'),'移除此条记录');assert.ok(remove);
  await remove.fire();assert.equal(slider(ui).disabled,false);
  assert.equal(ui.text('rows').includes(original.command_id),false);
  assert.equal(calls(ui,'playback_command').length,8);assert.equal(calls(ui,'playback_receipt').length,0);
  await slider(ui).fire('change');assert.equal(calls(ui,'playback_command').length,9);
  assert.deepEqual(calls(ui,'playback_command').at(-1).body.params.expected,current);
});

test('review13 only a fresh available different instance permits removal and a current unknown operation remains locked',async()=>{
  let visible=playback;
  const ui=await scene(undefined,{playback_presentation:()=>response(visible),
    playback_command:()=>{throw new Error('offline');}});
  await slider(ui).fire('change');await ui.click('refresh');
  const original=calls(ui,'playback_command')[0].body.params;
  assert.equal(find(ui.element('rows'),'移除此条记录'),null);assert.equal(slider(ui).disabled,true);
  const other={...playback,expected:{...expected,request_id:'9'.repeat(32),native_instance:'8'.repeat(36)}};
  visible=other;await ui.click('refresh');
  let remove=find(ui.element('rows'),'移除此条记录');assert.ok(remove);
  visible={available:false};await remove.fire();
  assert.equal(find(ui.element('rows'),'移除此条记录'),null);assert.equal(slider(ui),undefined);
  assert.equal(ui.text('rows').includes(original.command_id),true);
  visible=other;await ui.click('refresh');remove=find(ui.element('rows'),'移除此条记录');assert.ok(remove);
  visible=playback;await remove.fire();
  assert.equal(find(ui.element('rows'),'移除此条记录'),null);assert.equal(slider(ui).disabled,true);
  assert.equal(ui.text('rows').includes(original.command_id),true);
  await slider(ui).fire('change');assert.equal(calls(ui,'playback_command').length,1);
  assert.equal(calls(ui,'playback_receipt').length,0);
});

test('a new page recovers the original unknown operation from its authorization without replay',async()=>{
  const original=await scene(undefined,{playback_command:()=>{throw new Error('lost response');}});
  await slider(original).fire('change');
  const command=calls(original,'playback_command')[0].body.params;
  let saved={command,status:'unknown'};
  const ui=await scene(undefined,{'/manage/api/session':()=>response({playback_operations:[saved]}),
    playback_receipt:()=>{saved={...saved,status:'applied'};return response({command_id:command.command_id,status:'applied'});}});
  assert.equal(slider(ui).disabled,true);
  await slider(ui).fire('change');assert.equal(calls(ui,'playback_command').length,0);
  await find(ui.element('rows'),'核对这次播放操作').fire();
  assert.deepEqual(calls(ui,'playback_receipt')[0].body.params,{expected:command.expected,command_id:command.command_id});
  assert.equal(slider(ui).disabled,false);assert.equal(calls(ui,'playback_command').length,0);
});

test('server refusal to forget an unknown operation leaves its recovery record locked',async()=>{
  const ui=await scene(undefined,{playback_command:()=>{throw new Error('lost');},
    playback_forget:()=>response({error:'PLAYBACK_PENDING'},409)});
  await slider(ui).fire('change');
  ui.handlers.playback_presentation=()=>response({...playback,expected:{...expected,request_id:'2'.repeat(32)}});
  await ui.click('refresh');await find(ui.element('rows'),'移除此条记录').fire();
  assert.ok(find(ui.element('rows'),'核对这次播放操作'));
  assert.equal(calls(ui,'playback_forget').length,1);assert.equal(calls(ui,'playback_command').length,1);
});

test('late playback presentation cannot overwrite the next catalog page',async()=>{
  const pending=deferred();
  const ui=await scene();
  ui.handlers.playback_presentation=()=>pending.promise;
  const loading=ui.click('refresh');await flush();
  await ui.expire();await loading;
  await ui.click('itemsTab');const before=ui.text('rows');
  pending.resolve(response(playback));await flush();
  assert.equal(ui.text('rows'),before);assert.equal(slider(ui),undefined);
});

const transportPlayback={...playback,transport_protocol:1,can_pause:true,can_resume:true,can_stop:true,
  transport_state:'playing'};
const transportButtons=[['暂停播放','user_pause','can_pause'],['继续播放','user_resume','can_resume'],
  ['停止播放','user_stop','can_stop']];

test('user transport requires exact protocol and booleans without borrowing seek capability',async()=>{
  for(const protocol of [undefined,null,true,'1',0,2,1.1]){
    const ui=await scene(undefined,{playback_presentation:()=>response({...transportPlayback,transport_protocol:protocol})});
    for(const [label] of transportButtons){
      const control=find(ui.element('rows'),label);assert.ok(control,label);assert.equal(control.disabled,true);
      await control.fire();
    }
    assert.equal(slider(ui).disabled,false);assert.equal(find(ui.element('rows'),'关闭字幕').disabled,false);
    assert.equal(calls(ui,'playback_command').length,0);
  }
  for(const capability of [undefined,null,false,1,'true']){
    const ui=await scene(undefined,{playback_presentation:()=>response({...transportPlayback,
      can_pause:capability,can_resume:capability,can_stop:capability})});
    for(const [label] of transportButtons)assert.equal(find(ui.element('rows'),label).disabled,true);
    assert.equal(slider(ui).disabled,false);
  }
  const ui=await scene(undefined,{playback_presentation:()=>response({...transportPlayback,can_seek:false})});
  assert.equal(slider(ui).disabled,true);
  for(const [label] of transportButtons)assert.equal(find(ui.element('rows'),label).disabled,false);
});

test('read-only playback grant never enables user transport',async()=>{
  const ui=await scene(['playback_read'],{playback_presentation:()=>response(transportPlayback)});
  for(const [label] of transportButtons){const control=find(ui.element('rows'),label);
    assert.ok(control,label);assert.equal(control.disabled,true);await control.fire();}
  assert.equal(calls(ui,'playback_command').length,0);
});

for(const [label,action,capability] of transportButtons){
  test(action+' freezes an empty-params command once before transport awaits',async()=>{
    const pending=deferred();
    const ui=await scene(undefined,{playback_presentation:()=>response({...transportPlayback,
      can_pause:false,can_resume:false,can_stop:false,[capability]:true}),playback_command:()=>pending.promise});
    const control=find(ui.element('rows'),label);assert.ok(control,label);
    const sending=control.fire();await flush();await control.fire();
    const command=calls(ui,'playback_command')[0].body.params;
    assert.equal(command.action,action);assert.deepEqual(command.params,{});assert.deepEqual(command.expected,expected);
    assert.match(command.command_id,/^[0-9a-f]{32}$/);assert.equal(calls(ui,'playback_command').length,1);
    ui.handlers.playback_presentation=()=>response({...transportPlayback,expected:{...expected,
      request_id:'9'.repeat(32),native_instance:'8'.repeat(36),selection_epoch:2}});
    await ui.click('refresh');
    pending.resolve(response({command_id:command.command_id,status:'applied'}));await sending;
    await control.fire();assert.equal(calls(ui,'playback_command').length,1);
    assert.deepEqual(calls(ui,'playback_command')[0].body.params,command);
  });
}

test('user transport unknown locks every action after refresh without rebinding to a newer sequence',async()=>{
  const ui=await scene(undefined,{playback_presentation:()=>response(transportPlayback),
    playback_command:()=>{throw new Error('lost pause response');},playback_receipt:()=>response({status:'unknown'})});
  await find(ui.element('rows'),'暂停播放').fire();const command=calls(ui,'playback_command')[0].body.params;
  ui.handlers.playback_presentation=()=>response({...transportPlayback,transport_state:'paused',
    expected:{...expected,expected_sequence:9,user_intent:1}});
  await ui.click('refresh');await find(ui.element('rows'),'核对这次播放操作').fire();
  for(const [label] of transportButtons){const control=find(ui.element('rows'),label);
    assert.equal(control.disabled,true);await control.fire();}
  assert.equal(calls(ui,'playback_command').length,1);
  assert.deepEqual(calls(ui,'playback_receipt')[0].body.params,{expected:command.expected,command_id:command.command_id});
});

test('lost stop response remains recoverable after reload with no active presentation and never resends',async()=>{
  const first=await scene(undefined,{playback_presentation:()=>response(transportPlayback),
    playback_command:()=>{throw new Error('stop applied but response lost');}});
  await find(first.element('rows'),'停止播放').fire();const command=calls(first,'playback_command')[0].body.params;
  let saved={command,status:'unknown'};
  const reloaded=await scene(undefined,{'/manage/api/session':()=>response({playback_operations:[saved]}),
    playback_presentation:()=>response({available:false}),playback_receipt:()=>{
      saved={...saved,status:'applied'};return response({command_id:command.command_id,status:'applied'});}});
  assert.ok(find(reloaded.element('rows'),'核对这次播放操作'));
  assert.match(reloaded.text('rows'),/停止播放/);
  await find(reloaded.element('rows'),'核对这次播放操作').fire();await reloaded.click('refresh');
  assert.deepEqual(calls(reloaded,'playback_receipt')[0].body.params,{expected:command.expected,command_id:command.command_id});
  assert.equal(calls(reloaded,'playback_command').length,0);assert.match(reloaded.text('rows'),/原生播放器已执行/);
});

test('full retained unknown journal cannot submit user transport or evict old commands',async()=>{
  const saved=Array.from({length:8},(_,i)=>({command:{action:'user_stop',params:{},command_id:(i+1).toString(16).padStart(32,'0'),
    expected:{...expected,request_id:(i+1).toString(16).padStart(32,'0'),selection_epoch:i+2}},status:'unknown'}));
  const ui=await scene(undefined,{'/manage/api/session':()=>response({playback_operations:saved}),
    playback_presentation:()=>response(transportPlayback)});
  for(const [label] of transportButtons){const control=find(ui.element('rows'),label);
    assert.equal(control.disabled,true);await control.fire();}
  await ui.click('refresh');assert.equal(calls(ui,'playback_command').length,0);
  for(const row of saved)assert.ok(ui.text('rows').includes(row.command.command_id));
});
