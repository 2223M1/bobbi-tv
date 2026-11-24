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
