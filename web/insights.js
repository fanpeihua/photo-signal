/* Rule-based candidates with original evidence; not confirmed defects or market estimates. */
(function(root){
  const rules=[
    {id:'payment',name:'付费与权益体验',topic:'用户体验与付费',match:/收费|付费|会员|订阅|充值|退款|扣费|恢复购买|花钱|要钱|氪金|\b(paywall|subscription|refund|purchase|pricing)\b/i,action:'按原文分清价格预期、免费范围与权益异常；在对应端和版本核验免费入口、购买返回、恢复购买及换机后的状态。'},
    {id:'stability',name:'稳定性体验',topic:'用户体验与付费',match:/闪退|崩溃|打不开|卡死|黑屏|白屏|\b(crash\w*|freez\w*|black screen)\b/i,action:'从原文确认机型、系统、应用版本与入口；在对应设备复现并保留日志，再判断是启动、拍摄还是编辑路径。'},
    {id:'quality',name:'成片质量体验',topic:'画质与评测',match:/模糊|糊了|糊掉|画质|像素|噪点|失真|过曝|偏色|锐化|\b(blurry|blurred|noise|pixelated|overexposed)\b/i,action:'固定同一机位、光线、焦段和输出尺寸，保存原片与效果图各 3 次；对照预览与成片，结合裁切盲评定位质量损失。'},
    {id:'export',name:'保存与实况流程',topic:'实况与创作',match:/保存|导出|实况|相册|存不了|\b(export\w*|saving|save|live photo|gallery)\b/i,action:'按原文重走拍摄或导入、编辑、保存、相册打开和分享；分别核验 Android / iOS 的权限、格式、方向及实况兼容性。'}
  ];
  function build(items,asOf=new Date().toISOString()){
    const end=Date.parse(asOf);if(!Number.isFinite(end))throw Error('简报日期无效');
    const unique=[...new Map(items.filter(i=>i&&typeof i.id==='string').map(i=>[i.id,i])).values()];
    const reviews=unique.filter(i=>i.kind==='reviews'&&i.platform==='App Store'&&i.metric_name==='rating'&&Number.isInteger(i.metric)&&i.metric>=1&&i.metric<=5&&i.published_at&&Date.parse(i.published_at)<=end&&Date.parse(i.published_at)>end-30*864e5);
    const brands=['Kapi','Dazz','ProCCD'].map(brand=>{
      const rows=reviews.filter(i=>i.brand===brand),period=(a,b)=>{const rs=rows.filter(i=>Date.parse(i.published_at)>end-a*864e5&&Date.parse(i.published_at)<=end-b*864e5);return {count:rs.length,negative:rs.filter(i=>i.metric<=2).length};};
      const week=period(7,0),previous=period(14,7);
      // ponytail: recent-page samples only; no market trend claim without a complete sampling source.
      return {brand,count:rows.length,negative:rows.filter(i=>i.metric<=2).length,week,previous,comparable:week.count>=10&&previous.count>=10};
    });
    const candidates=[];
    for(const b of brands)for(const rule of rules){
      const evidence=reviews.filter(i=>i.brand===b.brand&&i.metric<=2&&rule.match.test(i.title+' '+i.summary)).sort((a,b)=>Date.parse(b.published_at)-Date.parse(a.published_at));
      if(evidence.length<2)continue;
      candidates.push({id:b.brand+'-'+rule.id,brand:b.brand,title:b.brand+' · '+rule.name,topic:rule.topic,count:evidence.length,total:b.count,negative:b.negative,action:rule.action,
        hypothesis:b.brand==='Kapi'?'先确认这些评论是否描述同一条可复现路径，以及是否仍影响当前版本。':'先在竞品复现原文路径，再与 Kapi 相同场景对照；不能把竞品抱怨直接当成 Kapi 的差距。',
        evidence:evidence.map(i=>({id:i.id,title:i.title,summary:i.summary,url:i.url,published_at:i.published_at,rating:i.metric}))});
    }
    candidates.sort((a,b)=>(b.brand==='Kapi')-(a.brand==='Kapi')||b.count-a.count||a.id.localeCompare(b.id));
    return {as_of:new Date(end).toISOString(),window_days:30,brands,candidates};
  }
  root.PhotoInsights={build};
  if(typeof module!=='undefined')module.exports={build};
})(typeof window==='undefined'?globalThis:window);
