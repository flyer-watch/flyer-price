let store="all",dateFilter="all",q="";
const F=window.FLYER_DATA||{meta:{},products:[]};
const P=F.products||[];
const S=document.getElementById("stores"),D=document.getElementById("dates"),L=document.getElementById("list"),SM=document.getElementById("summary");
const storeMap=new Map();
for(const p of P){if(p.store_id&&!storeMap.has(p.store_id))storeMap.set(p.store_id,`${p.chain||""} ${p.store_name||""}`.trim());}
const configuredStores=Array.isArray(F.meta?.stores)?F.meta.stores:[];
for(const s of configuredStores){if(s?.store_id&&!storeMap.has(s.store_id))storeMap.set(s.store_id,s.label||s.store_id);}
const stores=[["all","全店"],...Array.from(storeMap.entries()).sort((a,b)=>a[1].localeCompare(b[1],"ja"))];
function esc(v){return String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
// Date buttons represent flyer-advertised DAILY-SPECIAL dates, not dates inferred from surviving product rows.
// This deliberately keeps a button visible even when extraction produced 0 rows, making recall failures visible.
const configuredDates=Array.isArray(F.meta?.date_buttons)?F.meta.date_buttons:[];
const inferredDates=Array.from(new Set(P.filter(x=>x.sale_start&&x.sale_start===x.sale_end).map(x=>x.sale_start))).sort();
const dates=["all",...(configuredDates.length?configuredDates:inferredDates)];
function exactDayOnly(x,day){return x.sale_start===day&&x.sale_end===day;}
function buttons(el,arr,get,set){el.innerHTML="";arr.forEach(x=>{const v=Array.isArray(x)?x[0]:x,l=Array.isArray(x)?x[1]:(x==="all"?"全日":x),b=document.createElement("button");b.textContent=l;b.className=get()===v?"on":"";b.onclick=()=>{set(v);render()};el.appendChild(b);});}
function render(){
  buttons(S,stores,()=>store,v=>store=v);buttons(D,dates,()=>dateFilter,v=>dateFilter=v);
  const needle=q.toLowerCase();
  let a=P.filter(x=>(store==="all"||x.store_id===store)&&(dateFilter==="all"||exactDayOnly(x,dateFilter))&&(!needle||(x.product_name+" "+(x.specification||"")).toLowerCase().includes(needle)));
  a.sort((x,y)=>(x.store_name||"").localeCompare(y.store_name||"","ja")||(x.product_name||"").localeCompare(y.product_name||"","ja"));
  SM.textContent=dateFilter==="all"?`${a.length}件 / 全${P.length}件`:`${dateFilter}限定 ${a.length}件 / 全${P.length}件`;
  L.innerHTML="";
  for(const p of a){
    const d=document.createElement("div");d.className="card";
    const period=p.sale_start===p.sale_end?p.sale_start:`${p.sale_start}〜${p.sale_end}`;
    d.innerHTML=`<div><div class="badges"><span class="badge">${esc(p.chain)} ${esc(p.store_name)}</span><span class="badge date">${esc(period)}</span></div><div class="name">${esc(p.product_name)}</div><div class="spec">${esc(p.specification||"")}</div>${p.promotion?`<div class="promo">${esc(p.promotion)}</div>`:""}</div><div class="price"><div class="tax">${esc(p.price_in_tax_yen??"—")}円</div><div class="ex">税抜 ${esc(p.price_ex_tax_yen??"—")}円</div></div>`;
    L.appendChild(d);
  }
}
document.getElementById("q").oninput=e=>{q=e.target.value.trim();render();};render();
