'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot,calls,response,flush,deferred,find}=require('./catalog_test_dom.cjs');
const expected={boot_id:'a'.repeat(32),epoch:1,request_id:'b'.repeat(32),native_instance:'c'.repeat(36),
  file_sha256:'d'.repeat(64),selection_epoch:1,expected_sequence:2,user_intent:0,subtitle_intent:0,audio_intent:0};
const playback={available:true,expected,position_ms:2000,duration_ms:100000,can_seek:true,
  subtitle_visible:true,subtitle_status:'字幕已由你手动控制',audio_status:'原声优先',
  audio:[{index:0,stream_key:'e'.repeat(64),name:'音轨一',selected:true}],
  subtitles:[{index:0,stream_key:'f'.repeat(64),name:'字幕一',selected:true}],chapters:[]};
async function scene(scopes=['playback_read','playback_control'],handlers={}){
  const ui=await boot({handlers:{'/manage/api/pair':()=>response({csrf:'test',scopes}),
    playback_presentation:()=>response(playback),playback_command:()=>response({status:'queued'}),
    playback_receipt:()=>response({status:'applied'}),...handlers}});
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
