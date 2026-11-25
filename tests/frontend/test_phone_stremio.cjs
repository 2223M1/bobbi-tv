'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {boot, calls, find, response, text} = require('./catalog_test_dom.cjs');

function stremioBoot(items, extraHandlers = {}) {
  let addons = items.map(item => ({...item}));
  return boot({
    handlers: {
      '/manage/api/pair': () => response({
        csrf: 'stremio-csrf',
        scopes: ['stremio_addons'],
        catalog_kind: 'stremio',
      }),
      stremio_list: () => response({items: addons}),
      stremio_toggle: body => {
        const target = addons.find(a => a.id === body.params.id);
        if (target) {
          target.selected = {...target.selected, [body.params.category]: body.params.enabled};
        }
        return response({success: true});
      },
      stremio_remove: body => {
        addons = addons.filter(a => a.id !== body.params.id);
        return response({success: true});
      },
      stremio_validate: () => response({
        valid: true,
        manifest: {id: 'com.valid.addon', name: 'Valid Addon', version: '1.0.0'},
      }),
      stremio_add: () => {
        addons.push({
          id: 'com.valid.addon|0123456789abcdef',
          name: 'Valid Addon',
          version: '1.0.0',
          host: 'example.com',
          logo: '',
          logo_rejected: false,
          capabilities: {stream: true, catalog: false, tv: false},
          selected: {stream: true, catalog: false, tv: false},
        });
        return response({success: true});
      },
      ...extraHandlers,
    },
  });
}

function collectNoInlineAttributes(element) {
  for (const key of Object.keys(element)) {
    assert.ok(!/^on/i.test(key), 'unexpected event attribute: ' + key);
  }
  for (const child of element.children || []) {
    collectNoInlineAttributes(child);
  }
}

test('R02-01/R02-02: quotes, backslashes, newlines, entities and HTML tags never create event handlers and preserve exact ID', async () => {
  const quoteId = "com.quote');globalThis.__pwned=1;//";
  const complexId = 'com.special\\path\nline2<img src=x onerror=alert(1)>&quot;&lt;tag&gt;';
  const api = await stremioBoot([
    {
      id: quoteId,
      name: "Quote's <script>alert(1)</script> Addon",
      version: '2.0',
      host: 'addons.example',
      description: 'Line1\nLine2 &amp; <b>bold</b>',
      logo: '',
      logo_rejected: false,
      capabilities: {stream: true, catalog: true, tv: false},
      selected: {stream: true, catalog: false, tv: false},
    },
    {
      id: complexId,
      name: 'Complex\\ID\nAddon',
      version: '1.1',
      host: 'local.example',
      description: 'Special chars test',
      logo: '',
      logo_rejected: false,
      capabilities: {stream: true, catalog: false, tv: false},
      selected: {stream: false, catalog: false, tv: false},
    },
  ]);

  assert.equal(globalThis.__pwned, undefined);
  assert.equal(api.element('itemsTab').classList.contains('hidden'), true);
  assert.equal(api.element('stremioTab').classList.contains('hidden'), false);
  collectNoInlineAttributes(api.element('rows'));
  assert.ok(api.text('rows').includes(quoteId));
  assert.ok(api.text('rows').includes(complexId));

  const firstCard = api.element('rows').children[1];
  await find(firstCard, '✓ 已启用 · 视频源').fire();
  assert.deepEqual(calls(api, 'stremio_toggle')[0].body.params, {
    id: quoteId,
    category: 'stream',
    enabled: false,
  });

  const secondCard = api.element('rows').children[2];
  await find(secondCard, '移除此插件源').fire();
  assert.deepEqual(calls(api, 'stremio_remove')[0].body.params, {
    id: complexId,
  });
});

test('R02-03/R02-04: unsafe logo URLs are explicitly rejected without img elements while normal CRUD and revoke work', async () => {
  const api = await stremioBoot([
    {
      id: 'com.bad.logo',
      name: 'Unsafe Logo Addon',
      version: '1.0',
      host: 'bad.example',
      logo: 'javascript:alert(1)',
      logo_rejected: false,
      capabilities: {stream: true, catalog: false, tv: false},
      selected: {stream: true, catalog: false, tv: false},
    },
    {
      id: 'com.tmdb.logo',
      name: 'Safe Logo Addon',
      version: '1.0',
      host: 'good.example',
      logo: 'https://image.tmdb.org/t/p/w185/safe_poster.png',
      logo_rejected: false,
      capabilities: {stream: true, catalog: false, tv: false},
      selected: {stream: true, catalog: false, tv: false},
    },
  ]);

  const badCard = api.element('rows').children[1];
  assert.ok(text(badCard).includes('已拒绝非 HTTP(S) 图标地址'));
  assert.equal(badCard.children.some(child => child.tag === 'img'), false);

  const goodCard = api.element('rows').children[2];
  assert.equal(goodCard.children.some(child => child.tag === 'img'), true);

  const addCard = api.element('rows').children[0];
  const urlInput = find(addCard, 'Manifest 地址（https:// 或 stremio://）').children[0];
  urlInput.value = 'https://example.com/manifest.json';
  await find(addCard, '校验 Manifest').fire();
  assert.ok(text(addCard).includes('校验通过：Valid Addon'));
  await find(addCard, '添加插件源').fire();
  assert.equal(calls(api, 'stremio_add').length, 1);
  assert.ok(api.text('rows').includes('com.valid.addon|0123456789abcdef'));

  await api.click('revoke');
  assert.equal(api.element('workspace').classList.contains('hidden'), true);
});
test('SRC-05: paginated stremio_list navigates across pages, loads full truncated description, and supports page-2 CRUD', async () => {
  const allAddons = Array.from({length: 5}, (_, idx) => ({
    id: `com.paged.addon.${idx}|hash${idx}`,
    name: `分页插件 ${idx + 1}`,
    version: '1.0',
    host: `h${idx}.example`,
    description: idx === 0 ? '简短摘要…' : `插件 ${idx + 1} 说明`,
    description_truncated: idx === 0,
    logo: '',
    logo_rejected: false,
    capabilities: {stream: true, catalog: false, tv: false},
    selected: {stream: true, catalog: false, tv: false},
  }));

  const api = await boot({
    handlers: {
      '/manage/api/pair': () => response({
        csrf: 'stremio-csrf-page',
        scopes: ['stremio_addons'],
        catalog_kind: 'stremio',
      }),
      stremio_list: body => {
        const off = (body.params && body.params.offset) || 0;
        const slice = allAddons.slice(off, off + 2);
        const next_offset = off + slice.length < allAddons.length ? off + slice.length : null;
        return response({items: slice, total: allAddons.length, next_offset});
      },
      stremio_detail: body => response({
        addon: {...allAddons[0], id: body.params.id, description: '完整展开的六百字中文详细插件简介内容'},
      }),
      stremio_remove: body => {
        const idx = allAddons.findIndex(a => a.id === body.params.id);
        if (idx >= 0) allAddons.splice(idx, 1);
        return response({success: true});
      },
    },
  });

  assert.equal(api.element('previous').disabled, true);
  assert.equal(api.element('next').disabled, false);
  assert.ok(api.text('rows').includes('com.paged.addon.0|hash0'));
  assert.ok(!api.text('rows').includes('com.paged.addon.2|hash2'));

  // Expand truncated description on demand
  const firstCard = api.element('rows').children[1];
  await find(firstCard, '查看完整简介').fire();
  assert.ok(text(firstCard).includes('完整展开的六百字中文详细插件简介内容'));

  // Navigate to page 2 & page 3 (item #5 = index 4)
  await api.click('next');
  assert.equal(api.element('previous').disabled, false);
  assert.ok(api.text('rows').includes('com.paged.addon.2|hash2'));

  await api.click('next');
  assert.equal(api.element('next').disabled, true);
  assert.ok(api.text('rows').includes('com.paged.addon.4|hash4'));

  // Removing the sole item on page 3 automatically steps back to page 2!
  const lastCard = api.element('rows').children[1];
  await find(lastCard, '移除此插件源').fire();
  assert.ok(api.text('rows').includes('com.paged.addon.2|hash2'));
  collectNoInlineAttributes(api.element('rows'));
});

test('U10: paired subtitle_upload scope renders dedicated upload card, streams 4KB SHA-256 chunks, and isolates other tabs', async () => {
  const uploadedChunks = [];
  let committedId = null;
  const api = await boot({
    handlers: {
      '/manage/api/pair': () => response({
        csrf: 'sub-csrf',
        scopes: ['subtitle_upload'],
        catalog_kind: 'subtitle_upload',
      }),
      subtitle_upload_status: () => response({
        state: 'idle',
        target_id: 'a'.repeat(32),
        title: '星际穿越.2014.2160p',
      }),
      subtitle_upload_begin: body => response({
        state: 'receiving',
        target_id: 'a'.repeat(32),
        upload_id: body.params.upload_id,
        offset: 0,
        total_bytes: body.params.total_bytes,
      }),
      subtitle_upload_chunk: body => {
        uploadedChunks.push(body.params);
        return response({
          state: 'receiving',
          target_id: 'a'.repeat(32),
          upload_id: body.params.upload_id,
          offset: body.params.offset + 10,
          total_bytes: 28,
        });
      },
      subtitle_upload_commit: body => {
        committedId = body.params.upload_id;
        return response({
          state: 'committed',
          target_id: 'a'.repeat(32),
          committed: true,
          file_name: '中文字幕.srt',
          byte_length: 28,
          sha256: '0'.repeat(64),
        });
      },
    },
  });

  assert.equal(api.element('itemsTab').classList.contains('hidden'), true);
  assert.equal(api.element('stremioTab').classList.contains('hidden'), true);
  assert.equal(api.element('subtitleUploadTab').classList.contains('hidden'), false);
  assert.ok(api.text('rows').includes('星际穿越.2014.2160p'));

  const subCard = api.element('rows').children[0];
  const fileInput = find(subCard, '选择本地字幕文件').children[0];
  const srtBytes = Buffer.from('\uFEFF1\r\n00:00:01,000 --> 00:00:02,000\r\n你好\r\n', 'utf8');
  fileInput.files = [{
    name: '中文字幕.srt',
    size: srtBytes.length,
    arrayBuffer: async () => srtBytes.buffer.slice(srtBytes.byteOffset, srtBytes.byteOffset + srtBytes.byteLength),
  }];
  await find(subCard, '上传并应用字幕').fire();
  assert.equal(uploadedChunks.length, 1);
  assert.ok(committedId && committedId.length === 32);
  assert.ok(api.text('rows').includes('字幕已接收：中文字幕.srt'));
  collectNoInlineAttributes(api.element('rows'));
});
