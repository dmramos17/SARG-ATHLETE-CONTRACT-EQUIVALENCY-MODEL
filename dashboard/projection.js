let projectionRequest=0;
let projectionPlayer=null;
for(const [code,name] of Object.entries(states)){const o=document.createElement('option');o.value=code;o.textContent=name;$('projection-residence').append(o);}
$('projection-residence').value='NY';
const projectionCache=new Map();
async function fetchProjection(query){
 const key=query.toString();
 if(!projectionCache.has(key))projectionCache.set(key,(async()=>{const response=await fetch('/api/contract-projection?'+query);const out=await response.json();if(!response.ok)throw new Error(out.error);return out;})().catch(error=>{projectionCache.delete(key);throw error;}));
 return projectionCache.get(key);
}
function renderComparison(out,baseline){
 $('residence-comparison').hidden=!baseline;
 $('projection-single-totals').hidden=!!baseline;
 if(!baseline)return;
 const baselineName=states[baseline.residence];
 const different=out.residence!==baseline.residence;
 $('baseline-state').textContent=baselineName;
 $('comparison-explanation').textContent=baselineName+' stays as the team-based residence baseline. Picking a state replaces the comparison column. Both columns use the same advanced settings.'+(out.complete?'':' Only known cash years are included in both columns.');
 $('comparison-cash-label').textContent=out.complete?'Reported cash window':'Known-years cash subtotal';
 $('comparison-net-label').textContent=out.complete?'Estimated take-home · scenario mean':'Known-years take-home subtotal';
 $('comparison-tax-label').textContent=out.complete?'Estimated taxes':'Known-years tax subtotal';
 $('comparison-state').textContent=different?states[out.residence]+' · comparison':'Choose another state';
 for(const [suffix,key] of [['cash','gross'],['net','remaining'],['tax','total_tax']]){
  $('baseline-'+suffix).textContent=money(baseline[key]);
  $('comparison-'+suffix).textContent=different?money(out[key]):'—';
 }
 const difference=out.remaining-baseline.remaining;
 $('comparison-difference').textContent=out.remaining==null||baseline.remaining==null?'Verified annual cash is needed before take-home can be compared.':different?states[out.residence]+': '+money(Math.abs(difference))+' '+(difference>=0?'more':'less')+' estimated take-home than the '+baselineName+' baseline.':'Choose a different assumed residence above to compare it with '+baselineName+'.';
}
function configureProjection(row){
 projectionRequest++;projectionPlayer=row;
 $('projection-output').hidden=true;
 $('projection-coverage').textContent='';$('projection-headline').textContent='';
 $('projection-identity').textContent=row.player+' / '+row.team+' · CONTRACT PROJECTION';
 $('projection-residence').value=row.home_state;
 $('projection-filing').value='single';$('projection-advanced').open=false;
 $('projection-bonus').value='0';$('projection-travel').value='1';
 $('projection-bonus').disabled=row.player_id!=='00-0034857';
 loadProjection();
}
$('update-projection').addEventListener('click',loadProjection);
$('projection-residence').addEventListener('change',loadProjection);
for(const id of ['projection-filing','projection-bonus','projection-travel'])$(id).addEventListener('change',()=>{$('projection-output').hidden=true;$('projection-status').textContent='Assumptions changed. Update the contract projection to apply them.';projectionRequest++;$('update-projection').disabled=false;});
async function loadProjection(){
 const request=++projectionRequest;
 if(!projectionPlayer)return;
 const playerId=projectionPlayer.player_id;
 $('projection-status').textContent='Calculating the contract cash window and opponent scenarios…';$('projection-output').hidden=true;$('update-projection').disabled=true;
 try{
  const query=new URLSearchParams({player:playerId,residence:$('projection-residence').value,filing:$('projection-filing').value,qualifying:$('projection-bonus').value,travel_days:$('projection-travel').value});
  const selected=fetchProjection(query);
  const baselineQuery=new URLSearchParams(query);baselineQuery.set('residence',projectionPlayer.home_state);
  const [out,baseline]=await Promise.all([selected,fetchProjection(baselineQuery)]);
  if(request!==projectionRequest)return;
  renderComparison(out,baseline);
  $('projection-annual-caption').textContent='Annual contract projection · '+states[out.residence]+' residence · 2025 tax rules held constant';
  $('projection-total-label').textContent=out.total_label;
  $('projection-tax-label').textContent=out.complete?'Estimated taxes':'Known-years tax subtotal';
  $('projection-net-label').textContent=out.complete?'Estimated take-home · scenario mean':'Known-years take-home subtotal';
  $('projection-coverage').textContent=(out.complete?'Every displayed year has reported cash.':'Partial projection: cash is missing or unusable for '+out.missing_years.join(', ')+'. Totals include known years only.')+(out.reconciles_headline?' Cash totals reconcile to the reported headline value.':' The cash window does not reconcile to headline value; this is not a verified full-contract total.');
  $('projection-headline').textContent='Reported headline value: '+money(out.headline_value)+' · Cash window: '+out.year_start+'–'+out.year_end+'. '+(out.coverage_notes||[]).join(' ');
  $('projection-gross').textContent=money(out.gross);$('projection-net').textContent=money(out.remaining);$('projection-tax').textContent=money(out.total_tax);
  $('projection-range').textContent=out.remaining==null?'Annual cash is needed before a tax total can be calculated.':(out.complete?'Schedule-based take-home range: ':'Known-years take-home range: ')+money(out.low_remaining)+' – '+money(out.high_remaining);
  $('projection-guarantees').textContent=out.fully_guaranteed_at_signing==null?'Reported guarantees: '+money(out.reported_guarantees)+'. Guarantee type and vesting are not independently verified. Scheduled or historical cash is not necessarily guaranteed.':'Reported at signing: '+money(out.fully_guaranteed_at_signing)+' fully guaranteed; '+money(out.reported_total_guarantees)+' total guarantees, including conditional/vesting amounts. The '+money(out.gross)+' scheduled total is not all fully guaranteed.';
  for(const id of ['projection-years','projection-cash','projection-opponents','projection-notes','projection-sources'])$(id).replaceChildren();
  for(const year of out.annual){
   const row=text($('projection-years'),'tr','');for(const v of [year.year,...['cash','federal','payroll','state','local','remaining'].map(k=>money(year[k])),year.schedule_basis])text(row,'td',v);
   const range=text(row.children[6],'small',year.remaining==null?'Cash needed':money(year.low_remaining)+' – '+money(year.high_remaining));range.className='projection-year-range';
   row.title=year.remaining==null?'Annual cash needed before calculation.':'Take-home range '+money(year.low_remaining)+' – '+money(year.high_remaining)+'; '+year.scenarios+' jurisdiction combinations; '+year.duty_days+' modeled duty days.';
   const cash=text($('projection-cash'),'tr','');for(const v of [year.year,...['base_salary','signing_bonus','roster_bonus','workout_bonus','unclassified_cash','cash'].map(k=>money(year[k]))])text(cash,'td',v);
   const group=text($('projection-opponents'),'div','');text(group,'h3',year.year+' · '+year.schedule_basis);
   for(const [home,label] of [[true,'Home'],[false,'Away']])text(group,'p',label+': '+year.opponents.filter(g=>g.home===home).map(g=>g.opponent+(g.stage?' ['+g.stage+']':'')+(g.date?' ('+g.date+(g.date_status==='unconfirmed'?', provisional':'')+')':'')).join(', '));
  }
  out.notes.forEach(n=>text($('projection-notes'),'p',n));
  text($('projection-sources'),'p','Source snapshot checked '+out.accessed_date+'.');
  for(const source of out.sources){const p=text($('projection-sources'),'p','');const a=text(p,'a',source.name);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';}
  $('projection-output').hidden=false;$('projection-status').textContent='Projection ready · '+states[out.residence]+' residence · '+(out.filing==='single'?'single':'married filing jointly')+' · 2025 tax rules held constant.';
 }catch(error){if(request===projectionRequest)$('projection-status').textContent='Projection unavailable: '+error.message;}
 finally{if(request===projectionRequest)$('update-projection').disabled=false;}
}

fetchContracts();
