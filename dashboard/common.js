'use strict';
const $ = id => document.getElementById(id);
const money = value => value == null ? 'Not available' : new Intl.NumberFormat('en-US', {style:'currency',currency:'USD',maximumFractionDigits:0}).format(value);
const compactMoney = value => value == null ? 'Not available' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(value);
const teamColors={ARI:'#a62e46',ATL:'#ac233b',BAL:'#654498',BUF:'#2460b0',CAR:'#087ca9',CHI:'#ba4c21',CIN:'#c8481c',CLE:'#b74e26',DAL:'#326399',DEN:'#d65320',DET:'#2276a8',GB:'#326b4e',HOU:'#ad3042',IND:'#2b5da4',JAX:'#247978',KC:'#bf293c',LAC:'#1b77a2',LAR:'#3c5eaf',LV:'#616f80',MIA:'#147d80',MIN:'#7047a3',NE:'#b72a46',NO:'#877349',NYG:'#3459a0',NYJ:'#287350',PHI:'#277475',PIT:'#977616',SEA:'#507e15',SF:'#ad2a38',TB:'#b8343e',TEN:'#406a9d',WAS:'#8c3a40'};
function text(parent, tag, value, className){const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;parent.append(el);return el;}
function playerUrl(player){return '/players/'+encodeURIComponent(player.id);}
function sourceLink(parent, label, href){if(!href||!/^https:\/\//.test(href))return;const a=text(parent,'a',label);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;}
function contractCard(player,mode){
 const card=document.createElement('a');card.className='contract-card';card.href=mode==='estimate'?'/taxes/'+encodeURIComponent(player.estimate_id):playerUrl(player);card.style.setProperty('--card-accent',teamColors[player.team_code]||'#496780');
 const top=text(card,'div','','contract-card-top');text(top,'span',player.team_code,'team-badge');text(top,'span',player.position+' / '+player.team,'card-team-name');
 text(card,'h3',player.name);text(card,'p',mode==='estimate'?'2025 reported annual cash':'Signed '+player.contract.year_signed+' · '+player.contract.years+'-year reported deal','card-context');
 text(card,'strong',compactMoney(mode==='estimate'?player.estimate_cash:player.contract.total_value),'contract-amount');
 text(card,'p',mode==='estimate'?'Annual cash used in this tax example':'Total contract value','amount-caption');
 const foot=text(card,'div','','contract-card-footer');text(foot,'span',mode==='estimate'?'Tax estimate available':compactMoney(player.contract.average_per_year)+' average / year');text(foot,'span',mode==='estimate'?'View tax estimate ↗':'Contract details ↗');return card;
}
