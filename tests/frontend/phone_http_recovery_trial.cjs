'use strict';
// Real shipped JS -> real loopback HTTP -> PhoneManagement -> serial owner.
// Native is simulated by the Python fixture, not a device claim.
const assert=require('node:assert/strict');
const {boot,find}=require('./catalog_test_dom.cjs');
const [origin,code]=process.argv.slice(2);
let cookie='',dropped=false;
async function transport(url,body,options) {
  const reply=await fetch(origin+url,{method:'POST',headers:{...options.headers,
    Origin:origin,...(cookie?{Cookie:cookie}:{})},body:JSON.stringify(body),signal:options.signal});
  const issued=reply.headers.get('set-cookie');if(issued)cookie=issued.split(';')[0];
  if(body.action==='playback_command'&&!dropped){
    dropped=true;await reply.arrayBuffer();throw new Error('response lost after owner acceptance');
  }
  return reply;
}
async function ready(ui) {
  const deadline=Date.now()+5000;
  while(ui.element('workspace').classList.contains('hidden')){
    assert.ok(Date.now()<deadline,'authorization did not load: '+ui.text('status'));
    await new Promise(resolve=>setTimeout(resolve,5));
  }
  // boot's initial catalog request must release its UI lease before clicking.
  while(ui.element('search').disabled){
    assert.ok(Date.now()<deadline,'initial read did not finish');
    await new Promise(resolve=>setTimeout(resolve,5));
  }
}
function slider(ui){return ui.element('rows').children[0].children.find(row=>row.type==='range');}
(async()=>{
  const first=await boot({hash:'#'+code,transport});await ready(first);
  await first.click('playbackTab');slider(first).value='42000';await slider(first).fire('change');
  assert.match(first.text('status'),/不会自动重发/);
  const reloaded=await boot({hash:'',transport});await ready(reloaded);
  await reloaded.click('playbackTab');assert.equal(slider(reloaded).disabled,true);
  assert.match(reloaded.text('rows'),/操作编号/);
  await find(reloaded.element('rows'),'核对这次播放操作').fire();
  assert.equal(slider(reloaded).disabled,false);
  assert.equal(slider(reloaded).value,'42000');
  assert.match(reloaded.text('rows'),/原生播放器已执行/);
  console.log('HTTP_RELOAD_RECOVERED_ORIGINAL_COMMAND');
})().catch(error=>{console.error(error);process.exitCode=1;});
