'use strict';
async function status(){const {enabled,last}=await chrome.storage.local.get(['enabled','last']);document.querySelector('#status').textContent=(enabled?'定时采样已开启':'定时采样已停止')+'\n'+(last?`最后尝试 ${last.attempted_at}\n本轮 ${last.count} 条\n${last.errors.join('\n')}`:'尚未执行；安装不等于采样成功');}
for(const type of ['enable','run','stop'])document.querySelector('#'+type).onclick=async()=>{if(type==='run'&&!(await chrome.storage.local.get('enabled')).enabled)return document.querySelector('#status').textContent='请先开启采样。';await chrome.runtime.sendMessage({type});status();};
document.querySelector('#export').onclick=async()=>{const {batch}=await chrome.storage.local.get('batch');if(!batch)return;const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(batch,null,2)],{type:'application/json'}));a.href=url;a.download='photo-signal-browser-samples.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
chrome.storage.onChanged.addListener(status);status();
