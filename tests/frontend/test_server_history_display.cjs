'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot,calls,response}=require('./catalog_test_dom.cjs');

test('server history displays saved time without promising automatic resume',async()=>{
  const ui=await boot({handlers:{catalog_history:()=>response({items:[{
    id:'a'.repeat(64),name:'movie.mkv',position:42,duration:100,start_only:true
  }],next_offset:null})}});
  await ui.click('historyTab');
  assert.match(ui.text('rows'),/已观看 0:42 \/ 1:40/);
  assert.match(ui.text('rows'),/历史进度仅供查看.*从头播放，不自动续播/);
  assert.doesNotMatch(ui.text('rows'),/请在电视选择续播/);
  assert.equal(calls(ui,'pan_prepare_history_play').length,0);
  assert.equal(calls(ui,'playback_command').length,0);
});
