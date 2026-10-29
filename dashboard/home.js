'use strict';
const search=$('player-search'), suggestions=$('player-suggestions'), status=$('search-status');
let matches=[],selected=-1,request=0,controller,timer;
function closeSuggestions(){suggestions.hidden=true;search.setAttribute('aria-expanded','false');search.removeAttribute('aria-activedescendant');selected=-1;}
function selectSuggestion(index){selected=index;const options=suggestions.querySelectorAll('[role="option"]');for(let i=0;i<options.length;i++)options[i].setAttribute('aria-selected',String(i===index));if(options[index]){search.setAttribute('aria-activedescendant',options[index].id);options[index].scrollIntoView({block:'nearest'});}}
async function searchPlayers(){
 const query=search.value.trim();const current=++request;controller?.abort();matches=[];closeSuggestions();suggestions.replaceChildren();
 if(query.length<2){status.textContent='Type at least two letters. Search by name, team, or position.';return;}
 controller=new AbortController();status.textContent='Finding players…';
 try{
 const response=await fetch('/api/players?q='+encodeURIComponent(query),{signal:controller.signal});if(!response.ok)throw new Error('Player search is temporarily unavailable. Please try again.');const data=await response.json();if(current!==request)return;
 matches=data.players;
 if(!matches.length){status.textContent='No players found. Try another name, team, or position.';return;}
 for(let i=0;i<matches.length;i++){const player=matches[i];const option=document.createElement('a');option.id='player-option-'+i;option.href=playerUrl(player);option.setAttribute('role','option');option.setAttribute('aria-selected','false');option.tabIndex=-1;const badge=text(option,'span',player.team_code,'suggestion-badge');badge.style.background=teamColors[player.team_code]||'#496780';const copy=text(option,'span','','suggestion-copy');text(copy,'strong',player.name);text(copy,'small',player.position+' · '+player.team);text(option,'span',player.tax_ready?'Tax estimate':'Cash needed','suggestion-status');suggestions.append(option);}
 suggestions.hidden=false;search.setAttribute('aria-expanded','true');status.textContent=matches.length+' suggestions. Use ↑ ↓ and Enter to choose a player.';
 }catch(error){if(error.name==='AbortError'||current!==request)return;status.textContent=error.message;}
}
search.addEventListener('input',()=>{clearTimeout(timer);controller?.abort();request++;closeSuggestions();matches=[];timer=setTimeout(searchPlayers,140);});
search.addEventListener('keydown',event=>{
 if(event.key==='Escape'){clearTimeout(timer);controller?.abort();request++;closeSuggestions();status.textContent='Suggestions closed. Keep typing to search again.';return;}
 if(!suggestions.hidden&&matches.length&&(event.key==='ArrowDown'||event.key==='ArrowUp')){event.preventDefault();selectSuggestion((selected+(event.key==='ArrowDown'?1:-1)+matches.length)%matches.length);}
 if(event.key==='Enter'&&!suggestions.hidden&&matches.length){event.preventDefault();location.assign(playerUrl(matches[selected<0?0:selected]));}
 if(event.key==='Tab')closeSuggestions();
});
$('player-search-form').addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);searchPlayers();});
document.addEventListener('click',event=>{if(!$('player-search-form').contains(event.target))closeSuggestions();});
async function loadHome(){
 try{const response=await fetch('/api/directory');if(!response.ok)throw new Error('The contract cards could not be loaded. You can still try the player search.');const data=await response.json();const metadata=data.metadata;
 $('player-count').textContent=metadata.player_count.toLocaleString();$('team-count').textContent=metadata.team_count;$('cash-count').textContent=metadata.cash_count.toLocaleString();
 for(const player of data.featured)$('recent-contracts').append(contractCard(player,'contract'));
 $('coverage-description').textContent=metadata.roster_definition+' Estimates are prefilled for '+metadata.estimate_count.toLocaleString()+' players; '+metadata.cash_required_count+' require verified cash input.';
 $('snapshot-date').textContent='Source files accessed '+metadata.accessed_date+'. Contract source update: '+metadata.contract_source_timestamp+'. Cards show the largest matched deals signed in 2025, not a real-time transaction feed.';
 for(const [index,url] of metadata.sources.entries()){const p=text($('directory-sources'),'p','');sourceLink(p,index===0?'nflverse weekly roster data':'nflverse contract data from OverTheCap',url);}
 }catch(error){$('directory-error').textContent=error.message;}finally{$('recent-contracts').setAttribute('aria-busy','false');}
}
loadHome();
