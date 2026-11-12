'use strict';
const isPlayer=location.pathname.startsWith('/mlb/players/');
$('mlb-landing').hidden=isPlayer;$('mlb-player-view').hidden=!isPlayer;
const mlbColors={LAD:'#235ca9',NYY:'#344c6c',NYM:'#d85b26',BOS:'#bd3039',SEA:'#16776a',PHI:'#c74849',TOR:'#245fa6'};
const teamColor=code=>mlbColors[code]||'#307b70';
const contractInfo=$('mlb-contract-info');
contractInfo.addEventListener('toggle',()=>{contractInfo.querySelector('summary').textContent=contractInfo.open?'Close Contract Information':'Open Contract Information';});
const normalizeMlb=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const mlbMoney=value=>value==null?'—':money(value);
const mlbYears=years=>years.length>1?years[0]+'–'+years[years.length-1]:years.join('');
let mlbPlayers=[],mlbMatches=[],mlbSelected=-1,mlbRequest=0;
const mlbInput=$('mlb-player-search'),mlbSuggestions=$('mlb-suggestions');
function mlbUrl(player){return '/mlb/players/'+encodeURIComponent(player.id);}
function closeMlbSuggestions(){mlbSuggestions.hidden=true;mlbInput.setAttribute('aria-expanded','false');mlbInput.removeAttribute('aria-activedescendant');mlbSelected=-1;}
function searchMlb(){
 closeMlbSuggestions();mlbSuggestions.replaceChildren();const q=normalizeMlb(mlbInput.value.trim());
 const matches=q?mlbPlayers.filter(p=>normalizeMlb(p.name+' '+p.team+' '+p.team_code+' '+p.position).includes(q)):[];
 mlbMatches=matches.slice(0,25);
 if(!q){$('mlb-search-status').textContent=mlbPlayers.length.toLocaleString()+' active-status players · roster snapshot November 5, 2026.';return;}
 if(!matches.length){$('mlb-search-status').textContent='No matching player in this active roster snapshot. Try a team name or a shorter name.';return;}
 for(const [i,p] of mlbMatches.entries()){
  const a=text(mlbSuggestions,'a','');a.href=mlbUrl(p);a.id='mlb-option-'+i;a.tabIndex=-1;a.setAttribute('role','option');a.setAttribute('aria-selected','false');
  text(a,'span',p.team_code,'suggestion-badge').style.background=teamColor(p.team_code);const copy=text(a,'span','','suggestion-copy');text(copy,'strong',p.name);text(copy,'small',p.team+' · '+p.position);text(a,'span',p.tax_years.length?mlbYears(p.tax_years):'Inputs needed','suggestion-status');
 }
 mlbSuggestions.hidden=false;mlbInput.setAttribute('aria-expanded','true');$('mlb-search-status').textContent=matches.length+' matches'+(matches.length>25?' · first 25 shown; keep typing':'')+'. Use arrow keys and Enter to open.';
}
mlbInput.addEventListener('input',searchMlb);
mlbInput.addEventListener('keydown',e=>{
 if(e.key==='Escape'){closeMlbSuggestions();return;}
 if(!mlbMatches.length||mlbSuggestions.hidden)return;
 if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();mlbSelected=(mlbSelected+(e.key==='ArrowDown'?1:-1)+mlbMatches.length)%mlbMatches.length;for(const [i,a] of [...mlbSuggestions.children].entries())a.setAttribute('aria-selected',String(i===mlbSelected));mlbInput.setAttribute('aria-activedescendant','mlb-option-'+mlbSelected);}
 if(e.key==='Enter'){e.preventDefault();location.assign(mlbUrl(mlbMatches[mlbSelected<0?0:mlbSelected]));}
 if(e.key==='Tab')closeMlbSuggestions();
});
$('mlb-search-form').addEventListener('submit',e=>{e.preventDefault();searchMlb();});
document.addEventListener('click',e=>{if(!$('mlb-search-form').contains(e.target))closeMlbSuggestions();});
function sourceLink(parent,label,url){const a=text(parent,'a',label);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;}
function comparisonValues(prefix,result){
 $('mlb-'+prefix+'-cash').textContent=mlbMoney(result?.gross);
 $('mlb-'+prefix+'-remaining').textContent=mlbMoney(result?.remaining);
 $('mlb-'+prefix+'-tax').textContent=mlbMoney(result?.total_tax);
}
function annualTable(result,label){
 if(!result?.annual.length)return;
 const parent=$('mlb-annual-tables');text(parent,'h4',label+' · '+result.included_years.join(', '));
 const wrap=text(parent,'div','','table-wrap'),table=text(wrap,'table',''),head=text(table,'thead',''),header=text(head,'tr','');
 for(const name of ['Year / team','Reported cash','Federal','Payroll','State after credits','Selected local','Modeled U.S. taxes','Remaining cash'])text(header,'th',name);
 const body=text(table,'tbody','');
 for(const row of result.annual){const tr=text(body,'tr','');for(const value of [row.year+' · '+row.team,mlbMoney(row.cash),mlbMoney(row.federal),mlbMoney(row.payroll),mlbMoney(row.state),row.local_supported===false?'Not modeled':mlbMoney(row.local),mlbMoney(row.total_tax),mlbMoney(row.remaining)])text(tr,'td',value);}
}
function dutySummary(result){
 const parent=$('mlb-duty-summary');parent.replaceChildren();
 for(const row of result?.annual||[]){
  text(parent,'h4',row.year+' · '+row.team);text(parent,'p',row.start+'–'+row.end+' · '+row.duty_days+' estimated duty days · '+row.regular_games+' regular-season games, '+row.spring_games+' spring games and '+row.postseason_games+' postseason games. Doubleheaders count once per date.','help');
  text(parent,'p',row.camp_basis,'help');text(parent,'p',row.foreign_days+' foreign-location days. '+row.ambiguous_dates.length+' split-squad date(s) assigned to the spring base.','help');
  const wrap=text(parent,'div','','table-wrap'),table=text(wrap,'table',''),tr=text(text(table,'thead',''),'tr','');for(const label of ['Work location','Estimated days'])text(tr,'th',label);
  const body=text(table,'tbody','');for(const [state,days] of Object.entries(row.state_days).sort()){const r=text(body,'tr','');text(r,'td',state);text(r,'td',String(days));}
  if(row.foreign_days){const r=text(body,'tr','');text(r,'td','Outside U.S. states');text(r,'td',String(row.foreign_days));}
 }
 if(!result?.annual.length)text(parent,'p','No eligible duty-day allocation for this player yet. See the excluded-year reasons above.','help');
}
async function updateMlbComparison(p,data){
 const request=++mlbRequest,select=$('mlb-comparison-state'),code=select.value,filing=$('mlb-filing').value;
 const stateName=state=>data.comparison_states.find(s=>s.code===state)?.name||'Canada · not modeled';
 $('mlb-comparison-heading').textContent=code?stateName(code):'Comparison state';
 comparisonValues('base',null);comparisonValues('comparison',null);
 $('mlb-comparison-status').textContent='Calculating known-year U.S. estimates…';$('mlb-update').disabled=true;
 $('mlb-annual-tables').replaceChildren();
 $('mlb-future-output').hidden=true;$('mlb-future-status').textContent='Calculating contract-wide estimates…';
 const load=async (residence,future=false)=>{
  if(!residence)return null;
  const response=await fetch((future?'/api/mlb/projection?':'/api/mlb/taxes?')+new URLSearchParams({player:p.id,residence,filing,...(future?{scope:'full'}:{})}));const result=await response.json();if(!response.ok)throw new Error(result.error||'MLB estimate unavailable.');return result;
 };
 try{
  const [base,comparison,futureBase,futureComparison]=await Promise.all([load(p.base_state),code?load(code):null,load(p.base_state,true),code?load(code,true):null]);
  if(request!==mlbRequest)return;
  comparisonValues('base',base);comparisonValues('comparison',comparison);
  renderMlbProjection(futureBase,futureComparison,stateName,code);
  const reference=base||comparison;
  $('mlb-comparison-status').textContent=reference?.included_years.length?'Included years: '+reference.included_years.join(', ')+'. Historical cash estimates are separate from future salary scenarios above. All figures are provisional U.S. components only.':p.base_state?'No eligible cash years are available yet. See the coverage notes below.':'Canadian-residence taxes are not modeled. Choose a U.S. comparison state to see the assumed U.S.-resident components.';
  annualTable(base,stateName(p.base_state)+' · base residence');annualTable(comparison,stateName(code)+' · comparison residence');
  $('mlb-year-coverage').replaceChildren();
  for(const row of p.coverage){if(row.reason)text($('mlb-year-coverage'),'p',row.year+' excluded: '+row.reason);}
  const window=p.contract_window; text($('mlb-year-coverage'),'p',window.verified?'Reported contract window: '+window.start+'–'+window.end+'. Calculations stop at '+Math.min(window.end,2026)+'.':'Contract start has not been verified; this page shows the existing 2025/2026 annual cash window only.');text($('mlb-year-coverage'),'p','This historical cash subtotal excludes 2027 onward; future salary scenarios are shown separately above. Missing years are flagged, not treated as zero. Pre-2025 local taxes are not modeled; older state estimates remain provisional. These are eligible-year cash subtotals, not a prediction of the full contract’s after-tax value.');
  dutySummary(reference);$('mlb-tax-notes').replaceChildren();$('mlb-tax-sources').replaceChildren();
  for(const note of reference?.notes||[])text($('mlb-tax-notes'),'p',note);
  for(const year of reference?.included_years||[]){const para=text($('mlb-tax-sources'),'p','');sourceLink(para,year+' MLB published schedule and venues ↗','https://statsapi.mlb.com/api/v1/schedule?sportId=1&season='+year+'&gameTypes=S,R,F,D,L,W&hydrate=venue(location)');}
  if((reference?.included_years||[]).some(year=>year<2025)){const para=text($('mlb-tax-sources'),'p','');sourceLink(para,'MLB historical club appearances ↗','https://statsapi.mlb.com/api/v1/people/'+p.id+'/stats?stats=yearByYear&group=hitting,pitching');}
  for(const [year,url] of Object.entries(data.metadata.workout_sources)){const para=text($('mlb-tax-sources'),'p','');sourceLink(para,year+' official spring workout dates ↗',url);}
  for(const s of reference?.sources||[]){const para=text($('mlb-tax-sources'),'p','');sourceLink(para,s.state+' tax source · '+s.status+' ↗',s.source);}
 }catch(error){if(request===mlbRequest){$('mlb-comparison-status').textContent=error.message;$('mlb-future-status').textContent='Contract estimate unavailable: '+error.message;}}
 finally{if(request===mlbRequest)$('mlb-update').disabled=false;}
}
function renderMlbContract(p){
 const c=p.contract;
 $('mlb-contract-description').textContent=c?(c.description||c.years+'-year reported contract with '+c.team+' · '+c.start_year+'–'+c.end_year+'.'):'Full contract terms are not imported for this player. Available annual cash is listed below; no contract value is inferred from salary.';
 $('mlb-contract-source').hidden=!c;
 if(c){
  for(const [label,value] of [['Reported headline value',mlbMoney(c.headline_value)],['Reported guarantees',mlbMoney(c.reported_guarantees)],['Signing bonus · payment timing unverified unless detailed below',c.signing_bonus==null?'Not separately listed':money(c.signing_bonus)],['Source',c.source_name]]){const div=text($('mlb-contract-summary'),'div','');text(div,'dt',label);text(div,'dd',value);}
  const header=text($('mlb-contract-headers'),'tr','');
  const headers=c.detailed_cash?['Payment year','Salary / deferred cash','Signing cash','Listed incentives','Reported cash','Payment phase']:['Contract year','Reported base salary · not verified cash','Prorated signing bonus · accounting only','Contract status'];
  for(const name of headers)text(header,'th',name);
  for(const row of c.annual){const tr=text($('mlb-cash-rows'),'tr','');for(const value of c.detailed_cash?[row.year,mlbMoney(row.salary_cash),mlbMoney(row.signing_cash),mlbMoney(row.listed_incentives),mlbMoney(row.reported_cash),row.phase]:[row.year,mlbMoney(row.base_salary),mlbMoney(row.prorated_bonus),row.phase])text(tr,'td',value);}
  $('mlb-contract-table-title').textContent=c.detailed_cash?'Reported payment schedule · separate from future salary assumptions':'Reported contract schedule · separate from tax inputs';
  for(const note of c.notes)text($('mlb-contract-notes'),'p',note);
  $('mlb-contract-check').textContent=c.source_name+' snapshot checked '+c.accessed_date+'.';$('mlb-contract-source').href=c.source_url;
 }else{$('mlb-cash-rows').closest('.table-wrap').hidden=true;}
 if(!p.cash_records.length)text($('mlb-cash-sources'),'p','Reported annual cash has not been matched. Missing cash is not treated as zero.','help');
 for(const r of p.cash_records){const para=text($('mlb-cash-sources'),'p',r.year+': '+mlbMoney(r.amount)+' · ');sourceLink(para,'Spotrac total cash ↗',r.source_url);text(para,'small',' · checked '+r.accessed_date+'. '+r.basis);}
}
async function loadMlb(){
 try{
  const response=await fetch('/api/mlb/directory');if(!response.ok)throw new Error('MLB data could not be loaded. Please try again.');const data=await response.json();mlbPlayers=data.players;
  if(isPlayer){
   const id=decodeURIComponent(location.pathname.split('/').pop());const p=mlbPlayers.find(p=>p.id===id);if(!p)throw new Error('This player is not in the saved active roster. Return to MLB player search.');
   $('compare-player-link').href='/compare?league=MLB&player='+encodeURIComponent(p.id);
   document.title=p.name+' · MLB Contract Taxes · SARG';$('mlb-profile-name').textContent=p.name;$('mlb-profile-team').textContent=p.position+' · '+p.team;$('mlb-profile-badge').textContent=p.team_code;document.documentElement.style.setProperty('--team',teamColor(p.team_code));
   const state=data.comparison_states.find(s=>s.code===p.base_state)?.name||'Ontario, Canada · not modeled';$('mlb-base-state').value=state;$('mlb-base-heading').textContent=state+' · base';$('mlb-player-source').href=p.source;
   renderMlbContract(p);text($('mlb-comparison-state'),'option','Select a comparison state').value='';
   for(const s of data.comparison_states)text($('mlb-comparison-state'),'option',s.name).value=s.code;
   $('mlb-comparison-state').addEventListener('change',()=>updateMlbComparison(p,data));$('mlb-update').addEventListener('click',()=>updateMlbComparison(p,data));
   await updateMlbComparison(p,data);
  }else{
   const m=data.metadata;$('mlb-coverage-summary').textContent=m.player_count.toLocaleString()+' active-status players across '+m.team_count+' teams · snapshot '+m.as_of+'. '+m.cash_count.toLocaleString()+' have matched cash; '+m.estimate_count.toLocaleString()+' have at least one eligible schedule/cash year; '+m.projection_count.toLocaleString()+' have reported future salaries to project. Offseason active lists differ from in-season rosters. Historical cash estimates and future salary scenarios are provisional U.S. components. Future years repeat 2025/2026 work patterns under fixed 2026 tax rules.';
   $('mlb-featured-meta').textContent='Roster snapshot · '+m.as_of;
   for(const id of data.featured_ids){const p=mlbPlayers.find(p=>p.id===id);if(!p)continue;const a=text($('mlb-cards'),'a','','contract-card mlb-player-card');a.href=mlbUrl(p);a.style.setProperty('--card-accent',teamColor(p.team_code));const top=text(a,'div','','contract-card-top');text(top,'span',p.team_code,'team-badge');text(top,'span',p.team,'card-team-name');text(a,'h3',p.name);text(a,'p',p.position,'card-context');text(a,'span','Known schedules · '+mlbYears(p.tax_years),'mlb-card-status');text(a,'p','Reported contract value','mlb-card-focus');text(a,'strong',p.contract?.headline_value?compactMoney(p.contract.headline_value):'Cash available','contract-amount');text(a,'p',p.contract?p.contract.years+' years · '+p.contract.start_year+'–'+p.contract.end_year:'Reported annual cash','amount-caption');const foot=text(a,'div','','contract-card-footer');text(foot,'span',p.projection_years?.length?'Future salary estimates available':'Historical cash estimates');text(foot,'span','Open tax information ↗');}
   searchMlb();
  }
 }catch(error){$('mlb-error').hidden=false;$('mlb-error').textContent=error.message;if(isPlayer)$('mlb-player-view').hidden=true;}
 finally{$('mlb-cards').setAttribute('aria-busy','false');}
}
loadMlb();

function renderMlbProjection(base,comparison,stateName,code){
 const reference=base||comparison;
 $('mlb-future-output').hidden=false;
 TaxBreakdown.render($('mlb-tax-breakdown'),[{name:base?stateName(base.residence)+' · Base state':'Ontario, Canada · Base state',result:base,grossKey:'salary'},...(comparison&&(!base||comparison.residence!==base.residence)?[{name:stateName(comparison.residence)+' · Comparison state',result:comparison,grossKey:'salary'}]:[])]);
 $('mlb-future-status').textContent=reference?.annual.length?'Contract window: '+reference.start+'–'+reference.end+'. Published historical schedules and year-specific tax rules through 2026; future years use repeating work patterns and fixed 2026 rules. '+(reference.complete?'Income reconciles to the reported headline value.':'PARTIAL-CONTRACT ESTIMATE. Take-home covers modeled income only, not the full headline deal. ')+(reference.headline_gap?(' Headline/model difference: '+mlbMoney(Math.abs(reference.headline_gap))+' (not taxes).'):''):(reference?.reason||(!base&&!comparison?'Canadian-residence taxes are not modeled. Select a U.S. comparison state.':'No eligible contract salary years.'));
 $('mlb-future-base-heading').textContent=base?stateName(base.residence)+' · base':'Canada · not modeled';
 $('mlb-future-comparison-heading').textContent=code?stateName(code)+' · comparison':'Choose another state';
 for(const [prefix,result] of [['base',base],['comparison',comparison]]){
  for(const [suffix,key] of [['salary','salary'],['net','remaining'],['tax','total_tax']])$('mlb-future-'+prefix+'-'+suffix).textContent=mlbMoney(result?.[key]);
 }
 $('mlb-future-status').classList.toggle('coverage-warning',!!reference?.annual.length&&!reference.complete);
 $('mlb-future-income-label').textContent=reference?.complete?'Modeled contract income':'Modeled income subtotal · partial coverage';
 $('mlb-future-net-label').textContent=reference?.complete?'Estimated contract take-home':'Estimated take-home · modeled income only';
 const parent=$('mlb-future-annual');parent.replaceChildren();
 for(const [result,label] of [[comparison||base,comparison?'Comparison residence':'Base residence']]){
  if(!result?.annual.length)continue;
  text(parent,'h4',stateName(result.residence)+' · '+label);
  const wrap=text(parent,'div','','table-wrap'),table=text(wrap,'table','');
  text(table,'caption','Annual contract projection · '+stateName(result.residence)+' residence');
  const head=text(text(table,'thead',''),'tr','');
  for(const label of ['Year','Salary / verified signing cash','Federal','Payroll','State after credits','Selected local','Estimated U.S. taxes','Estimated take-home'])text(head,'th',label);
  const body=text(table,'tbody','');
  for(const row of result.annual){const tr=text(body,'tr','');for(const value of [row.year+(row.conditional?' *':''),...['salary','federal','payroll','state','local','total_tax','remaining'].map(k=>k==='local'&&row.local_supported===false?'Not modeled':mlbMoney(row[k]))])text(tr,'td',value);}
 }
 const coverage=$('mlb-future-coverage');coverage.replaceChildren();
 const player=mlbPlayers.find(p=>p.id===reference?.player_id);
 if(player?.contract?.headline_value){text(coverage,'p','Reported headline contract value: '+mlbMoney(player.contract.headline_value)+'.');if(reference.salary!=null&&Math.abs(reference.salary-player.contract.headline_value)>1)text(coverage,'p','The modeled income subtotal differs from the headline value; missing years and compensation outside the salary model are not filled in.');}
 for(const note of reference?.coverage_notes||[])text(coverage,'p',note);
 if(reference?.annual.some(r=>r.year<2025))text(coverage,'p','Local taxes before 2025 are not modeled. Those year totals exclude local taxes.');
 if(reference?.conditional_years.length)text(coverage,'p','* Conditional years assume the option/vesting/opt-out path continues: '+reference.conditional_years.join(', ')+'. These salaries are not guaranteed.');
 for(const row of reference?.excluded||[])text(coverage,'p',row.year+' excluded: '+row.reason);
 const method=$('mlb-future-method');method.replaceChildren();
 for(const note of reference?.notes||[])text(method,'p',note);
 if(reference?.source_url)sourceLink(text(method,'p',''),'Reported annual salaries · FanGraphs RosterResource ↗',reference.source_url);
 for(const source of reference?.payment_sources||[])sourceLink(text(method,'p',''),source.name+' ↗',source.url);
 for(const source of reference?.sources||[])sourceLink(text(method,'p',''),source.state+' tax source · '+source.status+' ↗',source.source);
 const days=$('mlb-future-duty');days.replaceChildren();
 for(const template of [2025,2026]){
  const row=reference?.annual.find(r=>r.year>2026&&r.template_year===template);if(!row)continue;
  text(days,'h4',template+' reference pattern · '+row.team);
  text(days,'p',row.duty_days+' estimated duty days · '+row.regular_games+' regular-season games · '+row.spring_games+' spring games · postseason excluded.');
  const wrap=text(days,'div','','table-wrap'),table=text(wrap,'table',''),head=text(text(table,'thead',''),'tr','');
  for(const label of ['Work location','Reference duty days','Share of salary'])text(head,'th',label);
  const body=text(table,'tbody','');
  for(const [state,n] of [...Object.entries(row.state_days),...(row.foreign_days?[['Outside U.S. states',row.foreign_days]]:[])]){const tr=text(body,'tr','');text(tr,'td',state);text(tr,'td',String(n));text(tr,'td',(100*n/row.duty_days).toFixed(2)+'%');}
 }
}
