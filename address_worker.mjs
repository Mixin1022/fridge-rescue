// Deploy with existing static assets, ADDRESS_BOOK KV and ADDRESS_WRITE_TOKEN secret.
export default {async fetch(request,env){
  const path=new URL(request.url).pathname;
  if(path!=='/api/backend-address')return env.ASSETS.fetch(request);
  const reply=(body,status=200)=>Response.json(body,{status,headers:{'Cache-Control':'no-store'}});
  if(!env.ADDRESS_BOOK)return reply({error:'地址登记尚未配置'},503);
  if(request.method==='GET'){
    const value=await env.ADDRESS_BOOK.get('current','json');
    return value?reply(value):reply({error:'电脑尚未登记地址'},404);
  }
  if(request.method!=='PUT')return reply({error:'Method not allowed'},405);
  if(!env.ADDRESS_WRITE_TOKEN||request.headers.get('Authorization')!=='Bearer '+env.ADDRESS_WRITE_TOKEN)return reply({error:'Unauthorized'},401);
  if(Number(request.headers.get('Content-Length')||0)>2048)return reply({error:'Too large'},413);
  let body;try{body=await request.json()}catch{return reply({error:'Invalid JSON'},400)}
  let url;try{url=new URL(body.url)}catch{return reply({error:'Invalid address'},400)}
  if(url.protocol!=='https:'||!/^[-a-z0-9]+\.trycloudflare\.com$/.test(url.hostname)||url.port||url.username||url.password||url.pathname!=='/'||url.search||url.hash)return reply({error:'Invalid tunnel address'},400);
  await env.ADDRESS_BOOK.put('current',JSON.stringify({url:url.origin,updated_at:new Date().toISOString()}));
  return reply({ok:true});
}};
