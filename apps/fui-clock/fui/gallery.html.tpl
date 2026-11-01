<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FUI Clock gallery</title>
<style>
:root{--bg:#0b0d10;--card:#13171c;--line:#222932;--fg:#cfd8e3;--dim:#7d8896;--acc:#00e5ff}
@media (prefers-color-scheme:light){:root{--bg:#eef1f4;--card:#fff;--line:#d5dbe2;--fg:#1d242c;--dim:#667384;--acc:#0086a8}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 ui-monospace,Consolas,monospace}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
h1{font-size:15px;margin:0;letter-spacing:.08em;text-transform:uppercase;color:var(--acc)}
label{color:var(--dim);display:flex;gap:6px;align-items:center}
button{background:var(--card);color:var(--fg);border:1px solid var(--line);padding:4px 10px;font:inherit;cursor:pointer}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,460px),1fr));gap:14px;padding:16px}
.card{background:var(--card);border:1px solid var(--line);padding:10px}
.card h2{font-size:13px;margin:0 0 2px;display:flex;justify-content:space-between}
.card h2 span{color:var(--dim);font-weight:400}
.card p{margin:0 0 8px;color:var(--dim);font-size:12px}
canvas{display:block;width:100%;height:auto;background:#000;image-rendering:pixelated}
</style></head><body>
<header><h1>FUI Clock</h1>
<button id="pp">pause</button>
<label>speed <input id="sp" type="range" min="0.25" max="2" step="0.25" value="1"></label>
<label><input id="rd" type="checkbox" checked> round LEDs</label>
<span style="color:var(--dim)">8 s per card, across a minute change</span></header>
<main id="m"></main>
<script>
const DATA=/*DATA*/;
const K=8,W=72,H=16;
let playing=true,speed=1,round=true;
const cards=[];
async function inflate(b64){
  const bin=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));
  const s=new Blob([bin]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(s).arrayBuffer());
}
function drawFrame(card,i){
  const {ctx,rgb}=card,o=i*W*H*3;
  ctx.fillStyle="#050607";ctx.fillRect(0,0,W*K,H*K);
  for(let y=0;y<H;y++)for(let x=0;x<W;x++){
    const p=o+(y*W+x)*3,r=rgb[p],g=rgb[p+1],b=rgb[p+2];
    if(!(r|g|b)){ctx.fillStyle="#11151a";}else ctx.fillStyle=`rgb(${r},${g},${b})`;
    if(round){ctx.beginPath();ctx.arc(x*K+K/2,y*K+K/2,K*0.38,0,6.2832);ctx.fill();}
    else ctx.fillRect(x*K+1,y*K+1,K-2,K-2);
  }
}
async function init(){
  const m=document.getElementById("m");
  for(const d of DATA.cards){
    const el=document.createElement("div");el.className="card";
    el.innerHTML=`<h2>${d.name}<span>${d.n} frames</span></h2><p>${d.desc}</p><canvas width="${W*K}" height="${H*K}"></canvas>`;
    m.appendChild(el);
    const ctx=el.querySelector("canvas").getContext("2d");
    cards.push({ctx,n:d.n,rgb:await inflate(d.data)});
    drawFrame(cards[cards.length-1],0);
  }
  let last=performance.now(),acc=0,idx=0;
  function tick(now){
    if(playing){
      acc+=(now-last)*speed;
      const step=1000/DATA.fps;
      while(acc>=step){acc-=step;idx++;}
      cards.forEach(c=>drawFrame(c,idx%c.n));
    }
    last=now;requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
document.getElementById("pp").onclick=e=>{playing=!playing;e.target.textContent=playing?"pause":"play"};
document.getElementById("sp").oninput=e=>speed=+e.target.value;
document.getElementById("rd").onchange=e=>round=e.target.checked;
init();
</script></body></html>
