import { test } from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {randomUUID} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import {existsSync, readdirSync, readFileSync} from 'node:fs';
import {join, resolve} from 'node:path';
import receiver from './worker.mjs';

const body = () => ({v:1, id:randomUUID().replaceAll('-',''), stage:'install', outcome:'space', build:'0.1.98', elapsed:5});
function request(event, url='https://test.invalid/v1/diagnostics') {
  return new Request(url, {
    method:'POST',
    headers:{'content-type':'application/json', 'content-encoding':'gzip'},
    body:gzipSync(JSON.stringify(event)),
  });
}

function discoverPersistRoots() {
  const roots = [];
  if (process.env.BOBBI_LOCAL_PERSIST_TO) {
    roots.push(resolve(process.env.BOBBI_LOCAL_PERSIST_TO));
  }
  if (existsSync('/proc')) {
    for (const entry of readdirSync('/proc')) {
      if (!/^\d+$/.test(entry)) continue;
      try {
        const argv = readFileSync(`/proc/${entry}/cmdline`, 'utf8').split('\0').filter(Boolean);
        const portIdx = argv.indexOf('--port');
        const persistIdx = argv.indexOf('--persist-to');
        if (portIdx >= 0 && argv[portIdx + 1] === '18744' && persistIdx >= 0 && argv[persistIdx + 1]) {
          roots.push(resolve(argv[persistIdx + 1]));
        }
      } catch {
        // Ignore unreadable processes owned by other users or already exited.
      }
    }
  }
  roots.push(resolve(process.cwd(), '.wrangler/state'));
  return [...new Set(roots)];
}

function findLocalD1Sqlite() {
  for (const root of discoverPersistRoots()) {
    const d1Dir = join(root, 'v3', 'd1', 'miniflare-D1DatabaseObject');
    if (!existsSync(d1Dir)) continue;
    for (const name of readdirSync(d1Dir)) {
      if (!name.endsWith('.sqlite') || name === 'metadata.sqlite') continue;
      const candidate = join(d1Dir, name);
      const db = new DatabaseSync(candidate);
      try {
        db.exec('PRAGMA busy_timeout = 5000; PRAGMA query_only = ON;');
        const tables = Number(
          db.prepare("SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table' AND name IN ('receipts','daily')").get().n
        );
        if (tables === 2) return candidate;
      } finally {
        db.close();
      }
    }
  }
  return null;
}

function queryLocalD1Counts(d1File, id) {
  const db = new DatabaseSync(d1File);
  try {
    db.exec('PRAGMA busy_timeout = 5000; PRAGMA query_only = ON;');
    const receiptCount = Number(db.prepare('SELECT COUNT(*) AS n FROM receipts WHERE id = ?').get(id).n);
    const row = db.prepare('SELECT build, stage, outcome, elapsed, day FROM receipts WHERE id = ?').get(id) ?? null;
    const dailySum = Number(db.prepare('SELECT COALESCE(SUM(total), 0) AS total FROM daily').get().total);
    return {receiptCount, row, dailySum};
  } finally {
    db.close();
  }
}

test('real SQL receipts, quotas, rejected fields, expiration and retry', async () => {
  const db = new DatabaseSync(':memory:');
  db.exec(readFileSync(new URL('./migrations/0001_receipts.sql', import.meta.url), 'utf8'));
  const env = {INTAKE:{limit:async()=>({success:true})}, DB:{prepare:sql=>{
    const wrap = (...args)=>({bind:wrap, run:()=>({meta:db.prepare(sql).run(...args)}), first:()=>db.prepare(sql).get(...args)});
    return wrap();
  }}};
  const e = body(), post = ev => receiver.fetch(request(ev), env);
  assert.equal((await post({...e, raw:'secret'})).status, 422);
  assert.equal((await post({...e, outcome:'arbitrary'})).status, 422);
  assert.equal((await post({...e, raw:'x'.repeat(4000)})).status, 400);
  assert.deepEqual(await (await post(e)).json(), {ack:e.id});
  assert.deepEqual(await (await post(e)).json(), {ack:e.id});
  assert.equal(db.prepare('SELECT total FROM daily').get().total, 1);
  assert.equal((await post({...e, elapsed:60})).status, 409);

  // Preserve distinct emby_play handoff vs AV_START ok semantics
  const handoff = {...body(), stage:'emby_play', outcome:'handoff'};
  const avStart = {...body(), stage:'emby_play', outcome:'ok'};
  assert.deepEqual(await (await post(handoff)).json(), {ack:handoff.id});
  assert.equal((await post({...handoff, outcome:'ok'})).status, 409);
  assert.deepEqual(await (await post(avStart)).json(), {ack:avStart.id});
  assert.equal(db.prepare('SELECT total FROM daily').get().total, 3);

  db.exec('UPDATE daily SET total=10000');
  assert.equal((await post(body())).status, 429);
  assert.equal((await post(e)).status, 200);
  db.exec('UPDATE receipts SET day=1; UPDATE daily SET day=1');
  await receiver.scheduled(null, env);
  assert.equal(db.prepare('SELECT count(*) n FROM receipts').get().n, 0);
  db.close();
});

test('real local Workers runtime and D1, never production', {skip:process.env.BOBBI_TEST_LOCAL !== '1'}, async (t) => {
  const url = 'http://127.0.0.1:18744/v1/diagnostics';
  const d1File = findLocalD1Sqlite();
  assert.ok(d1File, 'Local Wrangler D1 SQLite database with receipts/daily tables must exist');

  const e = body();
  const before = queryLocalD1Counts(d1File, e.id);
  assert.equal(before.receiptCount, 0);

  for (let i = 0; i < 2; i++) {
    const res = await fetch(request(e, url));
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), {ack:e.id});
  }
  assert.equal((await fetch(request({...e, elapsed:60}, url))).status, 409);
  assert.equal((await fetch(request({...e, title:'do not store'}, url))).status, 422);
  assert.equal((await fetch(request({...e, raw:'x'.repeat(2000)}, url))).status, 400);

  const after = queryLocalD1Counts(d1File, e.id);
  assert.equal(after.receiptCount, 1, 'Duplicate delivery ID must insert only one receipt row in local D1');
  assert.equal(after.dailySum - before.dailySum, 1, 'Duplicate delivery ID must increment daily.total only once');
  assert.deepEqual(
    {build:after.row.build, stage:after.row.stage, outcome:after.row.outcome, elapsed:Number(after.row.elapsed)},
    {build:e.build, stage:e.stage, outcome:e.outcome, elapsed:e.elapsed}
  );
  t.diagnostic(`D1_VERIFIED receipt_count=${after.receiptCount} daily_delta=${after.dailySum - before.dailySum}`);
});
