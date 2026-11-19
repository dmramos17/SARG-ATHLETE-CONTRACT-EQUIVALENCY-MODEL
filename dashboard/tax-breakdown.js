/* Shared NFL/MLB chart; all figures come from the existing annual estimates. */
(function(root){
 'use strict';
 const parts=[
  {key:'remaining',label:'Take-home',color:'#187968',description:'Modeled income remaining after the displayed U.S. taxes.'},
  {key:'federal',label:'Federal',color:'#3b66b3',description:'Estimated U.S. federal income tax.'},
  {key:'payroll',label:'Payroll',color:'#8354a5',description:'Estimated employee payroll taxes, including Social Security and Medicare.'},
  {key:'state',label:'State',color:'#9c581a',description:'Estimated state income taxes after the model’s resident-credit calculations.'},
  {key:'local',label:'Local',color:'#ba4c60',description:'Selected local work taxes supported by the model; this is not every city or county tax.'}
 ];
 const dollars=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v);
 const percent=v=>v>0&&v<.1?'<0.1%':v.toFixed(1)+'%';
 function summarize(result,grossKey){
  if(!result)return {available:false,reason:'Tax estimates for this residence are not available.'};
  const annual=(result.annual||[]).filter(y=>Number.isFinite(y.remaining));
  const income=result[grossKey];
  if(!annual.length||!Number.isFinite(income)||income<=0)return {available:false,reason:'Usable modeled income is needed before a tax breakdown can be displayed.'};
  const amounts={};
  for(const part of parts){
   if(annual.some(y=>!Number.isFinite(y[part.key])&&!(part.key==='local'&&y.local_supported===false)))return {available:false,reason:'A tax component is unavailable; the chart cannot represent it as zero.'};
   amounts[part.key]=annual.reduce((sum,y)=>sum+(Number.isFinite(y[part.key])?y[part.key]:0),0);
  }
  const sum=Object.values(amounts).reduce((a,b)=>a+b,0),tolerance=Math.max(.05,income*1e-9);
  if(Object.values(amounts).some(v=>v<0)||Math.abs(sum-income)>tolerance)return {available:false,reason:'The tax components do not reconcile to modeled income; no proportional chart is shown.'};
  return {available:true,income,amounts,complete:result.coverage_complete??result.complete??false,
   years:annual.map(y=>y.year),localOmitted:annual.some(y=>y.local_supported===false),
   percentages:Object.fromEntries(parts.map(p=>[p.key,amounts[p.key]/income*100]))};
 }
 function add(parent,tag,value,className){const el=document.createElement(tag);if(value)el.textContent=value;if(className)el.className=className;parent.append(el);return el;}
 function render(container,series){
  container.replaceChildren();container.className='tax-breakdown';
  add(container,'h3','Where modeled income goes');
  add(container,'p','Whole included contract window, not one year. Each bar represents 100% of modeled income—not the headline value. Hover, tap, or use Tab and Enter to explore.','tax-breakdown-intro');
  const data=series.map(s=>({...s,data:summarize(s.result,s.grossKey)}));
  const body=add(container,'div','','tax-breakdown-bars');
  const detail=add(container,'div','','tax-breakdown-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  let pinned=null;const buttons=[];
  function show(key,rowIndex){
   const part=parts.find(p=>p.key===key);detail.replaceChildren();
   add(detail,'strong',part.label+' · '+part.description);
   const rows=rowIndex==null?data:data.filter((_,i)=>i===rowIndex);
   for(const row of rows)if(row.data.available)add(detail,'p',row.name+': '+dollars(row.data.amounts[key])+' · '+percent(row.data.percentages[key])+' of '+dollars(row.data.income)+' modeled income.'+(key==='local'&&row.data.localOmitted?' Pre-2025 local taxes are excluded; this amount covers supported years only.':''));
   if(!rows.some(row=>row.data.available))add(detail,'p','No eligible breakdown is available yet.');
   for(const b of buttons)b.el.setAttribute('aria-pressed',String(b.key===key&&(rowIndex==null||b.rowIndex==null||b.rowIndex===rowIndex)));
  }
  function interactive(button,key,rowIndex){
   buttons.push({el:button,key,rowIndex});button.type='button';button.setAttribute('aria-pressed','false');
   button.addEventListener('mouseenter',()=>show(key,rowIndex));button.addEventListener('focus',()=>show(key,rowIndex));
   button.addEventListener('mouseleave',()=>{if(pinned)show(pinned.key,pinned.rowIndex);});
   button.addEventListener('click',()=>{pinned={key,rowIndex};show(key,rowIndex);});
  }
  data.forEach((row,index)=>{
   const section=add(body,'section','','tax-breakdown-row');section.setAttribute('aria-label',row.name+' tax breakdown');
   const heading=add(section,'div','','tax-breakdown-row-heading');add(heading,'h4',row.name);
   if(!row.data.available){add(section,'p',row.data.reason,'tax-breakdown-unavailable');return;}
   add(heading,'span',dollars(row.data.income)+' modeled income');
   const bar=add(section,'div','','tax-breakdown-bar');bar.setAttribute('role','group');bar.setAttribute('aria-label','Share of modeled income for '+row.name);
   for(const part of parts){
    const amount=row.data.amounts[part.key],share=row.data.percentages[part.key];
    if(amount===0)continue; // The legend still exposes zero/omitted components.
    const button=add(bar,'button','','tax-breakdown-segment');button.style.width=share+'%';button.style.background=part.color;
    button.setAttribute('aria-label',row.name+' · '+part.label+': '+dollars(amount)+', '+percent(share)+' of modeled income');
    if(share>=6)add(button,'span',percent(share));interactive(button,part.key,index);
   }
   const labels=add(section,'div','','tax-breakdown-percentages');labels.setAttribute('aria-label',row.name+' category percentages');
   for(const part of parts){const label=add(labels,'button','','tax-breakdown-percentage');const swatch=add(label,'span','','tax-breakdown-swatch');swatch.style.background=part.color;swatch.setAttribute('aria-hidden','true');add(label,'span',part.label);add(label,'strong',percent(row.data.percentages[part.key]));interactive(label,part.key,index);}
   const coverage=add(section,'p',row.coverage_text||(row.data.complete?'Covers the headline-reconciled modeled contract window.':'Partial-contract estimate: only included income and years are represented.'),'tax-breakdown-coverage');
   if(row.data.localOmitted)coverage.append(' Local taxes before 2025 are not modeled and are excluded.');
  });
  show('remaining',null);
 }
 root.TaxBreakdown={summarize,render};
})(typeof window==='undefined'?globalThis:window);
