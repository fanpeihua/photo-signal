/* Local-only, untrusted browser samples. No account IDs, access signatures or inferred sentiment. */
(function(root){
  function merge(existing,batch,topicRules={},clock=Date.now()){
    if(batch?.version!==1||!Array.isArray(batch.rows)||batch.rows.length>1000)throw Error('浏览器采样格式错误或超过 1000 条');
    const result=new Map(existing.map(i=>[i.id,i]));
    for(const r of batch.rows){
      const at=Date.parse(r.captured_at||batch.captured_at),first=Date.parse(r.first_observed_at||r.captured_at||batch.captured_at);
      if(!Number.isFinite(at)||!Number.isFinite(first)||at>clock+60000||first>at)throw Error('采样时间无效');
      if(typeof r.title!=='string'||!r.title.trim()||r.title.length>220||typeof r.query!=='string'||r.query.length>80)throw Error('采样标题或关键词无效');
      const u=new URL(r.url),m=u.pathname.match(/^\/(?:explore|search_result)\/([0-9a-f]{24})\/?$/);
      if(u.protocol!=='https:'||u.hostname!=='www.xiaohongshu.com'||u.port||u.username||u.password||!m)throw Error('只接受小红书笔记链接');
      const id='xhs-'+m[1],old=result.get(id);if(old&&Date.parse(old.last_seen)>=at)continue;
      const title=r.title.trim(),date=String(r.date_label||'').slice(0,40),likes=String(r.likes_label||'').slice(0,20);
      let published=null;
      if(/^\d{4}-\d{2}-\d{2}$/.test(date)){const d=new Date(date+'T00:00:00Z');if(Number.isFinite(+d)&&d.toISOString().startsWith(date)&&Date.parse(date+'T00:00:00+08:00')<=at)published=date+'T00:00:00+08:00';}
      const text=title.toLowerCase(),topics=Object.entries(topicRules).filter(([,words])=>Array.isArray(words)&&words.some(w=>{w=w.toLowerCase();return /^[a-z0-9 -]+$/.test(w)?new RegExp('(^|[^a-z])'+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'([^a-z]|$)').test(text):text.includes(w);})).map(([t])=>t);
      const order=r.sort==='最新'?'最新':'综合';
      result.set(id,{id,title,url:u.origin+u.pathname,platform:'小红书',source_id:'xiaohongshu',kind:'browser',brand:/kapi|咔皮/i.test(title)?'Kapi':/dazz/i.test(title)?'Dazz':/proccd/i.test(title)?'ProCCD':'',summary:`浏览器搜索「${r.query}」· ${order}排序 · 页面日期 ${date||'未显示'} · 点赞 ${likes||'未显示'}。日期未带年份或为相对时间时不推算发布时间。`,published_at:published,first_seen:old?.first_seen||new Date(first).toISOString(),last_seen:new Date(at).toISOString(),topics:topics.length?topics:['行业动态'],sentiment:'未判定',sentiment_basis:'搜索标题不足以判断情绪',metric:null,metric_name:'',metric_delta:null,search_url:'https://www.xiaohongshu.com/search_result?keyword='+encodeURIComponent(title)});
    }
    if(result.size>2000)throw Error('本地观察超过 2000 条，请先备份整理');
    return [...result.values()];
  }
  root.PhotoBrowserSamples={merge};if(typeof module!=='undefined')module.exports={merge};
})(typeof window==='undefined'?globalThis:window);
