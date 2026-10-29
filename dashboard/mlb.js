'use strict';
const isPlayer=location.pathname.startsWith('/mlb/players/');
$('mlb-landing').hidden=isPlayer;$('mlb-player-view').hidden=!isPlayer;
const mlbColors={LAD:'#235ca9',NYY:'#344c6c',NYM:'#d85b26'};
const normalizeMlb=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
let mlbPlayers=[],mlbMatches=[],mlbSelected=-1;
const mlbInput=$('mlb-player-search'),mlbSuggestions=$('mlb-suggestions');
function mlbUrl(player){return '/mlb/players/'+encodeURIComponent(player.id);}
function closeMlbSuggestions(){mlbSuggestions.hidden=true;mlbInput.setAttribute('aria-expanded','false');mlbInput.removeAttribute('aria-activedescendant');mlbSelected=-1;}
function searchMlb(){
 closeMlbSuggestions();mlbSuggestions.replaceChildren();const q=normalizeMlb(mlbInput.value.trim());
 mlbMatches=q?mlbPlayers.filter(p=>normalizeMlb(p.name+' '+p.team+' '+p.team_code+' '+p.position).includes(q)):[];
 if(!q){$('mlb-search-status').textContent='Three sample profiles · Full rosters and tax estimates coming soon.';return;}
 if(!mlbMatches.length){$('mlb-search-status').textContent='No matching sample profile. Try Ohtani, Judge, or Soto. Full roster search is coming soon.';return;}
 for(const [i,p] of mlbMatches.entries()){
  const a=text(mlbSuggestions,'a','');a.href=mlbUrl(p);a.id='mlb-option-'+i;a.tabIndex=-1;a.setAttribute('role','option');a.setAttribute('aria-selected','false');
  text(a,'span',p.team_code,'suggestion-badge').style.background=mlbColors[p.team_code];const copy=text(a,'span','','suggestion-copy');text(copy,'strong',p.name);text(copy,'small',p.team+' · Sample profile');text(a,'span','Preview','suggestion-status');
 }
 mlbSuggestions.hidden=false;mlbInput.setAttribute('aria-expanded','true');$('mlb-search-status').textContent=mlbMatches.length+' sample '+(mlbMatches.length===1?'profile':'profiles')+'. Use arrow keys and Enter to open.';
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
async function loadMlb(){
 try{
  const response=await fetch('/api/mlb/directory');if(!response.ok)throw new Error('MLB preview could not be loaded. Please try again.');const data=await response.json();mlbPlayers=data.players;
  if(isPlayer){
   const id=decodeURIComponent(location.pathname.split('/').pop());const p=mlbPlayers.find(p=>p.id===id);if(!p)throw new Error('This sample profile is not available. Return to MLB player search to choose Ohtani, Judge, or Soto.');
   document.title=p.name+' · MLB Preview · SARG';$('mlb-profile-name').textContent=p.name;$('mlb-profile-team').textContent=p.position+' · '+p.team;$('mlb-profile-badge').textContent=p.team_code;document.documentElement.style.setProperty('--team',mlbColors[p.team_code]);
   const state=data.comparison_states.find(s=>s.code===p.base_state).name;$('mlb-base-state').value=state;$('mlb-base-heading').textContent=state+' · base';$('mlb-player-source').href=p.source;
   renderMlbContract(p.contract);
   $('mlb-base-cash').textContent=money(p.contract.reported_cash_total);
   text($('mlb-comparison-state'),'option','Select a comparison state').value='';
   for(const s of data.comparison_states)text($('mlb-comparison-state'),'option',s.name).value=s.code;
   $('mlb-comparison-state').addEventListener('change',()=>{
    const selected=data.comparison_states.find(s=>s.code===$('mlb-comparison-state').value);
    $('mlb-comparison-heading').textContent=selected?selected.name:'Comparison state';$('mlb-comparison-cash').textContent=selected?money(p.contract.reported_cash_total):'—';$('mlb-comparison-status').textContent=selected?state+' versus '+selected.name+' · Layout preview only; MLB calculations are coming soon.':'Choose a comparison state to preview the layout.';
   });
  }else{
   for(const p of mlbPlayers){const a=text($('mlb-cards'),'a','','contract-card mlb-player-card');a.href=mlbUrl(p);a.style.setProperty('--card-accent',mlbColors[p.team_code]);const top=text(a,'div','','contract-card-top');text(top,'span',p.team_code,'team-badge');text(top,'span',p.team,'card-team-name');text(a,'h3',p.name);text(a,'p',p.position+' · 2025 team','card-context');text(a,'span','Spotrac snapshot','mlb-card-status');text(a,'p',p.focus,'mlb-card-focus');text(a,'strong',compactMoney(p.contract.headline_value),'contract-amount');text(a,'p',p.contract.years+' years · '+p.contract.start_year+'–'+p.contract.end_year+' · Tax estimates coming soon','amount-caption');const foot=text(a,'div','','contract-card-footer');text(foot,'span','MLB preview');text(foot,'span','Open player ↗');}
  }
 }catch(error){$('mlb-error').hidden=false;$('mlb-error').textContent=error.message;if(isPlayer)$('mlb-player-view').hidden=true;}
 finally{$('mlb-cards').setAttribute('aria-busy','false');}
}
function renderMlbContract(c){
 $('mlb-contract-description').textContent=c.years+'-year reported contract with '+c.team+' · '+c.start_year+'–'+c.end_year+'.';
 for(const [label,value] of [['Reported contract value',money(c.headline_value)],['Reported guarantees',money(c.reported_guarantees)],['Nominal average per contract year',money(c.average_annual_value)],['Signing bonus',c.signing_bonus==null?'Not separately listed':money(c.signing_bonus)],['Deferred payments',c.deferred_total==null?'No separate schedule listed':money(c.deferred_total)],['Scheduled salary / signing cash total',money(c.scheduled_cash_total)],['Spotrac cash total incl. listed incentives',money(c.reported_cash_total)]]){const div=text($('mlb-contract-summary'),'div','');text(div,'dt',label);text(div,'dd',value);}
 for(const row of c.annual){const tr=text($('mlb-cash-rows'),'tr','');for(const value of [row.year,money(row.salary_cash),row.signing_cash?money(row.signing_cash):'—',row.listed_incentives?money(row.listed_incentives):'—',money(row.reported_cash),row.phase])text(tr,'td',value);}
 for(const note of c.notes)text($('mlb-contract-notes'),'p',note);
 $('mlb-contract-check').textContent='Spotrac snapshot checked '+c.accessed_date+'.';$('mlb-contract-source').href=c.source_url;
}
loadMlb();
