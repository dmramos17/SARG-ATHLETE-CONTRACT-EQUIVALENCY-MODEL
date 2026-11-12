'use strict';
let comparisonPlayers=[],comparisonLeague='NFL',comparisonPick={left:null,right:null},comparisonEpoch=0,directoryEpoch=0,suggestionEpoch=0;
const normalizeComparison=s=>s.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
async function comparisonJson(path,params){const response=await fetch(path+'?'+new URLSearchParams(params));const result=await response.json();if(!response.ok)throw new Error(result.error||'Comparison unavailable.');return result;}
function hidePlayerOptions(side){$('compare-'+side+'-options').hidden=true;$('compare-'+side).setAttribute('aria-expanded','false');$('compare-'+side).removeAttribute('aria-activedescendant');}
function fillComparisonPick(side,p){comparisonPick[side]=p;$('compare-'+side).value=p.name+' · '+p.team;$('compare-'+side+'-base').textContent='Fixed residence: '+p.residence_name;hidePlayerOptions(side);}
function selectComparisonPlayer(side,p){
 comparisonEpoch++;$('compare-output').hidden=true;fillComparisonPick(side,p);
 if(side==='left'){
  if(comparisonPick.right?.id===p.id){comparisonPick.right=null;$('compare-right').value='';$('compare-right-base').textContent='';}
  loadComparisonSuggestions(p);
 }
 updatePlayerComparison();
}
async function loadComparisonSuggestions(p){
 const epoch=++suggestionEpoch;$('compare-suggestions').replaceChildren();$('compare-suggestion-note').textContent='Finding similar reported deals…';
 try{
  const result=await comparisonJson('/api/compare/suggestions',{league:comparisonLeague,player:p.id});if(epoch!==suggestionEpoch)return;
  $('compare-suggestion-note').textContent=result.players.length?'Closest matches to '+p.name+' by headline contract value and contract length, weighted equally. Select a suggestion or search for any other player.':'Contract value and length are needed for suggestions. You can still search for a second player.';
  for(const candidate of result.players){const button=text($('compare-suggestions'),'button','');button.type='button';button.dataset.player=candidate.id;button.setAttribute('aria-pressed',String(comparisonPick.right?.id===candidate.id));text(button,'strong',candidate.name);text(button,'span',candidate.team);text(button,'small',money(candidate.headline_value)+' · '+candidate.years+' years');button.addEventListener('click',()=>selectComparisonPlayer('right',candidate));}
 }catch(error){if(epoch===suggestionEpoch)$('compare-suggestion-note').textContent=error.message;}
}
for(const side of ['left','right']){
 const input=$('compare-'+side),list=$('compare-'+side+'-options');let matches=[],active=-1;
 input.addEventListener('input',()=>{
  comparisonEpoch++;comparisonPick[side]=null;$('compare-output').hidden=true;$('compare-'+side+'-base').textContent='';$('compare-status').textContent='Select two different players to compare.';list.replaceChildren();active=-1;
  if(side==='left'){suggestionEpoch++;$('compare-suggestions').replaceChildren();$('compare-suggestion-note').textContent='Choose a first player to see suggestions.';}
  const query=normalizeComparison(input.value.trim());matches=query?comparisonPlayers.filter(p=>p.id!==comparisonPick[side==='left'?'right':'left']?.id&&normalizeComparison(p.name+' '+p.team).includes(query)).slice(0,10):[];
  for(const [index,p] of matches.entries()){const option=text(list,'button','');option.type='button';option.id='compare-'+side+'-option-'+index;option.setAttribute('role','option');option.setAttribute('aria-selected','false');option.tabIndex=-1;text(option,'strong',p.name);text(option,'small',p.team+' · '+(p.headline_value?money(p.headline_value):'Contract value unavailable')+' · '+(p.years?p.years+' years':'Length unavailable'));option.addEventListener('click',()=>selectComparisonPlayer(side,p));}
  list.hidden=!matches.length;input.setAttribute('aria-expanded',String(!!matches.length));
 });
 input.addEventListener('keydown',event=>{
  if(event.key==='Escape'){hidePlayerOptions(side);return;}
  if(list.hidden||!matches.length)return;
  if(['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();active=(active+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length;for(const [i,el] of [...list.children].entries())el.setAttribute('aria-selected',String(i===active));input.setAttribute('aria-activedescendant',list.children[active].id);list.children[active].scrollIntoView({block:'nearest'});}
  if(event.key==='Enter'){event.preventDefault();selectComparisonPlayer(side,matches[active<0?0:active]);}
  if(event.key==='Tab')hidePlayerOptions(side);
 });
}
document.addEventListener('click',event=>{for(const side of ['left','right'])if(!$('compare-'+side).parentElement.contains(event.target))hidePlayerOptions(side);});
async function updatePlayerComparison(){
 const epoch=++comparisonEpoch,left=comparisonPick.left,right=comparisonPick.right;
 for(const el of $('compare-suggestions').children)el.setAttribute('aria-pressed',String(el.dataset.player===right?.id));
 if(!left||!right){$('compare-status').textContent='Choose a second player or select a similar deal below.';return;}
 $('compare-output').hidden=true;$('compare-status').textContent='Calculating both players at their fixed team-based residences…';
 try{
  const result=await comparisonJson('/api/compare',{league:comparisonLeague,left:left.id,right:right.id});if(epoch!==comparisonEpoch)return;
  const params=new URLSearchParams({league:comparisonLeague,left:left.id,right:right.id});history.replaceState(null,'','/compare?'+params);
  renderPlayerMatchup(result.players);
  $('compare-notes').replaceChildren();
  for(const p of result.players){const section=text($('compare-notes'),'div','');text(section,'h3',p.name+' · coverage');text(section,'p',p.complete?'Modeled income reconciles to the headline value. Conditional years and tax-model limitations may still apply.':'Partial or unavailable contract estimate. Take-home reflects modeled income only, not the full headline deal.');if(p.excluded_years.length)text(section,'p','Excluded years: '+p.excluded_years.join(', '));if(p.conditional_years.length)text(section,'p','Conditional years: '+p.conditional_years.join(', '));p.notes.forEach(n=>text(section,'p',n));const a=text(section,'a','Open '+p.name+'’s tax information ↗');a.href=p.url;}
  $('compare-assumptions').textContent=result.assumptions;$('compare-output').hidden=false;$('compare-status').textContent='Comparison ready · '+comparisonLeague+' · fixed team-based residences.';
 }catch(error){if(epoch===comparisonEpoch)$('compare-status').textContent=error.message;}
}
async function loadComparisonLeague(initial=false){
 const epoch=++directoryEpoch;comparisonEpoch++;suggestionEpoch++;comparisonLeague=$('compare-league').value;comparisonPick={left:null,right:null};comparisonPlayers=[];$('compare-output').hidden=true;$('compare-suggestions').replaceChildren();
 for(const side of ['left','right']){$('compare-'+side).value='';$('compare-'+side).disabled=true;$('compare-'+side+'-base').textContent='';hidePlayerOptions(side);}
 $('compare-status').textContent='Loading '+comparisonLeague+' players…';
 try{
  const result=await comparisonJson('/api/compare/directory',{league:comparisonLeague});if(epoch!==directoryEpoch)return;comparisonPlayers=result.players;
  const params=new URLSearchParams(location.search),requested=initial?(params.get('left')||params.get('player')):null;
  const left=comparisonPlayers.find(p=>p.id===requested)||comparisonPlayers.find(p=>p.id===(comparisonLeague==='NFL'?'00-0034857':'592450'))||comparisonPlayers[0];
  if(left){fillComparisonPick('left',left);loadComparisonSuggestions(left);if(!initial)history.replaceState(null,'','/compare?'+new URLSearchParams({league:comparisonLeague,left:left.id}));}
  const right=initial?comparisonPlayers.find(p=>p.id===params.get('right')&&p.id!==left?.id):null;if(right)fillComparisonPick('right',right);
  updatePlayerComparison();
 }catch(error){if(epoch===directoryEpoch)$('compare-status').textContent=error.message;}
 finally{if(epoch===directoryEpoch)for(const side of ['left','right'])$('compare-'+side).disabled=false;}
}
$('compare-league').value=new URLSearchParams(location.search).get('league')?.toUpperCase()==='MLB'?'MLB':'NFL';
$('compare-league').addEventListener('change',()=>loadComparisonLeague());loadComparisonLeague(true);


const mlbComparisonColors={ARI:'#a71930',ATL:'#b52a43',BAL:'#d75720',BOS:'#b82f46',CHC:'#245ab1',CWS:'#536274',CIN:'#c83240',CLE:'#b52a43',COL:'#705494',DET:'#c7602a',HOU:'#d85a23',KC:'#246cb3',LAA:'#bc2948',LAD:'#2463ae',MIA:'#087e91',MIL:'#8d742f',MIN:'#b32e4b',NYM:'#d56625',NYY:'#314d71',ATH:'#327455',OAK:'#327455',PHI:'#bd354c',PIT:'#a58020',SD:'#886a3c',SEA:'#16776a',SF:'#ce602c',STL:'#b83949',TB:'#276a93',TEX:'#2859ac',TOR:'#2762b0',WSH:'#b82f46',WAS:'#b82f46'};
function renderPlayerMatchup(players){
 const root=$('compare-matchup');root.replaceChildren();
 for(const [index,p] of players.entries()){
  const card=text(root,'article','','matchup-card');card.setAttribute('aria-label',p.name+' contract comparison');
  card.style.setProperty('--player-accent',(p.league==='NFL'?teamColors[p.team_code]:mlbComparisonColors[p.team_code])||'#39698d');
  const hero=text(card,'div','','matchup-hero');
  const badge=text(hero,'div','','matchup-team-badge');text(badge,'span',p.team_code,'matchup-initials');
  const logo=document.createElement('img');logo.src=p.logo_url;logo.alt=p.team+' logo';logo.className='matchup-logo';logo.addEventListener('error',()=>logo.remove(),{once:true});badge.append(logo);
  text(hero,'span',index===0?'PLAYER 01':'PLAYER 02','matchup-side');
  const identity=text(hero,'div','','matchup-identity');text(identity,'p',p.team,'matchup-team');text(identity,'h3',p.name);text(identity,'p',p.residence_name+' · assumed residence','matchup-residence');
  const emblem=document.createElement('img');emblem.src=p.logo_url;emblem.alt='';emblem.className='matchup-emblem';emblem.addEventListener('error',()=>emblem.remove(),{once:true});hero.append(emblem);
  const status=text(card,'p',p.complete?'Headline-reconciled estimate':p.remaining==null?'Estimate unavailable':'Partial-contract estimate','matchup-coverage');
  status.classList.toggle('coverage-warning',!p.complete);
  const coverage=text(card,'p','','matchup-income-coverage');
  if(p.income==null)coverage.textContent='No eligible income can be calculated for this residence.';
  else if(p.complete)coverage.textContent=money(p.income)+' modeled across '+p.included_years.length+' years, matching the headline amount. Conditional years are identified in the notes.';
  else coverage.textContent=money(p.income)+' modeled vs '+money(p.headline_value)+' headline.'+(p.headline_gap?' '+money(Math.abs(p.headline_gap))+' difference is not taxes.':'')+' Take-home covers included income only.';
  const metrics=text(card,'dl','','matchup-metrics');
  for(const [label,key,format,kind] of [
   ['Reported headline value','headline_value',money,'headline'],['Reported contract length','years',v=>v==null?'Not available':v+' years','detail'],
   ['Modeled contract income','income',money,'income'],['Estimated take-home','remaining',money,'take-home'],['Estimated U.S. taxes','total_tax',money,'tax'],
   ['Take-home percentage','take_home_percentage',v=>v==null?'Not available':v.toFixed(1)+'%','percent'],
   ['Average annual take-home','annual_take_home',money,'detail']]){
    const row=text(metrics,'div','','matchup-metric '+kind);text(row,'dt',key==='income'&&!p.complete?'Included-income subtotal':key==='remaining'?(p.complete?'Estimated contract take-home':'Take-home · included income only'):key==='annual_take_home'?'Average annual take-home · included years':label);text(row,'dd',format(p[key]));
    if(key==='take_home_percentage'&&p[key]!=null){const track=text(row,'div','','take-home-track');track.setAttribute('role','img');track.setAttribute('aria-label',p[key].toFixed(1)+' percent of modeled income remains after estimated U.S. taxes');const bar=text(track,'span','');bar.style.width=Math.max(0,Math.min(100,p[key]))+'%';}
  }
  const years=text(card,'div','','matchup-years');text(years,'strong','Years included');text(years,'p',p.included_years.length?p.included_years.join(' · '):'No eligible years');
  const link=text(card,'a','Explore '+p.name+'’s contract ↗','matchup-profile-link');link.href=p.url;
 }
}
