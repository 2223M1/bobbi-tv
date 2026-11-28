/* No bearer in storage, no arbitrary runtime RPC and no markup injection from filenames. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  let activeLocale = 'zh-CN', uiStrings = {}, hasServerLocale = false;
  const liveUpdaters = [];
  let lastCapsuleRows = undefined, lastPreviewCardsData = null, lastRowsRender = null;
  function fmt(template, ...args) {
    if (!args.length) return String(template);
    let idx = 0;
    return String(template).replace(/%[sd]/g, () => String(args[idx++] ?? ''));
  }
  function t(code, fallbackZh, ...args) {
    const raw = (uiStrings && Object.prototype.hasOwnProperty.call(uiStrings, String(code))) ? uiStrings[String(code)] : fallbackZh;
    return fmt(raw, ...args);
  }
  function isEn() { return activeLocale === 'en-GB'; }
  function bi(zhText, enText, ...args) { return fmt(isEn() ? enText : zhText, ...args); }
  function bindText(el, getter) {
    const fn = () => { el.textContent = getter(); };
    fn(); liveUpdaters.push(fn); return el;
  }
  function clearLiveUpdaters() { liveUpdaters.length = 0; }
  const LABEL_SPECS = {
    queued:[91353,'排队中'], running:[91354,'扫描中'], completed:[91355,'扫描完成'], failed:[91356,'未完整完成'],
    canceled:[91357,'已取消'], interrupted:[91358,'已中断'], unmatched:[91323,'待匹配'], ambiguous:[91324,'身份不明确'],
    proposed:[91325,'待确认建议'], confirmed:[91326,'人工确认'], ignored:[91327,'已忽略'], ready:[91359,'可提交'],
    conflict:[91360,'版本冲突，请刷新'], applied:[91361,'已保存'], cancel_requested:[91362,'已请求取消，等待后台确认']
  };
  function labelOf(key) {
    const spec = LABEL_SPECS[key];
    return spec ? t(spec[0], spec[1]) : key;
  }
  let csrf = '', tab = 'items', offset = 0, nextOffset = null, source = null, sourceName = '';
  let pageStarts = [0], pageIndex = 0;
  let query = {view:'works'}, cursor = null, nextCursor = null, queryStarts = [null], queryPage = 0;
  let trail = [], editing = null, selectedEntity = null, mountedSource = null;
  const REQUEST_MS = 15000, PREVIEW_MS = 110000, MAX_BODY = 8192;
  let queued = [], batch = null, batchGeneration = 0, busy = null;
  let authGeneration = 0, authClosed = false;
  let operation = null, viewGeneration = 0, candidateGeneration = 0, candidateRequest = null, candidateTimer = null;
  let pollTimer=null, pollUntil=0, pollDelay=5000, jobsActive=true;
  let grantedScopes=[], playbackBusy=false;
  const playbackOperations=[];
  const PLAYBACK_INSTANCE=['boot_id','epoch','request_id','native_instance','file_sha256','selection_epoch'];
  let supplementParent=null;
  const FILTER_INPUTS=['keyword','state','mediaKind','availability','sort'];
  const requests = new Set(), receipts = [];
  let statusSpec = () => t(91302, '正在连接当前电视授权…'), statusIsError = false;
  function node(tag, text, className) {
    const value = document.createElement(tag);
    if (text !== undefined) value.textContent = String(text);
    if (className) value.className = className;
    return value;
  }
  function status(textOrFn, error=false) {
    statusSpec = typeof textOrFn === 'function' ? textOrFn : () => String(textOrFn);
    statusIsError = error;
    byId('status').textContent = statusSpec();
    byId('status').classList.toggle('error', error);
  }
  function updateSelectOptions(selectId, ariaSpec, optionSpecs) {
    const sel = byId(selectId);
    if (!sel) return;
    sel.setAttribute('aria-label', t(ariaSpec[0], ariaSpec[1]));
    const savedValue = sel.value;
    if (Array.isArray(sel.children) && sel.children.length === optionSpecs.length) {
      optionSpecs.forEach(([val, code, zh], idx) => {
        sel.children[idx].value = val;
        sel.children[idx].textContent = t(code, zh);
      });
    } else {
      sel.replaceChildren(...optionSpecs.map(([val, code, zh]) => {
        const opt = node('option', t(code, zh)); opt.value = val; return opt;
      }));
    }
    sel.value = savedValue;
  }
  function renderStaticChrome() {
    const pageTitle = t(91300, '波比 TV · 片库整理');
    if (document.documentElement) {
      document.documentElement.lang = activeLocale;
      if (document.documentElement.setAttribute) document.documentElement.setAttribute('lang', activeLocale);
    }
    document.title = pageTitle;
    const setIfPresent = (id, code, zh) => { const el = byId(id); if (el) el.textContent = t(code, zh); };
    setIfPresent('pageTitle', 91300, '波比 TV · 片库整理');
    setIfPresent('pageIntro', 91301, '片库整理只修改本地描述，不更改云端文件。播放查看与控制需在电视上单独授权。关闭电视上的二维码窗口即撤销手机授权。');
    setIfPresent('itemsTab', 91303, '作品整理');
    setIfPresent('sourcesTab', 91304, '目录来源');
    setIfPresent('jobsTab', 91305, '后台任务');
    setIfPresent('historyTab', 91306, '继续观看摘要');
    setIfPresent('playbackTab', 91307, '当前播放');
    setIfPresent('stremioTab', 91308, '插件扩展');
    setIfPresent('sourceImportTab', 91309, '导入配置');
    setIfPresent('subtitleUploadTab', 91310, '上传字幕');
    setIfPresent('refresh', 91311, '刷新');
    setIfPresent('revoke', 91312, '结束授权');
    const kw = byId('keyword');
    if (kw) {
      kw.placeholder = t(91313, '搜索作品 / 原文件 / 版本备注');
      kw.setAttribute('placeholder', kw.placeholder);
      kw.setAttribute('aria-label', t(91314, '作品关键词'));
    }
    setIfPresent('search', 91315, '搜索');
    updateSelectOptions('mediaKind', [91316, '作品类型'], [
      ['', 91317, '全部类型'], ['movie', 91318, '电影'], ['tv', 91319, '剧集'], ['unknown', 91320, '尚未确认作品']
    ]);
    updateSelectOptions('state', [91321, '整理状态'], [
      ['', 91322, '全部状态'], ['unmatched', 91323, '待匹配'], ['ambiguous', 91324, '身份不明确'],
      ['proposed', 91325, '待确认建议'], ['confirmed', 91326, '人工确认'], ['ignored', 91327, '已忽略']
    ]);
    updateSelectOptions('availability', [91328, '来源观察'], [
      ['', 91329, '全部观察状态'], ['observed_present', 91330, '已收录 · 播放前核验'],
      ['observed_absent', 91331, '来源未发现此文件'], ['source_unavailable', 91332, '来源暂不可用'],
      ['unverified', 91333, '待确认来源']
    ]);
    updateSelectOptions('sort', [91334, '排序'], [
      ['name', 91335, '按名称'], ['recent_added', 91336, '最近加入'], ['recent_edited', 91337, '最近整理']
    ]);
    setIfPresent('clearFilters', 91338, '清除筛选（保留当前来源）');
    const cs = byId('clearSource');
    if (cs) cs.textContent = mountedSource ? t(91340, '当前授权已固定来源') : t(91339, '当前授权全部来源');
    setIfPresent('back', 91341, '返回作品');
    setIfPresent('previous', 91342, '上一页');
    setIfPresent('next', 91343, '下一页');
    setIfPresent('batchHeading', 91344, '待提交修改（每轮最多 100 项，每批最多 5 项）');
    setIfPresent('batchIntro', 91345, '先逐项预览，再确认分批提交。版本冲突不会自动覆盖。断网不代表未保存，请核对原提交；结束授权不会撤回已发修改。当前页面保留最近 20 批回执。');
    setIfPresent('preview', 91346, '预览全部修改');
    setIfPresent('apply', 91347, '确认 / 继续分批提交');
    setIfPresent('clear', 91348, '清空本轮编辑');
    setIfPresent('cancelPlan', 91349, '停止后续批次');
    setIfPresent('retry', 91350, '核对原提交');
    setIfPresent('reviewAgain', 91351, '读取当前修订重新核对');
    setIfPresent('pageFooter', 91352, '无效、过期或账号变更时，请在电视重新打开“手机详细管理”并扫码。播放控制只对本次明确授权的当前实例生效。');
  }
  function updateJobCapsule(rows) {
    lastCapsuleRows = rows;
    const capsule = byId('jobCapsule');
    if (!capsule) return;
    const prefix = t(91363, '后台任务 · ');
    if (!Array.isArray(rows)) {
      capsule.replaceChildren(node('strong', prefix), node('span', rows ? String(rows) : t(91364, '只读摘要待刷新（点击「后台任务」查看实时扫描进度）')));
      return;
    }
    const active = rows.filter(r => r && ['queued', 'running'].includes(r.state));
    if (active.length) {
      const first = active[0], counts = first.counts || {};
      const detail = t(91365, '%s（已扫描 %d 项 / 发现 %d 个视频）', labelOf(first.state), counts.scanned || 0, counts.discovered || 0);
      capsule.replaceChildren(node('strong', prefix), node('span', t(91366, '进行中 %d 项 · %s', active.length, detail)));
    } else if (rows.length) {
      const latest = rows[0];
      capsule.replaceChildren(node('strong', prefix), node('span', t(91367, '当前无运行中任务 · 最近状态：%s', labelOf(latest.state))));
    } else {
      capsule.replaceChildren(node('strong', prefix), node('span', t(91368, '当前无排队或扫描中任务')));
    }
  }
  function renderQueue() {
    byId('queue').replaceChildren(...queued.map((q,index) => node('p',(index+1)+'. '+q.name+' · '+q.command.action)));
  }
  function renderScopeStatus() {
    if (tab !== 'items') return;
    const mediaVal = byId('mediaKind').value || null;
    const stateVal = byId('state').value || null;
    const availVal = byId('availability').value || null;
    const sortVal = byId('sort').value || 'name';
    const available = {
      observed_present: t(91330, '已收录 · 播放前核验'),
      observed_absent: t(91331, '来源未发现此文件'),
      source_unavailable: t(91332, '来源暂不可用'),
      unverified: t(91333, '待确认来源')
    };
    const srcText = sourceName || (mountedSource ? bi('本次授权的已登记来源', 'Authorized registered source') : source ? bi('所选目录来源', 'Selected source') : bi('当前账号全部来源', 'All sources in account'));
    const kindText = ({movie: t(91318, '电影'), tv: t(91319, '剧集'), unknown: t(91320, '尚未确认作品')})[mediaVal] || t(91317, '全部类型');
    const stateText = stateVal ? labelOf(stateVal) : bi('全部整理状态', 'All review statuses');
    const availText = available[availVal] || t(91329, '全部观察状态');
    const sortText = ({name: t(91335, '按名称'), recent_added: t(91336, '最近加入'), recent_edited: t(91337, '最近整理')})[sortVal] || t(91335, '按名称');
    byId('scopeStatus').textContent = t(91485, '当前来源：%s · %s · %s · %s · %s', srcText, kindText, stateText, availText, sortText);
  }
  function previewMapping(value) {
    if (!value) return bi('未设置','Unset');
    const parts=[value.title || bi('未填写名称','Untitled'),
      ({movie:t(91318,'电影'),tv:t(91319,'剧集'),custom:bi('自定义名称','Custom')})[value.kind]];
    if (value.tmdb_id != null) parts.push('TMDb '+value.tmdb_id);
    if (value.kind==='tv') parts.push(Number.isInteger(value.season)&&Number.isInteger(value.episode)
      ? 'S'+String(value.season).padStart(2,'0')+'E'+String(value.episode).padStart(2,'0') : bi('季集未明确','S/E unset'));
    parts.push(bi('版本备注 %s','Version note %s',value.version||bi('未填写','None')));
    return parts.filter(Boolean).join(' · ');
  }
  function previewRelation(value) {
    if (!value) return bi('无补充关系','No extra link');
    return [value.title, value.metadata_key, value.kind,
      value.parent_file_id ? bi('指定文件版本 %s','File version %s',value.parent_file_id.slice(0,12)) : bi('整个作品','Whole work')].filter(Boolean).join(' · ');
  }
  function buildPreviewCard(entryName, row) {
    const card = node('div', undefined, 'card');
    card.append(node('h3', (entryName || bi('未知条目', 'Unknown item')) + ' · ' + labelOf(row.status)));
    const actions={confirm:bi('保存描述','Save mapping'),unbind:bi('解除绑定','Unbind'),ignore:bi('忽略此项','Ignore'),undo:bi('撤回上次修改','Undo'),supplement:bi('关联补充内容','Link extra'),detach_supplement:bi('移除补充内容关联','Unlink extra')};
    if (row.status==='failed') {card.append(node('p',bi('该文件不可用；未保存。','File unavailable; nothing saved.')));return card;}
    card.append(node('p',bi('记录修订 %s','Revision %s',row.revision??'—')+' · '+(actions[row.action]||bi('待核对','Pending'))),
      node('p',bi('修改前描述 %s','Before: %s',previewMapping(row.before))),node('p',bi('修改后描述 %s','After: %s',previewMapping(row.after))));
    if (row.before_state||row.after_state) card.append(node('p',bi('整理状态 %s → %s','Review state %s → %s',labelOf(row.before_state)||'—',labelOf(row.after_state)||'—')));
    if ('before_supplement' in row || 'after_supplement' in row) card.append(node('p',bi('原补充关系 %s','Extra before: %s',previewRelation(row.before_supplement))),node('p',bi('修改后补充关系 %s','Extra after: %s',previewRelation(row.after_supplement))));
    if ('before_segments' in row || 'after_segments' in row) {
      const segments=v=>!v ? bi('未设置','Unset') : [bi('人工标注 · 时长 %s 秒','Manual annotation · duration %s s',v.duration_ms/1000),
        v.state==='matched'?bi('与当前文件匹配','Matches current file'):bi('文件观察已变或不可用','File observation changed or unavailable'),
        ...(v.items||[]).map(s=>s.kind+' '+s.start_ms/1000+'–'+s.end_ms/1000+' s')].join(' · ');
      card.append(node('p',bi('原片段 %s','Segments before: %s',segments(row.before_segments))),node('p',bi('修改后片段 %s','Segments after: %s',segments(row.after_segments))));
    }
    return card;
  }
  function renderPreviewCards() {
    if (!lastPreviewCardsData) return;
    byId('batchPreview').replaceChildren(...lastPreviewCardsData.map(d => buildPreviewCard(d.name, d.row)));
  }
  function buildReceiptCard(original, indexedRows, all) {
    const messages = original.entries.map((entry, index) => {
      const row = indexedRows.get(index);
      const st = row ? (row.status === 'failed' ? bi('未保存', 'Not saved') : labelOf(row.status)) + (row.reason ? bi('（%s）', ' (%s)', row.reason) : '') : bi('提交结果待核对', 'Outcome pending check');
      return entry.name + ' · ' + st;
    });
    const card = node('article', undefined, 'card');
    card.append(node('h3', t(91493, '提交回执')), ...messages.map(text => node('p', text)));
    if (all) {
      const entry = original.entries.find(entry => entry.anchor && entry.command.action === 'confirm' && entry.command.mapping.kind === 'tv');
      if (entry) card.append(button(t(91494, '继续整理本剧'), () => groupEditor(entry.anchor, entry.candidate || {...entry.command.mapping, media_kind:'tv'})));
    }
    return card;
  }
  function renderStoredReceipts() {
    receipts.forEach(r => { if (r.original && r.indexedRows) r.card = buildReceiptCard(r.original, r.indexedRows, r.all); });
    byId('receipts').replaceChildren(...receipts.map(r => r.card));
  }
  function applyLocale(session, rerender=false) {
    if (!session || typeof session !== 'object') return false;
    let changed = false;
    if (typeof session.locale === 'string' && session.locale) {
      hasServerLocale = true;
      if (session.locale !== activeLocale) { activeLocale = session.locale; changed = true; }
    }
    if (session.ui_strings && typeof session.ui_strings === 'object') {
      hasServerLocale = true;
      uiStrings = {...session.ui_strings};
      changed = true;
    }
    renderStaticChrome();
    if (rerender && changed && !authClosed) {
      if (!byId('jobCapsule').classList.contains('hidden')) updateJobCapsule(lastCapsuleRows);
      renderScopeStatus();
      renderQueue();
      planProgress();
      renderPreviewCards();
      renderStoredReceipts();
      liveUpdaters.forEach(fn => fn());
      if (!editing && typeof lastRowsRender === 'function') lastRowsRender();
      byId('status').textContent = statusSpec();
      byId('status').classList.toggle('error', statusIsError);
    }
    return changed;
  }
  async function syncLocale() {
    if (authClosed || !csrf) return false;
    const generation = authGeneration;
    try {
      const session = await post('/manage/api/session', {});
      if (authClosed || generation !== authGeneration) return false;
      recoverPlayback(session);
      return applyLocale(session, true);
    } catch (error) {
      return false;
    }
  }
  if (typeof globalThis !== 'undefined') globalThis.__bobbiSyncLocale = syncLocale;
  if (document.addEventListener) document.addEventListener('bobbi:sync-locale', () => { syncLocale(); });

  function id() {
    return Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2,'0')).join('');
  }
  function failure(code, message) {const error=new Error(message);error.code=code;return error;}
  function utf8Size(text) {return encodeURIComponent(text).replace(/%[0-9A-F]{2}|[^%]/g,'x').length;}
  function sha256Hex(bytes) {
    const K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    let h0=0x6a09e667,h1=0xbb67ae85,h2=0x3c6ef372,h3=0xa54ff53a,h4=0x510e527f,h5=0x9b05688c,h6=0x1f83d9ab,h7=0x5be0cd19;
    const len=bytes.length, bitHi=Math.floor((len*8)/0x100000000), bitLo=(len*8)>>>0;
    const padLen=((len+9+63)&~63), buf=new Uint8Array(padLen), dv=new DataView(buf.buffer);
    buf.set(bytes);buf[len]=0x80;dv.setUint32(padLen-8,bitHi,false);dv.setUint32(padLen-4,bitLo,false);
    const w=new Uint32Array(64), rotr=(x,n)=>(x>>>n)|(x<<(32-n));
    for(let i=0;i<padLen;i+=64) {
      for(let j=0;j<16;j++)w[j]=dv.getUint32(i+j*4,false);
      for(let j=16;j<64;j++) {
        const s0=rotr(w[j-15],7)^rotr(w[j-15],18)^(w[j-15]>>>3);
        const s1=rotr(w[j-2],17)^rotr(w[j-2],19)^(w[j-2]>>>10);
        w[j]=(w[j-16]+s0+w[j-7]+s1)>>>0;
      }
      let a=h0,b=h1,c=h2,d=h3,e=h4,f=h5,g=h6,h=h7;
      for(let j=0;j<64;j++) {
        const S1=rotr(e,6)^rotr(e,11)^rotr(e,25), ch=(e&f)^((~e)&g), t1=(h+S1+ch+K[j]+w[j])>>>0;
        const S0=rotr(a,2)^rotr(a,13)^rotr(a,22), maj=(a&b)^(a&c)^(b&c), t2=(S0+maj)>>>0;
        h=g;g=f;f=e;e=(d+t1)>>>0;d=c;c=b;b=a;a=(t1+t2)>>>0;
      }
      h0=(h0+a)>>>0;h1=(h1+b)>>>0;h2=(h2+c)>>>0;h3=(h3+d)>>>0;h4=(h4+e)>>>0;h5=(h5+f)>>>0;h6=(h6+g)>>>0;h7=(h7+h)>>>0;
    }
    return [h0,h1,h2,h3,h4,h5,h6,h7].map(v=>v.toString(16).padStart(8,'0')).join('');
  }
  function bytesToBase64(slice) {
    const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    let out='', i=0;
    for(;i+2<slice.length;i+=3) {
      const n=(slice[i]<<16)|(slice[i+1]<<8)|slice[i+2];
      out+=alphabet[(n>>>18)&63]+alphabet[(n>>>12)&63]+alphabet[(n>>>6)&63]+alphabet[n&63];
    }
    if(i<slice.length) {
      const rem=slice.length-i, n=(slice[i]<<16)|(rem>1?(slice[i+1]<<8):0);
      out+=alphabet[(n>>>18)&63]+alphabet[(n>>>12)&63]+(rem>1?alphabet[(n>>>6)&63]:'=')+'=';
    }
    return out;
  }
  function frozen(value) {
    if (value && typeof value==='object') {Object.values(value).forEach(frozen);Object.freeze(value);}
    return value;
  }
  function snapshot(selected=queued, requestId=id()) {
    const entries=JSON.parse(JSON.stringify(selected));
    const value=frozen({entries,commands:entries.map(q=>q.command),requestId,generation:batchGeneration,authorization:authGeneration});
    if (utf8Size(JSON.stringify({action:'catalog_apply',params:{request_id:requestId,commands:value.commands}}))>MAX_BODY)
      throw new Error(t(91369, '本批完整请求超过 8192 字节，请减少条目或缩短描述。'));
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
  function playbackUnknown(record) {return ['queued','unknown'].includes(record.status);}
  function samePlayback(one,two) {return one&&two&&PLAYBACK_INSTANCE.every(key=>one[key]===two[key]);}
  function playbackPending(expected) {return playbackOperations.some(record=>playbackUnknown(record)&&samePlayback(record.command.expected,expected));}
  function recoverPlayback(session) {
    for(const saved of session.playback_operations||[]) {
      const record=playbackOperations.find(row=>row.command.command_id===saved.command.command_id);
      if(record)playbackResult(record,{command_id:saved.command.command_id,status:saved.status});
      else playbackOperations.push({command:frozen(saved.command),status:saved.status});
    }
  }
  function playbackResult(record,result) {
    const valid=result&&(!result.command_id||result.command_id===record.command.command_id);
    record.status=valid&&['queued','unknown','applied','rejected','failed'].includes(result.status)?result.status:'unknown';
  }
  function playbackResultText(record) {return ({applied:t(91370,'原生播放器已执行。'),rejected:t(91371,'播放状态已变化，操作未执行。'),
    failed:t(91372,'播放器执行失败。'),queued:t(91373,'原操作已排队，结果尚未确认。')})[record.status]||
    t(91374,'原操作结果未知；回执可能尚未到达或已过期。可只读核对，同实例不会重复提交。');}
  function controls() {
    const locked=Boolean(busy)||authClosed;
    for(const control of ['keyword','state','mediaKind','availability','sort','search','clearFilters'])byId(control).disabled=locked;
    byId('clearSource').disabled=locked||Boolean(mountedSource);
    byId('clear').disabled=locked||Boolean(unknown());
    byId('preview').disabled=locked||Boolean(unknown());
    byId('apply').disabled=locked||Boolean(operation&&operation.canceled)||!(batch&&batch.phase==='ready'||operation&&operation.phase==='paused');
    byId('retry').disabled=locked||!batch||batch.phase!=='unknown';
    byId('reviewAgain').disabled=locked||!batch||batch.phase!=='unknown_expired';
    byId('cancelPlan').disabled=authClosed||!operation||operation.canceled||operation.index>=operation.chunks.length;
  }
  function closeAuthorization() {
    authGeneration++;authClosed=true;csrf='';batch=null;busy=null;lastPreviewCardsData=null;lastRowsRender=null;clearLiveUpdaters();
    supplementParent=null;
    playbackOperations.length=0;
    cancelCandidates();if(operation)operation.canceled=true;
    clearTimeout(pollTimer);pollTimer=null;
    requests.forEach(request=>request.abort());
    byId('workspace').classList.add('hidden');controls();
  }
  async function post(path, body, options={}) {
    const generation=options.generation===undefined?authGeneration:options.generation;
    if (generation!==authGeneration || authClosed&&!options.control) throw failure('STALE',t(91375,'授权已结束。'));
    const encoded=JSON.stringify(body);
    if (utf8Size(encoded)>MAX_BODY) throw failure('REQUEST_TOO_LARGE',t(91376,'完整请求超过 8192 字节，请减少条目。'));
    const controller=options.controller||new AbortController();requests.add(controller);
    let timedOut=false, timer;
    const canceled=new Promise((resolve,reject)=>{
      controller.signal.addEventListener('abort',()=>reject(failure(timedOut?'TIMEOUT':'STALE',
        timedOut?t(91377,'请求超时，尚未取得结果。'):t(91375,'授权已结束。'))),{once:true});
      timer=setTimeout(()=>{timedOut=true;controller.abort();},REQUEST_MS);
    });
    try {
      const result=await Promise.race([canceled,(async()=>{
        const response=await fetch(path,{method:'POST',credentials:'same-origin',cache:'no-store',signal:controller.signal,
          headers:{'Content-Type':'application/json','X-Bobbi-CSRF':options.token===undefined?csrf:options.token},body:encoded});
        return {response,value:await response.json()};
      })()]);
      if (generation!==authGeneration) throw failure('STALE',t(91375,'授权已结束。'));
      const {response,value}=result;
      if (!response.ok) {
        if (response.status===401) {
          closeAuthorization();status(()=>t(91378,'授权已失效或账号已变化，请在电视重新开启并扫码。'),true);
          throw failure('STALE',bi('授权已失效或账号已变化。','Session expired or account changed.'));
        }
        if (value.error==='PREVIEW_REQUIRED') throw failure(value.error,t(91379,'预览已过期，请重新预览后再提交。'));
        if (value.error==='CATALOG_REPLY_LIMIT') throw failure(value.error,t(91380,'本批信息过长，请减少条目后重新预览。'));
        throw failure(value.error||String(response.status),t(91381,'操作未确认，请刷新状态后重试（%s）。',value.error||response.status));
      }
      return value;
    } catch(error) {
      if (generation!==authGeneration) throw failure('STALE',t(91375,'授权已结束。'));
      throw error;
    } finally {clearTimeout(timer);requests.delete(controller);}
  }
  const rpc = (action,params={}) => post('/manage/api',{action,params});
  function resetPage() { offset=0;pageStarts=[0];pageIndex=0; }
  function resetQueryPage() {cursor=null;nextCursor=null;queryStarts=[null];queryPage=0;editing=null;}
  function resetQuery() {resetQueryPage();trail=[];query={view:'works'};selectedEntity=null;}
  function clearQueryFilters() {for(const name of FILTER_INPUTS)byId(name).value=name==='sort'?'name':'';}
  function button(textOrFn, action) {
    const result = typeof textOrFn === 'function' ? bindText(node('button'), textOrFn) : node('button', textOrFn);
    result.addEventListener('click',() => guarded(action));
    return result;
  }
  async function guarded(action) {
    if (busy || authClosed) return;
    const lease={generation:authGeneration};busy=lease;controls();
    try { await action(); }
    catch(error) { if (lease.generation===authGeneration && error.code!=='STALE') status(error.message || t(91382,'连接中断，结果未确认。请重新读取状态。'),true); }
    finally { if(busy===lease)busy=null;controls(); }
  }
  function setLabelTitle(labelEl, inputEl, text) {
    if (labelEl.firstChild && labelEl.firstChild !== inputEl && 'nodeValue' in labelEl.firstChild) {
      labelEl.firstChild.nodeValue = text;
    } else {
      labelEl.textContent = text;
      if (!labelEl.children || !Array.from(labelEl.children).includes(inputEl)) labelEl.append(inputEl);
    }
  }
  function bindLabel(labelEl, inputEl, titleOrFn) {
    if (typeof titleOrFn === 'function') {
      const fn = () => setLabelTitle(labelEl, inputEl, titleOrFn());
      fn(); liveUpdaters.push(fn);
    } else {
      setLabelTitle(labelEl, inputEl, String(titleOrFn));
    }
  }
  function field(card, titleOrFn, type='text', value='') {
    const initTitle = typeof titleOrFn === 'function' ? titleOrFn() : titleOrFn;
    const label = node('label', initTitle), input = node('input');
    input.type = type; input.value = value == null ? '' : String(value);
    input.maxLength = 240; label.append(input);
    if (typeof titleOrFn === 'function') bindLabel(label, input, titleOrFn);
    card.append(label); return input;
  }
  function select(card, titleOrFn, choices, value) {
    const initTitle = typeof titleOrFn === 'function' ? titleOrFn() : titleOrFn;
    const label = node('label', initTitle), input = node('select');
    choices.forEach(([key, textOrFn]) => {
      const option = typeof textOrFn === 'function' ? bindText(node('option'), textOrFn) : node('option', textOrFn);
      option.value = key; input.append(option);
    });
    input.value=value; label.append(input);
    if (typeof titleOrFn === 'function') bindLabel(label, input, titleOrFn);
    card.append(label); return input;
  }
  function changedBatch() {
    batchGeneration++;batch=null;operation=null;lastPreviewCardsData=null;byId('batchPreview').replaceChildren();byId('planStatus').textContent='';controls();
    renderQueue();
  }
  function titleHint(name) {return name.replace(/\.[a-z0-9]{2,5}$/i,'').split(/(?:[ ._-]s\d+[ ._-]*e\d+|[ ._-]\d{1,2}x\d+)/i)[0].replace(/\[[^\]]*\]|\([^)]*\)|\b(?:19|20)\d{2}\b/g,' ').replace(/[._\s-]+/g,' ').trim().slice(0,120);}
  function candidateEditor(card,item,fields) {
    const section=node('section');section.append(bindText(node('h3'),()=>t(91383,'作品候选（优先）')));
    const evidence=(item.candidates||[])[0]||{};
    const query=field(section,()=>t(91384,'候选搜索关键词（仅发送此关键词）'),'text',titleHint(item.file.name));query.maxLength=120;
    const year=field(section,()=>t(91385,'候选年份（可选，重制版需核对）'),'number',evidence.year);
    const results=node('div'), message=node('p');let selected=null, msgGetter=()=>'';
    liveUpdaters.push(()=>{ message.textContent = msgGetter(); });
    const setMsg = fn => { msgGetter = fn; message.textContent = fn(); };
    const page=viewGeneration;
    async function searchCandidates() {
      if(authClosed||page!==viewGeneration)return;
      cancelCandidates();const generation=candidateGeneration,authorization=authGeneration;
      const controller=new AbortController();candidateRequest=controller;
      results.replaceChildren();setMsg(()=>t(91386,'正在搜索公开作品信息…'));selected=null;
      try {
        const value=await post('/manage/api',{action:'catalog_candidates',params:{query:query.value.trim(),year:year.value?Number(year.value):null,
          media_kind:fields.kind.value==='custom'?null:fields.kind.value}},{controller});
        if(generation!==candidateGeneration||authorization!==authGeneration||page!==viewGeneration)return;
        setMsg(()=>(value.items||[]).length?t(91387,'搜索结果只是候选，请核对年份、类型和季集。'):t(91388,'没有找到候选，可修改关键词或使用手动编号。'));
        for(const candidate of value.items||[]) {
          const row=node('article',undefined,'card');
          row.append(bindText(node('p'),()=>(candidate.media_kind==='tv'?t(91319,'剧集'):t(91318,'电影'))+' · '+candidate.title+' · '+(candidate.year||t(91389,'年份未知'))),
            node('small',(candidate.original_title||'')+' · '+candidate.basis));
          if(candidate.poster_path&&/^\/[A-Za-z0-9_-]{1,100}\.(jpg|png)$/.test(candidate.poster_path)) {
            const poster=node('img');poster.src='https://image.tmdb.org/t/p/w185'+candidate.poster_path;poster.alt=candidate.title;poster.loading='lazy';poster.referrerPolicy='no-referrer';poster.width=92;row.append(poster);
          }
          row.append(button(()=>t(91390,'采用此候选（尚未保存）'),()=>{
            if(page!==viewGeneration||generation!==candidateGeneration)throw new Error(t(91391,'候选已过期，请重新搜索。'));
            selected=candidate;fields.candidate=candidate;fields.kind.value=candidate.media_kind;fields.title.value=candidate.title;fields.tmdb.value=candidate.tmdb_id;
            if(candidate.media_kind==='tv') {fields.season.value=evidence.season==null?'':evidence.season;fields.episode.value=evidence.episode==null?'':evidence.episode;}
            setMsg(()=>t(91392,'已填入候选，尚未修改记录。请核对季集，再加入修改并预览。'));
          }));results.append(row);
        }
      } catch(error) {if(generation===candidateGeneration&&page===viewGeneration&&!authClosed)setMsg(()=>t(91393,'候选搜索未完成，可重试或使用手动编号。'));}
      finally {if(candidateRequest===controller)candidateRequest=null;}
    }
    const searchButton=bindText(node('button'),()=>t(91394,'搜索作品候选'));searchButton.addEventListener('click',searchCandidates);
    for(const input of [query,year])input.addEventListener('input',()=>{
      cancelCandidates();selected=null;fields.candidate=null;results.replaceChildren();setMsg(()=>t(91395,'关键词已变化，旧候选失效。'));
      candidateTimer=setTimeout(searchCandidates,350);
    });
    section.append(searchButton,message,results,button(()=>t(91396,'查看同目录逐集整理建议'),async()=>{
      if(!selected||selected.media_kind!=='tv')throw new Error(t(91397,'请先搜索并采用一个剧集候选。'));
      if(unknown())throw new Error(t(91398,'请先核对原提交结果。'));
      await groupEditor(item,selected);
    }));card.append(section);
  }
  async function groupSourcePicker(anchor,candidate,start,offset=0) {
    const page=viewGeneration, value=await rpc('catalog_sources',{offset,limit:5});
    if(page!==viewGeneration)return;
    const panel=byId('groupRows');panel.replaceChildren(bindText(node('h2'),()=>t(91399,'请选择可信来源')),
      bindText(node('p'),()=>t(91400,'此文件被多个目录来源收录。请明确选择包含该文件的可信来源；不会扩大到其他目录或账号。')));
    for(const row of value.items||[])panel.append(button(row.name+' · '+row.id.slice(0,8),async()=>{
      if(page!==viewGeneration)throw new Error(bi('页面已变化，请重新读取目录建议。','Page changed; reload folder suggestions.'));
      await groupEditor(anchor,candidate,start,row.id);
    }));
    if(value.next_offset!=null)panel.append(button(()=>t(91401,'下一页来源'),()=>groupSourcePicker(anchor,candidate,start,value.next_offset)));
  }
  async function groupEditor(anchor,candidate,start=0,trustedSource=null) {
    if(unknown())throw new Error(bi('请先核对原提交结果，不能覆盖未知批次。','Check original submission outcome first; cannot overwrite unknown batch.'));
    const deadline=Date.now()+60000, rows=[];let next=start,identity=null,revision=null;
    const params={file_id:anchor.file.id,limit:5};if(trustedSource||source||mountedSource)params.source_id=trustedSource||source||mountedSource;
    try {
      if(start) {
        const fresh=await rpc('catalog_group',{...params,offset:0});
        identity=fresh.group_id;revision=fresh.projection_revision;params.source_id=fresh.source_id;
      }
      do {
        if(Date.now()>=deadline)throw new Error(bi('同目录读取已到等待期限，请重新获取建议。','Same-folder read timed out; reload suggestions.'));
        const value=await rpc('catalog_group',{...params,offset:next,...(revision===null?{}:{projection_revision:revision})});
        if(Date.now()>=deadline)throw new Error(bi('同目录读取已到等待期限，请重新获取建议。','Same-folder read timed out; reload suggestions.'));
        if(identity!==null&&(identity!==value.group_id||revision!==value.projection_revision))throw new Error(bi('目录记录已变化，请重新获取建议。','Folder records changed; reload suggestions.'));
        identity=value.group_id;revision=value.projection_revision;params.source_id=value.source_id;
        rows.push(...value.items);const previous=next;next=value.next_offset;
        if(next!==null&&(!Number.isInteger(next)||next<=previous))throw new Error(bi('目录分页未完整，请重新读取。','Folder pagination incomplete; reload.'));
      }while(next!==null&&rows.length<100);
    } catch(error) {
      if(error.code==='CATALOG_GROUP_AMBIGUOUS'&&!params.source_id){await groupSourcePicker(anchor,candidate,start);return;}
      throw error;
    }
    const panel=byId('groupRows');panel.replaceChildren(bindText(node('h2'),()=>t(91402,'同目录逐项建议 · %s',candidate.title)),
      bindText(node('p'),()=>t(91403,'同目录不证明同一作品。请核对每个文件，排除重制版、合集和多集文件；特别篇保留 S00。只有勾选项加入计划。')));
    const editors=[];
    for(const item of rows) {
      const evidence=(item.candidates||[])[0]||{},mapping=item.mapping||{},card=node('article',undefined,'card');
      card.append(node('h3',item.file.name),bindText(node('small'),()=>t(91404,'当前修订 %d · 原描述 %s',item.revision,mapping.title||t(91405,'未绑定'))));
      const keep=field(card,()=>t(91406,'加入本轮'),'checkbox');
      keep.checked=!item.file.truncated&&item.state!=='ambiguous'&&item.available!==false&&evidence.season!=null&&evidence.episode!=null&&
        titleHint(item.file.name).toLowerCase()===titleHint(anchor.file.name).toLowerCase()&&
        (!evidence.year||!candidate.year||evidence.year===candidate.year)&&(!mapping.tmdb_id||mapping.kind==='tv'&&mapping.tmdb_id===candidate.tmdb_id);
      const season=field(card,()=>t(91407,'拟绑定季号（特别篇为 0）'),'number',evidence.season),episode=field(card,()=>t(91408,'拟绑定集号（多集文件请排除）'),'number',evidence.episode);
      const version=field(card,()=>t(91409,'版本备注（可选，不作为续播证明）'),'text',mapping.version);version.maxLength=80;
      if(!keep.checked)card.append(bindText(node('p',undefined,'error'),()=>t(91410,'存在未知季集、年份 / 类型差异或身份疑点，默认未选。请人工核对。')));
      editors.push({item,keep,season,episode,version});panel.append(card);
    }
    panel.append(button(()=>t(91411,'将勾选项加入分批预览'),()=>{
      if(unknown())throw new Error(t(91398,'请先核对原提交结果。'));
      const entries=[];
      for(const editor of editors.filter(row=>row.keep.checked)) {
        if(!editor.season.value||!editor.episode.value||!Number.isInteger(Number(editor.season.value))||Number(editor.season.value)<0||!Number.isInteger(Number(editor.episode.value))||Number(editor.episode.value)<1)throw new Error(t(91412,'勾选项必须明确季号和集号；多集文件请排除。'));
        entries.push({name:editor.item.file.name,command:{file_id:editor.item.file.id,expected_revision:editor.item.revision,action:'confirm',
          mapping:{kind:'tv',title:candidate.title,tmdb_id:candidate.tmdb_id,season:Number(editor.season.value),episode:Number(editor.episode.value),version:editor.version.value.trim()||null}}});
      }
      if(!entries.length)throw new Error(t(91413,'请至少勾选一项。'));
      queued=entries;changedBatch();status(()=>t(91414,'已加入 %d 项建议。请预览全部逐项修改后，再确认分批保存。',entries.length));
    }));
    if(next!==null)panel.append(button(()=>t(91415,'下一轮同目录文件（保留已保存回执）'),async()=>{
      if(unknown()||queued.length&&(!operation||operation.phase!=='complete'))throw new Error(bi('请先完成本轮或明确清空未提交选择；原回执和未知提交不能被覆盖。','Finish this round or clear unsent selections first; saved receipts and unknown submissions cannot be overwritten.'));
      if(queued.length){queued=[];changedBatch();}
      await groupEditor(anchor,candidate,next,params.source_id);
    }));
    status(()=>t(91416,'已读取本轮第 %d–%d 个同目录文件%s尚未自动确认或提交。',start+1,start+rows.length,next!==null?bi('；尚有后续轮次。','; more pages remain. '):bi('。','. ')));
  }
  function itemCard(item) {
    clearLiveUpdaters();
    const card=node('article',undefined,'card');card.append(node('h2',item.file.name));
    card.append(bindText(node('small'),()=>item.file.parent+(item.file.truncated?t(91417,'（显示已截短）'):'')));
    card.append(bindText(node('p'),()=>t(91418,'%s · 修订 %d',labelOf(item.state),item.revision)));
    if (item.available === false) card.append(bindText(node('p',undefined,'error'),()=>t(91419,'当前来源未发现此文件；本地描述和观看记录仍保留。')));
    for (const hint of item.candidates||[]) {
      if (hint.origin==='filename') card.append(bindText(node('small',undefined,'muted'),()=>{
        const parts=[Number.isInteger(hint.year)?String(hint.year):'',Number.isInteger(hint.season)&&Number.isInteger(hint.episode)?'S'+String(hint.season).padStart(2,'0')+'E'+String(hint.episode).padStart(2,'0'):''].filter(Boolean);
        return parts.length?bi('文件名提示：%s（身份尚未确认）','Filename hint: %s (identity unverified)',parts.join(' · ')):bi('文件名不能确认作品身份。','The filename does not establish identity.');
      }));
      else if(hint.origin==='server' && hint.description) card.append(bindText(node('small',undefined,'muted'),()=>bi('服务器描述：%s','Server description: %s',[hint.description.title,hint.description.year].filter(Boolean).join(' · '))));
    }
    const current=item.mapping||{};
    const action=select(card,()=>t(91420,'操作'),[
      ['confirm',()=>t(91421,'设置作品 / 自定义名称')],['supplement',()=>t(91422,'设为补充视频')],
      ['detach_supplement',()=>t(91423,'解除补充关系')],['unbind',()=>t(91424,'解除绑定')],
      ['ignore',()=>t(91425,'忽略此项')],['undo',()=>t(91426,'撤回上次修改')]
    ],'confirm');
    if(item.supplement)card.append(bindText(node('p'),()=>t(91427,'补充关系：%s%s',item.supplement.title,item.supplement.state==='verification_required'?t(91428,' · 父版本已变化，需重新核对'):'')));
    if(!item.supplement && item.file.observation_key && (item.state==='confirmed'||current.kind==='custom'&&item.provenance==='manual')) {
      card.append(button(()=>t(91429,'选作补充视频的父版本'),()=>{
        supplementParent=frozen({file_id:item.file.id,revision:item.revision,evidence:item.file.observation_key,
          metadata_key:['movie','tv'].includes(current.kind)?'tmdb:'+current.kind+':'+current.tmdb_id:null,title:current.title||item.file.name});
        status(()=>t(91430,'已选父版本「%s」。返回并整理补充视频，选择“设为补充视频”；尚未保存关系。',supplementParent.title));
      }));
    }
    const advanced=node('details');advanced.append(bindText(node('summary'),()=>t(91431,'高级：手填编号 / 自定义名称')));
    const kind=select(advanced,()=>t(91432,'描述类型'),[
      ['custom',()=>t(91433,'自定义名称')],['movie',()=>t(91434,'电影 TMDb')],['tv',()=>t(91435,'剧集 TMDb')]
    ],current.kind||'custom');
    const title=field(advanced,()=>t(91436,'显示名称'),'text',current.title||item.file.name);
    const tmdb=field(advanced,()=>t(91437,'TMDb 编号（仅电影 / 剧集）'),'number',current.tmdb_id);
    const season=field(card,()=>t(91438,'季号（剧集，特别篇为 0）'),'number',current.season);
    const episode=field(card,()=>t(91439,'集号（剧集）'),'number',current.episode);
    const version=field(card,()=>bi('版本备注（可选，不作为同源续播证明）','Version Note (optional; not proof of same-source continuity)'),'text',current.version);
    version.maxLength=80;
    const fields={kind,title,tmdb,season,episode,version};
    candidateEditor(card,item,fields);card.append(advanced);
    const relation=node('details');relation.append(bindText(node('summary'),()=>t(91440,'补充视频关系')));
    const originalRelation=item.supplement&&frozen(Object.fromEntries(
      ['metadata_key','parent_file_id','parent_revision','parent_evidence'].map(key=>[key,item.supplement[key]??null])));
    let chosenParent=supplementParent;
    const targets=(originalRelation?[['current',()=>t(91441,'保留当前关联')]]:[]).concat(
      chosenParent?[['version',()=>t(91442,'已选父版本：%s',chosenParent.title)]]:[],
      [['work',()=>t(91443,'作品共有（使用作品候选 / 编号）')]]
    );
    const target=select(relation,()=>t(91444,'关联范围'),targets,originalRelation?'current':chosenParent?'version':'work');
    if(chosenParent)relation.append(button(()=>t(91445,'清除已选父版本'),()=>{
      supplementParent=null;chosenParent=null;
      target.replaceChildren(...Array.from(target.children).filter(option=>option.value!=='version'));
      target.value=originalRelation?'current':'work';status(()=>bi('已清除临时父版本选择；已有补充关系仍保留。','Cleared temporary parent selection; existing extra link is kept.'));
    }));
    else relation.append(bindText(node('p'),()=>bi('精确关联到某个版本或无 TMDb 的自建内容时，请先打开父文件并选择“选作补充视频的父版本”。','To link to a specific release or custom non-TMDb item, open the parent file first and choose "Use as Parent Release for Extras".')));
    const supplementKind=select(relation,()=>bi('补充类型','Extra Kind'),[
      ['bonus',()=>bi('花絮','Bonus')],['interview',()=>bi('访谈','Interview')],
      ['deleted',()=>bi('删减片段','Deleted Scene')],['trailer',()=>bi('预告','Trailer')],['other',()=>bi('其他','Other')]
    ],(item.supplement||{}).kind||'bonus');
    const supplementTitle=field(relation,()=>t(91446,'补充视频名称'),'text',(item.supplement||{}).title||item.file.name);
    card.append(relation);
    card.append(button(()=>t(91447,'加入本批修改'),() => {
      if (unknown()) throw new Error(bi('上一批提交结果待核对，请先核对原提交，不能覆盖未知结果。','Previous submission outcome pending; check original submission first.'));
      if (queued.length>=100 && !queued.some(q=>q.command.file_id===item.file.id)) throw new Error(bi('每轮最多 100 项，请分轮整理。','Up to 100 items per round; organize in separate rounds.'));
      let mapping=null;
      if (action.value==='confirm') {
        mapping={kind:kind.value,title:title.value.trim(),tmdb_id:kind.value==='custom'?null:Number(tmdb.value),
          season:kind.value==='tv'?Number(season.value):null,episode:kind.value==='tv'?Number(episode.value):null,
          version:version.value.trim()||null};
        if (!mapping.title || kind.value!=='custom' && !tmdb.value || kind.value==='tv' && (!season.value || !episode.value)) throw new Error(t(91448,'请填写所选描述需要的编号与季集。'));
      } else if(action.value==='supplement') {
        const parent=target.value==='version'?chosenParent:null;
        if(parent&&parent.file_id===item.file.id)throw new Error(bi('补充视频不能关联自己。','An extra video cannot link to itself.'));
        const retained=target.value==='current'&&originalRelation;
        if(!parent&&!retained&&(!['movie','tv'].includes(kind.value)||!Number.isSafeInteger(Number(tmdb.value))||Number(tmdb.value)<1))
          throw new Error(bi('作品共有关系需要明确电影 / 剧集候选或 TMDb 编号；自建内容请选择父版本。','Work-level extra requires a Movie/Series candidate or TMDb ID; select a parent release for custom items.'));
        if(!supplementTitle.value.trim())throw new Error(bi('请填写补充视频名称。','Enter an extra video title.'));
        mapping={...(retained||{metadata_key:parent?parent.metadata_key:'tmdb:'+kind.value+':'+Number(tmdb.value),
          parent_file_id:parent?parent.file_id:null,parent_revision:parent?parent.revision:null,
          parent_evidence:parent?parent.evidence:null}),kind:supplementKind.value,title:supplementTitle.value.trim()};
      }
      queued=queued.filter(q=>q.command.file_id!==item.file.id);
      const candidate=fields.candidate&&mapping&&fields.candidate.tmdb_id===mapping.tmdb_id&&fields.candidate.media_kind===mapping.kind?fields.candidate:null;
      queued.push({name:item.file.name,anchor:item,candidate,command:{file_id:item.file.id,expected_revision:item.revision,action:action.value,mapping}});
      changedBatch();status(()=>t(91449,'已加入本批，尚未写入。请预览后确认。'));
    }));
    return card;
  }
  async function editFile(entity, announce=true) {
    selectedEntity=entity.entity_id;cancelCandidates();const generation=++viewGeneration, auth=authGeneration;
    const result=await rpc('catalog_item',{file_id:entity.entity_id});
    const record=result.item||result;
    if(authClosed||auth!==authGeneration||generation!==viewGeneration||selectedEntity!==entity.entity_id)return;
    if(!record.file||record.file.id!==entity.entity_id)throw new Error(bi('条目已变化，请刷新。','Item changed; refresh.'));
    editing=record;
    byId('editorRows').replaceChildren(itemCard(editing));byId('rows').classList.add('hidden');
    byId('editorRows').classList.remove('hidden');byId('back').disabled=false;
    if(announce)status(()=>t(91450,'仅按需读取此原文件。候选只是建议，修改仍需逐项预览。'));
  }
  function summaryCard(row) {
    const card=node('article',undefined,'card');card.append(node('h2',row.display_title),
      node('small',t(91451,'%s · %d 个原文件 · %s',labelOf(row.review_state),row.variant_count,row.availability)));
    if(row.entity_kind==='file') {
      const names=(row.sources||[]).map(source=>source.name);
      if(row.source_total>names.length)names.push(bi('等 %d 个来源','and %d sources',row.source_total));
      card.append(node('p',[row.version_label,row.file_name,row.file_size==null?'':row.file_size.toLocaleString()+bi(' 字节',' bytes'),...names].filter(Boolean).join(' · ')));
      if(row.truncated)card.append(node('small',bi('显示已截短，原始名称与整理记录保留。','Display truncated; original name and review record kept.')));
    }
    const direct=row.entity_kind==='file'||row.entity_kind==='work'&&row.media_kind==='unknown';
    const next=row.entity_kind==='work'?(row.media_kind==='tv'?'seasons':'files'):row.entity_kind==='season'?'episodes':'files';
    const open=button(direct?t(91452,'整理此文件'):next==='seasons'?t(91453,'查看季'):next==='episodes'?t(91454,'查看分集'):t(91455,'查看具体文件'),async()=>{
      if(direct){await editFile(row);return;}
      trail.push({query:{...query},cursor,queryStarts:[...queryStarts],queryPage,selectedEntity:row.entity_id});
      query={...query,view:next,parent_entity_id:row.entity_id};resetQueryPage();
      selectedEntity=null;await load();
    });
    if(row.entity_id===selectedEntity&&open.focus)setTimeout(()=>open.focus(),0);
    card.append(open);
    if(!row.supplement&&['work','file'].includes(row.entity_kind))card.append(button(t(91456,'查看补充视频'),async()=>{
      trail.push({query:{...query},cursor,queryStarts:[...queryStarts],queryPage,selectedEntity:row.entity_id});
      query={...query,view:'supplements',parent_entity_id:row.entity_id};resetQueryPage();selectedEntity=null;await load();
    }));
    if(row.supplement)card.append(node('small',bi('补充视频 · ','Extra · ')+row.supplement.title+(row.supplement.state==='verification_required'?bi(' · 关系待核对',' · Link needs check'):'')));
    return card;
  }
  function jobCard(job) {
    const card=node('article',undefined,'card');card.append(node('h2',labelOf(job.state)));
    const counts=job.counts||{};
    card.append(node('p',t(91457,'已扫描 %d 项 · 已发现 %d 个视频',counts.scanned||0,counts.discovered||0)));
    card.append(node('small',({
      CATALOG_NETWORK_INCOMPLETE:bi('网络目录未提供完整子项列表，未推断删除。','Network folder returned an incomplete listing; no deletions inferred.'),
      CATALOG_NETWORK_METADATA_REQUIRED:bi('网络目录缺少大小或精确修改时间，未推断删除。','Network folder lacked size or exact mtime; no deletions inferred.')
    })[job.result_summary]||job.result_summary||''));
    if (job.cancel_requested && ['queued','running'].includes(job.state)) card.append(node('p',bi('已请求取消，等待后台确认。','Cancel requested; awaiting confirmation.')));
    else if (['queued','running'].includes(job.state)) card.append(button(t(91458,'请求取消本次扫描'),async()=>{
      if (!confirm(bi('仅取消本次扫描，已有索引和云端文件保留。继续？','Cancel only this scan? Existing index and cloud files are kept.'))) return;
      const receipt=await rpc('catalog_cancel',{task_id:job.task_id});
      status(()=>receipt.state==='canceled'?bi('后台已确认取消。','Scan cancellation confirmed.'):bi('已请求取消，尚未确认停止。','Cancel requested; stop not yet confirmed.'));await load();
    }));return card;
  }
  function sourceCard(row) {
    const card=node('article',undefined,'card');card.append(node('h2',row.name));
    const observation=row.observation;
    if(observation) {
      const state=observation.latest_state, counts=observation.counts||{};
      card.append(node('p',[(state==='none'?bi('尚未扫描','Never scanned'):state==='cancel_requested'?t(91362,'已请求取消，等待后台确认'):labelOf(state)),
        ({never:bi('未观察范围','Unobserved scope'),partial:bi('仅已提交部分','Committed portion only'),complete:bi('上次完整扫描','Last full scan')})[observation.coverage],
        bi('已扫描 %d 项 / 发现 %d 文件 · 已收录 %d','Scanned %d / Found %d files · Indexed %d',counts.scanned||0,counts.discovered||0,observation.indexed_count||0)].filter(Boolean).join(' · ')));
      if(observation.availability==='source_unavailable')card.append(node('small',bi('来源离线，已保存的整理记录保留。','Source offline; saved review records are kept.')));
      else if(observation.recheck_required)card.append(node('small',bi('观察范围待复核，可重新扫描；播放前仍核验。','Observation scope needs recheck; rescan if needed (verified before play).')));
    }
    card.append(button(t(91459,'查看此来源'),async()=>{source=row.id;sourceName=row.name;tab='items';resetQuery();await load();}));
    card.append(button(t(91460,'重新完整扫描'),async()=>{
      if (!confirm(bi('重新扫描此已登记目录？不修改云端文件。','Rescan this registered folder? Cloud files are never modified.'))) return;
      await rpc('catalog_scan',{source_id:row.id});tab='jobs';resetPage();await load();
    }));return card;
  }
  function historyCard(row) {
    const card=node('article',undefined,'card');card.append(node('h2',row.work_title||row.name));
    function clock(seconds) {const value=Math.max(0,Math.floor(seconds));return Math.floor(value/60)+':'+String(value%60).padStart(2,'0');}
    card.append(node('p',t(91461,'已观看 %s%s',clock(row.position),row.duration==null?bi(' · 总时长未知',' · Duration unknown'):' / '+clock(row.duration))));
    card.append(node('small',row.start_only?bi('历史进度仅供查看；请在电视选择从头播放，不自动续播。','History progress is read-only; start from beginning on TV.'):bi('仅展示当前账号的继续观看摘要，请在电视选择续播。','Read-only Continue Watching summary for current account; resume on TV.')));
    if(row.description)card.append(node('small',row.description));
    if(row.navigation&&row.navigation.view==='files') {
      const open=button(t(91462,'查看文件版本'),async()=>{
        const previous={returnTab:tab,offset,pageStarts:[...pageStarts],pageIndex,query:{...query},cursor,
          queryStarts:[...queryStarts],queryPage,selectedEntity:row.id,source,sourceName,trail:[...trail],
          filters:Object.fromEntries(FILTER_INPUTS.map(name=>[name,byId(name).value]))};
        resetQuery();trail.push(previous);clearQueryFilters();source=null;sourceName='';
        tab='items';query={view:'files',parent_entity_id:row.navigation.parent_entity_id};selectedEntity=row.id;await load();
      });
      card.append(open);if(row.id===selectedEntity&&open.focus)setTimeout(()=>open.focus(),0);
    }
    return card;
  }
  async function loadPlayback() {
    const generation=viewGeneration;
    const session=await post('/manage/api/session',{});
    if(authClosed||generation!==viewGeneration)return;
    applyLocale(session, false);
    recoverPlayback(session);
    const value=await rpc('playback_presentation',{});
    if(authClosed||generation!==viewGeneration)return;
    function renderPlaybackDom() {
      clearLiveUpdaters();
      const card=node('article',undefined,'card');byId('rows').replaceChildren(card);
      byId('previous').disabled=true;byId('next').disabled=true;
      const receiptsPanel=node('section');
      function renderReceipts() {
        receiptsPanel.replaceChildren();
        for(const record of playbackOperations) {
          const receipt=node('div',undefined,'card');
          const label=({
            seek:bi('跳转播放位置','Seek position'),audio_stream:bi('选择音轨','Select audio track'),
            manual_subtitle_stream:bi('选择字幕','Select subtitle'),subtitle_visible:bi('切换字幕显示','Toggle subtitles'),
            user_pause:t(91465,'暂停播放'),user_resume:t(91466,'继续播放'),user_stop:t(91467,'停止播放')
          })[record.command.action];
          const identified=value.available===true&&value.expected;
          const current=identified&&samePlayback(record.command.expected,value.expected);
          receipt.append(node('small',label+(identified?(current?bi('（当前播放）',' (Current)'):bi('（先前播放）',' (Previous)')):bi('（播放归属待核对）',' (Scope pending)'))+
            bi(' · 操作编号 ',' · ID ')+record.command.command_id),node('p',playbackResultText(record)));
          if(playbackUnknown(record))receipt.append(button(bi('核对这次播放操作','Check This Playback Command'),async()=>{
            if(playbackBusy||authClosed||generation!==viewGeneration)return;
            playbackBusy=true;
            try {playbackResult(record,await rpc('playback_receipt',{
              expected:record.command.expected,command_id:record.command.command_id}));}
            catch(error) {if(!authClosed)record.status='unknown';}
            finally {playbackBusy=false;}
            if(!authClosed&&generation===viewGeneration)await load();
          }));
          if(playbackUnknown(record)&&identified&&!current){
            receipt.append(node('small',bi('移除只清除本次授权的核对记录，不能撤销原操作；原操作仍可能已经执行。','Removing clears only this session receipt and does not undo the command.')));
            receipt.append(button(bi('移除此条记录','Forget Receipt'),async()=>{
              if(playbackBusy||authClosed||generation!==viewGeneration)return;
              playbackBusy=true;let removed=false;
              try {
                const fresh=await rpc('playback_presentation',{});
                if(authClosed||generation!==viewGeneration)return;
                if(fresh.available===true&&fresh.expected&&!samePlayback(record.command.expected,fresh.expected)){
                  const result=await rpc('playback_forget',{
                    expected:record.command.expected,command_id:record.command.command_id});
                  if(result.status!=='forgotten'||authClosed||generation!==viewGeneration)return;
                  const index=playbackOperations.indexOf(record);
                  if(index>=0){playbackOperations.splice(index,1);removed=true;}
                }
              } finally {playbackBusy=false;}
              if(!authClosed&&generation===viewGeneration){
                await load();
                if(!removed)status(()=>bi('当前无法核实为先前播放，已保留原操作记录。','Cannot verify as a previous playback; receipt kept.'),true);
              }
            }));
          }
          receiptsPanel.append(receipt);
        }
      }
      renderReceipts();
      if(!value.available){card.append(node('p',t(91463,'当前播放不属于本次授权，或内核不支持安全控制。请在电视操作。')),receiptsPanel);status(()=>t(91464,'播放控制不可用'));return;}
      const expected=frozen(JSON.parse(JSON.stringify(value.expected)));
      const permitted=grantedScopes.includes('playback_control');
      const pending=playbackPending(expected), full=playbackOperations.filter(playbackUnknown).length>=8;
      const editable=permitted&&!pending&&!full;
      const pbControls=[];
      let used=false;
      const detail=node('p',value.subtitle_status||bi('字幕状态尚未确认','Subtitle status unconfirmed'));
      card.append(node('h2',t(91307,'当前播放')),node('p',value.audio_status),detail);
      if(!permitted)card.append(node('small',bi('本次只授权查看；如需控制，请在电视重新选择权限。','Read-only permission granted; reopen on TV to enable playback control.')));
      else if(full)card.append(node('small',bi('待核对记录已满。可核对原回执，或移除先前播放记录后再操作。','Pending receipt journal full; check receipts or forget settled ones first.')));
      else if(pending)card.append(node('small',bi('尚有待核对操作。请先核对原回执；刷新不会重发或解除同实例保护。','Pending command unconfirmed; check receipt first. Refresh will not resend.')));
      const commandStatus=node('p',bi('操作仅提交一次；“已发送”不代表执行成功。','Commands submit once; "sent" does not guarantee execution.'));
      async function send(action,params) {
        if(!editable||used||playbackBusy||playbackPending(expected)||generation!==viewGeneration||authClosed)return;
        used=true;playbackBusy=true;pbControls.forEach(control=>control.disabled=true);
        while(playbackOperations.length>=8){
          const settled=playbackOperations.findIndex(record=>!playbackUnknown(record));
          if(settled<0){playbackBusy=false;return;}
          playbackOperations.splice(settled,1);
        }
        const command=frozen({expected,command_id:id(),action,params});
        const record={command,status:'unknown'};playbackOperations.push(record);
        try {
          let result=await rpc('playback_command',command);
          playbackResult(record,result);
          for(let attempt=0;playbackUnknown(record)&&attempt<6;attempt++) {
            commandStatus.textContent=bi('已发送，等待原生播放器确认…','Sent; awaiting player confirmation…');
            await new Promise(resolve=>setTimeout(resolve,500));
            if(generation!==viewGeneration||authClosed)return;
            result=await rpc('playback_receipt',{expected,command_id:command.command_id});
            playbackResult(record,result);
          }
          if(generation!==viewGeneration||authClosed)return;
          commandStatus.textContent=playbackResultText(record);status(()=>playbackResultText(record),record.status!=='applied');
        } catch(error) {
          if(generation===viewGeneration&&!authClosed){commandStatus.textContent=bi('连接中断或结果未知，请刷新核对；不会自动重发。','Connection interrupted or outcome unknown; refresh to check (never auto-resent).');status(()=>commandStatus.textContent,true);}
        } finally {playbackBusy=false;if(!authClosed&&generation===viewGeneration)renderReceipts();}
      }
      const transportReady=value.transport_protocol===1;
      card.append(node('p',transportReady?({paused:bi('已暂停','Paused'),playing:bi('播放中','Playing')})[value.transport_state]||bi('播放状态未确认','Transport state unconfirmed'):
        bi('内核尚未提供安全的暂停、继续和停止控制。','Kernel does not expose safe pause/resume/stop controls.')));
      for(const [label,action,capability] of [[t(91465,'暂停播放'),'user_pause','can_pause'],
        [t(91466,'继续播放'),'user_resume','can_resume'],[t(91467,'停止播放'),'user_stop','can_stop']]){
        const supported=transportReady&&value[capability]===true;
        const control=button(label,()=>{if(supported)return send(action,{});});
        control.disabled=!editable||!supported;pbControls.push(control);card.append(control);
      }
      function timeLabel(ms){const seconds=Math.max(0,Math.floor(ms/1000));return Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');}
      const slider=node('input');slider.type='range';slider.min='0';slider.max=String(Math.max(0,value.duration_ms-1));slider.step='1000';slider.value=String(value.position_ms);
      slider.disabled=!editable||!value.can_seek;slider.setAttribute('aria-label',t(91468,'播放进度'));
      const position=node('p',timeLabel(value.position_ms)+' / '+timeLabel(value.duration_ms));
      slider.addEventListener('input',()=>position.textContent=timeLabel(Number(slider.value))+' / '+timeLabel(value.duration_ms));
      slider.addEventListener('change',()=>send('seek',{position_ms:Number(slider.value)}));
      pbControls.push(slider);card.append(position,slider);
      function tracks(title,rows,action,truncated) {
        card.append(node('h3',title));
        rows.forEach(row=>{
          const choose=button((row.selected?'✓ ':'')+(row.name||row.language||bi('轨道 %d','Track %d',row.index+1)),()=>send(action,{index:row.index,stream_key:row.stream_key}));
          choose.disabled=!editable;pbControls.push(choose);card.append(choose);
        });
        if(truncated)card.append(node('small',bi('轨道较多，其余请在电视选择。','List truncated; select remaining tracks on TV.')));
      }
      tracks(t(91469,'音轨'),value.audio,'audio_stream',value.audio_truncated);
      tracks(t(91470,'字幕'),value.subtitles,'manual_subtitle_stream',value.subtitles_truncated);
      const visibility=button(value.subtitle_visible?t(91471,'关闭字幕'):t(91472,'显示字幕'),()=>send('subtitle_visible',{visible:!value.subtitle_visible}));
      visibility.disabled=!editable;pbControls.push(visibility);card.append(visibility);
      if(value.chapters.length){card.append(node('h3',bi('原生章节','Chapters')));value.chapters.forEach(chapter=>{
        const choose=button((chapter.name||bi('章节','Chapter'))+' · '+timeLabel(chapter.position_ms),()=>send('seek',{position_ms:chapter.position_ms}));
        choose.disabled=!editable||!value.can_seek;pbControls.push(choose);card.append(choose);
      });}
      card.append(commandStatus,receiptsPanel);status(()=>bi('已读取当前实例；播放或轨道变化后请刷新。','Loaded current playback; refresh after track or playback changes.'));
    }
    lastRowsRender = renderPlaybackDom;
    renderPlaybackDom();
  }
  function isHttpOrHttpsLogo(value) {
    return typeof value==='string'&&/^https?:\/\/[A-Za-z0-9.-]+(?::\d{1,5})?(?:\/[^\s"'<>\\]*)?$/i.test(value);
  }
  function isAllowedRenderedLogo(value) {
    return typeof value==='string'&&/^https:\/\/image\.tmdb\.org\/[A-Za-z0-9/_.-]{1,240}\.(?:jpg|jpeg|png|webp)$/i.test(value);
  }
  function stremioCard(addon) {
    const addonId=String(addon.id||''), card=node('article',undefined,'card');
    card.append(bindText(node('h3'),()=>(addon.name||bi('未命名插件','Unnamed Add-on'))+(addon.version?' v'+addon.version:'')));
    card.append(bindText(node('small'),()=>bi('标识：','ID: ')+addonId+(addon.host?bi(' · 来源主机：',' · Host: ')+addon.host:'')));
    if(addon.logo_rejected===true||(addon.logo&&!isHttpOrHttpsLogo(addon.logo))) {
      card.append(bindText(node('small',undefined,'error'),()=>bi('已拒绝非 HTTP(S) 图标地址','Rejected non-HTTP(S) logo URL')));
    } else if(addon.logo&&isAllowedRenderedLogo(addon.logo)) {
      const img=node('img');img.src=addon.logo;img.alt=addon.name||'';img.loading='lazy';img.referrerPolicy='no-referrer';img.width=48;card.append(img);
    }
    const descNode=addon.description?node('p',addon.description,'muted'):null;
    if(descNode)card.append(descNode);
    const caps=addon.capabilities||{}, selected=addon.selected||{}, row=node('div',undefined,'row');
    if(addon.description_truncated===true&&descNode) {
      row.append(button(()=>bi('查看完整简介','Full Description'),async()=>{
        const detail=await rpc('stremio_detail',{id:addonId});
        if(detail&&detail.addon&&typeof detail.addon.description==='string') {
          descNode.textContent=detail.addon.description;
        }
      }));
    }
    [['stream',()=>bi('视频源','Streams')],['catalog',()=>bi('目录','Catalogs')],['tv',()=>bi('直播','Live TV')]].forEach(([catKey,catLabel])=>{
      if(!caps[catKey])return;
      const enabled=Boolean(selected[catKey]);
      row.append(button(()=>(enabled?bi('✓ 已启用 · ','✓ Enabled · '):bi('未启用 · ','Disabled · '))+catLabel(),async()=>{
        await rpc('stremio_toggle',{id:addonId,category:catKey,enabled:!enabled});
        await loadStremio();
      }));
    });
    row.append(button(()=>t(91477,'移除此插件源'),async()=>{
      if(!confirm(bi('确认移除此自定义插件源？','Remove this custom add-on?')))return;
      await rpc('stremio_remove',{id:addonId});
      await loadStremio();
    }));
    card.append(row);
    return card;
  }
  async function loadStremio() {
    const page=viewGeneration;
    let value=await rpc('stremio_list',offset>0?{offset}:{});
    if(page!==viewGeneration)return;
    let items=value.items||[];
    if(!items.length&&offset>0) {
      pageIndex=Math.max(0,pageIndex-1);
      offset=pageStarts[pageIndex]||0;
      value=await rpc('stremio_list',offset>0?{offset}:{});
      if(page!==viewGeneration)return;
      items=value.items||[];
    }
    nextOffset=value.next_offset==null?null:value.next_offset;
    byId('previous').disabled=offset===0;
    byId('next').disabled=nextOffset==null;
    clearLiveUpdaters();
    lastRowsRender = null;
    const addCard=node('section',undefined,'card');
    addCard.append(bindText(node('h2'),()=>t(91473,'添加自定义 Stremio 插件源')),
      bindText(node('p',undefined,'muted'),()=>bi('仅向当前配置添加自定义 Manifest，页面不回显已保存地址中的凭据参数。','Adds custom Manifest URLs to current profile without echoing saved URL credentials.')));
    const urlInput=field(addCard,()=>t(91474,'Manifest 地址（https:// 或 stremio://）'),'url','');urlInput.maxLength=2048;
    const previewBox=node('div'), actions=node('div',undefined,'row');
    actions.append(button(()=>t(91475,'校验 Manifest'),async()=>{
      const rawUrl=urlInput.value.trim();
      if(!rawUrl)throw new Error(bi('请输入 Manifest 地址。','Enter a Manifest URL.'));
      const checked=await rpc('stremio_validate',{url:rawUrl});
      if(page!==viewGeneration)return;
      const info=checked.manifest||{};
      previewBox.replaceChildren(bindText(node('p'),()=>bi('校验通过：','Validated: ')+(info.name||info.id||bi('未知名称','Unknown'))+(info.version?' v'+info.version:'')));
      status(()=>bi('Manifest 校验通过，可点击添加。','Manifest validated; ready to add.'));
    }),button(()=>t(91476,'添加插件源'),async()=>{
      const rawUrl=urlInput.value.trim();
      if(!rawUrl)throw new Error(bi('请输入 Manifest 地址。','Enter a Manifest URL.'));
      await rpc('stremio_add',{url:rawUrl});
      urlInput.value='';
      await loadStremio();
      status(()=>bi('已添加自定义插件源。','Custom add-on added.'));
    }));
    addCard.append(actions,previewBox);
    const totalCount=Number.isInteger(value.total)?value.total:items.length;
    byId('rows').replaceChildren(addCard,...(items.length?items.map(stremioCard):[bindText(node('p'),()=>bi('当前暂无自定义 Stremio 插件源。','No custom Stremio add-ons configured.'))]));
    status(()=>bi('已读取 Stremio 插件源 · 第 %d 页（本页 %d 项，共 %d 项）。','Loaded Stremio add-ons · Page %d (%d on page, %d total).',pageIndex+1,items.length,totalCount));
  }
  function renderImportDiagnosis(box, diag, awaitingTv) {
    box.replaceChildren();
    if(!diag)return;
    const card=node('article',undefined,'card');
    const c=diag.counts||{};
    card.append(bindText(node('h3'),()=>diag.can_save_t4?bi('校验通过 · 等待电视端确认保存','Validated · Awaiting Confirmation on TV'):bi('配置诊断结果（未写入电视片库）','Config Diagnosis (Library Unchanged)')));
    card.append(node('p',diag.summary_zh||bi('已完成结构诊断。','Structural diagnosis completed.')));
    card.append(bindText(node('small'),()=>bi('SHA256：%s… · 大小：%d 字节','SHA256: %s… · Size: %d bytes',(diag.sha256||'').slice(0,16),diag.byte_length||0)));
    card.append(bindText(node('small'),()=>bi('可用 type-4：%d · 传统 type-3 Spider：%d · 请求头受限：%d · 直播订阅：%d','Usable type-4: %d · Legacy type-3: %d · Restricted headers: %d · Live: %d',c.type4||0,c.type3||0,c.unsupported_headers||0,c.lives||0)));
    if(Array.isArray(diag.type4_names)&&diag.type4_names.length) {
      card.append(bindText(node('p',undefined,'muted'),()=>bi('可导入 T4 站点：','Importable T4 sites: ')+diag.type4_names.join('、')));
    }
    if(Array.isArray(diag.type3_names)&&diag.type3_names.length) {
      card.append(bindText(node('p',undefined,'muted'),()=>bi('识别到的传统 type-3 Spider（需外部 T4 桥接或改连原生 AList/WebDAV/Emby）：','Detected legacy type-3 Spiders (use external T4 bridge or native AList/WebDAV/Emby): ')+
        diag.type3_names.slice(0,10).join('、')+(diag.type3_names.length>10?bi(' 等',' etc.'):'')));
    }
    if(awaitingTv) {
      card.append(bindText(node('p'),()=>bi('请在电视上关闭二维码窗口并在确认框中选择“是”完成保存。','Close the QR window on TV and choose "Yes" to confirm saving.')));
    }
    box.append(card);
  }
  async function loadSourceImport() {
    const page=viewGeneration, cur=await rpc('source_import_status',{});
    if(page!==viewGeneration)return;
    byId('previous').disabled=true;byId('next').disabled=true;
    clearLiveUpdaters(); lastRowsRender = null;
    const uploadCard=node('section',undefined,'card');
    uploadCard.append(bindText(node('h2'),()=>t(91478,'上传 TVBox / 小雅 T4 JSON 配置文件')),
      bindText(node('p',undefined,'muted'),()=>bi('采用 4 KB 受控分片上传（最大 2 MB），支持在普通局域网 HTTP 环境校验整包 SHA-256。0 个可用 type-4 站点时绝不污染电视片库。','4 KB chunked upload (up to 2 MB) with full SHA-256 verification over LAN HTTP. Never modifies TV library when 0 type-4 sites are usable.')));
    const fileLabel=node('label',bi('选择本地 JSON 配置文件','Select local JSON config file')), fileInput=node('input');
    fileInput.type='file';fileInput.accept='.json,application/json';
    fileLabel.append(fileInput);bindLabel(fileLabel,fileInput,()=>bi('选择本地 JSON 配置文件','Select local JSON config file'));uploadCard.append(fileLabel);
    const baseInput=field(uploadCard,()=>bi('可选订阅基址（用于解析相对 ./spider.jar 或相对 api，可留空）','Optional base URL (for relative ./spider.jar or api paths)'),'url','');
    baseInput.maxLength=2048;
    const progressText=bindText(node('small'),()=>bi('尚未选择文件。','No file selected yet.')), resultBox=node('div'), actions=node('div',undefined,'row');
    let activeUploadId=cur.upload_id||null;
    actions.append(button(()=>t(91479,'开始分片上传并诊断'),async()=>{
      const chosen=fileInput.files&&fileInput.files[0];
      if(!chosen)throw new Error(bi('请先选择一份 JSON 配置文件。','Select a JSON config file first.'));
      if(chosen.size<1||chosen.size>2097152)throw new Error(bi('文件大小须在 1 B 到 2 MB 之间。','File size must be between 1 B and 2 MB.'));
      const rawBuf=new Uint8Array(await chosen.arrayBuffer());
      const digest=sha256Hex(rawBuf), uploadId=id();
      activeUploadId=uploadId;
      progressText.textContent=bi('正在初始化上传（共 %d 字节）…','Initializing upload (%d bytes)…',rawBuf.length);
      await rpc('source_import_begin',{
        upload_id:uploadId,
        file_name:(chosen.name||'config.json').slice(0,128),
        total_bytes:rawBuf.length,
        sha256:digest,
        base_url:baseInput.value.trim()
      });
      const CHUNK=4096;
      for(let pos=0;pos<rawBuf.length;pos+=CHUNK) {
        if(authClosed||page!==viewGeneration)return;
        const slice=rawBuf.subarray(pos,Math.min(pos+CHUNK,rawBuf.length));
        await rpc('source_import_chunk',{upload_id:uploadId,offset:pos,data_b64:bytesToBase64(slice)});
        progressText.textContent=bi('已上传 %d / %d 字节…','Uploaded %d / %d bytes…',Math.min(pos+CHUNK,rawBuf.length),rawBuf.length);
      }
      const committed=await rpc('source_import_commit',{upload_id:uploadId});
      activeUploadId=null;
      progressText.textContent=bi('上传与整包 SHA-256 核验已完成。','Upload and SHA-256 verification completed.');
      renderImportDiagnosis(resultBox,committed.diagnosis,committed.awaiting_tv_confirm===true);
      status(()=>committed.awaiting_tv_confirm?bi('配置校验通过，请回到电视确认保存。','Config validated; confirm saving on TV.'):bi('已完成配置诊断（无可直接保存的 type-4 站点）。','Diagnosis finished (no directly saveable type-4 sites).'));
    }),button(()=>t(91480,'取消暂存分片'),async()=>{
      if(!activeUploadId){progressText.textContent=bi('当前无进行中的分片上传。','No active chunked upload.');return;}
      await rpc('source_import_cancel',{upload_id:activeUploadId});
      activeUploadId=null;progressText.textContent=bi('已取消并清理暂存分片。','Cancelled and cleaned staged chunks.');
      status(()=>bi('已清理暂存分片。','Cleaned staged chunks.'));
    }));
    uploadCard.append(progressText,actions);
    if(cur.state==='committed'&&cur.diagnosis) {
      renderImportDiagnosis(resultBox,cur.diagnosis,cur.awaiting_tv_confirm===true);
    }
    byId('rows').replaceChildren(uploadCard,resultBox);
    status(()=>bi('手机配置分片导入已就绪。','Phone config import ready.'));
  }
  async function loadSubtitleUpload() {
    const page=viewGeneration, cur=await rpc('subtitle_upload_status',{});
    if(page!==viewGeneration)return;
    byId('previous').disabled=true;byId('next').disabled=true;
    clearLiveUpdaters(); lastRowsRender = null;
    const card=node('section',undefined,'card');
    card.append(bindText(node('h2'),()=>t(91481,'上传外挂字幕（仅绑定当前所选片源）')),
      bindText(node('p',undefined,'muted'),()=>bi('支持 .srt / .ass / .ssa / .sub / .vtt / .txt（最大 2 MB），保留中文文件名与 UTF-8 / BOM。关闭电视二维码或切换片源立即撤销。','Supports .srt / .ass / .ssa / .sub / .vtt / .txt (max 2 MB), preserving UTF-8/BOM and filenames. Revoked when QR closes or source changes.')));
    if(cur.title)card.append(bindText(node('p'),()=>bi('当前绑定片源：%s','Bound source: %s',cur.title)));
    const fileLabel=node('label',bi('选择本地字幕文件','Select local subtitle file')), fileInput=node('input');
    fileInput.type='file';fileInput.accept='.srt,.ass,.ssa,.sub,.vtt,.txt';
    fileLabel.append(fileInput);bindLabel(fileLabel,fileInput,()=>bi('选择本地字幕文件','Select local subtitle file'));card.append(fileLabel);
    const progressText=bindText(node('small'),()=>cur.state==='committed'&&cur.file_name?bi('已上传字幕：%s','Uploaded subtitle: %s',cur.file_name):bi('尚未选择字幕文件。','No subtitle file selected yet.'));
    const actions=node('div',undefined,'row');
    let activeSubUploadId=cur.upload_id||null;
    actions.append(button(()=>t(91482,'上传并应用字幕'),async()=>{
      const chosen=fileInput.files&&fileInput.files[0];
      if(!chosen)throw new Error(bi('请先选择一份字幕文件。','Select a subtitle file first.'));
      if(chosen.size<1||chosen.size>2097152)throw new Error(bi('字幕大小须在 1 B 到 2 MB 之间。','Subtitle size must be between 1 B and 2 MB.'));
      const rawBuf=new Uint8Array(await chosen.arrayBuffer());
      const digest=sha256Hex(rawBuf), uploadId=id();
      activeSubUploadId=uploadId;
      progressText.textContent=bi('正在初始化字幕上传（共 %d 字节）…','Initializing subtitle upload (%d bytes)…',rawBuf.length);
      await rpc('subtitle_upload_begin',{
        upload_id:uploadId,
        file_name:(chosen.name||'subtitle.srt').slice(0,180),
        total_bytes:rawBuf.length,
        sha256:digest,
        target_id:cur.target_id||undefined
      });
      const CHUNK=4096;
      for(let pos=0;pos<rawBuf.length;pos+=CHUNK) {
        if(authClosed||page!==viewGeneration)return;
        const slice=rawBuf.subarray(pos,Math.min(pos+CHUNK,rawBuf.length));
        await rpc('subtitle_upload_chunk',{upload_id:uploadId,offset:pos,data_b64:bytesToBase64(slice)});
        progressText.textContent=bi('已上传 %d / %d 字节…','Uploaded %d / %d bytes…',Math.min(pos+CHUNK,rawBuf.length),rawBuf.length);
      }
      const committed=await rpc('subtitle_upload_commit',{upload_id:uploadId});
      activeSubUploadId=null;
      progressText.textContent=bi('字幕已接收：%s（电视正在自动挂载播放）。','Subtitle received: %s (TV mounting playback).',committed.file_name||chosen.name);
      status(()=>bi('字幕上传完成，电视将对当前片源起播。','Subtitle upload complete; TV starting playback.'));
    }),button(()=>t(91483,'取消上传'),async()=>{
      if(!activeSubUploadId){progressText.textContent=bi('当前无进行中的字幕上传。','No active subtitle upload.');return;}
      await rpc('subtitle_upload_cancel',{upload_id:activeSubUploadId});
      activeSubUploadId=null;progressText.textContent=bi('已取消并清理暂存字幕。','Cancelled and cleaned staged subtitle.');
      status(()=>bi('已取消字幕上传。','Subtitle upload cancelled.'));
    }));
    card.append(progressText,actions);
    byId('rows').replaceChildren(card);
    status(()=>bi('手机配对字幕上传已就绪。','Paired subtitle upload ready.'));
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
    const generation=++viewGeneration;cancelCandidates();clearLiveUpdaters();byId('groupRows').replaceChildren();
    status(()=>t(91484,'正在读取电视上的当前状态…'));
    byId('filters').classList.toggle('hidden',tab!=='items');
    byId('editorRows').classList.add('hidden');byId('rows').classList.remove('hidden');editing=null;
    byId('back').disabled=tab!=='items'||!trail.length;
    if(tab==='playback'){await loadPlayback();return;}
    if(tab==='stremio'){await loadStremio();return;}
    if(tab==='sourceImport'){await loadSourceImport();return;}
    if(tab==='subtitleUpload'){await loadSubtitleUpload();return;}
    if(tab==='items') {
      const filters={...query,text:byId('keyword').value.trim(),review_state:byId('state').value||null,
        media_kind:byId('mediaKind').value||null,availability:byId('availability').value||null,
        sort:byId('sort').value||'name',source_id:source||mountedSource};
      renderScopeStatus();
      let value;
      try {value=await rpc('catalog_query',{query:filters,cursor,limit:32});}
      catch(error) {
        if(authClosed||generation!==viewGeneration)return;
        if(error.code!=='CATALOG_CURSOR_STALE'||cursor===null)throw error;
        cursor=null;queryStarts=[null];queryPage=0;
        value=await rpc('catalog_query',{query:filters,cursor:null,limit:32});
      }
      if(authClosed||generation!==viewGeneration)return;
      nextCursor=value.next_cursor;
      const itemsList = value.items || [];
      lastRowsRender = () => {
        byId('rows').replaceChildren(...itemsList.map(summaryCard));
        if(!itemsList.length)byId('rows').append(node('p',t(91486,'此范围暂无作品；可调整筛选，或清除筛选后查看当前来源。')));
      };
      lastRowsRender();
      byId('previous').disabled=queryPage===0;byId('next').disabled=nextCursor==null;
      status(()=>t(91487,'作品检索 · 第 %d 页 · 每页最多 32 项；点击具体文件才读取整理记录。',queryPage+1));return;
    }
    const params={offset,limit:5};
    const currentTab=tab;let value;
    try {value=await rpc('catalog_'+currentTab,params);}
    catch(error) {if(currentTab==='jobs'){jobsActive=true;scheduleJobs(!automatic,true);}throw error;}
    nextOffset=value.next_offset;
    const rows=value.items||[];
    lastRowsRender = () => {
      byId('rows').replaceChildren(...rows.map(currentTab==='jobs'?jobCard:currentTab==='history'?historyCard:sourceCard));
      if (!rows.length) byId('rows').append(node('p',t(91488,'此页暂无记录。扫描未完成时仅显示已提交部分。')));
    };
    lastRowsRender();
    byId('previous').disabled=offset===0;byId('next').disabled=nextOffset==null;
    status(()=>t(91489,'已读取当前状态 · 第 %d 页。关闭浏览器不会取消后台任务。',pageIndex+1));
    if(currentTab==='jobs') {updateJobCapsule(rows);jobsActive=rows.some(row=>['queued','running'].includes(row.state));pollDelay=5000;scheduleJobs(!automatic);}
  }
  ['items','sources','jobs','history','playback','stremio','sourceImport','subtitleUpload'].forEach(name=>byId(name+'Tab').addEventListener('click',()=>guarded(async()=>{tab=name;resetPage();await load();})));
  byId('refresh').addEventListener('click',()=>guarded(async()=>{
    if(hasServerLocale&&csrf){try{const s=await post('/manage/api/session',{});applyLocale(s,false);recoverPlayback(s);}catch(e){}}
    await load();
  }));
  for(const control of ['state','mediaKind'])byId(control).addEventListener('change',()=>guarded(async()=>{resetQuery();await load();}));
  for(const control of ['availability','sort'])byId(control).addEventListener('change',()=>guarded(async()=>{resetQueryPage();await load();}));
  byId('search').addEventListener('click',()=>guarded(async()=>{resetQuery();await load();}));
  byId('clearSource').addEventListener('click',()=>guarded(async()=>{source=null;sourceName='';resetQuery();await load();}));
  byId('clearFilters').addEventListener('click',()=>guarded(async()=>{
    clearQueryFilters();resetQuery();await load();
  }));
  byId('back').addEventListener('click',()=>guarded(async()=>{
    if(editing){editing=null;clearLiveUpdaters();await load();return;}
    const previous=trail.pop();if(previous){
      ({query,cursor,queryStarts,queryPage,selectedEntity}=previous);
      if(previous.returnTab){tab=previous.returnTab;({offset,pageStarts,pageIndex,source,sourceName,trail}=previous);
        for(const name of FILTER_INPUTS)byId(name).value=previous.filters[name];}
      await load();
    }
  }));
  byId('next').addEventListener('click',()=>guarded(async()=>{
    if(tab==='items'){if(nextCursor!=null){queryStarts=queryStarts.slice(0,queryPage+1);queryStarts.push(nextCursor);queryPage++;cursor=nextCursor;await load();}}
    else if(nextOffset!=null){pageStarts=pageStarts.slice(0,pageIndex+1);pageStarts.push(nextOffset);pageIndex++;offset=nextOffset;await load();}
  }));
  byId('previous').addEventListener('click',()=>guarded(async()=>{
    if(tab==='items'){queryPage=Math.max(0,queryPage-1);cursor=queryStarts[queryPage];}
    else{pageIndex=Math.max(0,pageIndex-1);offset=pageStarts[pageIndex];}await load();
  }));
  byId('clear').addEventListener('click',()=>{
    if(busy||authClosed||unknown())return;
    queued=[];changedBatch();status(()=>t(91490,'本批已清空，重新选择后请重新预览。已提交回执仍保留。'));
  });
  byId('preview').addEventListener('click',()=>guarded(async()=>{
    if (unknown()) throw new Error(bi('请先核对上一批提交结果。','Check the previous batch outcome first.'));
    if (!queued.length) throw new Error(bi('请先把要修改的条目加入本批。','Add items to the batch queue first.'));
    const plan={chunks:chunks(queued),index:0,phase:'previewing',canceled:false,results:new Map(),sent:new Set(),total:queued.length};
    operation=plan;const previewData=[];let ready=true;const deadline=Date.now()+90000;
    try {
      for(const original of plan.chunks) {
        if(plan.canceled||Date.now()>=deadline)throw new Error(bi('本轮预览已停止或超时，请重新预览。','Preview stopped or timed out; preview again.'));
        batch={snapshot:original,phase:'previewing'};
        const value=await rpc('catalog_preview',{commands:original.commands});
        if(Date.now()>=deadline)throw new Error(bi('本轮预览已到等待期限，请重新预览。','Preview deadline reached; preview again.'));
        if(!batch||batch.snapshot!==original||original.generation!==batchGeneration)return;
        for(const [index,row] of (value.items||[]).entries()) {
          previewData.push({name:(original.entries[index]||{}).name,row});
        }
        ready=ready&&Array.isArray(value.items)&&value.items.length===original.entries.length&&value.items.every(row=>row.status==='ready');
      }
    } catch(error) {if(batch)batch.phase='editing';plan.phase='editing';throw error;}
    if(plan.canceled) {batch.phase='editing';status(()=>bi('预览已取消，请重新预览。','Preview cancelled; preview again.'));return;}
    lastPreviewCardsData=previewData;renderPreviewCards();
    batch={snapshot:plan.chunks[0],phase:ready?'ready':'editing',previewUntil:Date.now()+PREVIEW_MS};
    plan.phase=ready?'ready':'editing';
    const qLen=queued.length, cLen=plan.chunks.length;
    status(()=>ready?t(91491,'请核对全部 %d 项预览，将分 %d 批保存。已保存批次不会因后续冲突自动回滚。',qLen,cLen):t(91492,'本轮包含冲突或无效条目，请刷新后重新选择。'),!ready);
  }));
  function showReceipt(original, rows, indexed=false) {
    const indexedRows=batch.knownRows||new Map();
    rows.forEach((row,index)=>{
      const key=indexed?row.index:index;
      if(Number.isInteger(key)&&key>=0&&key<original.entries.length&&['applied','conflict','failed'].includes(row.status))indexedRows.set(key,row);
    });
    batch.knownRows=indexedRows;
    const complete=original.entries.every((entry,index)=>indexedRows.has(index));
    const all=complete&&original.entries.every((entry,index)=>indexedRows.get(index).status==='applied');
    const card=buildReceiptCard(original,indexedRows,all);
    const old=receipts.findIndex(receipt=>receipt.requestId===original.requestId);
    if(old>=0)receipts.splice(old,1);
    receipts.unshift({requestId:original.requestId,original,indexedRows,all,card});receipts.splice(20);
    byId('receipts').replaceChildren(...receipts.map(receipt=>receipt.card));
    lastPreviewCardsData=null;byId('batchPreview').replaceChildren();
    batch.phase=complete?(all?'applied':'partial'):'unknown';
    if(operation)operation.results.set(original.requestId,indexedRows);
    planProgress();
    status(()=>all?t(91495,'本批已保存。刷新可读取新修订。'):complete?t(91496,'本批部分修改未保存，请查看逐项结果并刷新。'):t(91497,'本批仍有提交结果待核对，已知回执已保留。'),!all);
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
        status(()=>wasUnknown?bi('原提交尚未核对，预览授权已过期。请读取当前修订人工核对，不能盲目重新提交。','Original submission unconfirmed and preview expired. Reload current revisions to verify manually; never resubmit blindly.'):bi('预览已过期，本次提交未获准。请重新预览后再确认。','Preview expired; submission rejected. Preview again before confirming.'),true);
        return;
      }
      batch.phase='unknown';
      planProgress();
      status(()=>bi('提交结果待核对。网络超时或中断不代表后台未保存；原提交编号与内容已保留，请核对原提交。','Submission outcome pending. Timeout/disconnect does not mean unsaved; original ID and payload kept — check original submission.'),true);
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
    byId('planStatus').textContent=t(91498,'已保存 %d/%d，待核对 %d，未保存 %d，未开始 %d%s',saved,operation.total,unchecked,failed,unstarted,operation.canceled?bi('。已停止后续批次。','. Stopped remaining batches.'):bi('。','.'));
  }
  async function runPlan() {
    const plan=operation,deadline=Date.now()+90000;plan.phase='saving';
    while(plan.index<plan.chunks.length&&!plan.canceled) {
      if(Date.now()>=deadline){plan.phase='paused';status(()=>bi('本轮已到等待期限，已保存结果保留。可继续后续批次。','Round deadline reached; saved batches kept. You can continue remaining batches.'));return;}
      const original=plan.chunks[plan.index];
      batch={snapshot:original,phase:'previewing'};
      let value;
      try {value=await rpc('catalog_preview',{commands:original.commands});}
      catch(error) {plan.phase='paused';if(batch)batch.phase='editing';throw error;}
      if(plan.canceled)break;
      if(!Array.isArray(value.items)||value.items.length!==original.entries.length||!value.items.every(row=>row.status==='ready')) {
        batch.phase='editing';plan.phase='conflict';status(()=>bi('本批修订已变化，已停止保存。此前真实回执保留，请重新选择冲突项。','Revisions changed; stopped saving. Previous receipts kept; reselect conflicting items.'),true);return;
      }
      batch.phase='ready';batch.previewUntil=Date.now()+PREVIEW_MS;
      await submit(original);
      if(authClosed)return;
      if(batch.phase!=='applied'){plan.phase=batch.phase;return;}
      plan.index++;
    }
    plan.phase=plan.canceled?'canceled':'complete';planProgress();
    if(plan.phase==='complete' && editing && plan.chunks.some(c=>c.entries.some(e=>e.command.file_id===editing.file.id))) {
      try {await editFile({entity_id:editing.file.id},false);} catch(error) {
        if(!authClosed)status(()=>bi('修改已保存。当前条目未能重新读取，请刷新后再整理。','Changes saved. Refresh this item before editing again.'),true);
      }
    }
    if(plan.canceled)status(()=>bi('已停止未开始的批次。已发提交及其真实回执保留。','Stopped unstarted batches. Sent submissions and receipts kept.'));
  }
  byId('apply').addEventListener('click',()=>guarded(async()=>{
    if(!operation||operation.canceled||!(batch&&batch.phase==='ready'||operation.phase==='paused')||!confirm(bi('确认按逐项预览分批修改本地描述？已保存批次不会自动回滚。','Confirm batched edits as previewed? Saved batches do not auto-rollback.')))return;
    await runPlan();
  }));
  byId('cancelPlan').addEventListener('click',()=>{
    if(!operation)return;operation.canceled=true;planProgress();controls();
    status(()=>bi('已请求停止后续批次。正在进行的提交仍须等待或核对真实回执，不会被撤回。','Requested stop for remaining batches. In-flight submissions still require receipt check and are not undone.'));
  });
  byId('retry').addEventListener('click',()=>guarded(async()=>{
    if(!batch||batch.phase!=='unknown')return;
    const original=batch.snapshot, value=await rpc('catalog_receipt',{request_id:original.requestId});
    if(value.status==='found') {
      showReceipt(original,Array.isArray(value.items)?value.items:[],true);
      if(batch.phase!=='unknown'){resumePlan();return;}
    }
    if(Date.now()<batch.previewUntil) {
      status(()=>bi('正在使用原提交编号与原内容核对；不会新建提交编号。','Checking with original submission ID and payload; never mints a new ID.'));
      await submit(original);
      resumePlan();
    } else {
      batch.phase='unknown_expired';
      status(()=>bi('原回执不可用或不完整，不能判断是否已保存。请读取当前修订后人工核对；不会自动重新提交。','Original receipt unavailable or incomplete; reload current revisions to check manually (never auto-resubmitted).'),true);
    }
  }));
  function resumePlan() {
    if(operation&&batch&&batch.phase==='applied'&&operation.chunks[operation.index]===batch.snapshot) {
      operation.index++;operation.phase=operation.index<operation.chunks.length?'paused':'complete';
      if(operation.phase==='paused'&&!operation.canceled)status(()=>bi('原提交已核对。后续批次尚未开始，点击确认提交继续。','Original submission verified. Click Confirm Submit to continue remaining batches.'));
      planProgress();
    }
  }
  byId('reviewAgain').addEventListener('click',()=>guarded(async()=>{
    if(!batch||batch.phase!=='unknown_expired'||!confirm(bi('原提交结果仍未确认。读取当前修订后逐项人工核对，确认需要修改的内容再重新预览。继续？','Original outcome still unconfirmed. Reload current revisions for manual check before previewing again?')))return;
    const original=batch.snapshot;
    showReceipt(original,[]);queued=[];changedBatch();await load();
    status(()=>bi('已重新读取当前修订。原提交结果未确认，请人工核对后重新选择和预览；修订变化不证明原提交成功。','Reloaded current revisions. Verify manually before reselecting and previewing; revision changes do not prove success.'),true);
  }));
  byId('revoke').addEventListener('click',async()=>{
    if(authClosed)return;
    const token=csrf;closeAuthorization();byId('revoke').disabled=true;
    status(()=>bi('本页已停止操作；正在请求电视结束授权。已发提交不会因关闭页面而撤回。','Stopped local actions; requesting session end on TV. Sent edits are not undone.'));
    try {
      const value=await post('/manage/api/revoke',{}, {control:true,token});
      status(()=>value.revoked===true?t(91499,'电视已确认授权结束，后台任务保持原状态。'):bi('本页已停止操作，电视端撤销尚未确认。请关闭电视二维码窗口。','Local session stopped; TV revocation unconfirmed. Close the TV QR window.'),value.revoked!==true);
    } catch(error) {status(()=>bi('本页已停止操作，电视端撤销尚未确认。请关闭电视二维码窗口或等待授权到期。','Local session stopped; close the TV QR window or wait for expiry.'),true);}
  });
  byId('previewRows').replaceChildren(byId('batchPreview'),byId('receipts'));
  if(document.addEventListener)document.addEventListener('visibilitychange',()=>{
    clearTimeout(pollTimer);pollTimer=null;
    if(document.hidden){cancelCandidates();}
    else{if(hasServerLocale&&csrf)syncLocale();scheduleJobs();}
  });
  controls();
  guarded(async()=>{
    const code=location.hash.slice(1);
    history.replaceState(null,'',location.pathname);
    const session=await post(code?'/manage/api/pair':'/manage/api/session',code?{code}:{});
    csrf=session.csrf;mountedSource=session.source_id||null;
    applyLocale(session, false);
    recoverPlayback(session);
    grantedScopes=session.scopes||[];
    const hasCatalog=!session.scopes||grantedScopes.includes('catalog_read');
    for(const item of ['itemsTab','sourcesTab','jobsTab'])byId(item).classList.toggle('hidden',!hasCatalog);
    byId('jobCapsule').classList.toggle('hidden',!hasCatalog);
    if(hasCatalog)updateJobCapsule();
    byId('batch').classList.toggle('hidden',!hasCatalog);
    byId('playbackTab').classList.toggle('hidden',!grantedScopes.includes('playback_read'));
    byId('stremioTab').classList.toggle('hidden',!grantedScopes.includes('stremio_addons'));
    byId('sourceImportTab').classList.toggle('hidden',!grantedScopes.includes('source_import'));
    byId('subtitleUploadTab').classList.toggle('hidden',!grantedScopes.includes('subtitle_upload'));
    if(!hasCatalog&&grantedScopes.includes('stremio_addons'))tab='stremio';
    if(!hasCatalog&&grantedScopes.includes('source_import'))tab='sourceImport';
    if(!hasCatalog&&grantedScopes.includes('subtitle_upload'))tab='subtitleUpload';
    if(mountedSource){byId('clearSource').disabled=true;byId('clearSource').textContent=t(91340,'当前授权已固定来源');}
    byId('historyTab').classList.toggle('hidden',!hasCatalog||['mounted','local','network','stremio','source_import','subtitle_upload'].includes(session.catalog_kind));
    byId('workspace').classList.remove('hidden');await load();
  });
})();
