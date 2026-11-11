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
  const REQUEST_MS = 15000, PREVIEW_MS = 110000, MAX_BODY = 8192;
  let queued = [], batch = null, batchGeneration = 0, busy = null;
  let authGeneration = 0, authClosed = false;
  let operation = null, viewGeneration = 0, candidateGeneration = 0, candidateRequest = null, candidateTimer = null;
  let pollTimer=null, pollUntil=0, pollDelay=5000, jobsActive=true;
  const requests = new Set(), receipts = [];
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
  function failure(code, message) {const error=new Error(message);error.code=code;return error;}
  function utf8Size(text) {return encodeURIComponent(text).replace(/%[0-9A-F]{2}|[^%]/g,'x').length;}
  function frozen(value) {
    if (value && typeof value==='object') {Object.values(value).forEach(frozen);Object.freeze(value);}
    return value;
  }
  function snapshot(selected=queued, requestId=id()) {
    const entries=JSON.parse(JSON.stringify(selected));
    const value=frozen({entries,commands:entries.map(q=>q.command),requestId,generation:batchGeneration,authorization:authGeneration});
    if (utf8Size(JSON.stringify({action:'catalog_apply',params:{request_id:requestId,commands:value.commands}}))>MAX_BODY)
      throw new Error('本批完整请求超过 8192 字节，请减少条目或缩短描述。');
    return value;
  }
  function chunks(entries) {
    const result=[];let current=[];
    for(const entry of entries) {
      let fits=current.length<5;
      if(fits) {try{snapshot([...current,entry]);}catch(error){fits=false;}}
      if(!fits&&current.length){result.push(snapshot(current));current=[];}
      snapshot([entry]);current.push(entry);
    }
    if(current.length)result.push(snapshot(current));
    return result;
  }
  function cancelCandidates() {
    candidateGeneration++;clearTimeout(candidateTimer);candidateTimer=null;
    if(candidateRequest)candidateRequest.abort();candidateRequest=null;
  }
  function unknown() {return batch && ['unknown','unknown_expired'].includes(batch.phase);}
  function controls() {
    const locked=Boolean(busy)||authClosed;
    byId('clear').disabled=locked||Boolean(unknown());
    byId('preview').disabled=locked||Boolean(unknown());
    byId('apply').disabled=locked||Boolean(operation&&operation.canceled)||!(batch&&batch.phase==='ready'||operation&&operation.phase==='paused');
    byId('retry').disabled=locked||!batch||batch.phase!=='unknown';
    byId('reviewAgain').disabled=locked||!batch||batch.phase!=='unknown_expired';
    byId('cancelPlan').disabled=authClosed||!operation||operation.canceled||operation.index>=operation.chunks.length;
  }
  function closeAuthorization() {
    authGeneration++;authClosed=true;csrf='';batch=null;busy=null;
    cancelCandidates();if(operation)operation.canceled=true;
    clearTimeout(pollTimer);pollTimer=null;
    requests.forEach(request=>request.abort());
    byId('workspace').classList.add('hidden');controls();
  }
  async function post(path, body, options={}) {
    const generation=options.generation===undefined?authGeneration:options.generation;
    if (generation!==authGeneration || authClosed&&!options.control) throw failure('STALE','授权已结束。');
    const encoded=JSON.stringify(body);
    if (utf8Size(encoded)>MAX_BODY) throw failure('REQUEST_TOO_LARGE','完整请求超过 8192 字节，请减少条目。');
    const controller=options.controller||new AbortController();requests.add(controller);
    let timedOut=false, timer;
    const canceled=new Promise((resolve,reject)=>{
      controller.signal.addEventListener('abort',()=>reject(failure(timedOut?'TIMEOUT':'STALE',
        timedOut?'请求超时，尚未取得结果。':'授权已结束。')),{once:true});
      timer=setTimeout(()=>{timedOut=true;controller.abort();},REQUEST_MS);
    });
    try {
      const result=await Promise.race([canceled,(async()=>{
        const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
          headers:{'Content-Type':'application/json','X-Bobbi-CSRF':options.token===undefined?csrf:options.token},body:encoded});
        return {response,value:await response.json()};
      })()]);
      if (generation!==authGeneration) throw failure('STALE','授权已结束。');
      const {response,value}=result;
      if (!response.ok) {
        if (response.status===401) {
          closeAuthorization();status('授权已失效或账号已变化，请在电视重新开启并扫码。',true);
          throw failure('STALE','授权已失效或账号已变化。');
        }
        if (value.error==='PREVIEW_REQUIRED') throw failure(value.error,'预览已过期，请重新预览后再提交。');
        if (value.error==='CATALOG_REPLY_LIMIT') throw failure(value.error,'本批信息过长，请减少条目后重新预览。');
        throw failure(value.error||String(response.status),'操作未确认，请刷新状态后重试（'+(value.error||response.status)+'）。');
      }
      return value;
    } catch(error) {
      if (generation!==authGeneration) throw failure('STALE','授权已结束。');
      throw error;
    } finally {clearTimeout(timer);requests.delete(controller);}
  }
  const rpc = (action,params={}) => post('/manage/api',{action,params});
  function resetPage() { offset=0;pageStarts=[0];pageIndex=0; }
  function button(text, action) {
    const result = node('button',text);
    result.addEventListener('click',() => guarded(action));
    return result;
  }
  async function guarded(action) {
    if (busy || authClosed) return;
    const lease={generation:authGeneration};busy=lease;controls();
    try { await action(); }
    catch(error) { if (lease.generation===authGeneration && error.code!=='STALE') status(error.message || '连接中断，结果未确认。请重新读取状态。',true); }
    finally { if(busy===lease)busy=null;controls(); }
  }
  function field(card, title, type='text', value='') {
    const label = node('label',title), input = node('input');
    input.type = type; input.value = value == null ? '' : String(value);
    input.maxLength = 240; label.append(input); card.append(label); return input;
  }
  function select(card, title, choices, value) {
    const label = node('label',title), input = node('select');
    choices.forEach(([key,text]) => {const option=node('option',text);option.value=key;input.append(option);});
    input.value=value;label.append(input);card.append(label);return input;
  }
  function changedBatch() {
    batchGeneration++;batch=null;operation=null;byId('batchPreview').replaceChildren();byId('planStatus').textContent='';controls();
    byId('queue').replaceChildren(...queued.map((q,index) => node('p',(index+1)+'. '+q.name+' · '+q.command.action)));
  }
  function titleHint(name) {return name.replace(/\.[a-z0-9]{2,5}$/i,'').split(/(?:[ ._-]s\d+[ ._-]*e\d+|[ ._-]\d{1,2}x\d+)/i)[0].replace(/\[[^\]]*\]|\([^)]*\)|\b(?:19|20)\d{2}\b/g,' ').replace(/[._\s-]+/g,' ').trim().slice(0,120);}
  function candidateEditor(card,item,fields) {
    const section=node('details');section.append(node('summary','搜索作品候选 / 同目录分集整理'));
    const evidence=(item.candidates||[])[0]||{};
    const query=field(section,'候选搜索关键词（仅发送此关键词）','text',titleHint(item.file.name));query.maxLength=120;
    const year=field(section,'候选年份（可选，重制版需核对）','number',evidence.year);
    const results=node('div'), message=node('p');let selected=null;
    const page=viewGeneration;
    async function searchCandidates() {
      if(authClosed||page!==viewGeneration)return;
      cancelCandidates();const generation=candidateGeneration,authorization=authGeneration;
      const controller=new AbortController();candidateRequest=controller;
      results.replaceChildren();message.textContent='正在搜索公开作品信息…';selected=null;
      try {
        const value=await post('/manage/api',{action:'catalog_candidates',params:{query:query.value.trim(),year:year.value?Number(year.value):null,
          media_kind:fields.kind.value==='custom'?null:fields.kind.value}},{controller});
        if(generation!==candidateGeneration||authorization!==authGeneration||page!==viewGeneration)return;
        message.textContent=(value.items||[]).length?'搜索结果只是候选，请核对年份、类型和季集。':'没有找到候选，可修改关键词或使用手动编号。';
        for(const candidate of value.items||[]) {
          const row=node('article',undefined,'card');
          row.append(node('p',(candidate.media_kind==='tv'?'剧集':'电影')+' · '+candidate.title+' · '+(candidate.year||'年份未知')),
            node('small',(candidate.original_title||'')+' · '+candidate.basis));
          if(candidate.poster_path&&/^\/[A-Za-z0-9_-]{1,100}\.(jpg|png)$/.test(candidate.poster_path)) {
            const poster=node('img');poster.src='https://image.tmdb.org/t/p/w185'+candidate.poster_path;poster.alt=candidate.title;poster.loading='lazy';poster.referrerPolicy='no-referrer';poster.width=92;row.append(poster);
          }
          row.append(button('采用此候选（尚未保存）',()=>{
            if(page!==viewGeneration||generation!==candidateGeneration)throw new Error('候选已过期，请重新搜索。');
            selected=candidate;fields.kind.value=candidate.media_kind;fields.title.value=candidate.title;fields.tmdb.value=candidate.tmdb_id;
            if(candidate.media_kind==='tv') {fields.season.value=evidence.season==null?'':evidence.season;fields.episode.value=evidence.episode==null?'':evidence.episode;}
            message.textContent='已填入候选，尚未修改记录。请核对季集，再加入修改并预览。';
          }));results.append(row);
        }
      } catch(error) {if(generation===candidateGeneration&&page===viewGeneration&&!authClosed)message.textContent='候选搜索未完成，可重试或使用手动编号。';}
      finally {if(candidateRequest===controller)candidateRequest=null;}
    }
    const searchButton=node('button','搜索作品候选');searchButton.addEventListener('click',searchCandidates);
    for(const input of [query,year])input.addEventListener('input',()=>{
      cancelCandidates();selected=null;results.replaceChildren();message.textContent='关键词已变化，旧候选失效。';
      candidateTimer=setTimeout(searchCandidates,350);
    });
    section.append(searchButton,message,results,button('查看同目录逐集整理建议',async()=>{
      if(!selected||selected.media_kind!=='tv')throw new Error('请先搜索并采用一个剧集候选。');
      if(unknown())throw new Error('请先核对原提交结果。');
      await groupEditor(item,selected);
    }));card.append(section);
  }
  async function groupEditor(anchor,candidate) {
    const deadline=Date.now()+60000, rows=[];let next=0,identity=null,revision=null;
    const params={file_id:anchor.file.id,limit:5};if(source)params.source_id=source;
    do {
      if(rows.length>=100||Date.now()>=deadline)throw new Error('同目录条目超出本轮 100 项或等待期限，请缩小来源后分轮整理。');
      const value=await rpc('catalog_group',{...params,offset:next,...(revision===null?{}:{projection_revision:revision})});
      if(Date.now()>=deadline)throw new Error('同目录读取已到等待期限，请重新获取建议。');
      if(identity!==null&&(identity!==value.group_id||revision!==value.projection_revision))throw new Error('目录记录已变化，请重新获取建议。');
      identity=value.group_id;revision=value.projection_revision;params.source_id=value.source_id;
      rows.push(...value.items);const previous=next;next=value.next_offset;
      if(next!==null&&(!Number.isInteger(next)||next<=previous))throw new Error('目录分页未完整，请重新读取。');
    }while(next!==null);
    const panel=byId('groupRows');panel.replaceChildren(node('h2','同目录逐项建议 · '+candidate.title),
      node('p','同目录不证明同一作品。请核对每个文件，排除重制版、合集和多集文件；特别篇保留 S00。只有勾选项加入计划。'));
    const editors=[];
    for(const item of rows) {
      const evidence=(item.candidates||[])[0]||{},mapping=item.mapping||{},card=node('article',undefined,'card');
      card.append(node('h3',item.file.name),node('small','当前修订 '+item.revision+' · 原描述 '+(mapping.title||'未绑定')));
      const keep=field(card,'加入本轮','checkbox');
      keep.checked=!item.file.truncated&&item.state!=='ambiguous'&&item.available!==false&&evidence.season!=null&&evidence.episode!=null&&
        titleHint(item.file.name).toLowerCase()===titleHint(anchor.file.name).toLowerCase()&&
        (!evidence.year||!candidate.year||evidence.year===candidate.year)&&(!mapping.tmdb_id||mapping.kind==='tv'&&mapping.tmdb_id===candidate.tmdb_id);
      const season=field(card,'拟绑定季号（特别篇为 0）','number',evidence.season),episode=field(card,'拟绑定集号（多集文件请排除）','number',evidence.episode);
      const version=field(card,'版本备注（可选，不作为续播证明）','text',mapping.version);version.maxLength=80;
      if(!keep.checked)card.append(node('p','存在未知季集、年份 / 类型差异或身份疑点，默认未选。请人工核对。','error'));
      editors.push({item,keep,season,episode,version});panel.append(card);
    }
    panel.append(button('将勾选项加入分批预览',()=>{
      if(unknown())throw new Error('请先核对原提交结果。');
      const entries=[];
      for(const editor of editors.filter(row=>row.keep.checked)) {
        if(!editor.season.value||!editor.episode.value||!Number.isInteger(Number(editor.season.value))||Number(editor.season.value)<0||!Number.isInteger(Number(editor.episode.value))||Number(editor.episode.value)<1)throw new Error('勾选项必须明确季号和集号；多集文件请排除。');
        entries.push({name:editor.item.file.name,command:{file_id:editor.item.file.id,expected_revision:editor.item.revision,action:'confirm',
          mapping:{kind:'tv',title:candidate.title,tmdb_id:candidate.tmdb_id,season:Number(editor.season.value),episode:Number(editor.episode.value),version:editor.version.value.trim()||null}}});
      }
      if(!entries.length)throw new Error('请至少勾选一项。');
      queued=entries;changedBatch();status('已加入 '+entries.length+' 项建议。请预览全部逐项修改后，再确认分批保存。');
    }));status('已读取 '+rows.length+' 个同目录文件，尚未确认作品或提交修改。');
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
    version.maxLength=80;
    card.append(button('加入本批修改',() => {
      if (unknown()) throw new Error('上一批提交结果待核对，请先核对原提交，不能覆盖未知结果。');
      if (queued.length>=100 && !queued.some(q=>q.command.file_id===item.file.id)) throw new Error('每轮最多 100 项，请分轮整理。');
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
    }));
    candidateEditor(card,item,{kind,title,tmdb,season,episode,version});
    return card;
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
  function scheduleJobs(reset=false,failed=false) {
    clearTimeout(pollTimer);pollTimer=null;
    if(reset){pollUntil=Date.now()+120000;pollDelay=5000;}
    if(failed)pollDelay=Math.min(30000,pollDelay*2);else if(!busy)pollDelay=5000;
    if(authClosed||tab!=='jobs'||document.hidden||!jobsActive||Date.now()+pollDelay>pollUntil)return;
    pollTimer=setTimeout(async()=>{
      pollTimer=null;
      if(authClosed||tab!=='jobs'||document.hidden||Date.now()>=pollUntil)return;
      if(busy){scheduleJobs();return;}
      await guarded(()=>load(true));
    },pollDelay);
  }
  async function load(automatic=false) {
    clearTimeout(pollTimer);pollTimer=null;
    viewGeneration++;cancelCandidates();byId('groupRows').replaceChildren();
    status('正在读取电视上的当前状态…');
    byId('filters').classList.toggle('hidden',tab!=='items');
    const params={offset,limit:5};
    if (tab==='items') {if(source)params.source=source;if(byId('state').value)params.state=byId('state').value;}
    const currentTab=tab;let value;
    try {value=await rpc('catalog_'+currentTab,params);}
    catch(error) {if(currentTab==='jobs'){jobsActive=true;scheduleJobs(!automatic,true);}throw error;}
    nextOffset=value.next_offset;
    const rows=value.items||[];
    byId('rows').replaceChildren(...rows.map(currentTab==='items'?itemCard:currentTab==='jobs'?jobCard:currentTab==='history'?historyCard:sourceCard));
    if (!rows.length) byId('rows').append(node('p','此页暂无记录。扫描未完成时仅显示已提交部分。'));
    byId('previous').disabled=offset===0;byId('next').disabled=nextOffset==null;
    status('已读取当前状态 · 第 '+(pageIndex+1)+' 页。关闭浏览器不会取消后台任务。');
    if(currentTab==='jobs') {jobsActive=rows.some(row=>['queued','running'].includes(row.state));pollDelay=5000;scheduleJobs(!automatic);}
  }
  ['items','sources','jobs','history'].forEach(name=>byId(name+'Tab').addEventListener('click',()=>guarded(async()=>{tab=name;resetPage();await load();})));
  byId('refresh').addEventListener('click',()=>guarded(load));
  byId('state').addEventListener('change',()=>guarded(async()=>{resetPage();await load();}));
  byId('clearSource').addEventListener('click',()=>guarded(async()=>{source=null;resetPage();await load();}));
  byId('next').addEventListener('click',()=>guarded(async()=>{if(nextOffset!=null){pageStarts=pageStarts.slice(0,pageIndex+1);pageStarts.push(nextOffset);pageIndex++;offset=nextOffset;await load();}}));
  byId('previous').addEventListener('click',()=>guarded(async()=>{pageIndex=Math.max(0,pageIndex-1);offset=pageStarts[pageIndex];await load();}));
  byId('clear').addEventListener('click',()=>{
    if(busy||authClosed||unknown())return;
    queued=[];changedBatch();status('本批已清空，重新选择后请重新预览。已提交回执仍保留。');
  });
  byId('preview').addEventListener('click',()=>guarded(async()=>{
    if (unknown()) throw new Error('请先核对上一批提交结果。');
    if (!queued.length) throw new Error('请先把要修改的条目加入本批。');
    const plan={chunks:chunks(queued),index:0,phase:'previewing',canceled:false,results:new Map(),sent:new Set(),total:queued.length};
    operation=plan;const cards=[];let ready=true;const deadline=Date.now()+90000;
    try {
      for(const original of plan.chunks) {
        if(plan.canceled||Date.now()>=deadline)throw new Error('本轮预览已停止或超时，请重新预览。');
        batch={snapshot:original,phase:'previewing'};
        const value=await rpc('catalog_preview',{commands:original.commands});
        if(Date.now()>=deadline)throw new Error('本轮预览已到等待期限，请重新预览。');
        if(!batch||batch.snapshot!==original||original.generation!==batchGeneration)return;
        for(const [index,row] of (value.items||[]).entries()) {
          const card=node('div',undefined,'card');card.append(node('h3',(original.entries[index]||{name:'未知条目'}).name+' · '+(labels[row.status]||row.status)));
          card.append(node('pre','修改前\n'+JSON.stringify(row.before,null,2)+'\n修改后\n'+JSON.stringify(row.after,null,2)));cards.push(card);
        }
        ready=ready&&Array.isArray(value.items)&&value.items.length===original.entries.length&&value.items.every(row=>row.status==='ready');
      }
    } catch(error) {if(batch)batch.phase='editing';plan.phase='editing';throw error;}
    if(plan.canceled) {batch.phase='editing';status('预览已取消，请重新预览。');return;}
    byId('batchPreview').replaceChildren(...cards);
    batch={snapshot:plan.chunks[0],phase:ready?'ready':'editing',previewUntil:Date.now()+PREVIEW_MS};
    plan.phase=ready?'ready':'editing';
    status(ready?'请核对全部 '+queued.length+' 项预览，将分 '+plan.chunks.length+' 批保存。已保存批次不会因后续冲突自动回滚。':'本轮包含冲突或无效条目，请刷新后重新选择。',!ready);
  }));
  function showReceipt(original, rows, indexed=false) {
    const indexedRows=batch.knownRows||new Map();
    rows.forEach((row,index)=>{
      const key=indexed?row.index:index;
      if(Number.isInteger(key)&&key>=0&&key<original.entries.length&&['applied','conflict','failed'].includes(row.status))indexedRows.set(key,row);
    });
    batch.knownRows=indexedRows;
    const messages=original.entries.map((entry,index)=>{
      const row=indexedRows.get(index);
      return entry.name+' · '+(row?(row.status==='failed'?'未保存':labels[row.status]||row.status)+(row.reason?'（'+row.reason+'）':''):'提交结果待核对');
    });
    const complete=original.entries.every((entry,index)=>indexedRows.has(index));
    const all=complete&&original.entries.every((entry,index)=>indexedRows.get(index).status==='applied');
    const card=node('article',undefined,'card');card.append(node('h3','提交回执'),...messages.map(text=>node('p',text)));
    const old=receipts.findIndex(receipt=>receipt.requestId===original.requestId);
    if(old>=0)receipts.splice(old,1);
    receipts.unshift({requestId:original.requestId,card});receipts.splice(20);
    byId('receipts').replaceChildren(...receipts.map(receipt=>receipt.card));
    byId('batchPreview').replaceChildren();
    batch.phase=complete?(all?'applied':'partial'):'unknown';
    if(operation)operation.results.set(original.requestId,indexedRows);
    planProgress();
    status(all?'本批已保存。刷新可读取新修订。':complete?'本批部分修改未保存，请查看逐项结果并刷新。':'本批仍有提交结果待核对，已知回执已保留。',!all);
  }
  async function submit(original) {
    const wasUnknown=batch.phase==='unknown';
    batch.phase='submitting';controls();
    if(operation)operation.sent.add(original.requestId);
    try {
      const requestId=original.requestId;
      const value=await rpc('catalog_apply',{request_id:requestId,commands:original.commands});
      if(batch&&batch.snapshot===original)showReceipt(original,Array.isArray(value.items)?value.items:[]);
    } catch(error) {
      if(error.code==='STALE'||!batch||batch.snapshot!==original)return;
      if(error.code==='PREVIEW_REQUIRED') {
        batch.phase=wasUnknown?'unknown_expired':'editing';
        if(!wasUnknown&&operation)operation.sent.delete(original.requestId);
        planProgress();
        status(wasUnknown?'原提交尚未核对，预览授权已过期。请读取当前修订人工核对，不能盲目重新提交。':'预览已过期，本次提交未获准。请重新预览后再确认。',true);
        return;
      }
      batch.phase='unknown';
      planProgress();
      status('提交结果待核对。网络超时或中断不代表后台未保存；原提交编号与内容已保留，请核对原提交。',true);
    }
  }
  function planProgress() {
    if(!operation)return;
    let saved=0,unchecked=0,unstarted=0,failed=0;
    for(const chunk of operation.chunks) {
      const results=operation.results.get(chunk.requestId)||new Map();
      chunk.entries.forEach((entry,index)=>{
        const row=results.get(index);
        if(row&&row.status==='applied')saved++;
        else if(row)failed++;
        else if(operation.sent.has(chunk.requestId))unchecked++;
        else unstarted++;
      });
    }
    byId('planStatus').textContent='已保存 '+saved+'/'+operation.total+'，待核对 '+unchecked+'，未保存 '+failed+'，未开始 '+unstarted+(operation.canceled?'。已停止后续批次。':'。');
  }
  async function runPlan() {
    const plan=operation,deadline=Date.now()+90000;plan.phase='saving';
    while(plan.index<plan.chunks.length&&!plan.canceled) {
      if(Date.now()>=deadline){plan.phase='paused';status('本轮已到等待期限，已保存结果保留。可继续后续批次。');return;}
      const original=plan.chunks[plan.index];
      if(!batch||batch.snapshot!==original||batch.phase!=='ready') {
        batch={snapshot:original,phase:'previewing'};
        let value;
        try {value=await rpc('catalog_preview',{commands:original.commands});}
        catch(error) {plan.phase='paused';if(batch)batch.phase='editing';throw error;}
        if(plan.canceled)break;
        if(!Array.isArray(value.items)||value.items.length!==original.entries.length||!value.items.every(row=>row.status==='ready')) {
          batch.phase='editing';plan.phase='conflict';status('后续批次修订已变化，已停止保存。此前真实回执保留，请重新选择冲突项。',true);return;
        }
        batch.phase='ready';batch.previewUntil=Date.now()+PREVIEW_MS;
      }
      await submit(original);
      if(authClosed)return;
      if(batch.phase!=='applied'){plan.phase=batch.phase;return;}
      plan.index++;
    }
    plan.phase=plan.canceled?'canceled':'complete';planProgress();
    if(plan.canceled)status('已停止未开始的批次。已发提交及其真实回执保留。');
  }
  byId('apply').addEventListener('click',()=>guarded(async()=>{
    if(!operation||operation.canceled||!(batch&&batch.phase==='ready'||operation.phase==='paused')||!confirm('确认按逐项预览分批修改本地描述？已保存批次不会自动回滚。'))return;
    await runPlan();
  }));
  byId('cancelPlan').addEventListener('click',()=>{
    if(!operation)return;operation.canceled=true;planProgress();controls();
    status('已请求停止后续批次。正在进行的提交仍须等待或核对真实回执，不会被撤回。');
  });
  byId('retry').addEventListener('click',()=>guarded(async()=>{
    if(!batch||batch.phase!=='unknown')return;
    const original=batch.snapshot, value=await rpc('catalog_receipt',{request_id:original.requestId});
    if(value.status==='found') {
      showReceipt(original,Array.isArray(value.items)?value.items:[],true);
      if(batch.phase!=='unknown'){resumePlan();return;}
    }
    if(Date.now()<batch.previewUntil) {
      status('正在使用原提交编号与原内容核对；不会新建提交编号。');
      await submit(original);
      resumePlan();
    } else {
      batch.phase='unknown_expired';
      status('原回执不可用或不完整，不能判断是否已保存。请读取当前修订后人工核对；不会自动重新提交。',true);
    }
  }));
  function resumePlan() {
    if(operation&&batch&&batch.phase==='applied'&&operation.chunks[operation.index]===batch.snapshot) {
      operation.index++;operation.phase=operation.index<operation.chunks.length?'paused':'complete';
      if(operation.phase==='paused'&&!operation.canceled)status('原提交已核对。后续批次尚未开始，点击确认提交继续。');
      planProgress();
    }
  }
  byId('reviewAgain').addEventListener('click',()=>guarded(async()=>{
    if(!batch||batch.phase!=='unknown_expired'||!confirm('原提交结果仍未确认。读取当前修订后逐项人工核对，确认需要修改的内容再重新预览。继续？'))return;
    const original=batch.snapshot;
    showReceipt(original,[]);queued=[];changedBatch();await load();
    status('已重新读取当前修订。原提交结果未确认，请人工核对后重新选择和预览；修订变化不证明原提交成功。',true);
  }));
  byId('revoke').addEventListener('click',async()=>{
    if(authClosed)return;
    const token=csrf;closeAuthorization();byId('revoke').disabled=true;
    status('本页已停止操作；正在请求电视结束授权。已发提交不会因关闭页面而撤回。');
    try {
      const value=await post('/manage/api/revoke',{}, {control:true,token});
      status(value.revoked===true?'电视已确认授权结束，后台任务保持原状态。':'本页已停止操作，电视端撤销尚未确认。请关闭电视二维码窗口。',value.revoked!==true);
    } catch(error) {status('本页已停止操作，电视端撤销尚未确认。请关闭电视二维码窗口或等待授权到期。',true);}
  });
  byId('previewRows').replaceChildren(byId('batchPreview'),byId('receipts'));
  if(document.addEventListener)document.addEventListener('visibilitychange',()=>{
    clearTimeout(pollTimer);pollTimer=null;
    if(document.hidden)cancelCandidates();else scheduleJobs();
  });
  controls();
  guarded(async()=>{
    const code=location.hash.slice(1);
    history.replaceState(null,'',location.pathname);
    const session=await post(code?'/manage/api/pair':'/manage/api/session',code?{code}:{});
    csrf=session.csrf;byId('workspace').classList.remove('hidden');await load();
  });
})();
