(()=>{
 const video=document.getElementById('home-video'),fallback=document.querySelector('.hero-motion-fallback');if(!video||!fallback)return;
 const poster=fallback.getAttribute('src'),motion=fallback.dataset.motion;
 let visible=true,pending=false,playing=false,timer;
 video.muted=true;video.defaultMuted=true;video.loop=true;video.playsInline=true;
 video.setAttribute('muted','');video.setAttribute('playsinline','');
 const active=()=>visible&&!document.hidden;
 function usePoster(){if(fallback.getAttribute('src')!==poster)fallback.setAttribute('src',poster)}
 function useMotion(){if(active()&&!playing&&motion&&fallback.getAttribute('src')!==motion)fallback.setAttribute('src',motion)}
 function sync(){
  if(!active()){clearTimeout(timer);video.pause();usePoster();return}
  if(playing||pending)return;
  pending=true;clearTimeout(timer);timer=setTimeout(useMotion,1200);
  try{Promise.resolve(video.play()).catch(useMotion).finally(()=>{pending=false;if(!active())video.pause()})}
  catch{pending=false;useMotion()}
 }
 video.addEventListener('playing',()=>{playing=true;clearTimeout(timer);usePoster();video.classList.add('is-playing');if(!active())video.pause()});
 for(const event of ['pause','waiting','error','ended'])video.addEventListener(event,()=>{playing=false;video.classList.remove('is-playing');useMotion()});
 for(const event of ['loadeddata','canplay'])video.addEventListener(event,sync);
 document.addEventListener('visibilitychange',sync);window.addEventListener('pageshow',sync);
 for(const event of ['touchend','click','keydown'])document.addEventListener(event,sync,{passive:true});
 if('IntersectionObserver' in window)new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;sync()}).observe(video);
 sync();
})();
