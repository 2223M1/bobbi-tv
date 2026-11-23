'use strict';
// Shipped JS -> real loopback HTTP -> PhoneManagement -> serial authority.
// The Python fixture owns synthetic native transitions; this is not device proof.
const assert=require('node:assert/strict');
const {boot,find}=require('./catalog_test_dom.cjs');
const [origin,code]=process.argv.slice(2);
let cookie='',dropped=false,inFlight=0;
const commands=[],receipts=[];
async function transport(url,body,options){
  if(body.action==='playback_command')commands.push(body.params);
  if(body.action==='playback_receipt')receipts.push(body.params);
  inFlight++;
  try {
    const reply=await fetch(origin+url,{method:'POST',headers:{...options.headers,Origin:origin,
      ...(cookie?{Cookie:cookie}:{})},body:JSON.stringify(body),signal:options.signal});
    const issued=reply.headers.get('set-cookie');if(issued)cookie=issued.split(';')[0];
    if(body.action==='playback_command'&&body.params.action==='user_stop'&&!dropped){
      dropped=true;await reply.arrayBuffer();throw new Error('stop reply lost after owner acceptance');
    }
    return reply;
  } finally {inFlight--;}
}
async function ready(ui){
  const deadline=Date.now()+5000;
  while(ui.element('workspace').classList.contains('hidden')||ui.element('search').disabled){
    assert.ok(Date.now()<deadline,'authorization did not load: '+ui.text('status'));
    await new Promise(resolve=>setTimeout(resolve,5));
  }
}
async function settle(ui,operation){
  let done=false,error;
  const observed=Promise.resolve(operation).then(()=>{done=true;},failure=>{error=failure;done=true;});
  const deadline=Date.now()+5000;
  while(!done){
    assert.ok(Date.now()<deadline,'UI operation did not settle: '+ui.text('status'));
    await new Promise(resolve=>setTimeout(resolve,10));
    // Advance browser receipt polling only between real HTTP operations.
    if(!inFlight)await ui.tick(500);
  }
  await observed;if(error)throw error;
}
function control(ui,label){const button=find(ui.element('rows'),label);assert.ok(button,label);return button;}
function sameInstance(one,two){
  for(const key of ['boot_id','epoch','request_id','native_instance','file_sha256','selection_epoch'])
    assert.equal(one[key],two[key],key+' was rebound');
}
(async()=>{
  const ui=await boot({hash:'#'+code,transport});await ready(ui);await ui.click('playbackTab');
  assert.equal(control(ui,'暂停播放').disabled,false);assert.equal(control(ui,'继续播放').disabled,true);
  await settle(ui,control(ui,'暂停播放').fire());assert.match(ui.text('status'),/原生播放器已执行/);
  await ui.click('refresh');assert.match(ui.text('rows'),/已暂停/);
  assert.equal(control(ui,'暂停播放').disabled,true);assert.equal(control(ui,'继续播放').disabled,false);
  await settle(ui,control(ui,'继续播放').fire());assert.match(ui.text('status'),/原生播放器已执行/);
  await ui.click('refresh');assert.match(ui.text('rows'),/播放中/);
  const stop=control(ui,'停止播放');assert.equal(stop.disabled,false);
  await settle(ui,stop.fire());await stop.fire();assert.match(ui.text('status'),/不会自动重发/);
  assert.deepEqual(commands.map(row=>row.action),['user_pause','user_resume','user_stop']);
  assert.equal(new Set(commands.map(row=>row.command_id)).size,3);
  for(const command of commands){assert.deepEqual(command.params,{});sameInstance(command.expected,commands[0].expected);}
  const original=commands[2],priorReceipts=receipts.length;
  const reloaded=await boot({hash:'',transport});await ready(reloaded);await reloaded.click('playbackTab');
  assert.match(reloaded.text('rows'),/停止播放/);
  assert.ok(reloaded.text('rows').includes(original.command_id));
  const review=control(reloaded,'核对这次播放操作');
  await settle(reloaded,review.fire());await reloaded.click('refresh');
  assert.match(reloaded.text('rows'),/原生播放器已执行/);
  assert.equal(commands.length,3,'reload or receipt lookup replayed a control');
  assert.ok(receipts.length>priorReceipts);
  for(const receipt of receipts.slice(priorReceipts))
    assert.deepEqual(receipt,{expected:original.expected,command_id:original.command_id});
  console.log('HTTP_USER_TRANSPORT_ORIGINAL_STOP_RECOVERED');
})().catch(error=>{console.error(error);process.exitCode=1;});
