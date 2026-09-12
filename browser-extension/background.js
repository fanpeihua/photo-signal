'use strict';
const QUERIES=['摄影','咔皮相机','Dazz','ProCCD'],SITES=['https://fanpeihua.github.io/photo-signal/*','http://127.0.0.1:8840/*'];
let running=false;
async function schedule(){const {enabled}=await chrome.storage.local.get('enabled');if(enabled&&!await chrome.alarms.get('sample'))await chrome.alarms.create('sample',{periodInMinutes:120});}
async function run(){
  if(running)return;running=true;
  const attempted_at=new Date().toISOString(),errors=[];let count=0;
  try{
    const {batch}=await chrome.storage.local.get('batch'),rows=new Map((batch?.rows||[]).map(r=>[r.url,r]));
    // ponytail: four recent-page samples, at most 30 cards each; full-history search requires another authorized source.
    for(const query of QUERIES){
      const {enabled}=await chrome.storage.local.get('enabled');if(!enabled)break;
      let tab;
      try{
        tab=await chrome.tabs.create({url:'https://www.xiaohongshu.com/search_result?keyword='+encodeURIComponent(query),active:false});
        let result;
        for(let attempt=0;attempt<25;attempt++){
          try{result=await chrome.tabs.sendMessage(tab.id,{type:'collect',query});if(result?.rows?.length)break;}catch{}
          await new Promise(resolve=>setTimeout(resolve,1000));
        }
        if(!result?.rows?.length)throw Error(result?.error||'页面未响应');
        for(const r of result.rows){r.first_observed_at=rows.get(r.url)?.first_observed_at||r.captured_at;rows.set(r.url,r);count++;}
      }catch(e){errors.push(query+'：'+e.message);}finally{if(tab){const current=await chrome.tabs.get(tab.id).catch(()=>null);if(current&&!current.active&&current.url?.startsWith('https://www.xiaohongshu.com/search_result'))await chrome.tabs.remove(tab.id).catch(()=>{});}}
    }
    const saved=[...rows.values()].sort((a,b)=>Date.parse(b.captured_at)-Date.parse(a.captured_at)).slice(0,1000);
    await chrome.storage.local.set({batch:{version:1,captured_at:new Date().toISOString(),rows:saved},last:{attempted_at,count,errors}});
    for(const tab of await chrome.tabs.query({url:SITES}))chrome.tabs.sendMessage(tab.id,{type:'updated'}).catch(()=>{});
  }catch(e){await chrome.storage.local.set({last:{attempted_at,count,errors:[...errors,e.message]}});}finally{running=false;}
}
chrome.alarms.onAlarm.addListener(a=>{if(a.name==='sample')run();});
chrome.runtime.onStartup.addListener(async()=>{await schedule();const {enabled,last}=await chrome.storage.local.get(['enabled','last']);if(enabled&&(!last||Date.now()-Date.parse(last.attempted_at)>7200000))run();});
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.url!==chrome.runtime.getURL('popup.html'))return;
  if(message.type==='enable'){chrome.storage.local.set({enabled:true}).then(schedule).then(run);reply({ok:true});}
  if(message.type==='stop'){chrome.storage.local.set({enabled:false}).then(()=>chrome.alarms.clear('sample'));reply({ok:true});}
  if(message.type==='run'){run();reply({ok:true});}
});
schedule();
