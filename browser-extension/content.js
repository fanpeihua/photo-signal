'use strict';
if(location.hostname==='www.xiaohongshu.com'){
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(message.type!=='collect')return;
    const input=document.querySelector('input[placeholder="搜索小红书"]');
    if(!input||input.value!==message.query)return reply({error:'搜索页尚未就绪'});
    if(document.querySelector('div.filter')?.textContent.includes('已筛选'))return reply({error:'搜索页有额外筛选，无法确认默认综合采样范围'});
    const rows=[...document.querySelectorAll('section.note-item')].map(n=>{
      const a=n.querySelector('a.title');if(!a)return null;
      const u=new URL(a.href);return {title:a.innerText.trim().slice(0,220),url:u.origin+u.pathname,date_label:n.querySelector('.time')?.textContent||'',likes_label:n.querySelector('.count')?.textContent||'',query:message.query,sort:'综合',captured_at:new Date().toISOString()};
    }).filter(r=>r?.title).slice(0,30);
    reply(rows.length?{rows}:{error:'没有可读取的搜索卡片；请检查登录、验证码或页面是否有结果'});
  });
}else{
  const deliver=async()=>{const {batch}=await chrome.storage.local.get('batch');if(batch)window.postMessage({type:'photo-signal-browser-samples',batch},location.origin);};
  window.addEventListener('message',e=>{if(e.source===window&&e.origin===location.origin&&e.data?.type==='photo-signal-ready')deliver();});
  chrome.runtime.onMessage.addListener(m=>{if(m.type==='updated')deliver();});
  deliver();
}
