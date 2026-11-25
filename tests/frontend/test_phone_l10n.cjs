'use strict';
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const { boot, calls, find, flush, response, row, text } = require('./catalog_test_dom.cjs');

const ROOT = path.resolve(__dirname, '../..');

function loadPoSessionPayload(kodiLocale) {
  const py = process.env.BOBBI_TEST_PYTHON || 'python';
  const script = [
    'import json, sys',
    `sys.path.insert(0, ${JSON.stringify(path.join(ROOT, 'addons/plugin.video.bobbi'))})`,
    `sys.path.insert(0, ${JSON.stringify(path.join(ROOT, 'addons/script.module.bobbi.platform/lib'))})`,
    'import types',
    'xbmc = types.ModuleType("xbmc")',
    `xbmc.executeJSONRPC = lambda req: json.dumps({"result": {"value": ${JSON.stringify(kodiLocale)}}})`,
    'sys.modules["xbmc"] = xbmc',
    'from lib.services.phone_l10n import session_locale_payload',
    'print(json.dumps(session_locale_payload()))',
  ].join('; ');
  const out = execFileSync(py, ['-c', script], { encoding: 'utf8' });
  return JSON.parse(out.trim());
}

test('manage.html and manage.js never use unsafe HTML string sinks', () => {
  const html = fs.readFileSync(path.join(ROOT, 'addons/plugin.video.bobbi/resources/web/manage.html'), 'utf8');
  const js = fs.readFileSync(path.join(ROOT, 'addons/plugin.video.bobbi/resources/web/manage.js'), 'utf8');
  const sinkWord = 'inner' + 'HTML';
  const outerWord = 'outer' + 'HTML';
  assert.equal(html.includes(sinkWord), false);
  assert.equal(js.includes(sinkWord), false);
  assert.equal(js.includes(outerWord), false);
  assert.equal(fs.existsSync(path.join(ROOT, 'addons/plugin.video.bobbi/resources/web/upload.html')), false);
});

test('phone web UI renders authoritative English PO strings and survives live ZH -> EN -> ZH switch without losing queued, preview, receipts, or unsaved inputs', async () => {
  const zhPayload = loadPoSessionPayload('resource.language.zh_cn');
  const enPayload = loadPoSessionPayload('resource.language.en_gb');
  assert.equal(zhPayload.locale, 'zh-CN');
  assert.equal(enPayload.locale, 'en-GB');

  let currentLocalePayload = zhPayload;
  const docElement = { lang: 'zh-CN', setAttribute(k, v) { this[k] = v; } };

  const ui = await boot({
    rows: [row(0, 3), row(1, 5)],
    handlers: {
      '/manage/api/pair': () => response({
        csrf: 'live-csrf',
        scopes: ['catalog_read', 'catalog_review', 'catalog_tasks', 'playback_read'],
        catalog_kind: 'native',
        ...currentLocalePayload,
      }),
      '/manage/api/session': () => response({
        csrf: 'live-csrf',
        scopes: ['catalog_read', 'catalog_review', 'catalog_tasks', 'playback_read'],
        catalog_kind: 'native',
        ...currentLocalePayload,
      }),
    },
  });

  // Attach documentElement onto synthetic test document via sync run
  assert.equal(ui.element('itemsTab').textContent, '作品整理');
  assert.equal(ui.element('preview').textContent, '预览全部修改');
  assert.equal(ui.element('keyword').placeholder, '搜索作品 / 原文件 / 版本备注');
  assert.equal(ui.element('keyword')['aria-label'], '作品关键词');

  // 1. Save one committed receipt first so receipts[] is populated
  await ui.edit(0);
  ui.field(0, '显示名称').value = 'Committed Movie';
  await find(ui.element('editorRows'), '加入本批修改').fire();
  await ui.click('back');
  await ui.click('preview');
  await ui.click('apply');
  assert.match(ui.text('receipts'), /提交回执/);
  assert.equal(calls(ui, 'catalog_apply').length, 1);

  // 2. Stage a second item into queued[] and preview it so batch.phase === 'ready'
  await ui.edit(1);
  ui.field(1, '显示名称').value = 'Queued Series';
  await find(ui.element('editorRows'), '加入本批修改').fire();
  await ui.click('back');
  await ui.click('preview');
  assert.equal(ui.element('apply').disabled, false);
  assert.match(ui.text('batchPreview'), /修改前/);
  assert.match(ui.text('queue'), /Episode 1\.mkv/);

  // 3. Set filter values and open editor on row 0 with unsaved user typing
  ui.element('keyword').value = 'unsaved-filter-keyword';
  ui.element('mediaKind').value = 'tv';
  await ui.edit(0);
  const titleInput = ui.field(0, '显示名称');
  const versionInput = ui.field(0, '版本备注（可选，不作为同源续播证明）');
  const candidateQueryInput = ui.field(0, '候选搜索关键词（仅发送此关键词）');
  titleInput.value = 'My Unsaved Custom Title';
  versionInput.value = 'Director Cut 4K';
  candidateQueryInput.value = 'Custom Search Query';

  const applyCallsBeforeSwitch = calls(ui, 'catalog_apply').length;
  const previewCallsBeforeSwitch = calls(ui, 'catalog_preview').length;

  // 4. Switch TV locale to English and trigger foreground visibility sync
  currentLocalePayload = enPayload;
  ui.visibility(true);
  ui.visibility(false);
  await flush();
  await flush();

  // Chrome, tabs, placeholders, aria-labels, capsule, preview, receipts, and open editor labels are now English!
  assert.equal(ui.element('pageTitle').textContent, 'bobbi TV · Library Organizer');
  assert.equal(ui.element('itemsTab').textContent, 'Organize Works');
  assert.equal(ui.element('sourcesTab').textContent, 'Sources');
  assert.equal(ui.element('jobsTab').textContent, 'Background Jobs');
  assert.equal(ui.element('preview').textContent, 'Preview All Edits');
  assert.equal(ui.element('apply').textContent, 'Confirm / Continue Batch Submit');
  assert.equal(ui.element('keyword').placeholder, 'Search works / files / version notes');
  assert.equal(ui.element('keyword')['aria-label'], 'Work keyword');
  assert.equal(ui.element('mediaKind')['aria-label'], 'Media type');
  assert.equal(ui.element('mediaKind').children[2].textContent, 'TV Series');
  assert.match(ui.text('jobCapsule'), /Background Jobs/);
  assert.match(ui.text('batchPreview'), /Before/);
  assert.match(ui.text('receipts'), /Submission Receipt/);
  assert.notEqual(find(ui.element('editorRows'), 'Display Title'), null);
  assert.notEqual(find(ui.element('editorRows'), 'Add to Batch Queue'), null);

  // Critical invariants: unsaved inputs, filter values, queued[], batch readiness, and receipts are 100% intact, with 0 extra mutations!
  assert.equal(ui.element('keyword').value, 'unsaved-filter-keyword');
  assert.equal(ui.element('mediaKind').value, 'tv');
  assert.equal(titleInput.value, 'My Unsaved Custom Title');
  assert.equal(versionInput.value, 'Director Cut 4K');
  assert.equal(candidateQueryInput.value, 'Custom Search Query');
  assert.match(ui.text('queue'), /Episode 1\.mkv/);
  assert.equal(ui.element('apply').disabled, false);
  assert.equal(calls(ui, 'catalog_apply').length, applyCallsBeforeSwitch);
  assert.equal(calls(ui, 'catalog_preview').length, previewCallsBeforeSwitch);

  // 5. Switch TV locale back to Chinese -> round-trip restores Chinese without losing state, and queued batch still submits cleanly!
  currentLocalePayload = zhPayload;
  ui.visibility(true);
  ui.visibility(false);
  await flush();
  await flush();

  assert.equal(ui.element('pageTitle').textContent, '波比 TV · 片库整理');
  assert.equal(ui.element('itemsTab').textContent, '作品整理');
  assert.equal(ui.element('preview').textContent, '预览全部修改');
  assert.match(ui.text('receipts'), /提交回执/);
  assert.equal(titleInput.value, 'My Unsaved Custom Title');
  assert.equal(versionInput.value, 'Director Cut 4K');
  assert.equal(ui.element('apply').disabled, false);

  await ui.click('apply');
  assert.equal(calls(ui, 'catalog_apply').length, applyCallsBeforeSwitch + 1);
  void docElement;
});
