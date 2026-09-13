(function(g){
  function isoDates(start,end){
    const out=[];
    const a=Date.parse(start+"T00:00:00Z"),b=Date.parse(end+"T00:00:00Z");
    if(!Number.isFinite(a)||!Number.isFinite(b)||a>b)return out;
    for(let t=a;t<=b;t+=86400000)out.push(new Date(t).toISOString().slice(0,10));
    return out;
  }
  function activeOn(p,d){return p.sale_start<=d&&p.sale_end>=d;}
  g.FLYER_DATE_UTILS={isoDates,activeOn};
})(globalThis);
