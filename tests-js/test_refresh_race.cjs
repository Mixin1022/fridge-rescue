const fs=require('fs'),vm=require('vm'),assert=require('assert');
const text=fs.readFileSync('cloud_client.js','utf8');
const snippet=text.slice(text.indexOf('async function refresh()'),text.indexOf('  async function connect()'));
const pending=[],shown=[];
const node=()=>({append(){},replaceChildren(){}});
const ctx={refreshVersion:0,librarySignature:'',backend:'https://backend.example',currentJobId:'old',library:[],active:'library-view',pollTimer:null,
 api:path=>new Promise(resolve=>pending.push({path,resolve})),persist:()=>{},drawLibrary:()=>shown.push(ctx.library.map(x=>x.id)),
 jobs:node(),node,Promise,Math,Number,JSON,setInterval,clearInterval};
vm.createContext(ctx);vm.runInContext(snippet,ctx);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 const old=ctx.refresh();ctx.currentJobId='new';const fresh=ctx.refresh();
 pending[1].resolve([]);await tick();pending[2].resolve([{id:'new'}]);await fresh;
 pending[0].resolve([{id:"old",state:"completed"}]);await tick();pending[3].resolve([{id:'old'}]);await old;
 assert.deepEqual(shown,[['new']]);
 const again=ctx.refresh();pending[4].resolve([]);await again;
 assert.equal(pending.length,5,'unchanged library must not download again');
 console.log('PASS: stale refresh rejected; unchanged library not downloaded again.');
})().catch(e=>{console.error(e);process.exitCode=1});
