// No raw logs, account/device identifiers, media titles, or free-form messages.
const stages = new Set(['emby_browse','emby_play','install','update','rollback']);
const outcomes = new Set(['ok','handoff','failed','auth','unavailable','space','changed','unsupported']);
const reply = (status) => new Response(null, {status, headers:{'Cache-Control':'no-store'}});

async function bounded(stream, max) {
  if (!stream) throw Error();
  const reader = stream.getReader(), bytes = new Uint8Array(max);
  let pos = 0;
  try {
    while (true) {
      const {done,value} = await reader.read();
      if (done) return bytes.subarray(0,pos);
      if (pos + value.length > max) { await reader.cancel(); throw Error(); }
      bytes.set(value,pos); pos += value.length;
    }
  } finally { reader.releaseLock(); }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname !== '/v1/diagnostics' || url.search) return reply(404);
    if (req.method !== 'POST') return reply(405);
    if (req.headers.get('content-type') !== 'application/json' ||
        req.headers.get('content-encoding') !== 'gzip') return reply(415);
    if (+req.headers.get('content-length') > 1024) return reply(413);
    if (!(await env.INTAKE.limit({key:req.headers.get('cf-connecting-ip') || 'local'})).success)
      return reply(429);
    let e;
    try {
      const wire = await bounded(req.body, 1024);
      const data = new Blob([wire]).stream().pipeThrough(new DecompressionStream('gzip'));
      e = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(await bounded(data, 768)));
    } catch { return reply(400); }
    if (!e || Object.keys(e).sort().join(',') !== 'build,elapsed,id,outcome,stage,v' ||
        e.v !== 1 || typeof e.id !== 'string' || !/^[a-f0-9]{32}$/.test(e.id) ||
        typeof e.build !== 'string' || !/^\d{1,3}\.\d{1,3}\.\d{1,4}$/.test(e.build) ||
        !stages.has(e.stage) || !outcomes.has(e.outcome) ||
        ![0,1,2,5,15,60,120].includes(e.elapsed)) return reply(422);
    try {
      // One row per delivery ID, including when a prior acknowledgement was lost.
      // Cap new writes; do not claim delivery on exhaustion or storage failure.
      const wrote = await env.DB.prepare(
        'INSERT INTO receipts(id,build,stage,outcome,elapsed) SELECT ?,?,?,?,? ' +
        'WHERE COALESCE((SELECT total FROM daily WHERE day=unixepoch()/86400),0)<10000 ' +
        'ON CONFLICT(id) DO NOTHING'
      ).bind(e.id,e.build,e.stage,e.outcome,e.elapsed).run();
      if (!wrote.meta.changes) {
        const row = await env.DB.prepare('SELECT build,stage,outcome,elapsed FROM receipts WHERE id=?').bind(e.id).first();
        if (!row) return reply(429);
        if (['build','stage','outcome','elapsed'].some(k => row[k] !== e[k])) return reply(409);
      }
      return Response.json({ack:e.id},{headers:{'Cache-Control':'no-store'}});
    } catch { return reply(503); }
  },
  async scheduled(_event, env) {
    await env.DB.prepare('DELETE FROM receipts WHERE day < unixepoch()/86400-13').run();
    await env.DB.prepare('DELETE FROM daily WHERE day < unixepoch()/86400-13').run();
  }
};
