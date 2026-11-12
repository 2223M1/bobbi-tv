'use strict';
// Execute the shipped browser script, not a copied lifecycle implementation.
// A minimal DOM and deterministic transport/clock exercise its real event handlers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const flush=()=>new Promise(setImmediate);
class Element {
  constructor(tag) {
    this.tag=tag;this.children=[];this.listeners={};this.value='';this.textContent='';this.disabled=false;
    const classes=new Set();
    this.classList={add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name),
      toggle(name,force){const selected=force===undefined?!classes.has(name):!!force;selected?classes.add(name):classes.delete(name);}};
  }
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=[...children];}
  addEventListener(type,handler){this.listeners[type]=handler;}
  async fire(type='click') {
    if(type==='click'&&this.disabled)return;
    assert.equal(typeof this.listeners[type],'function',this.tag+' has no '+type+' handler');
    return this.listeners[type]({target:this,preventDefault(){},stopPropagation(){}});
  }
}
function text(root){return [root.textContent,...root.children.map(text)].join('\n');}
function find(root,label){if(root.textContent===label)return root;for(const child of root.children){const result=find(child,label);if(result)return result;}return null;}
function row(index=0,revision=0){return {file:{id:(index+1).toString(16).padStart(64,'0'),name:'Episode '+index+'.mkv',parent:'folder'},state:'unmatched',revision,mapping:null,candidates:[],available:true};}
function response(value,status=200){return {ok:status>=200&&status<300,status,json:async()=>value};}
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
async function boot(overrides={}) {
  const filename=overrides.filename||path.resolve(__dirname,'../../addons/plugin.video.bobbi/resources/web/manage.js');
  const source=fs.readFileSync(filename,'utf8');
  const ids=new Map(),requests=[],timers=new Map();let timerId=0,now=100000;
  const element=id=>{if(!ids.has(id))ids.set(id,new Element(id));return ids.get(id);};
  element('workspace').classList.add('hidden');
  const api={element,requests,rows:[row()],handlers:{},now:()=>now,
    async tick(ms){now+=ms;const pending=[...timers.entries()].filter(([key,timer])=>timer.due<=now);pending.forEach(([key,timer])=>{timers.delete(key);timer.fn();});await flush();},
    async expire(){await api.tick(15001);},
    advance(ms){now+=ms;},text:id=>text(element(id)),
    click:id=>element(id).fire(),
    async add(index=0){const card=element('rows').children[index];await find(card,'加入本批修改').fire();},
    field(index,label){return find(element('rows').children[index],label).children[0];}};
  Object.assign(api,overrides);
  const document={getElementById:element,createElement:tag=>new Element(tag),hidden:false,listeners:{},addEventListener(name,handler){this.listeners[name]=handler;}};
  api.visibility=hidden=>{document.hidden=hidden;document.listeners.visibilitychange();};
  const context={document,crypto:webcrypto,AbortController,
    setTimeout(fn,ms){const key=++timerId;timers.set(key,{fn,due:now+ms});return key;},clearTimeout:key=>timers.delete(key),
    Date:{now:()=>now},location:{hash:api.hash||'#pair-example',pathname:'/manage'},history:{replaceState(){}},confirm:()=>true,
    fetch:async(url,options)=>{
      const body=JSON.parse(options.body), action=body.action||url;
      requests.push({url,body,options});
      if(api.transport)return api.transport(url,body,options);
      if(api.handlers[action])return api.handlers[action](body,options);
      if(url==='/manage/api/pair')return response({csrf:'test-csrf'});
      if(url==='/manage/api/revoke')return response({revoked:true});
      if(body.action==='catalog_preview')return response({items:body.params.commands.map(()=>({status:'ready',before:null,after:{kind:'custom'}}))});
      if(body.action==='catalog_apply')return response({items:body.params.commands.map(()=>({status:'applied',revision:1}))});
      if(body.action==='catalog_receipt')return response({status:'missing',items:[]});
      return response({items:api.rows,next_offset:null});
    }};
  vm.runInNewContext(source,context,{filename});await flush();return api;
}
function calls(api,action){return api.requests.filter(request=>request.body.action===action);}

module.exports={boot,calls,deferred,find,flush,response,row,text};
