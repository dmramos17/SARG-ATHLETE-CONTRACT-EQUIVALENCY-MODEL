function projectionCoverageComplete(out){return out.coverage_complete??out.complete;}
let projectionRequest=0;
let projectionPlayer=null;
// Residence choices use 2025 NFL stadium and practice states from teams.csv.
const nflResidenceStates=new Set(["AZ", "CA", "CO", "FL", "GA", "IL", "IN", "LA", "MA", "MD", "MI", "MN", "MO", "NC", "NJ", "NV", "NY", "OH", "PA", "TN", "TX", "VA", "WA", "WI"]);
for(const [code,name] of Object.entries(states).filter(([code])=>nflResidenceStates.has(code))){const o=document.createElement('option');o.value=code;o.textContent=name;$('projection-residence').append(o);}
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
 $('comparison-explanation').textContent=baselineName+' stays as the team-based residence baseline. Picking a state replaces the comparison column. Both columns use the same advanced settings.'+(projectionCoverageComplete(out)?'':' Only known cash years are included in both columns.');
 $('comparison-cash-label').textContent=projectionCoverageComplete(out)?'Reported cash window':'Modeled cash subtotal';
 $('comparison-net-label').textContent=projectionCoverageComplete(out)?'Estimated take-home · scenario mean':'Take-home · modeled income only';
 $('comparison-tax-label').textContent=projectionCoverageComplete(out)?'Estimated taxes':'Taxes · modeled income only';
 $('comparison-state').textContent=different?states[out.residence]+' · comparison':'Choose another state';
 for(const [suffix,key] of [['cash','gross'],['net','remaining'],['tax','total_tax']]){
  $('baseline-'+suffix).textContent=money(baseline[key]);
  $('comparison-'+suffix).textContent=different?money(out[key]):'—';
 }
 const difference=out.remaining-baseline.remaining;
 $('comparison-difference').textContent=out.remaining==null||baseline.remaining==null?'Verified annual cash is needed before take-home can be compared.':different?states[out.residence]+': '+money(Math.abs(difference))+' '+(difference>=0?'more':'less')+' estimated take-home than the '+baselineName+' baseline.':'';
}
function configureProjection(row){
 projectionRequest++;projectionPlayer=row;
 $('compare-player-link').href='/compare?league=NFL&player='+encodeURIComponent(row.player_id);
 $('open-contract-info').href='/players/'+encodeURIComponent(row.player_id);
 $('projection-output').hidden=true;
 $('projection-coverage').textContent='';$('projection-headline').textContent='';
 $('projection-identity').textContent=row.player+' / '+row.team+' · CONTRACT PROJECTION';
 $('team-location-state').value=states[row.home_state];
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
  TaxBreakdown.render($('projection-tax-breakdown'),[{name:states[baseline.residence]+' · Base state',result:baseline,grossKey:'gross'},...(out.residence!==baseline.residence?[{name:states[out.residence]+' · Comparison state',result:out,grossKey:'gross'}]:[])]);
  renderContractHistory(out,baseline);
  $('projection-annual-caption').textContent='Annual contract projection · '+states[out.residence]+' residence · 2025 tax rules held constant';
  $('projection-total-label').textContent=projectionCoverageComplete(out)?out.total_label:'Modeled cash subtotal';
  $('projection-tax-label').textContent=projectionCoverageComplete(out)?'Estimated taxes':'Taxes · modeled income only';
  $('projection-net-label').textContent=projectionCoverageComplete(out)?'Estimated take-home · scenario mean':'Take-home · modeled income only';
  $('projection-coverage').hidden=projectionCoverageComplete(out);
  $('projection-coverage').textContent=projectionCoverageComplete(out)?'':'Partial-contract estimate: '+(out.coverage_issues||[]).join(' ');
  $('projection-headline').textContent='Reported headline value: '+money(out.headline_value)+' · Cash window: '+out.year_start+'–'+out.year_end+'. '+(out.coverage_notes||[]).join(' ');
  $('projection-gross').textContent=money(out.gross);$('projection-net').textContent=money(out.remaining);$('projection-tax').textContent=money(out.total_tax);
  $('projection-range').textContent=out.remaining==null?'Annual cash is needed before a tax total can be calculated.':(projectionCoverageComplete(out)?'Schedule-based take-home range: ':'Known-years take-home range: ')+money(out.low_remaining)+' – '+money(out.high_remaining);
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
  $('projection-output').hidden=false;$('projection-status').textContent='';
 }catch(error){if(request===projectionRequest)$('projection-status').textContent='Projection unavailable: '+error.message;}
 finally{if(request===projectionRequest)$('update-projection').disabled=false;}
}

fetchContracts();

function renderContractHistory(out,baseline){
 const history=out.history,base=baseline.history;
 const root=$('contract-history-output');root.replaceChildren();
 if(!history){text(root,'p','Historical contract information is unavailable.');return;}
 text(root,'p','Reported contract start '+history.year_start+' · cash window through '+history.year_end+'. Each year uses its own tax rules. This is separate from the unchanged full-contract forecast; do not add the two totals together.');
 const wrap=text(root,'div','');wrap.className='table-wrap';
 const table=text(wrap,'table','');const head=text(table,'thead','');const headers=text(head,'tr','');
 for(const v of ['Included years only',states[base.residence]+' · Base State',out.residence===base.residence?'Choose another state':states[out.residence]+' · comparison'])text(headers,'th',v);
 const body=text(table,'tbody','');
 for(const [label,key] of [['Reported cash','gross'],['Estimated take-home','remaining'],['Estimated taxes','total_tax']]){
  const row=text(body,'tr','');text(row,'th',label);text(row,'td',money(base[key]));text(row,'td',out.residence===base.residence?'—':money(history[key]));
 }
 text(root,'p','Included years: '+(history.included_years.join(', ')||'None')+'.'+(history.excluded_years.length?' Excluded years: '+history.excluded_years.join(', ')+'.':''));
 const annualWrap=text(root,'div','');annualWrap.className='table-wrap';
 const annual=text(annualWrap,'table','');text(annual,'caption','Contract start through 2026 · '+states[out.residence]+' residence · year-specific tax rules');
 const annualHead=text(text(annual,'thead',''),'tr','');
 for(const v of ['Year','Reported team','Cash','Federal','Payroll','State','Selected local','Take-home','Coverage'])text(annualHead,'th',v);
 const annualBody=text(annual,'tbody','');
 for(const year of history.annual){
  const row=text(annualBody,'tr','');
  for(const v of [year.year,year.team||'Unverified',money(year.cash),...['federal','payroll','state'].map(k=>year.status==='estimated'?money(year[k]):'Unavailable'),year.status!=='estimated'?'Unavailable':year.local_supported?money(year.local):'Not modeled',year.status==='estimated'?money(year.remaining):'Unavailable',year.reason||year.duty_days+' modeled duty days'])text(row,'td',v);
 }
 const details=text(root,'details','');text(details,'summary','Historical assumptions & sources');
 history.notes.forEach(n=>text(details,'p',n));
 for(const source of history.sources){if(!source.url)continue;const a=text(text(details,'p',''),'a',source.name);a.href=source.url;a.target='_blank';a.rel='noopener noreferrer';}
}
