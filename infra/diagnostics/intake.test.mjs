import { test } from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import receiver from './worker.mjs';

const body = () => ({v:1, id:randomUUID().replaceAll('-',''), stage:'install',outcome:'space',build:'0.1.98',elapsed:5});
function request(event, url='https://test.invalid/v1/diagnostics') {
  return new Request(url,{method:'POST',headers:{'content-type':'application/json','content-encoding':'gzip'},
    body:gzipSync(JSON.stringify(event))});
}
test('real SQL receipts, quotas, rejected fields, expiration and retry', async () => {
  const db=new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./migrations/0001_receipts.sql', import.meta.url),'utf8'));
  const env={INTAKE:{limit:async()=>({success:true})}, DB:{prepare:sql=>{
    const wrap=(...args)=>({bind:wrap, run:()=>({meta:db.prepare(sql).run(...args)}),first:()=>db.prepare(sql).get(...args)});
    return wrap();
  }}};
  const e=body(), post=e=>receiver.fetch(request(e),env);
  assert.equal((await post({...e, raw:'secret'})).status,422);
  assert.equal((await post({...e, outcome:'arbitrary'})).status,422);
  assert.equal((await post({...e, raw:'x'.repeat(4000)})).status,400);
  assert.deepEqual(await (await post(e)).json(),{ack:e.id});
  assert.deepEqual(await (await post(e)).json(),{ack:e.id});
  assert.equal(db.prepare('SELECT total FROM daily').get().total,1);
  assert.equal((await post({...e,elapsed:60})).status,409);
  db.exec('UPDATE daily SET total=10000');
  assert.equal((await post(body())).status,429);
  assert.equal((await post(e)).status,200);
  db.exec('UPDATE receipts SET day=1; UPDATE daily SET day=1');
  await receiver.scheduled(null,env);
  assert.equal(db.prepare('SELECT count(*) n FROM receipts').get().n,0);
  db.close();
});
test('real local Workers runtime and D1, never production', {skip:!process.env.BOBBI_TEST_LOCAL}, async()=>{
  const url='http://127.0.0.1:18744/v1/diagnostics',e=body();
  for(let i=0;i<2;i++) assert.deepEqual(await (await fetch(request(e,url))).json(),{ack:e.id});
  assert.equal((await fetch(request({...e,title:'do not store'},url))).status,422);
});
