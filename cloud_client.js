// Included only in the hosted application, never in the standalone offline HTML.
if(CLOUD_MODE){
  function currentJobOutcome(list,recipes,id){
    const job=list.find(j=>j.id===id);
    if(!job)return {state:'missing'};
    if(job.state!=='completed')return {state:job.state,error:job.error};
    const entry=recipes.find(e=>e.id===job.recipe_id);
    if(!entry)return {state:'missing'};
    if((!entry.recipe.auto_review?.passed&&!['ready','needs_confirmation'].includes(entry.recipe.note_status))||entry.recipe.art_status!=='completed')return {state:'incomplete',error:entry.recipe.art_warning};
    return {state:'completed',entry};
  }
  $('review-confirm').parentElement.hidden=true;
  document.querySelector('#review .page-title').textContent='这一份料理便签';
  document.querySelector('#review .subtitle').textContent='选择菜系，收录或告诉我们哪里不对';
  $('review-open').textContent='查看完整便签 ↗';
  const reject=node('button','不符合要求 · 报错','wide');reject.id='reject-recipe';$('confirm-collect').after(reject);
  reject.onclick=async()=>{if(!drafts.length)return;const reason=window.prompt('哪里不符合要求？例如漏步骤、用量错误、插图不对应。');if(!reason?.trim())return;try{await api('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({recipe_id:drafts[0].id,reason:reason.trim()})});drafts.shift();if(drafts.length)startReview();else{view('library-view');await refresh();$('library-status').textContent='已记录报错，这份便签未收录。'}}catch(e){$('review-status').textContent=e.message}};
  const feedbackButton=node('button','查看报错记录');$('collect').append(feedbackButton);
  const feedbackList=node('section',undefined,'paper');feedbackList.hidden=true;$('collect').append(feedbackList);
  feedbackButton.onclick=async()=>{try{const reports=await api('/api/feedback');feedbackList.replaceChildren(node('h3','报错记录'));reports.forEach(r=>feedbackList.append(node('p',r.reason||(r.issues||[]).map(i=>i.text).join('；'))));if(!reports.length)feedbackList.append(node('p','暂无报错'));feedbackList.hidden=false}catch(e){$('cloud-status').textContent=e.message}};
  let backend=localStorage.getItem('fridge-backend-url')||(location.protocol==='file:'?'':location.origin);
  let accessToken=localStorage.getItem('fridge-service-access-token')||localStorage.getItem('fridge-access-token:'+backend)||sessionStorage.getItem('fridge-access-token')||'',pollTimer=null,connected=false,refreshVersion=0;
  let currentJobId=sessionStorage.getItem('fridge-active-job:'+backend)||'';
  function trackJob(job){if(!job?.id)throw Error('后台未返回本次任务编号');currentJobId=job.id;sessionStorage.setItem('fridge-active-job:'+backend,job.id);drafts=[];}
  const panel=node('section',undefined,'paper');panel.innerHTML='<h3>连接我的小厨房</h3><details><summary>后台地址（自动更新）</summary><input id="cloud-url" type="url" placeholder="后台 HTTPS 地址" aria-label="后台地址"></details><div class="row"><input id="cloud-token" type="password" autocomplete="off" placeholder="你的私人访问口令" aria-label="私人访问口令"><button id="cloud-connect" class="primary">连接</button></div><p id="cloud-status" class="status" role="status">正在自动获取后台地址；首次连接只需填写访问口令。</p>';
  $('collect').append(panel);$('cloud-url').value=backend;
  $('processing-help').textContent='连接后台后，识别结果会自动返回，无需导入文件。';$('import').parentElement.hidden=true;
  $('cloud-token').value=accessToken;
  const upload=node('label','上传视频到小厨房','import'),file=node('input');file.type='file';file.accept='video/mp4,video/quicktime,.mp4,.mov';upload.append(file);
  $('save-link').parentElement.after(upload);
  $('save-link').textContent='提交后台识别';$('link-status').previousElementSibling.textContent='上传或提交链接后，由云端处理，提交后可继续添加任务；电脑后台需保持运行。视频限制：250MB、5 分钟。';
  const jobs=node('div');jobs.id='cloud-jobs';$('pending').parentElement.insertBefore(jobs,$('pending'));$('pending').hidden=true;
  $('link-status').textContent='云端获取失败时，可以直接上传你有权处理的视频。';
  const tasksButton=node('button','查看后台任务','wide');$('collect').append(tasksButton);tasksButton.onclick=()=>{view('processing');refresh().catch(e=>{$('processing-status').textContent=e.message})};
  const addAnother=node('button','＋ 添加另一个识别任务','wide');jobs.before(addAnother);addAnother.onclick=()=>view('collect');
  $('processing-help').textContent='任务在电脑后台继续处理，可添加其他任务。完成后由你选择收录或报错。';
  async function api(path,options={}){
    if(!accessToken)throw Error('请先连接你自己的小厨房');
    const response=await fetch(backend+path,{...options,headers:{...(options.headers||{}),'X-Fridge-Token':accessToken},cache:'no-store'});
    const value=await response.json();if(!response.ok)throw Error(value.error||'请求未完成');return value;
  }
  let librarySignature='';
  async function refresh(){const version=++refreshVersion,targetBackend=backend,jobAtStart=currentJobId;const list=await api('/api/jobs');const signature=targetBackend+JSON.stringify(list.map(j=>[j.id,j.state,j.recipe_id,j.library_version]))+(list.some(j=>!j.library_version)?':legacy:'+version:'');const entries=signature===librarySignature?library:await api('/api/recipes');if(version!==refreshVersion||targetBackend!==backend||jobAtStart!==currentJobId)return;const changed=librarySignature!==signature;librarySignature=signature;library=entries.filter(e=>!e.rejected);if(changed){persist();drawLibrary()}jobs.replaceChildren();let processing=false;
    jobs.append(node('h3','后台任务 · '+list.filter(j=>['queued','running'].includes(j.state)).length+' 个进行中'));
    list.forEach(job=>{
      const row=node('div',undefined,'recipe-strip job-card');
      const entry=library.find(e=>e.id===job.recipe_id);
      const warnings=job.warnings||[entry?.recipe.art_warning,...((entry?.recipe.auto_review&&!entry.recipe.auto_review.passed)?(entry.recipe.auto_review.issues||[]).map(i=>i.text):[])].filter(Boolean);
      row.append(node('h4',job.title|| (entry?title(entry):'任务 '+job.id.slice(0,6))));
      row.append(node('p',job.stage));
      if(job.decision==='reported')row.append(node('p','你已报错 · 未收录'));
      if(job.decision==='saved')row.append(node('p','你已收录')); 
      row.append(node('p',({'queued':'排队中 · 可以继续提交其他任务','running':'后台处理中 · 可以离开此页','completed':(job.needs_attention||warnings.length)?'结果有待处理问题':'结果已生成 · 请决定是否收录','failed':'处理失败 · 已保留断点'}[job.state])||job.state));
      if(job.error)row.append(node('p',job.error,'job-warning'));
      for(const warning of warnings)row.append(node('p',warning,'job-warning'));
      if(job.recovered_failures)row.append(node('p','此前失败 '+job.recovered_failures+' 次，相关阶段现已恢复','hint'));
      if(job.failure_history?.length){const history=node('details');history.append(node('summary','之前哪里出过错'));job.failure_history.forEach(t=>history.append(node('p',t.label+'：'+t.error+(t.recovered?'（已恢复）':'（未恢复）'))));row.append(history)}
      if(job.state==='running')row.append(node('p','当前阶段已用 '+Math.round(job.stage_seconds||0)+' 秒','hint'));
      const stages=job.stages||job.timings||[];
      if(stages.length){const detail=node('details'),summary=node('summary','阶段进度与耗时');detail.append(summary);stages.forEach(t=>detail.append(node('p',t.label+' · '+({'completed':'完成','failed':'失败','incomplete':'未完成','running':'处理中'}[t.state]||t.state)+' · '+Number(t.seconds||0).toFixed(1)+' 秒'+((t.cache_hit||t.resumed_snapshot)?' · 复用结果':''))));row.append(detail)}
      if(entry){const open=node('button',entry.reviewed?'查看已收录便签':'查看结果 · 收录或报错');open.onclick=()=>{currentJobId=job.id;drafts=[entry];startReview();$('review-status').textContent=warnings.join('；')};row.append(open)}
      if(job.retryable){const retry=node('button','从断点继续');retry.onclick=async()=>{retry.disabled=true;try{trackJob(await api('/api/jobs/'+job.id+'/retry',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}));await refresh()}catch(e){row.append(node('p',e.message,'job-warning'));retry.disabled=false}};row.append(retry)}
      jobs.append(row);if(['queued','running'].includes(job.state))processing=true;
    });
    if(active==='processing'){const outcome=currentJobOutcome(list,library,currentJobId);$('loading-orb').hidden=!['queued','running'].includes(outcome.state);if(outcome.state==='completed'){$('processing-status').textContent='结果已生成，请在任务卡片中查看，再决定收录或报错。'}else if(outcome.state==='failed'){$('processing-status').textContent='本次处理失败：'+(outcome.error||'请查看任务提示');drafts=[]}else if(outcome.state==='incomplete'){$('processing-status').textContent='本次便签尚未完成：'+(outcome.error||'复核或插画未完成');drafts=[]}else{const job=list.find(j=>j.id===currentJobId);$('processing-status').textContent=outcome.state==='missing'?'尚未找到本次任务，请重新提交。':(job?.stage||'等待处理')+' · '+Math.round(job?.stage_seconds||0)+' 秒';}}
    if(processing&&!pollTimer)pollTimer=setInterval(()=>{if(!document.hidden)refresh().catch(e=>{$('cloud-status').textContent=e.message})},5000);
    if(!processing&&pollTimer){clearInterval(pollTimer);pollTimer=null}
  }
  async function connect(){accessToken=$('cloud-token').value.trim();try{const parsed=new URL($('cloud-url').value.trim());if((parsed.protocol!=='https:'&&!(parsed.protocol==='http:'&&parsed.origin===location.origin&&['localhost','127.0.0.1','[::1]'].includes(parsed.hostname)))||parsed.username||parsed.password||parsed.pathname!=='/'||parsed.search||parsed.hash)throw Error('请填写后台 HTTPS 域名，不含路径');backend=parsed.origin;currentJobId=sessionStorage.getItem('fridge-active-job:'+backend)||'';await refresh();localStorage.setItem('fridge-backend-url',backend);connected=true;drawLibrary();sessionStorage.setItem('fridge-access-token',accessToken);localStorage.setItem('fridge-service-access-token',accessToken);localStorage.setItem('fridge-access-token:'+backend,accessToken);$('cloud-status').textContent='已连接，口令已保存在此设备；后台地址会自动更新。'}catch(e){connected=false;$('cloud-status').textContent=e.message}}
  $('cloud-connect').onclick=connect;
  const forget=node('button','忘记此设备的口令','step-back');panel.append(forget);
  forget.onclick=()=>{for(let i=localStorage.length-1;i>=0;i--){const key=localStorage.key(i);if(key?.startsWith('fridge-access-token:'))localStorage.removeItem(key)}sessionStorage.removeItem('fridge-access-token');localStorage.removeItem('fridge-service-access-token');accessToken='';connected=false;refreshVersion++;if(pollTimer){clearInterval(pollTimer);pollTimer=null}$('cloud-token').value='';$('cloud-status').textContent='已忘记口令，自动连接已关闭。';};
  $('save-link').onclick=async()=>{try{if(!connected)throw Error('请先连接小厨房');trackJob(await api('/api/jobs/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({share:$('link').value})}));$('link').value='';view('processing');$('processing-help').textContent='自动整理和复核完成后生成便签，再选择收录或报错。';$('loading-orb').hidden=false;$('processing-status').textContent='已提交，正在等待处理……';await refresh()}catch(e){$('link-status').textContent=e.message}};
  file.onchange=async e=>{try{if(!connected)throw Error('请先连接小厨房');const video=e.target.files[0];if(!video)return;if(video.size>250*1024*1024)throw Error('视频不能超过 250MB');$('link-status').textContent='正在上传视频，请保持页面打开……';trackJob(await api('/api/jobs/video',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:video}));$('link-status').textContent='上传完成，开始云端处理。';await refresh()}catch(e){$('link-status').textContent=e.message}};
  $('confirm-collect').onclick=async()=>{if(!drafts.length)return;if(!reviewCuisine||!$('review-title').value.trim()){$('review-status').textContent='请选择菜系并填写菜名。已显示的问题会随便签保留。';return}try{const entry={...drafts[0],title:$('review-title').value.trim(),cuisine:reviewCuisine,reviewed:true};await api('/api/recipes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(entry)});drafts.shift();if(drafts.length)startReview();else{view('library-view');await refresh();$('library-status').textContent='已收录到小本。'}}catch(e){$('review-status').textContent=e.message}};
  const post=node('section',undefined,'paper');post.innerHTML='<h3>图文料理也能收</h3><textarea id="post-text" placeholder="粘贴帖子正文（按原顺序）" aria-label="帖子正文"></textarea><label class="import">选择帖子图片<input id="post-images" type="file" accept="image/jpeg,image/png,image/webp" multiple></label><p class="hint">按选取顺序识别图片文字；最多12张，总计20MB。无文字的动作画面暂不识别。</p><button id="submit-post">整理图文</button>'; const fallback=node('details');fallback.append(node('summary','链接获取失败？手动补充图文'),post);$('collect').append(fallback);
  $('submit-post').onclick=async()=>{try{if(!connected)throw Error('请先连接小厨房');const files=[...$('post-images').files];if(files.length>12||files.reduce((n,f)=>n+f.size,0)>20*1024*1024||files.some(f=>f.size>8*1024*1024))throw Error('最多12张，总计20MB，单张8MB');const images=await Promise.all(files.map(f=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=()=>reject(Error('图片读取失败'));r.readAsDataURL(f)})));trackJob(await api('/api/jobs/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:$('post-text').value,images})}));view('processing');$('loading-orb').hidden=false;$('processing-help').textContent='图文整理完成后自动进入核对页。';await refresh()}catch(e){$('link-status').textContent=e.message}};
  const originalDraw=drawLibrary;drawLibrary=function(){originalDraw();const rows=[...$('library').children];rows.forEach((row,index)=>{const entry=collectedEntries()[index];if(!entry)return;row.querySelector('select').onchange=async e=>{try{await api('/api/recipes/'+entry.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({cuisine:e.target.value})});await refresh()}catch(error){$('library-status').textContent=error.message}};const buttons=row.querySelectorAll('button');buttons[1].onclick=async()=>{const value=window.prompt('菜名',title(entry));if(!value?.trim())return;try{await api('/api/recipes/'+entry.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:value.trim()})});await refresh()}catch(e){$('library-status').textContent=e.message}};buttons[2].onclick=async()=>{try{await api('/api/recipes/'+entry.id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({reviewed:!entry.reviewed})});await refresh()}catch(e){$('library-status').textContent=e.message}}})};
  // The cached shell and locally cached library remain usable without the server.
  window.addEventListener('online',()=>{if(connected)refresh().catch(()=>{})});
  let discovering=false;
  async function discoverAndConnect(){
    if(discovering||document.hidden)return;discovering=true;const previous=backend;
    try{
    try{const r=await fetch('/api/backend-address',{cache:'no-store'});if(r.ok){const data=await r.json(),u=new URL(data.url);if(u.protocol==='https:'&&/^[-a-z0-9]+\.trycloudflare\.com$/.test(u.hostname)&&!u.port&&!u.username&&!u.password&&u.pathname==='/'&&!u.search&&!u.hash){backend=u.origin;$('cloud-url').value=backend;localStorage.setItem('fridge-backend-url',backend);currentJobId=sessionStorage.getItem('fridge-active-job:'+backend)||'';}}}catch{}
    if(accessToken&&backend&&(!connected||previous!==backend))await connect();
    }finally{discovering=false}
  }
  discoverAndConnect();
  setInterval(()=>{if(!document.hidden)discoverAndConnect()},30000);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')discoverAndConnect()});
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
}
