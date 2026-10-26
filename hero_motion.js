/* Local mesh deformation preview. No network or generative video calls. */
(()=>{
 const host=document.getElementById('motion-hero');if(!host)return;
 const img=host.querySelector('img'),canvas=host.querySelector('canvas'),button=host.querySelector('button');
 if(!canvas.getContext)return;const ctx=canvas.getContext('2d');if(!ctx)return;
 const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');let paused=reduce.matches,visible=true,frame=0,last=0,time=0;
 const cols=40,rows=50;
 // Normalized joint regions are specific to kitchen-motion-source-v1.png.
 function point(x,y,t){
  const region=(cx,cy,sx,sy)=>{const r=((x-cx)/sx)**2+((y-cy)/sy)**2;return r>=1?0:(1-r)**3};
  const wave=(cx,cy,sx,sy,angle)=>{const k=region(cx,cy,sx,sy),a=angle*k;return [(Math.cos(a)-1)*(x-cx)-Math.sin(a)*(y-cy),Math.sin(a)*(x-cx)+(Math.cos(a)-1)*(y-cy)]};
  let dx=0,dy=0;
  // Upper back expands very slightly; waist and hand on fridge stay fixed.
  const breath=Math.sin(t*1.28);
  const back=region(.59,.33,.19,.19);dx+=back*.0012*breath;dy-=back*.0018*breath;
  // Wind acts below the waist, increasing toward free fabric edges.
  const hem=region(.51,.64,.28,.18)*Math.max(0,(y-.49)/.22);dx+=hem*.004*Math.sin(t*.92);dy+=hem*.001*Math.sin(t*.92+.4);
  // Milk and tomato hands pivot in restricted areas, no whole-scene movement.
  for(const [cx,cy,sx,sy,phase] of [[.075,.252,.048,.055,0],[.216,.272,.055,.064,1],[.075,.455,.055,.068,.4],[.223,.458,.055,.066,1.4]]){
   const v=wave(cx,cy,sx,sy,.12*Math.sin(t*2.2+phase));dx+=v[0];dy+=v[1];
  }
  // Sleeping bread: slow shallow chest rise, body remains anchored.
  dy-=region(.17,.81,.16,.12)*.0017*Math.sin(t*1.15);
  // Mushroom offering hand and held strawberry move together, shoulder anchored.
  dy-=region(.846,.761,.082,.073)*.007*(.5+.5*Math.sin(t*1.25));
  // Brief local eyelid compression; independent, slow blink schedules.
  const blink=(period,offset)=>{const q=(t+offset)%period;return q<.42?Math.sin(Math.PI*q/.42)**2:0};
  for(const [cx,cy,sx,sy,period,offset] of [[.525,.166,.028,.015,6.8,2],[.583,.157,.027,.014,6.8,2],[.222,.326,.025,.019,4.9,.9]]){
   dy-=(y-cy)*.87*region(cx,cy,sx,sy)*blink(period,offset);
  }
  return [(x+dx)*canvas.width,(y+dy)*canvas.height];
 }
 function triangle(src,dst){
  const [a,b,c]=src,[u,v,w]=dst;
  const d=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]);
  const aa=((v[0]-u[0])*(c[1]-a[1])-(w[0]-u[0])*(b[1]-a[1]))/d;
  const cc=((w[0]-u[0])*(b[0]-a[0])-(v[0]-u[0])*(c[0]-a[0]))/d;
  const bb=((v[1]-u[1])*(c[1]-a[1])-(w[1]-u[1])*(b[1]-a[1]))/d;
  const dd=((w[1]-u[1])*(b[0]-a[0])-(v[1]-u[1])*(c[0]-a[0]))/d;
  ctx.save();ctx.beginPath();const center=[(u[0]+v[0]+w[0])/3,(u[1]+v[1]+w[1])/3];
  [u,v,w].forEach((p,i)=>{const dx=p[0]-center[0],dy=p[1]-center[1],length=Math.hypot(dx,dy)||1;const q=[p[0]+dx/length*.45,p[1]+dy/length*.45];i?ctx.lineTo(...q):ctx.moveTo(...q)});
  ctx.closePath();ctx.clip();ctx.setTransform(aa,bb,cc,dd,u[0]-aa*a[0]-cc*a[1],u[1]-bb*a[0]-dd*a[1]);ctx.drawImage(img,0,0,canvas.width,canvas.height);ctx.restore();
 }
 function draw(t){ctx.clearRect(0,0,canvas.width,canvas.height);
  for(let j=0;j<rows;j++)for(let i=0;i<cols;i++){
   const uv=[[i/cols,j/rows],[(i+1)/cols,j/rows],[(i+1)/cols,(j+1)/rows],[i/cols,(j+1)/rows]];
   const src=uv.map(p=>[p[0]*canvas.width,p[1]*canvas.height]),dst=uv.map(p=>point(...p,t));
   triangle([src[0],src[1],src[2]],[dst[0],dst[1],dst[2]]);triangle([src[0],src[2],src[3]],[dst[0],dst[2],dst[3]]);
  }
 }
 function tick(now){frame=0;if(paused||!visible||document.hidden){last=0;return}if(now-last>=42){time+=last?Math.min((now-last)/1000,.1):0;last=now;draw(time)}frame=requestAnimationFrame(tick)}
 function sync(){button.textContent=paused?'点击播放轻动效':'暂停轻动效';host.querySelector('small').textContent=paused?'当前静止 · 点击上方按钮播放':'局部动作试版 · 呼吸、挥手、眨眼与睡眠泡泡';button.setAttribute('aria-pressed',String(!paused));canvas.hidden=paused;img.hidden=!paused;bubbles.hidden=paused||!visible||document.hidden;cancelAnimationFrame(frame);frame=0;last=0;if(!paused&&visible&&!document.hidden)frame=requestAnimationFrame(tick)}
 const bubbles=document.createElement('span');bubbles.className='sleep-bubbles';bubbles.setAttribute('aria-hidden','true');bubbles.innerHTML='<i></i><i></i><i></i>';host.append(bubbles);
 function ready(){canvas.width=Math.min(img.naturalWidth,840);canvas.height=Math.round(canvas.width*img.naturalHeight/img.naturalWidth);button.hidden=false;draw(time);sync()}
 button.onclick=()=>{paused=!paused;sync()};img.addEventListener('load',ready);if(img.complete&&img.naturalWidth)ready();
 reduce.addEventListener('change',e=>{paused=e.matches;sync()});document.addEventListener('visibilitychange',sync);
 if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(host);
})();
