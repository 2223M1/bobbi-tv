'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {boot,calls,find,row}=require('./catalog_test_dom.cjs');

test('shared supplement uses the existing review preview/apply with no new write API',async()=>{
  const ui=await boot();await ui.edit();
  ui.field(0,'操作').value='supplement';ui.field(0,'描述类型').value='movie';
  ui.field(0,'TMDb 编号（仅电影 / 剧集）').value='123';
  ui.field(0,'补充类型').value='interview';ui.field(0,'补充视频名称').value='访谈';
  await find(ui.element('editorRows'),'加入本批修改').fire();
  assert.equal(calls(ui,'catalog_apply').length,0);
  await ui.click('preview');await ui.click('apply');
  const command=calls(ui,'catalog_apply')[0].body.params.commands[0];
  assert.equal(command.action,'supplement');
  assert.deepEqual(command.mapping,{metadata_key:'tmdb:movie:123',parent_file_id:null,parent_revision:null,
    parent_evidence:null,kind:'interview',title:'访谈'});
});

test('custom parent selection freezes exact original revision/evidence for later supplement review',async()=>{
  const parent={...row(0,4),provenance:'manual',mapping:{kind:'custom',title:'家庭视频'},
    file:{...row(0).file,observation_key:'e'.repeat(64)}};
  const ui=await boot({rows:[parent,row(1)]});await ui.edit(0);
  await find(ui.element('editorRows'),'选作补充视频的父版本').fire();await ui.click('back');
  await ui.edit(1);ui.field(0,'操作').value='supplement';
  await find(ui.element('editorRows'),'加入本批修改').fire();await ui.click('preview');
  const mapping=calls(ui,'catalog_preview')[0].body.params.commands[0].mapping;
  assert.equal(mapping.metadata_key,null);assert.equal(mapping.parent_file_id,parent.file.id);
  assert.equal(mapping.parent_revision,4);assert.equal(mapping.parent_evidence,'e'.repeat(64));
  assert.equal(calls(ui,'catalog_apply').length,0);
});

test('supplement detach and undo remain review commands and read navigation never plays',async()=>{
  const ui=await boot();await find(ui.element('rows'),'查看补充视频').fire();
  assert.equal(calls(ui,'catalog_query').at(-1).body.params.query.view,'supplements');
  await ui.edit();ui.field(0,'操作').value='detach_supplement';
  await find(ui.element('editorRows'),'加入本批修改').fire();await ui.click('preview');
  assert.equal(calls(ui,'catalog_preview').at(-1).body.params.commands[0].mapping,null);
  assert.equal(calls(ui,'playback_command').length,0);
});
