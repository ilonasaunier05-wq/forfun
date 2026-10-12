/* Lightweight 3D particle shell; speech intensity comes from actual decoded audio. */
'use strict';
(()=>{
 const canvas=document.getElementById('jarvis-orb'),reactor=document.getElementById('reactor');
 const ctx=canvas?.getContext('2d');if(!ctx)return;
 const N=210,points=[],edges=[],golden=Math.PI*(3-Math.sqrt(5));
 for(let i=0;i<N;i++){const y=1-2*(i+.5)/N,r=Math.sqrt(1-y*y),a=i*golden;points.push({x:Math.cos(a)*r,y,z:Math.sin(a)*r});}
 for(let i=0;i<N;i++){const nearest=points.map((p,j)=>({j,d:(p.x-points[i].x)**2+(p.y-points[i].y)**2+(p.z-points[i].z)**2})).filter(p=>p.j!==i).sort((a,b)=>a.d-b.d).slice(0,4);for(const p of nearest)if(p.j>i)edges.push([i,p.j]);}
 let energy=0,target=0,mic=0,playing=false,lastEnergy=0,last=0,angle=0,phase=0,theme='',rgb='87,219,255',accent='187,128,255';
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 window.jarvisOrb={speech(level,active){target=Number.isFinite(level)?Math.max(0,Math.min(level,1)):0;playing=Boolean(active);lastEnergy=performance.now();},microphone(level){mic=Math.max(0,Math.min(Number(level)||0,1));}};
 const resize=()=>{const dpr=Math.min(devicePixelRatio||1,2),size=Math.max(1,canvas.clientWidth);canvas.width=Math.round(size*dpr);canvas.height=canvas.width;ctx.setTransform(canvas.width/600,0,0,canvas.width/600,0,0);};
 new ResizeObserver(resize).observe(canvas);resize();
 function draw(now){requestAnimationFrame(draw);if(document.hidden){last=now;return;}const quiet=reduced.matches||document.body.dataset.reduced==='true';if(now-last<(quiet?100:1000/30))return;const dt=Math.min((now-last)/1000,.1);last=now;
  if(theme!==document.body.dataset.theme){theme=document.body.dataset.theme;const css=getComputedStyle(document.body);rgb=css.getPropertyValue('--rgb').trim();accent=css.getPropertyValue('--rg2').trim();}
  const state=reactor.dataset.state;if(now-lastEnergy>350){target=0;playing=false;}
  const input=playing?target:state==='listening'?Math.min(mic*12,1):0;energy+=(input-energy)*(1-Math.exp(-dt*14));
  if(!quiet){angle+=dt*(state==='thinking'?.38:state==='speaking'?.23:.13);phase+=dt;}
  ctx.clearRect(0,0,600,600);const radius=quiet?198:198+energy*24,cy=Math.cos(angle),sy=Math.sin(angle),tilt=.23,ct=Math.cos(tilt),st=Math.sin(tilt);
  const projected=points.map((p,i)=>{const ripple=quiet?1:1+energy*.065*Math.sin(p.y*9+phase*7+i*.12);let x=(p.x*cy+p.z*sy)*ripple,z=(-p.x*sy+p.z*cy)*ripple,y=p.y*ct-z*st;z=p.y*st+z*ct;const perspective=1/(1-z*.12);return{x:300+x*radius*perspective,y:300+y*radius*perspective,z,alpha:.18+(z+1)*.34};});
  const glow=ctx.createRadialGradient(300,300,40,300,300,260);glow.addColorStop(0,`rgba(${rgb},${.025+energy*.035})`);glow.addColorStop(.7,`rgba(${rgb},${.035+energy*.045})`);glow.addColorStop(1,`rgba(${rgb},0)`);ctx.fillStyle=glow;ctx.fillRect(0,0,600,600);
  ctx.lineWidth=.7+energy*.7;for(const [a,b]of edges){const p=projected[a],q=projected[b];ctx.strokeStyle=`rgba(${rgb},${Math.min(.52,(p.alpha+q.alpha)*(.1+energy*.13))})`;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke();}
  const ordered=projected.map((p,i)=>({...p,i})).sort((a,b)=>a.z-b.z);for(const p of ordered){const bright=p.i%11===0;ctx.fillStyle=`rgba(${bright?accent:rgb},${Math.min(1,p.alpha+energy*.16)})`;ctx.beginPath();ctx.arc(p.x,p.y,(bright?2.25:1.4)+(p.z+1)*.45+energy*.7,0,Math.PI*2);ctx.fill();}
  canvas.dataset.state=state;canvas.dataset.energy=energy.toFixed(3);
 }
 requestAnimationFrame(draw);
})();
