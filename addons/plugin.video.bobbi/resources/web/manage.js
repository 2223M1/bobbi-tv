/* No bearer in storage, no arbitrary runtime RPC and no HTML from filenames. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const labels = {queued:'排队中',running:'扫描中',completed:'扫描完成',failed:'未完整完成',
    canceled:'已取消',interrupted:'已中断',unmatched:'待匹配',ambiguous:'身份不明确',
    proposed:'待确认建议',confirmed:'人工确认',ignored:'已忽略',ready:'可提交',
    conflict:'版本冲突，请刷新',applied:'已保存',cancel_requested:'已请求取消，等待后台确认'};
  let csrf = '', tab = 'items', offset = 0, nextOffset = null, source = null;
  let pageStarts = [0], pageIndex = 0;
  let queued = [], previewed = false, requestId = null, busy = false;
  function node(tag, text, className) {
    const value = document.createElement(tag);
    if (text !== undefined) value.textContent = String(text);
    if (className) value.className = className;
    return value;
  }
  function status(text, error=false) {
    byId('status').textContent = text;
    byId('status').classList.toggle('error', error);
  }
  function id() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2,'0')).join('');
  }
  async function post(path, body) {
    const response = await fetch(path, {method:'POST',credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json','X-Bobbi-CSRF':csrf},body:JSON.stringify(body)});
    const value = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        csrf = ''; byId('workspace').classList.add('hidden');
        throw new Error('授权已失效或账号已变化，请在电视重新开启并扫码。');
      }
      if (value.error === 'PREVIEW_REQUIRED') throw new Error('预览已过期，请重新预览后再提交。');
      if (value.error === 'CATALOG_REPLY_LIMIT') throw new Error('本批预览信息过长，请减少条目后重新预览，尚未提交修改。');
      throw new Error('操作未确认，请刷新状态后重试（' + (value.error || response.status) + '）。');
    }
    return value;
  }
  const rpc = (action,params={}) => post('/manage/api',{action,params});
  function resetPage() { offset=0;pageStarts=[0];pageIndex=0; }
  function button(text, action) {
    const result = node('button',text);
    result.addEventListener('click',() => guarded(action));
    return result;
  }
  async function guarded(action) {
    if (busy) return;
    busy = true;
    try { await action(); }
    catch(error) { status(error.message || '连接中断，结果未确认。请重新读取状态。',true); }
    finally { busy = false; }
  }
  function field(card, title, type='text', value='') {
    const label = node('label',title), input = node('input');
    input.type = type; input.value = value == null ? '' : value;
    input.maxLength = 240; label.append(input); card.append(label); return input;
  }
  function select(card, title, choices, value) {
    const label = node('label',title), input = node('select');
    choices.forEach(([key,text]) => {const option=node('option',text);option.value=key;input.append(option);});
    input.value=value;label.append(input);card.append(label);return input;
  }
  function changedBatch() {
    previewed=false;requestId=null;byId('apply').disabled=true;byId('previewRows').replaceChildren();
    byId('queue').replaceChildren(...queued.map((q,index) => node('p',(index+1)+'. '+q.name+' · '+q.command.action)));
  }
  function itemCard(item) {
    const card=node('article',undefined,'card');card.append(node('h2',item.file.name));
    card.append(node('small',item.file.parent+(item.file.truncated?'（显示已截短）':'')));
    card.append(node('p',(labels[item.state]||item.state)+' · 修订 '+item.revision));
    if (item.available === false) card.append(node('p','当前来源未发现此文件；本地描述和观看记录仍保留。','error'));
    if (item.candidates && item.candidates.length) card.append(node('pre',JSON.stringify(item.candidates,null,2),'muted'));
    const current=item.mapping||{};
    const action=select(card,'操作',[['confirm','设置作品 / 自定义名称'],['unbind','解除绑定'],['ignore','忽略此项'],['undo','撤回上次修改']],'confirm');
    const kind=select(card,'描述类型',[['custom','自定义名称'],['movie','电影 TMDb'],['tv','剧集 TMDb']],current.kind||'custom');
    const title=field(card,'显示名称','text',current.title||item.file.name);
    const tmdb=field(card,'TMDb 编号（仅电影 / 剧集）','number',current.tmdb_id);
    const season=field(card,'季号（剧集，特别篇为 0）','number',current.season);
    const episode=field(card,'集号（剧集）','number',current.episode);
    const version=field(card,'版本备注（可选，不作为同源续播证明）','text',current.version);
    card.append(button('加入本批修改',() => {
      if (queued.length>=5 && !queued.some(q=>q.command.file_id===item.file.id)) throw new Error('每批最多 5 项。');
      let mapping=null;
      if (action.value==='confirm') {
        mapping={kind:kind.value,title:title.value.trim(),tmdb_id:kind.value==='custom'?null:Number(tmdb.value),
          season:kind.value==='tv'?Number(season.value):null,episode:kind.value==='tv'?Number(episode.value):null,
          version:version.value.trim()||null};
        if (!mapping.title || kind.value!=='custom' && !tmdb.value || kind.value==='tv' && (!season.value || !episode.value)) throw new Error('请填写所选描述需要的编号与季集。');
      }
      queued=queued.filter(q=>q.command.file_id!==item.file.id);
      queued.push({name:item.file.name,command:{file_id:item.file.id,expected_revision:item.revision,action:action.value,mapping}});
      changedBatch();status('已加入本批，尚未写入。请预览后确认。');
    }));return card;
  }
  function jobCard(job) {
    const card=node('article',undefined,'card');card.append(node('h2',labels[job.state]||job.state));
    const counts=job.counts||{};
    card.append(node('p','已扫描 '+(counts.scanned||0)+' 项 · 已发现 '+(counts.discovered||0)+' 个视频'));
    card.append(node('small',job.result_summary||''));
    if (job.cancel_requested && ['queued','running'].includes(job.state)) card.append(node('p','已请求取消，等待后台确认。'));
    else if (['queued','running'].includes(job.state)) card.append(button('请求取消本次扫描',async()=>{
      if (!confirm('仅取消本次扫描，已有索引和云端文件保留。继续？')) return;
      const receipt=await rpc('catalog_cancel',{task_id:job.task_id});
      status(receipt.state==='canceled'?'后台已确认取消。':'已请求取消，尚未确认停止。');await load();
    }));return card;
  }
  function sourceCard(row) {
    const card=node('article',undefined,'card');card.append(node('h2',row.name));
    card.append(button('查看此来源',async()=>{source=row.id;tab='items';resetPage();await load();}));
    card.append(button('重新完整扫描',async()=>{
      if (!confirm('重新扫描此已登记目录？不修改云端文件。')) return;
      await rpc('catalog_scan',{source_id:row.id});tab='jobs';resetPage();await load();
    }));return card;
  }
  function historyCard(row) {
    const card=node('article',undefined,'card');card.append(node('h2',row.name));
    function clock(seconds) {const value=Math.max(0,Math.floor(seconds));return Math.floor(value/60)+':'+String(value%60).padStart(2,'0');}
    card.append(node('p','已观看 '+clock(row.position)+(row.duration==null?' · 总时长未知':' / '+clock(row.duration))));
    card.append(node('small','仅展示当前账号的继续观看摘要，请在电视选择续播。'));
    return card;
  }
  async function load() {
    status('正在读取电视上的当前状态…');
    byId('filters').classList.toggle('hidden',tab!=='items');
    const params={offset,limit:5};
    if (tab==='items') {if(source)params.source=source;if(byId('state').value)params.state=byId('state').value;}
    const value=await rpc('catalog_'+tab,params);
    nextOffset=value.next_offset;
    const rows=value.items||[];
    byId('rows').replaceChildren(...rows.map(tab==='items'?itemCard:tab==='jobs'?jobCard:tab==='history'?historyCard:sourceCard));
    if (!rows.length) byId('rows').append(node('p','此页暂无记录。扫描未完成时仅显示已提交部分。'));
    byId('previous').disabled=offset===0;byId('next').disabled=nextOffset==null;
    status('已读取当前状态 · 第 '+(pageIndex+1)+' 页。关闭浏览器不会取消后台任务。');
  }
  ['items','sources','jobs','history'].forEach(name=>byId(name+'Tab').addEventListener('click',()=>guarded(async()=>{tab=name;resetPage();await load();})));
  byId('refresh').addEventListener('click',()=>guarded(load));
  byId('state').addEventListener('change',()=>guarded(async()=>{resetPage();await load();}));
  byId('clearSource').addEventListener('click',()=>guarded(async()=>{source=null;resetPage();await load();}));
  byId('next').addEventListener('click',()=>guarded(async()=>{if(nextOffset!=null){pageStarts=pageStarts.slice(0,pageIndex+1);pageStarts.push(nextOffset);pageIndex++;offset=nextOffset;await load();}}));
  byId('previous').addEventListener('click',()=>guarded(async()=>{pageIndex=Math.max(0,pageIndex-1);offset=pageStarts[pageIndex];await load();}));
  byId('clear').addEventListener('click',()=>{queued=[];changedBatch();});
  byId('preview').addEventListener('click',()=>guarded(async()=>{
    if (!queued.length) throw new Error('请先把要修改的条目加入本批。');
    const value=await rpc('catalog_preview',{commands:queued.map(q=>q.command)});
    byId('previewRows').replaceChildren(...value.items.map((row,index)=>{
      const card=node('div',undefined,'card');card.append(node('h3',queued[index].name+' · '+(labels[row.status]||row.status)));
      card.append(node('pre','修改前\n'+JSON.stringify(row.before,null,2)+'\n修改后\n'+JSON.stringify(row.after,null,2)));
      return card;
    }));
    previewed=value.items.length===queued.length && value.items.every(r=>r.status==='ready');
    requestId=id();byId('apply').disabled=!previewed;
    status(previewed?'请核对每项预览，再点击确认提交。':'本批包含冲突或无效条目，请刷新后重新选择。',!previewed);
  }));
  byId('apply').addEventListener('click',()=>guarded(async()=>{
    if (!previewed || !requestId || !confirm('确认按预览修改本批本地描述？')) return;
    const value=await rpc('catalog_apply',{request_id:requestId,commands:queued.map(q=>q.command)});
    const messages=value.items.map((row,index)=>queued[index].name+' · '+(labels[row.status]||row.status));
    const all=value.items.length===queued.length && value.items.every(r=>r.status==='applied');
    byId('previewRows').replaceChildren(...messages.map(text=>node('p',text)));
    previewed=false;byId('apply').disabled=true;
    status(all?'本批已保存。刷新可读取新修订。':'本批部分修改未保存，请查看逐项结果并刷新。',!all);
  }));
  byId('revoke').addEventListener('click',()=>guarded(async()=>{
    await post('/manage/api/revoke',{});csrf='';byId('workspace').classList.add('hidden');status('授权已结束，后台任务保持原状态。');
  }));
  guarded(async()=>{
    const code=location.hash.slice(1);
    history.replaceState(null,'',location.pathname);
    const session=await post(code?'/manage/api/pair':'/manage/api/session',code?{code}:{});
    csrf=session.csrf;byId('workspace').classList.remove('hidden');await load();
  });
})();
