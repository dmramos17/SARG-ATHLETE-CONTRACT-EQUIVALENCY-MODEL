/* charts.js - interactive visuals added on top of the existing dashboard.
 * Load this file LAST on each page (after the page's own scripts).
 * It never edits existing code: it reads the same API endpoints and wraps
 * two existing render functions so it receives the same data they do.
 *   index.html   -> animated stat counters + "Same contract, 51 residences" ranking
 *   tax.html     -> paycheck waterfall + season duty-day calendar
 *   compare.html -> head-to-head mirrored bars
 *   offers.html  -> every-team ranking + break-even map for Offer A
 *   mlb.html     -> 51-residence ranking (home), paycheck waterfall + duty-day calendar (players)
 */
(function(){
'use strict';
const byId=id=>document.getElementById(id);
const SVG='http://www.w3.org/2000/svg';
const reduceMotion=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const usd=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(v);
const usdShort=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(v);
const pct=v=>(v>0&&v<0.1?'<0.1':v.toFixed(1))+'%';
const signed=v=>(v>0?'+':v<0?'\u2212':'')+(Math.abs(v)<1000?usd(Math.abs(v)):usdShort(Math.abs(v)));
const STATE_NAMES={AL:'Alabama',AK:'Alaska',AZ:'Arizona',AR:'Arkansas',CA:'California',CO:'Colorado',CT:'Connecticut',DE:'Delaware',DC:'District of Columbia',FL:'Florida',GA:'Georgia',HI:'Hawaii',ID:'Idaho',IL:'Illinois',IN:'Indiana',IA:'Iowa',KS:'Kansas',KY:'Kentucky',LA:'Louisiana',ME:'Maine',MD:'Maryland',MA:'Massachusetts',MI:'Michigan',MN:'Minnesota',MS:'Mississippi',MO:'Missouri',MT:'Montana',NE:'Nebraska',NV:'Nevada',NH:'New Hampshire',NJ:'New Jersey',NM:'New Mexico',NY:'New York',NC:'North Carolina',ND:'North Dakota',OH:'Ohio',OK:'Oklahoma',OR:'Oregon',PA:'Pennsylvania',RI:'Rhode Island',SC:'South Carolina',SD:'South Dakota',TN:'Tennessee',TX:'Texas',UT:'Utah',VT:'Vermont',VA:'Virginia',WA:'Washington',WV:'West Virginia',WI:'Wisconsin',WY:'Wyoming'};
const stateName=code=>STATE_NAMES[code]||code;
// Same colors as the existing "Where modeled income goes" chart (tax-breakdown.js).
const TAX_COLORS={cash:'#152c46',federal:'#3b66b3',payroll:'#8354a5',state:'#9c581a',local:'#ba4c60',remaining:'#187968'};

function el(parent,tag,textValue,className){const node=document.createElement(tag);if(textValue!=null&&textValue!=='')node.textContent=textValue;if(className)node.className=className;if(parent)parent.append(node);return node;}
function svgEl(parent,tag,attrs){const node=document.createElementNS(SVG,tag);for(const [k,v] of Object.entries(attrs||{}))node.setAttribute(k,v);if(parent)parent.append(node);return node;}
async function getJson(url,body){
 const response=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
 const out=await response.json();if(!response.ok)throw new Error(out.error||'Request failed.');return out;
}
// Wrap an existing global function so it still runs exactly as before, then call `after` with the same arguments.
function wrapGlobal(name,after){
 const original=window[name];if(typeof original!=='function')return false;
 window[name]=function(...args){const value=original.apply(this,args);try{after(...args);}catch(error){console.error('[charts.js]',error);}return value;};
 return true;
}
function segmented(parent,label,options,current,onPick){
 const group=el(parent,'div','','viz-segmented');group.setAttribute('role','group');group.setAttribute('aria-label',label);
 for(const option of options){const b=el(group,'button',option.label);b.type='button';b.setAttribute('aria-pressed',String(option.value===current));b.addEventListener('click',()=>{for(const other of group.children)other.setAttribute('aria-pressed',String(other===b));onPick(option.value);});}
 return group;
}

/* ---------------------------------------------------------------------------
 * 1. ANIMATED COUNTERS (index.html stats strip)
 * ------------------------------------------------------------------------- */
function countUp(node){
 const target=Number(node.textContent.replace(/[^0-9.]/g,''));
 if(!Number.isFinite(target)||target<=0||reduceMotion)return;
 node.dataset.vizCounted='1';
 const start=performance.now(),duration=1100;
 function frame(now){const t=Math.min(1,(now-start)/duration),eased=1-Math.pow(1-t,3);node.textContent=Math.round(target*eased).toLocaleString();if(t<1)requestAnimationFrame(frame);}
 requestAnimationFrame(frame);
}
function initCounters(){
 const ids=['player-count','team-count','cash-count'].filter(id=>byId(id));
 for(const id of ids){
  const node=byId(id);
  if(/\d/.test(node.textContent)){countUp(node);continue;}
  // home.js fills these in after /api/directory loads; animate as soon as a number appears.
  const observer=new MutationObserver(()=>{if(/\d/.test(node.textContent)&&!node.dataset.vizCounted){observer.disconnect();countUp(node);}});
  observer.observe(node,{childList:true,characterData:true,subtree:true});
 }
}

/* ---------------------------------------------------------------------------
 * 2. "SAME CONTRACT, 51 RESIDENCES" RANKING (index.html)
 * One 2025 season, the player's real 2025 duty-day calendar, only the
 * residence changes. Uses POST /api/duty-days and POST /api/calculate.
 * ------------------------------------------------------------------------- */
const rankingCache=new Map();
async function computeRanking(player,filing,cfg){
 const key=cfg.league+'|'+player.id+'|'+filing;
 if(rankingCache.has(key))return rankingCache.get(key);
 const job=(async()=>{
  // cfg.season(player) returns one season: {cash, tax_year, state_days, unsourced_days, total_days, residence_default}.
  const duty=await cfg.season(player),cash=duty.cash;
  if(!Number.isFinite(cash)||cash<=0)throw new Error(cfg.noCash);
  const days={};for(const [state,n] of Object.entries(duty.state_days||{}))if(n>0&&STATE_NAMES[state])days[state]=n;
  const codes=Object.keys(STATE_NAMES),rows=[];let next=0;
  async function worker(){while(next<codes.length){const code=codes[next++];
   try{const r=await getJson('/api/calculate',{tax_year:duty.tax_year||2025,residence:code,filing,salary:cash,days,unsourced:duty.unsourced_days||0});
    rows.push({code,remaining:r.remaining,total:r.total_tax,federal:r.national.federal,payroll:r.national.payroll.total,state:r.tax.total,residenceTax:r.tax.residence_tax,credit:r.tax.credit,nonresident:Object.values(r.tax.nonresident||{}).reduce((a,b)=>a+b,0)});
   }catch(error){/* A state the tax tables cannot handle is left out of the ranking. */}
  }}
  await Promise.all([worker(),worker(),worker(),worker()]);
  // Equal take-home (to the dollar) is a tie: tied states share a rank and are listed A-Z.
  rows.sort((a,b)=>(Math.round(b.remaining)-Math.round(a.remaining))||stateName(a.code).localeCompare(stateName(b.code)));
  return {cash,duty,rows};
 })();
 rankingCache.set(key,job);job.catch(()=>rankingCache.delete(key));return job;
}
function initRanking(cfg){
 const anchor=cfg.anchor();if(!anchor)return;
 const section=document.createElement('section');section.className='home-section viz-ranking';section.setAttribute('aria-labelledby','viz-ranking-heading');anchor.after(section);
 const title=el(section,'div','','section-title');const tl=el(title,'div');el(tl,'p','Across state lines','eyebrow');const rankingHeadingId='viz-ranking-heading-'+cfg.league.toLowerCase();el(tl,'h2','Same contract, 51 residences').id=rankingHeadingId;section.setAttribute('aria-labelledby',rankingHeadingId);const periodLabel=el(title,'span',cfg.periodLabel);
 el(section,'p',cfg.description,'section-description');
 const card=el(section,'div','','viz-ranking-card');
 const controls=el(card,'div','','viz-ranking-controls');
 // Player search box (same /api/players endpoint as the search at the top of the page).
 const pickWrap=el(controls,'div','','viz-field viz-search');
 const searchLabel=el(pickWrap,'label','Player');searchLabel.htmlFor='viz-ranking-search-'+cfg.league.toLowerCase();
 const search=el(pickWrap,'input');search.id='viz-ranking-search-'+cfg.league.toLowerCase();search.type='search';search.autocomplete='off';search.spellcheck=false;search.placeholder=cfg.placeholder;
 search.setAttribute('role','combobox');search.setAttribute('aria-autocomplete','list');search.setAttribute('aria-expanded','false');search.setAttribute('aria-controls','viz-ranking-options-'+cfg.league.toLowerCase());
 const listbox=el(pickWrap,'div','','viz-options');listbox.id='viz-ranking-options-'+cfg.league.toLowerCase();listbox.setAttribute('role','listbox');listbox.setAttribute('aria-label','Matching players');listbox.hidden=true;
 let filing='single',expanded=false,current=null,request=0,matches=[],active=-1,timer=null,searchRequest=0;
 const filingWrap=el(controls,'div','','viz-field');el(filingWrap,'span','Filing status');
 segmented(filingWrap,'Filing status',[{label:'Single',value:'single'},{label:'Married jointly',value:'mfj'}],filing,v=>{filing=v;load();});
 const quick=el(card,'div','','viz-quick');quick.hidden=true;el(quick,'span','Try:');
 const summary=el(card,'div','','viz-ranking-summary');summary.setAttribute('aria-live','polite');
 const list=el(card,'div','','viz-ranking-list');list.setAttribute('role','list');
 const detail=el(card,'p','Hover over or tap a state to see its tax breakdown.','viz-ranking-detail viz-detail');detail.setAttribute('role','status');
 const toggle=el(card,'button','Show all states','viz-link-button');toggle.type='button';toggle.hidden=true;
 el(card,'p','Ties: states with the same take-home share a rank (T1 = tied for first). Duty-day sourcing treats all reported cash as service wages (the dashboard default). Local work taxes, county taxes, deductions beyond the standard deduction, and real domicile rules are not modeled. Research estimates, not tax advice.','viz-footnote');
 toggle.addEventListener('click',()=>{expanded=!expanded;load();});
 const cashOf=cfg.cashOf;
 function choose(player){current=player;search.value=player.name;closeOptions();expanded=false;load();}
 function closeOptions(){listbox.hidden=true;search.setAttribute('aria-expanded','false');search.removeAttribute('aria-activedescendant');active=-1;}
 function highlight(i){active=i;[...listbox.children].forEach((o,k)=>o.setAttribute('aria-selected',String(k===i)));const o=listbox.children[i];if(o){search.setAttribute('aria-activedescendant',o.id);o.scrollIntoView({block:'nearest'});}}
 async function findPlayers(){
  const q=search.value.trim(),mine=++searchRequest;if(q.length<2){closeOptions();return;}
  try{
   const found=await cfg.search(q);if(mine!==searchRequest)return;
   matches=found||[];listbox.replaceChildren();
   if(!matches.length){el(listbox,'p','No players found.','viz-option-empty');}
   matches.forEach((p,i)=>{
    const ok=Number.isFinite(cashOf(p))&&cashOf(p)>0;
    const o=el(listbox,'div','','viz-option'+(ok?'':' is-disabled'));o.id='viz-ranking-option-'+cfg.league.toLowerCase()+'-'+i;o.setAttribute('role','option');o.setAttribute('aria-selected','false');if(!ok)o.setAttribute('aria-disabled','true');
    el(o,'strong',p.name);el(o,'span',p.team_code+' \u00b7 '+(p.position||'')+' \u00b7 '+(ok?usdShort(cashOf(p))+' '+(cfg.cashYearOf?cfg.cashYearOf(p):'')+' cash':'needs verified cash'));
    o.addEventListener('mousedown',e=>{e.preventDefault();if(ok)choose(p);});
   });
   listbox.hidden=false;search.setAttribute('aria-expanded','true');
  }catch(error){if(mine===searchRequest){listbox.replaceChildren();el(listbox,'p',error.message,'viz-option-empty');listbox.hidden=false;}}
 }
 search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(findPlayers,150);});
 search.addEventListener('keydown',e=>{
  const usable=matches.map((p,i)=>Number.isFinite(cashOf(p))&&cashOf(p)>0?i:-1).filter(i=>i>=0);
  if(e.key==='Escape'){closeOptions();return;}
  if((e.key==='ArrowDown'||e.key==='ArrowUp')&&!listbox.hidden&&usable.length){e.preventDefault();const at=usable.indexOf(active);highlight(usable[(at+(e.key==='ArrowDown'?1:-1)+usable.length)%usable.length]);}
  if(e.key==='Enter'){e.preventDefault();const pick=active>=0?active:usable[0];if(pick!=null&&matches[pick]&&!listbox.hidden)choose(matches[pick]);}
 });
 search.addEventListener('blur',()=>setTimeout(closeOptions,120));

 async function load(){
  const mine=++request,player=current;if(!player)return;
  list.setAttribute('aria-busy','true');summary.textContent='Calculating '+player.name+'\u2019s take-home in every state\u2026';
  try{
   const result=await computeRanking(player,filing,cfg);if(mine!==request)return;
   render(player,result);
  }catch(error){if(mine!==request)return;list.replaceChildren();summary.textContent=error.message;toggle.hidden=true;}
  finally{if(mine===request)list.setAttribute('aria-busy','false');}
 }
 // Name the actual states: full names for up to 3, postal codes (A-Z by name) for longer ties.
 function tieLabel(group){return group.length===1?stateName(group[0].code):group.length<=3?group.map(r=>stateName(r.code)).join(', '):group.map(r=>r.code).join(', ');}
 function render(player,{cash,duty,rows}){
  periodLabel.textContent=duty.tax_year+' season cash \u00b7 '+duty.tax_year+' tax rules';
  const home=duty.residence_default||player.home_state||null;let base=rows.find(r=>r.code===home);
  // A club outside the U.S. (Toronto) has no team state: bars then compare with the best state.
  if(!base&&home){summary.textContent='The team state could not be calculated.';return;}
  if(!base)base=rows[0];
  const same=(a,b)=>Math.round(a.remaining)===Math.round(b.remaining);
  // Competition ranking: tied states share the best rank in their group (1, 1, 1, 4 ...).
  let shown=rows.map((r,i,all)=>{let first=i;while(first>0&&same(all[first-1],r))first--;let count=0;for(const x of all)if(same(x,r))count++;return {...r,rank:first+1,tied:count>1};});
  const bestGroup=shown.filter(r=>same(r,shown[0])),worstGroup=shown.filter(r=>same(r,shown[shown.length-1]));
  const best=bestGroup[0],worst=worstGroup[0],spread=best.remaining-worst.remaining;
  const away=Object.entries(duty.state_days||{}).filter(([s])=>s!==home).reduce((a,[,n])=>a+n,0)+(duty.unsourced_days||0);
  const allNoTax=g=>g.every(r=>r.residenceTax===0);
  summary.replaceChildren();
  for(const [label,value,note] of [[duty.tax_year+' cash',usdShort(cash),duty.total_days+' duty days \u00b7 '+(home?away+' outside '+home:(duty.unsourced_days||0)+' in Canada (not modeled)')],['Best residence',tieLabel(bestGroup),(bestGroup.length>1?'Tied \u00b7 ':'')+usdShort(best.remaining)+' take-home'+(bestGroup.length>1?(allNoTax(bestGroup)?' each \u00b7 no wage tax':' each'):'')],['Toughest residence',tieLabel(worstGroup),(worstGroup.length>1?'Tied \u00b7 ':'')+usdShort(worst.remaining)+' take-home'+(worstGroup.length>1?' each':'')],['Spread',usdShort(spread),'kept by picking the best over the worst state']]){
   const box=el(summary,'div','','viz-stat');el(box,'small',label);el(box,'strong',value,value.length>16?'is-long':'');el(box,'span',note);
   const group=label==='Best residence'?bestGroup:label==='Toughest residence'?worstGroup:null;if(group&&group.length>1)box.title=group.map(r=>stateName(r.code)).join(', ');
  }
  const max=Math.max(...rows.map(r=>Math.abs(r.remaining-base.remaining)),1);
  if(!expanded&&shown.length>22){
   // Collapsed view: the whole top tie group plus the next places up to 10, the team state, and the bottom 10.
   const topCount=Math.max(10,bestGroup.length),top=shown.slice(0,topCount),bottom=shown.slice(-10),mid=shown.slice(topCount,-10).filter(r=>r.code===home);
   shown=[...top,...(mid.length?[null,...mid]:[]),null,...bottom];
  }
  list.replaceChildren();
  for(const row of shown){
   if(!row){el(list,'div','\u22ef','viz-rank-gap').setAttribute('aria-hidden','true');continue;}
   const diff=row.remaining-base.remaining,isHome=row.code===home,rankText=(row.tied?'T':'')+row.rank;
   const item=el(list,'button','','viz-rank-row'+(isHome?' is-home':''));item.type='button';item.setAttribute('role','listitem');
   item.setAttribute('aria-label',(row.tied?'Tied for '+row.rank:'Rank '+row.rank)+'. '+stateName(row.code)+': '+usd(row.remaining)+' take-home, '+(isHome?'team state baseline':signed(diff)+' versus '+(home?stateName(home):'the best state')));
   el(item,'span',rankText,'viz-rank-number');
   const name=el(item,'span','','viz-rank-name');el(name,'strong',stateName(row.code));
   if(isHome)el(name,'em','Team state','viz-tag');else if(row.residenceTax===0)el(name,'em','No wage tax','viz-tag viz-tag-soft');
   const track=el(item,'span','','viz-rank-track');el(track,'span','','viz-rank-axis');
   const bar=el(track,'span','','viz-rank-bar '+(diff>=0?'is-up':'is-down'));
   bar.style.setProperty('--w',(Math.abs(diff)/max*50).toFixed(2)+'%');
   el(item,'span',isHome?'Baseline':(!home&&Math.abs(diff)<1?'Best':signed(diff)),'viz-rank-diff '+(isHome?'':diff>=0?'is-up':'is-down'));
   el(item,'span',usdShort(row.remaining),'viz-rank-value');
   const explain=()=>{detail.textContent=stateName(row.code)+' residence'+(row.tied?' (tied for '+row.rank+')':'')+': '+usd(row.remaining)+' take-home ('+pct(row.remaining/cash*100)+'). Federal '+usdShort(row.federal)+' \u00b7 payroll '+usdShort(row.payroll)+' \u00b7 home-state tax '+usdShort(row.residenceTax)+(row.credit?' after a '+usdShort(row.credit)+' credit':'')+' \u00b7 tax to other states '+usdShort(row.nonresident)+'.';};
   item.addEventListener('mouseenter',explain);item.addEventListener('focus',explain);item.addEventListener('click',explain);
  }
  toggle.hidden=rows.length<=22;toggle.textContent=expanded?'Show top and bottom 10':'Show all '+rows.length+' states';
  if(!reduceMotion)requestAnimationFrame(()=>list.classList.add('is-drawn'));else list.classList.add('is-drawn');
 }
 // Start with the largest featured 2025 signing and offer the featured deals as one-click picks.
 cfg.featured().then(list=>{
  const featured=(list||[]).filter(p=>Number.isFinite(cashOf(p))&&cashOf(p)>0);
  for(const p of featured){const b=el(quick,'button',p.name,'viz-chip-button');b.type='button';b.addEventListener('click',()=>choose(p));}
  quick.hidden=!featured.length;
  if(!featured.length){summary.textContent='Search for a player to rank all 51 residences.';return;}
  current=featured[0];search.value=current.name;
  // Only start the 51 calculations when the section scrolls near the screen.
  const io=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){io.disconnect();load();}},{rootMargin:'300px'});io.observe(section);
 }).catch(()=>{summary.textContent='Search for a player to rank all 51 residences.';});
}

const NFL_RANKING={league:'NFL',anchor:()=>byId('recent-heading')?.closest('section'),periodLabel:'2025 season cash \u00b7 2025 tax rules',
 description:'Search any NFL player with reported 2025 cash. The team, schedule, and 2025 duty days stay the same; only the player\u2019s home state changes. Bars show how much more or less he keeps compared with living in his team\u2019s state.',
 placeholder:'Search a player, e.g. Josh Allen',noCash:'This player needs verified 2025 cash before states can be ranked.',
 cashOf:p=>p.estimate_cash??p.season_cash,cashYearOf:()=>'2025',
 search:async q=>(await getJson('/api/players?q='+encodeURIComponent(q))).players||[],
 featured:async()=>(await getJson('/api/directory')).featured||[],
 season:async p=>({...await getJson('/api/duty-days',{player_id:p.id}),cash:p.estimate_cash??p.season_cash})};
// MLB: the latest reported season (2025 or 2026) with its modeled calendar from /api/mlb/taxes.
let mlbDirectoryJob=null;
function mlbDirectory(){
 if(!mlbDirectoryJob){mlbDirectoryJob=getJson('/api/mlb/directory').then(d=>{
  const latestCash=p=>{const r=(p.cash_records||[]).filter(c=>c.year<=2026&&c.amount>0).sort((a,b)=>b.year-a.year)[0];return r?{cash:r.amount,year:r.year}:{cash:null,year:null};};
  const players=d.players.map(p=>{const c=latestCash(p);return {id:p.id,name:p.name,team_code:p.team_code,position:p.position,base_state:p.base_state,home_state:p.base_state,cash:p.tax_years&&p.tax_years.length?c.cash:null,cash_year:c.year};});
  return {players,featured:(d.featured_ids||[]).map(id=>players.find(p=>p.id===id)).filter(Boolean)};
 });mlbDirectoryJob.catch(()=>{mlbDirectoryJob=null;});}
 return mlbDirectoryJob;
}
const MLB_RANKING={league:'MLB',anchor:()=>byId('mlb-featured-heading')?.closest('section'),periodLabel:'Latest season cash \u00b7 same-year tax rules',
 description:'Search any MLB player with reported season cash. The club, schedule, and modeled work days stay the same; only the player\u2019s home state changes. Bars compare each state with living in his club\u2019s state (for Toronto, with the best state, since Canadian taxes are not modeled).',
 placeholder:'Search a player, e.g. Aaron Judge',noCash:'This player needs reported season cash before states can be ranked.',
 cashOf:p=>p.cash,cashYearOf:p=>p.cash_year||'',
 search:async q=>{const d=await mlbDirectory(),t=q.toLowerCase();return d.players.filter(p=>p.name.toLowerCase().includes(t)||(p.team_code||'').toLowerCase()===t).sort((a,b)=>(b.cash||0)-(a.cash||0)).slice(0,10);},
 featured:async()=>(await mlbDirectory()).featured,
 season:async p=>{
  const r=await getJson('/api/mlb/taxes?'+new URLSearchParams({player:p.id,residence:p.base_state||'NY',filing:'single'}));
  const a=(r.annual||[]).filter(y=>y.cash>0&&y.state_days).sort((x,y)=>y.year-x.year)[0];
  if(!a)throw new Error('This player has no modeled season with reported cash yet.');
  return {cash:a.cash,tax_year:a.year,state_days:a.state_days,unsourced_days:a.foreign_days||0,total_days:a.duty_days,residence_default:p.base_state};
 }};

/* ---------------------------------------------------------------------------
 * 3. PAYCHECK WATERFALL (tax.html) - wraps renderComparison(out, baseline)
 * ------------------------------------------------------------------------- */
function waterfallAmounts(result,year,opts){
 // opts.key: the yearly cash field ('cash' for NFL, 'salary' for MLB); opts.grossKey: TaxBreakdown's total field.
 const key=opts&&opts.key||'cash',grossKey=opts&&opts.grossKey||'gross',cashLabel=opts&&opts.cashLabel||'Reported cash';
 if(year==='all'){
  const s=window.TaxBreakdown?.summarize(result,grossKey);
  return s&&s.available?{cash:s.income,...s.amounts,cashLabel,label:'Whole contract window \u00b7 '+s.years[0]+'\u2013'+s.years[s.years.length-1]}:{error:s?s.reason:'Not available.'};
 }
 const y=(result.annual||[]).find(a=>String(a.year)===String(year));
 if(!y||!Number.isFinite(y.remaining)||!Number.isFinite(y[key]))return {error:'Annual cash is needed before '+year+' can be shown.'};
 const local=Number.isFinite(y.local)?y.local:0;
 const basis=y.schedule_basis||(y.template_year&&y.template_year!==y.year?y.template_year+' work pattern repeated':'')+(y.conditional?' \u00b7 conditional year':'');
 return {cash:y[key],federal:y.federal,payroll:y.payroll,state:y.state,local,remaining:y.remaining,cashLabel,label:'Calendar year '+y.year+(basis?' \u00b7 '+basis:'')};
}

function drawWaterfall(host,amounts,detail,ghost){
 host.replaceChildren();
 if(amounts.error){el(host,'p',amounts.error,'viz-empty');return;}
 const W=760,H=346,top=34,bottom=270,left=18,right=W-18,cols=6,slot=(right-left)/cols,barW=Math.min(84,slot*0.62);
 const y=v=>bottom-(v/amounts.cash)*(bottom-top);
 const svg=svgEl(host,'svg',{viewBox:'0 0 '+W+' '+H,class:'viz-waterfall-svg',role:'img','aria-label':'Paycheck waterfall: '+usd(amounts.cash)+' cash minus federal '+usd(amounts.federal)+', payroll '+usd(amounts.payroll)+', state '+usd(amounts.state)+', local '+usd(amounts.local)+' leaves '+usd(amounts.remaining)+' take-home.'});
 for(const f of [0.25,0.5,0.75,1])svgEl(svg,'line',{x1:left,x2:right,y1:y(amounts.cash*f),y2:y(amounts.cash*f),class:'viz-grid'});
 svgEl(svg,'line',{x1:left,x2:right,y1:bottom,y2:bottom,class:'viz-baseline'});
 let running=amounts.cash;
 const steps=[{key:'cash',label:amounts.cashLabel||'Reported cash',from:0,to:amounts.cash}];
 for(const key of ['federal','payroll','state','local']){steps.push({key,label:key[0].toUpperCase()+key.slice(1),from:running-amounts[key],to:running,drop:true});running-=amounts[key];}
 steps.push({key:'remaining',label:'Take-home',from:0,to:amounts.remaining});
 // Ghost: the other residence's bars, drawn as dashed outlines only where the amount differs by $1 or more.
 const ghostSteps={};
 if(ghost&&!ghost.amounts.error&&Math.abs(ghost.amounts.cash-amounts.cash)<1){let g=ghost.amounts.cash;for(const key of ['federal','payroll','state','local']){ghostSteps[key]={from:g-ghost.amounts[key],to:g};g-=ghost.amounts[key];}ghostSteps.remaining={from:0,to:ghost.amounts.remaining};}
 steps.forEach((s,i)=>{
  const cx=left+slot*i+slot/2,x=cx-barW/2,h=Math.max(1.5,y(s.from)-y(s.to)),value=s.to-s.from;
  const g=svgEl(svg,'g',{class:'viz-wf-step',tabindex:'0',role:'button','aria-label':s.label+': '+usd(value)+', '+pct(value/amounts.cash*100)+' of cash'});
  svgEl(g,'rect',{x:cx-slot/2,y:top-24,width:slot,height:bottom-top+24,fill:'transparent'});
  const rect=svgEl(g,'rect',{x,y:y(s.to),width:barW,height:h,rx:4,fill:TAX_COLORS[s.key],class:'viz-wf-bar'+(s.drop?' is-drop':'')});
  rect.style.animationDelay=(i*90)+'ms';
  const gs=ghostSteps[s.key];
  if(gs&&Math.abs((gs.to-gs.from)-(s.to-s.from))>=1){
   svgEl(g,'rect',{x:x-4,y:y(gs.to),width:barW+8,height:Math.max(1.5,y(gs.from)-y(gs.to)),rx:5,class:'viz-wf-ghost'});
  }
  if(i<steps.length-1){const nextTop=s.drop?y(s.from):y(s.to);svgEl(svg,'line',{x1:x+barW,x2:x+slot,y1:nextTop,y2:nextTop,class:'viz-connector'});}
  const t=svgEl(g,'text',{x:cx,y:y(s.to)-8,class:'viz-wf-value','text-anchor':'middle'});t.textContent=(s.drop?'\u2212':'')+usdShort(value);
  const n=svgEl(g,'text',{x:cx,y:bottom+20,class:'viz-wf-label','text-anchor':'middle'});n.textContent=s.label;
  const p=svgEl(g,'text',{x:cx,y:bottom+37,class:'viz-wf-pct','text-anchor':'middle'});p.textContent=pct(value/amounts.cash*100);
  let deltaText='',deltaVal=0;
  if(ghost&&ghostSteps[s.key]&&(s.key==='remaining'||s.key==='state')){
   const other=ghostSteps[s.key].to-ghostSteps[s.key].from,delta=value-other;
   if(Math.abs(delta)>=1){deltaVal=delta;deltaText=signed(delta)+' vs '+ghost.code;const d=svgEl(g,'text',{x:cx,y:bottom+56,class:'viz-wf-delta '+((s.key==='remaining'?delta>0:delta<0)?'is-better':'is-worse'),'text-anchor':'middle'});d.textContent=deltaText;}
  }
  const show=()=>{detail.textContent=s.label+': '+usd(value)+' \u00b7 '+pct(value/amounts.cash*100)+' of '+usd(amounts.cash)+' '+(amounts.cashLabel||'Reported cash').toLowerCase()+(s.key==='local'?' (supported local work taxes only)':'')+(deltaText?' \u00b7 '+usdShort(Math.abs(deltaVal))+(deltaVal>0?' more':' less')+' than in '+ghost.name:ghost&&(s.key==='federal'||s.key==='payroll')?' \u00b7 same in '+ghost.name+': it does not depend on residence':'')+'.';};
  g.addEventListener('mouseenter',show);g.addEventListener('focus',show);g.addEventListener('click',show);
 });
}
// One waterfall card. setData(base, comparison): either may be null (an MLB club in Canada has no
// modeled base state). opts: {key, grossKey, cashLabel} for waterfallAmounts; idSuffix keeps ids unique.
function makeWaterfall(anchor,opts){
 opts=opts||{};
 const box=document.createElement('section');box.className='viz-card viz-waterfall';const headingId='viz-waterfall-heading'+(opts.idSuffix||'');box.setAttribute('aria-labelledby',headingId);anchor.after(box);box.hidden=true;
 let latest=null,who='comparison',year='all';
 const cashWord=(opts.cashLabel||'Reported cash').toLowerCase();
 function render(){
  if(!latest)return;const {base,comparison}=latest;box.replaceChildren();
  if(!base&&!comparison){box.hidden=true;return;}box.hidden=false;
  const different=!!(base&&comparison&&comparison.residence!==base.residence);
  if(!different)who=base?'base':'comparison';
  const result=who==='base'?base:comparison;
  el(box,'h3','Paycheck waterfall').id=headingId;
  el(box,'p','Start with '+cashWord+', then watch each tax come out. Hover over, tap, or Tab to a bar for exact amounts.','viz-intro');
  const controls=el(box,'div','','viz-controls');
  if(different)segmented(controls,'Residence',[{label:stateName(base.residence)+' \u00b7 base',value:'base'},{label:stateName(comparison.residence)+' \u00b7 comparison',value:'comparison'}],who,v=>{who=v;render();});
  else el(controls,'span',stateName(result.residence)+(base?' \u00b7 base state':' \u00b7 comparison state'),'viz-chip');
  const sel=el(controls,'select','','viz-select');sel.setAttribute('aria-label','Period');
  el(sel,'option','Whole contract window').value='all';
  for(const a of result.annual||[])el(sel,'option',String(a.year)).value=String(a.year);
  if(![...sel.options].some(o=>o.value===year))year='all';sel.value=year;sel.addEventListener('change',()=>{year=sel.value;render();});
  const amounts=waterfallAmounts(result,year,opts);
  const otherResult=different?(who==='base'?comparison:base):null;
  const ghost=otherResult?{amounts:waterfallAmounts(otherResult,year,opts),code:otherResult.residence,name:stateName(otherResult.residence)}:null;
  if(amounts.label)el(box,'p',amounts.label,'viz-caption');
  const chart=el(box,'div','','viz-waterfall-chart');
  const detail=el(box,'p','','viz-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  if(ghost&&!ghost.amounts.error){const legend=el(box,'p','','viz-wf-legend');el(legend,'span','','viz-wf-legend-swatch');el(legend,'span','Dashed outline = '+ghost.name+(who==='base'?' (comparison)':' (base)')+'. Federal and payroll tax do not depend on residence, so only the bars that differ are outlined.');chart.before(legend);}
  drawWaterfall(chart,amounts,detail,ghost);
  if(!amounts.error){const gap=ghost&&!ghost.amounts.error?amounts.remaining-ghost.amounts.remaining:0;detail.textContent='Take-home: '+usd(amounts.remaining)+' \u00b7 '+pct(amounts.remaining/amounts.cash*100)+' of '+cashWord+'. Taxes: '+usd(amounts.cash-amounts.remaining)+'.'+(ghost&&Math.abs(gap)>=1?' That is '+usd(Math.abs(gap))+(gap>0?' more':' less')+' than living in '+ghost.name+'.':'');}
 }
 return {box,setData(base,comparison){latest={base,comparison};who=comparison&&base&&comparison.residence!==base.residence?'comparison':(base?'base':'comparison');render();}};
}
function initWaterfall(){
 const anchor=byId('projection-tax-breakdown');if(!anchor)return;
 const w=makeWaterfall(anchor,{});
 wrapGlobal('renderComparison',(out,baseline)=>{if(!baseline)return;w.setData(baseline,out);});
}
function initMlbWaterfall(){
 const anchor=byId('mlb-tax-breakdown');if(!anchor)return;
 const w=makeWaterfall(anchor,{key:'salary',grossKey:'salary',cashLabel:'Contract salary',idSuffix:'-mlb'});
 wrapGlobal('renderMlbProjection',(base,comparison)=>{w.setData(base||null,comparison||null);});
}

/* ---------------------------------------------------------------------------
 * 4. SEASON DUTY-DAY CALENDAR (tax.html) - POST /api/duty-days
 * ------------------------------------------------------------------------- */
const ROAD_COLORS=['#e8743b','#3b9ab2','#c9a227','#b5446e','#5a8f29','#8354a5','#d4572a','#2c7fb8','#7f6a3a','#16a085','#c0392b','#6d6e9c','#a0522d','#3d8c6e'];
const HOME_COLOR='#1d3f66',OFF_COLOR='#e5ecf3';
const dutyCache=new Map();
function dutyDays(playerId,travel){const key=playerId+'|'+travel;if(!dutyCache.has(key)){const job=getJson('/api/duty-days',{player_id:playerId,travel_days:travel});dutyCache.set(key,job);job.catch(()=>dutyCache.delete(key));}return dutyCache.get(key);}
function eventKind(event){const e=String(event||'');if(/game/i.test(e))return {kind:'game',stage:/PRE/.test(e)?'Preseason game':/POST/.test(e)?'Postseason game':'Regular-season game'};if(/travel|away/i.test(e))return {kind:'travel',stage:'Travel / away preparation'};return {kind:'service',stage:'Team service'};}
function iso(d){return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
function initCalendar(){
 const anchor=byId('projection-tax-breakdown');if(!anchor)return;
 const box=document.createElement('section');box.className='viz-card viz-calendar';box.setAttribute('aria-labelledby','viz-calendar-heading');
 (document.querySelector('.viz-waterfall')||anchor).after(box);
 let request=0,focusState=null;
 async function load(out){
  const current=++request,player=typeof projectionPlayer!=='undefined'?projectionPlayer:null;if(!player)return;
  const travel=Number(byId('projection-travel')?.value||1);
  box.replaceChildren();el(box,'h3','Where he worked: the duty-day calendar').id='viz-calendar-heading';
  const status=el(box,'p','Loading the season calendar\u2026','viz-intro');
  try{const duty=await dutyDays(player.player_id,travel);if(current!==request)return;status.remove();draw(duty,out,player);}
  catch(error){if(current===request)status.textContent='Duty-day calendar unavailable: '+error.message;}
 }
 function draw(duty,out,player){
  const year=duty.tax_year,home=duty.residence_default||player.home_state;
  const games=new Map();for(const g of (out.annual||[]).find(a=>a.year===year)?.opponents||[])if(g.date)games.set(g.date,g);
  const byDate=new Map(duty.calendar.map(d=>[d.date,d]));
  const states=Object.entries(duty.state_days||{}).sort((a,b)=>(a[0]===home?-1:b[0]===home?1:b[1]-a[1]));
  const colors={};let ci=0;for(const [s] of states)colors[s]=s===home?HOME_COLOR:ROAD_COLORS[ci++%ROAD_COLORS.length];
  const away=states.filter(([s])=>s!==home).reduce((a,[,n])=>a+n,0);
  el(box,'p','Every modeled '+year+' work day, colored by the state it happened in. States tax visiting players on the days they work there, which is the \u201cjock tax.\u201d Hover over or tap a day; use the arrow keys to move through the calendar.','viz-intro');
  const stats=el(box,'div','','viz-mini-stats');
  for(const [v,l] of [[duty.total_days,'duty days'],[duty.state_days[home]||0,'in '+home+' (team state)'],[away,'on the road'],[states.length,'states with sourced income']]){const s=el(stats,'div');el(s,'strong',String(v));el(s,'span',l);}
  const legend=el(box,'div','','viz-legend');legend.setAttribute('aria-label','Filter calendar by state');
  for(const [s,n] of states){
   const b=el(legend,'button','','viz-legend-item');b.type='button';b.setAttribute('aria-pressed','false');
   const sw=el(b,'span','','viz-swatch');sw.style.background=colors[s];el(b,'span',stateName(s));el(b,'strong',String(n));
   b.addEventListener('click',()=>{focusState=focusState===s?null:s;for(const x of legend.children)x.setAttribute('aria-pressed',String(x===b&&focusState===s));applyFocus();});
  }
  const key=el(legend,'span','','viz-legend-note');key.innerHTML='<span class="viz-dot"></span> game day &nbsp; <span class="viz-swatch viz-swatch-faded"></span> travel day &nbsp; <span class="viz-swatch" style="background:'+OFF_COLOR+'"></span> no modeled duty';
  const wrap=el(box,'div','','viz-calendar-wrap');
  const cell=14,gap=3,step=cell+gap,leftPad=30,topPad=22;
  const jan1=new Date(year,0,1),dec31=new Date(year,11,31);
  const weeks=Math.ceil((jan1.getDay()+ (dec31-jan1)/864e5+1)/7);
  const W=leftPad+weeks*step,H=topPad+7*step+4;
  const svg=svgEl(wrap,'svg',{viewBox:'0 0 '+W+' '+H,class:'viz-calendar-svg',role:'grid','aria-label':year+' duty-day calendar for '+player.player});
  ['Sun','','Tue','','Thu','','Sat'].forEach((d,i)=>{if(d){const t=svgEl(svg,'text',{x:leftPad-6,y:topPad+i*step+cell-3,class:'viz-cal-axis','text-anchor':'end'});t.textContent=d;}});
  const tip=el(wrap,'div','','viz-tooltip');tip.hidden=true;
  const detail=el(box,'div','','viz-detail viz-cal-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');detail.textContent='Select a day to see what happened and where.';
  const cells=[];
  for(let d=new Date(jan1),i=0;d<=dec31;d.setDate(d.getDate()+1),i++){
   const date=iso(d),dayIndex=i+jan1.getDay(),col=Math.floor(dayIndex/7),row=d.getDay();
   if(d.getDate()===1){const t=svgEl(svg,'text',{x:leftPad+col*step,y:12,class:'viz-cal-axis'});t.textContent=d.toLocaleDateString('en-US',{month:'short'});}
   const entry=byDate.get(date),kind=entry?eventKind(entry.event):null;
   const r=svgEl(svg,'rect',{x:leftPad+col*step,y:topPad+row*step,width:cell,height:cell,rx:3,class:'viz-day'+(entry?'':' is-off')+(kind?' is-'+kind.kind:''),fill:entry?colors[entry.state]||'#888':OFF_COLOR,tabindex:'-1',role:'gridcell'});
   if(kind?.kind==='game')svgEl(svg,'circle',{cx:leftPad+col*step+cell/2,cy:topPad+row*step+cell/2,r:2.6,class:'viz-game-dot','pointer-events':'none'});
   const info={date,entry,kind,rect:r,state:entry?.state};
   info.text=describeDay(info,games,byDate,home);r.setAttribute('aria-label',info.text.replace(/\n/g,'. '));
   cells.push(info);
  }
  cells.forEach((c,i)=>{
   const show=()=>{const box2=c.rect.getBoundingClientRect(),host=wrap.getBoundingClientRect();tip.textContent=c.text;tip.hidden=false;
    const x=Math.min(Math.max(box2.left-host.left+box2.width/2,90),host.width-90);const below=box2.top-host.top<70;tip.classList.toggle('is-below',below);tip.style.left=x+'px';tip.style.top=((below?box2.bottom:box2.top)-host.top+wrap.scrollTop)+'px';};
   const pin=()=>{detail.replaceChildren();const lines=c.text.split('\n');el(detail,'strong',lines[0]);for(const l of lines.slice(1))el(detail,'span',l);
    if(c.entry?.source&&/^https:\/\//.test(c.entry.source)){const a=el(detail,'a','Game source \u2197');a.href=c.entry.source;a.target='_blank';a.rel='noopener noreferrer';}
    if(c.entry?.note)el(detail,'small',c.entry.note);};
   c.rect.addEventListener('mouseenter',show);c.rect.addEventListener('mouseleave',()=>{tip.hidden=true;});
   c.rect.addEventListener('click',()=>{pin();c.rect.focus({preventScroll:true});});
   c.rect.addEventListener('focus',()=>{for(const o of cells)o.rect.setAttribute('tabindex','-1');c.rect.setAttribute('tabindex','0');show();pin();});
   c.rect.addEventListener('blur',()=>{tip.hidden=true;});
   c.rect.addEventListener('keydown',e=>{const move={ArrowRight:7,ArrowLeft:-7,ArrowDown:1,ArrowUp:-1}[e.key];if(move==null)return;e.preventDefault();const target=cells[i+move];if(target)target.rect.focus();});
  });
  const first=cells.find(c=>c.entry)||cells[0];first.rect.setAttribute('tabindex','0');
  function applyFocus(){for(const c of cells)c.rect.classList.toggle('is-dimmed',!!focusState&&c.state!==focusState);}
  el(box,'p','Days, venues and travel are modeled from team schedules; individual attendance is not verified. Calendar year '+year+' includes the January tail of the previous season.','viz-footnote');
 }
 function describeDay(c,games,byDate,home){
  const d=new Date(c.date+'T12:00:00'),dateText=d.toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'});
  if(!c.entry)return dateText+'\nNo modeled duty day';
  const lines=[dateText];let game=games.get(c.date);
  if(c.kind.kind==='travel'){for(let k=1;k<=3&&!game;k++){const n=new Date(d);n.setDate(n.getDate()+k);const g=games.get(iso(n));if(g&&g.state===c.state)game=g;}}
  if(c.kind.kind==='game'){lines.push(c.kind.stage+(game?(game.home?' vs ':' at ')+game.opponent:''));}
  else if(c.kind.kind==='travel'){lines.push(c.kind.stage+(game?' before the game at '+game.opponent:''));}
  else lines.push(c.kind.stage);
  lines.push(stateName(c.entry.state)+(c.entry.state===home?' \u00b7 team state':' \u00b7 nonresident work day')+(game?.city&&c.kind.kind!=='service'?' \u00b7 '+game.city:'')+(c.entry.locality?' \u00b7 local tax: '+c.entry.locality:''));
  return lines.join('\n');
 }
 wrapGlobal('renderComparison',out=>{load(out);});
}

/* ---------------------------------------------------------------------------
 * 5. HEAD-TO-HEAD MIRRORED BARS (compare.html) - wraps renderPlayerMatchup(players)
 * ------------------------------------------------------------------------- */
function initMirror(){
 const anchor=byId('compare-matchup');if(!anchor)return;
 const box=document.createElement('section');box.className='viz-card viz-mirror';box.setAttribute('aria-labelledby','viz-mirror-heading');anchor.after(box);box.hidden=true;
 function colorDistance(x,y){const rgb=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));const [p,q]=[rgb(x),rgb(y)];return Math.hypot(p[0]-q[0],p[1]-q[1],p[2]-q[2]);}
 function colorFor(p){const nfl=typeof teamColors!=='undefined'?teamColors:{},mlb=typeof mlbComparisonColors!=='undefined'?mlbComparisonColors:{};return (p.league==='NFL'?nfl[p.team_code]:mlb[p.team_code])||'#39698d';}
 wrapGlobal('renderPlayerMatchup',players=>{
  box.replaceChildren();if(!players||players.length<2){box.hidden=true;return;}box.hidden=false;
  const [a,b]=players;let ca=colorFor(a),cb=colorFor(b);if(colorDistance(ca,cb)<90)cb='#ff763d';
  el(box,'h3','Head to head').id='viz-mirror-heading';
  el(box,'p','Each row is scaled to the larger of the two values, so you can compare rows at a glance. Hover over or tap a row for the exact gap.','viz-intro');
  const head=el(box,'div','','viz-mirror-head');
  const ha=el(head,'div','','viz-mirror-name');ha.style.setProperty('--c',ca);el(ha,'strong',a.name+(a.complete?'':' *'));el(ha,'span',a.team_code+' \u00b7 '+a.residence_name);
  el(head,'span','vs','viz-mirror-vs');
  const hb=el(head,'div','','viz-mirror-name is-right');hb.style.setProperty('--c',cb);el(hb,'strong',b.name+(b.complete?'':' *'));el(hb,'span',b.team_code+' \u00b7 '+b.residence_name);
  const rows=el(box,'div','','viz-mirror-rows');
  const detail=el(box,'p','','viz-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  const metrics=[['Modeled income','income',usdShort,'more modeled income'],['Estimated U.S. taxes','total_tax',usdShort,'more in estimated taxes'],['Estimated take-home','remaining',usdShort,'more take-home'],['Take-home %','take_home_percentage',v=>v.toFixed(1)+'%','higher share kept'],['Avg. annual take-home','annual_take_home',usdShort,'more per year']];
  for(const [label,key,fmt,gapText] of metrics){
   const va=a[key],vb=b[key],ok=Number.isFinite(va)&&Number.isFinite(vb);
   const max=key==='take_home_percentage'?100:Math.max(Math.abs(va||0),Math.abs(vb||0),1);
   const row=el(rows,'button','','viz-mirror-row');row.type='button';
   const left=el(row,'span','','viz-mirror-side is-left'),mid=el(row,'span',label,'viz-mirror-label'),right=el(row,'span','','viz-mirror-side');
   for(const [side,v,c,winner] of [[left,va,ca,ok&&va>vb],[right,vb,cb,ok&&vb>va]]){
    el(side,'span',Number.isFinite(v)?fmt(v):'n/a','viz-mirror-value'+(winner&&key!=='total_tax'?' is-lead':''));
    const track=el(side,'span','','viz-mirror-track');const bar=el(track,'span','','viz-mirror-bar');bar.style.background=c;bar.style.setProperty('--w',(Number.isFinite(v)?Math.max(0,v)/max*100:0).toFixed(2)+'%');
   }
   row.setAttribute('aria-label',label+': '+a.name+' '+(Number.isFinite(va)?fmt(va):'not available')+', '+b.name+' '+(Number.isFinite(vb)?fmt(vb):'not available'));
   const explain=()=>{if(!ok){detail.textContent=label+': not available for both players.';return;}if(va===vb){detail.textContent=label+': tied.';return;}
    const lead=va>vb?a:b,gap=Math.abs(va-vb);detail.textContent=label+': '+lead.name+' has '+(key==='take_home_percentage'?gap.toFixed(1)+' points':usd(gap))+' '+gapText+'.';};
   row.addEventListener('mouseenter',explain);row.addEventListener('focus',explain);row.addEventListener('click',explain);
  }
  detail.textContent='Hover over or tap a row to see who leads and by how much.';
  if(!a.complete||!b.complete)el(box,'p','* Partial-contract estimate: only modeled income is included, so totals are not the full headline deal.','viz-footnote');
  requestAnimationFrame(()=>requestAnimationFrame(()=>rows.classList.add('is-drawn')));
 });
}

/* ---------------------------------------------------------------------------
 * 6. OFFER LAB: EVERY TEAM, ONE OFFER (offers.html) - POST /api/offers/rank
 * Ranks every team for Offer A's salaries and draws a break-even map:
 * what each team would need to pay for the same take-home as Offer A.
 * ------------------------------------------------------------------------- */
// OFFER_MAP: U.S. state outlines (us-atlas, Albers USA, simplified) and team marker positions.
// teams[league][code] = [x, y, true x, true y]; markers that overlap are nudged apart.
const OFFER_MAP={"w":960,"h":600,"land":"M664,469L664,469M166,518L166,518M165,531L165,531M162,533L162,533M162,533L162,533M161,533L161,533M161,540L161,540M160,535L160,535M160,524L160,524M159,535L159,535M158,526L158,526M155,541L156,541L157,539L157,540L158,537L159,537L159,538L161,539L160,540L158,540L157,542L155,541M155,531L155,531M152,551L152,551M151,552L153,552L153,553L151,552M150,546L152,544L153,544L154,542L156,543L155,542L159,542L159,545L160,544L160,546L158,545L158,547L157,546L153,551L154,548L152,550L151,549L151,548L150,546M150,553L150,553M146,558L146,558M142,556L142,556M141,555L141,555M139,552L139,552M137,553L137,553M133,557L133,557M132,556L132,556M130,564L130,564M131,557L131,557M130,563L130,563M129,564L129,564M129,561L129,561M128,564L128,564M128,562L128,562M127,560L127,560M127,563L128,561L128,562L127,563M129,535L129,535M127,559L127,559M128,535L128,535M124,560L126,560L126,561L124,561L124,560M126,536L126,535L128,534L127,536L126,536M122,560L122,560M121,560L121,560M120,561L120,561M117,562L117,562M125,499L125,499M115,565L115,565M115,558L115,558M106,566L106,566M105,566L105,566M104,566L104,566M103,566L103,566M103,565L103,565M101,565L102,565L103,566L101,566L101,565M100,566L100,566M104,520L106,521L107,520L109,520L109,520L111,521L111,524L109,524L108,525L105,521L104,520M92,570L95,569L97,568L96,567L97,566L99,566L99,567L100,567L99,568L101,567L97,570L96,570L93,570L92,570M110,481L116,478L120,476L123,476L124,477L124,479L124,480L127,480L130,481L131,480L132,480L131,478L130,479L130,478L128,475L129,474L130,476L129,476L131,478L131,478L130,476L131,474L130,474L128,474L125,472L125,469L122,465L120,464L120,463L118,462L120,461L120,459L123,459L126,459L128,458L129,457L130,453L132,451L133,450L135,450L136,450L137,449L139,447L140,447L141,447L143,447L144,446L146,444L147,444L149,445L149,446L148,446L149,447L150,445L151,446L152,447L153,448L153,447L155,447L157,447L157,449L159,449L158,450L160,451L162,450L162,450L164,449L167,451L168,450L169,451L174,451L176,452L179,450L180,450L185,453L186,453L200,520L202,520L202,520L204,520L204,519L207,518L207,520L209,521L209,522L214,525L215,527L217,525L218,524L218,521L220,519L222,520L223,522L224,522L227,524L229,525L231,526L232,528L238,533L238,534L239,534L239,536L240,536L241,537L242,537L244,537L249,538L249,539L249,541L251,544L251,547L250,549L249,548L247,546L248,545L247,543L247,546L246,546L244,545L243,542L243,545L242,544L241,542L241,543L240,542L239,542L239,540L240,540L238,537L235,536L233,535L233,534L231,531L229,529L227,529L223,525L222,522L221,523L222,524L224,527L225,530L223,529L222,529L221,528L220,526L220,527L217,526L220,528L221,530L219,531L215,529L213,528L212,527L205,525L206,524L205,522L203,524L201,524L198,523L195,523L193,523L189,524L188,523L186,523L186,521L185,522L183,522L181,522L182,522L179,523L180,522L182,521L180,520L179,518L178,519L177,517L177,519L176,518L175,520L174,520L175,517L174,519L174,518L173,520L174,520L173,522L174,522L175,523L174,524L176,525L174,526L174,525L173,526L170,526L170,525L169,528L169,527L169,529L168,529L167,531L167,530L165,531L164,532L163,532L162,533L161,532L161,531L163,530L164,528L162,529L161,528L161,526L162,525L163,523L162,521L164,521L166,519L167,520L168,519L167,518L167,517L165,517L163,519L162,519L161,521L159,523L159,524L158,525L158,526L156,529L155,529L154,531L153,532L152,533L155,534L155,536L153,537L152,541L149,542L149,543L147,543L146,545L145,545L143,547L144,547L143,549L141,549L140,550L139,550L137,552L137,552L135,552L135,553L136,554L134,556L130,557L129,556L126,558L126,559L124,558L123,559L122,559L122,557L121,557L120,561L115,562L112,564L109,563L109,564L107,564L107,563L108,563L109,561L113,560L114,562L114,560L116,560L119,557L121,555L125,555L125,556L127,556L126,555L127,553L129,551L133,549L134,550L134,548L136,547L138,544L140,538L141,536L141,535L137,537L136,535L136,534L134,536L135,537L134,538L133,535L131,534L131,535L129,533L129,533L125,535L123,536L123,535L124,533L123,530L124,529L123,524L122,525L120,526L117,526L116,525L116,524L114,522L113,520L114,520L112,519L114,518L113,517L114,516L113,515L112,515L112,514L111,512L111,511L112,511L111,510L113,510L113,508L117,504L118,501L120,500L122,502L123,502L126,499L128,500L130,500L131,498L131,494L130,492L131,492L132,491L131,489L130,490L129,490L126,492L125,493L125,492L123,491L120,491L118,491L115,490L114,488L114,487L113,485L114,485L115,484L115,484L112,483L110,481L110,481M86,572L88,570L90,569L90,568L92,568L93,569L90,570L89,571L86,572M85,572L85,572M84,570L84,570M90,544L90,544M84,570L84,570M82,571L82,571M82,570L82,570M81,572L81,572M88,540L88,540M78,572L78,572M77,572L77,572M76,572L76,572M95,493L96,491L96,492L98,494L100,493L101,494L101,495L102,496L105,497L104,498L102,498L101,499L100,496L97,494L96,495L95,494L95,493M70,572L70,572M85,513L86,513L88,516L86,515L85,513M85,512L85,512M63,571L65,572L68,573L66,573L63,571M58,570L62,570L63,569L64,570L60,571L58,570M57,570L57,570M57,569L57,569M56,570L56,570M55,570L55,570M54,568L54,568M53,570L53,570M49,570L51,568L52,570L53,570L50,571L49,570M48,568L48,568M47,569L50,568L49,570L47,569M45,567L46,567L46,568L45,567M42,568L42,568M41,568L41,568M42,566L42,566M40,569L40,569M39,569L39,569M35,562L35,562M31,563L31,563M31,560L31,560M30,561L30,561M30,559L30,559M26,558L26,558M22,553L22,553M16,547L16,547M15,546L15,546M15,546L15,546M12,547L13,547L13,548L12,547M10,542L13,543L13,545L11,544L10,542M247,547L247,547M246,548L246,548M246,548L246,548M245,548L245,546L246,548L245,548M244,546L245,546L245,547L244,546M239,539L239,539M239,540L239,540M238,539L238,539M241,550L241,550M237,541L237,541M237,540L237,540L238,540L238,541L237,540M238,547L238,547M238,551L238,551M236,546L236,546M236,546L236,546M236,548L237,546L238,548L237,549L236,548M235,544L235,542L235,541L236,541L238,543L239,543L241,544L242,546L241,545L244,547L245,551L243,551L243,550L241,550L239,548L241,550L241,550L242,552L241,552L240,550L239,549L238,549L239,547L236,545L235,544M231,535L231,535M234,545L234,545M233,545L233,545M230,539L231,538L233,538L231,537L232,536L235,536L238,538L237,539L236,539L234,541L234,540L234,543L233,544L230,539M225,528L227,529L229,529L231,532L229,531L231,534L231,535L230,537L229,536L229,535L227,533L227,532L225,528M225,527L225,527M222,524L222,524M224,536L225,535L228,535L230,540L231,544L227,540L226,540L226,537L224,536M222,529L222,529M224,537L225,537L225,539L225,539L224,537M220,528L220,528M221,530L221,530M220,533L220,532L222,530L224,531L226,531L226,532L228,534L227,535L224,534L224,536L222,535L220,533M183,522L183,522M182,522L182,522M177,519L177,519M176,521L176,521M177,524L177,524M175,527L177,525L178,523L179,524L177,526L175,527M175,524L176,521L176,525L175,524M174,521L174,521M818,564L818,564M816,565L816,565M811,568L811,568M799,573L805,567L809,569L799,573M795,574L795,574M792,574L792,574M784,530L784,530M777,575L777,575M731,472L731,472M934,120L934,120M932,121L932,121M931,117L931,117M927,121L927,121M928,129L928,129M926,124L926,124M925,121L925,121M923,186L923,186M914,188L917,184L920,186L914,188M864,318L864,318M863,337L863,337M135,360L135,360M133,369L133,369M127,358L127,358M124,345L124,345M117,360L117,360M116,342L116,342M110,342L110,342M107,341L107,341M346,555L351,549L350,544L362,549L365,555L371,559L368,563L357,567L354,572L350,569L350,563L346,555M334,530L341,529L347,533L346,536L339,537L338,533L334,530M333,538L333,538M326,530L326,530M322,526L322,524L333,525L330,527L322,526M302,516L309,513L315,522L306,522L302,516M273,507L277,503L283,505L282,509L276,510L273,507M264,510L264,510M848,274L848,274M841,262L841,262M691,134L691,134M680,137L680,137M678,137L678,137M677,142L677,142M676,139L676,139M674,145L674,145M672,152L672,152M671,155L671,155M661,143L661,143M621,99L629,93L629,95L622,100L621,99M660,470L660,470M656,470L656,470M652,471L652,471M649,470L649,470M896,194L896,194M896,198L896,198M894,197L894,197M819,156L819,156M818,156L818,156M731,220L731,220M729,219L729,219M851,279L851,279M850,277L851,277L850,277M150,60L150,60M155,36L155,36M155,32L155,32M154,35L154,35M151,42L156,47L154,50L151,42M152,30L152,30M150,31L150,31M152,25L152,25M148,33L154,33L152,38L148,33M148,31L148,31M658,149L658,149M652,153L652,153M604,118L604,118M604,121L604,121M602,120L602,120M600,122L600,122M601,119L601,119M600,118L600,118M600,123L600,123M597,119L597,119M654,474L654,474M646,474L646,474M641,486L641,486M628,496L628,496M625,496L625,496M621,497L621,497M598,487L598,487M904,184L904,184M905,188L905,188M903,195L903,195M899,192L883,198L873,206L876,206L889,202L892,198L897,200L882,212L871,216L869,214L868,214L866,218L871,220L872,233L870,241L862,253L863,248L851,244L850,241L850,241L851,240L850,245L855,252L861,256L863,264L862,273L859,280L857,293L853,292L853,284L856,276L852,278L852,271L847,272L843,267L847,265L841,260L842,250L838,253L840,267L843,274L837,274L832,270L829,273L830,267L829,274L833,272L834,275L840,275L847,279L846,290L850,296L847,301L855,299L859,306L856,307L859,312L848,321L863,318L865,326L860,332L844,331L855,335L851,343L856,339L859,341L856,349L854,347L848,349L840,356L836,362L835,369L826,371L823,373L818,380L815,391L805,401L797,406L798,408L792,416L788,423L787,434L786,436L786,445L792,463L800,477L809,487L811,497L823,517L826,526L826,545L825,545L823,556L811,560L805,548L797,546L792,536L784,529L773,515L778,507L772,504L774,508L769,508L768,501L771,495L769,486L766,481L763,481L755,475L749,468L742,464L737,465L736,469L733,469L724,477L719,476L718,471L707,465L694,463L678,467L674,468L669,459L667,467L662,467L653,467L642,472L637,475L640,479L643,474L645,478L645,483L640,484L644,489L649,489L651,497L638,491L631,496L627,491L620,497L610,493L605,484L600,482L592,488L576,484L564,486L559,487L547,493L549,485L543,487L545,494L548,494L536,504L521,512L506,524L508,520L517,515L510,514L510,517L502,520L506,521L503,525L498,524L501,528L498,536L497,547L498,553L503,565L499,567L490,562L483,562L478,558L466,554L463,545L460,541L460,531L452,525L452,521L445,514L439,497L425,482L415,481L410,479L404,481L398,492L394,496L376,487L370,481L367,474L367,468L363,458L356,454L347,442L343,439L338,432L308,428L307,438L292,436L256,431L195,395L198,390L156,385L154,382L155,372L153,367L144,356L139,355L139,349L134,348L128,344L124,337L109,332L106,329L110,318L102,304L96,284L100,278L93,267L94,255L99,263L97,252L94,254L88,248L90,243L82,225L86,207L81,196L81,192L87,185L92,173L94,161L92,159L95,149L94,143L104,128L116,99L120,89L121,83L124,79L129,78L122,76L128,68L124,66L125,60L126,43L124,35L127,31L135,38L147,44L151,44L151,49L145,54L153,49L153,53L148,63L152,61L154,52L158,48L155,42L157,42L158,33L155,31L156,27L233,46L247,49L413,74L508,79L537,79L536,71L541,73L544,84L555,86L556,89L562,86L567,86L574,89L576,94L577,91L585,94L588,97L592,96L597,93L599,96L608,95L612,97L616,97L610,100L603,104L594,110L590,116L581,124L582,125L590,124L597,120L600,121L598,127L601,125L606,127L614,121L619,121L636,106L643,107L636,112L634,117L634,121L636,117L645,119L649,125L661,125L667,120L677,119L684,116L684,122L690,123L695,120L698,129L702,130L706,128L706,131L698,131L694,132L690,130L688,135L685,132L678,131L676,134L668,135L666,139L661,142L663,138L656,139L649,155L644,163L645,167L649,160L652,159L657,150L657,154L652,166L652,174L649,181L650,185L648,194L651,210L651,214L657,226L661,227L667,224L670,221L675,209L674,197L668,184L669,181L667,175L670,169L670,162L672,157L676,155L678,150L679,159L682,155L682,148L688,145L685,141L689,136L698,138L700,141L709,143L713,149L711,151L714,156L714,164L711,170L708,172L706,177L711,180L716,171L721,169L726,173L729,185L732,190L731,198L727,199L724,206L723,212L720,219L728,222L729,220L736,224L742,220L747,220L757,211L764,207L774,199L783,191L786,186L781,176L789,172L801,171L804,172L813,170L820,163L822,162L822,154L818,152L818,149L823,144L830,133L836,127L858,122L884,116L885,110L889,108L892,109L893,102L897,93L895,84L896,76L903,57L905,57L909,62L917,55L925,59L933,87L938,87L940,94L945,95L950,101L946,105L944,111L940,110L938,115L931,119L932,124L927,119L926,115L923,129L914,134L909,141L907,152L906,157L910,160L906,167L913,172L916,177L921,178L924,175L926,177L916,183L915,179L909,186L906,187L907,183L906,182L903,181L904,190L899,192","inner":"M662,467L658,435L660,371L658,369L702,365L714,409L721,421L718,424L717,430L720,437L720,444L722,447L675,452L675,455L680,459L681,464L678,467M198,390L201,390L203,385L200,383L201,376L206,371L208,363L214,360L211,356L209,343L211,320L218,320L221,323L223,320L226,303L309,317L292,436M722,447L725,453L773,450L777,454L777,444L786,445M702,365L724,362L744,359L741,367L750,370L757,380L769,389L773,395L778,397L781,405L783,406L787,415L792,416M667,224L699,221L699,222L705,277L706,283L696,286L697,290L691,296L690,301L684,301L680,304L676,304L670,308L662,305L656,309L654,307L663,289L659,280L661,276L657,226M428,265L536,268L543,272L539,278L544,285L547,287L548,332L455,330L424,329M907,152L901,147L900,143L889,108M906,182L902,176L896,178L870,184L870,169L882,166L900,162L906,157M909,186L907,183M582,125L578,127L579,139L573,143L571,150L574,152L573,156L572,167L576,171L586,175L587,178L593,182L596,185L597,192L518,194L518,156L512,150L516,143L516,134L513,127L513,108L509,97L509,85L508,79M851,240L852,237L861,227L854,223L851,218L850,212L855,202L869,207L869,214M868,214L866,218M850,241L850,241M724,362L724,357L728,355L731,349L736,348L744,343L749,336L750,338L756,333L759,333L763,323L786,320L859,306M826,371L803,354L784,357L779,351L757,353L744,359M516,143L407,138L413,74M548,332L548,342L551,366L551,403L544,401L538,396L528,399L522,399L519,402L509,396L505,401L504,397L500,399L496,396L491,395L484,392L482,394L469,387L461,386L456,382L458,341L408,338L408,328M774,199L775,204L842,191L847,194L848,198L855,202M852,237L846,240L788,251L772,254L768,235L764,207M518,194L515,211L518,215L514,212L505,207L496,207L494,209L487,204L402,199L405,157L407,138M551,403L559,405L559,405L559,416L559,438L563,446L569,454L569,462L565,472L567,478L563,483L564,486M338,432L337,427L400,433L403,392L407,338L408,338M402,199L398,242M320,233L398,242L430,244L428,265L424,329L408,328L344,322L309,317L320,233L289,228L292,207L301,156L302,145L405,157M896,178L899,192M873,206L873,199L870,184M536,268L531,262L528,256L547,256L592,254L597,258L597,266L599,272L610,282L611,289L620,290L617,301L617,303L631,314L633,320L632,322L636,328L639,328L639,335L635,339L634,339L633,339L633,344L630,350L619,350L624,344L623,340L548,342M788,251L790,262L799,251L805,253L809,248L814,250L817,254L816,259L807,253L807,260L801,269L799,268L796,278L789,275L789,279L782,296L783,300L769,308L766,306L761,310L757,307L756,303L750,301L743,292L743,286L747,285L748,278L750,272L753,275L754,268L758,263L762,263L767,255L768,242L766,237L768,235M597,258L598,254L602,252L604,243L601,240L602,236L613,232L615,227L615,221L612,219L607,213L651,210M656,309L655,316L649,319L650,325L642,323L639,328M630,350L632,352L627,356L629,357L624,362L626,368L622,371L619,376L618,384L615,385L613,391L610,394L612,398L608,403L610,404L609,414L559,416M94,161L109,166L156,179L156,179L141,241L167,281L187,311L209,343M863,264L853,266L846,240M597,192L600,197L598,200L601,208L606,210L607,213M528,256L526,237L523,236L524,230L521,225L518,215M705,277L711,276L715,282L725,284L731,284L737,280L743,286M756,303L750,310L744,314L739,323L730,327L700,330L682,331L661,334L657,333L658,337L635,339M634,339L633,339M851,277L850,277M862,273L856,276M830,267L830,263M829,261L830,263L829,261L821,258L817,254M720,219L699,222M649,155L645,150L645,150L645,143L640,141L640,138L630,137L625,135L610,132L607,128L607,128L606,127M622,371L658,369M642,472L636,462L637,455L603,457L605,446L615,428L611,426L611,417L609,414M301,156L297,149L295,153L283,151L281,153L272,151L271,144L267,142L267,138L264,131L264,125L262,123L256,127L253,124L254,120L261,103L253,96L249,87L245,82L246,77L242,70L247,49M882,166L879,148L882,136L880,132L886,126L884,121L884,116M858,122L859,130L861,134L861,142L866,152L870,169M129,78L135,82L138,87L137,94L143,98L154,97L159,101L168,101L173,102L177,101L190,102L192,101L221,108L226,118L218,128L216,133L210,138L209,142L213,145L210,153L201,190L156,179M730,327L763,323M226,303L247,199L292,207M233,46L222,99L221,108M247,199L201,190","teams":{"NFL":{"ARI":[248.4,384.3,248.4,384.3],"ATL":[725.7,388.5,725.7,388.5],"BAL":[837.2,249.6,834.9,251.7],"BUF":[787.3,185.7,787.3,185.7],"CAR":[781.5,348.9,781.5,348.9],"CHI":[654.8,223,654.8,223],"CIN":[709.8,276.1,709.8,276.1],"CLE":[748.4,220.3,747.3,219.6],"DAL":[510.2,413.4,510.2,413.4],"DEN":[380.5,266.9,380.5,266.9],"DET":[722.9,204.6,724,205.2],"GB":[643.3,168.1,643.3,168.1],"HOU":[535.5,486.6,535.5,486.6],"IND":[681.9,265.1,682,265.2],"JAX":[783.9,453.6,783.9,453.6],"KC":[549.3,288.2,549.3,288.2],"LV":[204.2,318.7,204.2,318.7],"LAC":[144.4,362.6,140.5,351.7],"LAR":[134.5,334.8,138.4,345.7],"MIA":[824,539.7,824,539.7],"MIN":[567,165,567,165],"NE":[903.6,174.3,903.6,174.3],"NO":[632.4,477.7,632.4,477.7],"NYG":[879.6,210.2,867.6,211.3],"NYJ":[850,208.6,862.8,212.9],"PHI":[863.2,235.3,854.9,234],"PIT":[776.9,237.4,776.9,237.4],"SF":[100.6,265.1,100.6,265.1],"SEA":[155,58.8,155,58.8],"TB":[775.4,504.5,775.4,504.5],"TEN":[679.7,342,679.7,342],"WAS":[812.4,265.8,822.2,259.5]},"MLB":{"ARI":[246.2,383.5,246.2,383.5],"ATH":[117.8,240.8,114.6,243],"ATL":[724,385.7,724,385.7],"BAL":[830.3,242.6,834.9,251.7],"BOS":[904.6,168.4,904.6,168.4],"CHC":[665.8,213,654,221.2],"CWS":[647.8,236.3,654.7,223.7],"CIN":[709.9,276.1,709.9,276.1],"CLE":[748.4,220.2,747.4,219.6],"COL":[381,266.5,381,266.5],"DET":[723,204.4,724,205],"HOU":[536.4,485,536.4,485],"KC":[549.3,288.2,549.3,288.2],"LAA":[159.9,357,148.7,356.2],"LAD":[133.6,343.6,144,349.2],"MIA":[825,543.3,825,543.3],"MIL":[642.5,194.4,647.3,198.9],"MIN":[565.1,162.3,565.1,162.3],"NYM":[883.9,217.3,871.2,211.5],"NYY":[857.8,203.5,869.7,210.4],"PHI":[858.7,233.4,854.9,233.8],"PIT":[777.1,237.4,777.1,237.4],"SD":[155,386.4,155.8,381.5],"SF":[93,257.6,96.2,255.4],"SEA":[153.8,56.5,153.8,56.5],"STL":[619.2,294.6,619.2,294.6],"TB":[773.3,509.3,773.3,509.3],"TEX":[505.8,421.8,505.8,421.8],"WSH":[830.5,272.2,830.5,261.5]}}};
function divergingColor(t){
 // t in [-1, 1]: negative = team can pay less (teal), positive = must pay more (orange).
 const mix=(a,b,k)=>a.map((v,i)=>Math.round(v+(b[i]-v)*k));
 const mid=[226,232,239],lo=[24,121,104],hi=[194,84,31];
 const c=t<0?mix(mid,lo,Math.min(1,-t)):mix(mid,hi,Math.min(1,t));
 return 'rgb('+c.join(',')+')';
}
function initOfferRanking(){
 const anchor=byId('offer-output');if(!anchor||typeof offerPayload!=='function')return;
 const panel=document.createElement('section');panel.className='panel viz-offer-rank';panel.setAttribute('aria-labelledby','viz-offer-rank-heading');anchor.after(panel);
 el(panel,'p','Every team, one offer','eyebrow');
 el(panel,'h2','Which team pays the most after taxes?').id='viz-offer-rank-heading';
 el(panel,'p','Uses Offer A from the form above: its team, residence, salary years and amounts, plus the model settings. For every other team we estimate take-home for the same salaries, and the salary that team would need to pay to match Offer A\u2019s whole-contract take-home.','viz-intro');
 const controls=el(panel,'div','','viz-controls');
 let rule='team',request=0,last=null,selected=null;
 const ruleWrap=el(controls,'div','','viz-field-inline');el(ruleWrap,'span','Residence','viz-field-label');
 segmented(ruleWrap,'Residence for each team',[{label:'Each team\u2019s state',value:'team'},{label:'Keep Offer A\u2019s residence',value:'fixed'}],rule,v=>{rule=v;if(last)run();});
 const go=el(controls,'button','Rank every team','calculate viz-rank-go');go.type='button';
 const status=el(panel,'p','','viz-status');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const out=el(panel,'div','','viz-offer-out');out.hidden=true;
 function teamCount(){try{const lg=byId('offer-league').value;const list=typeof offerCatalog!=='undefined'&&offerCatalog?offerCatalog.teams[lg]:null;return list?list.length:(lg==='MLB'?30:32);}catch(e){return 32;}}
 function label(){go.textContent='Rank all '+teamCount()+' '+(byId('offer-league')?.value||'')+' teams';}
 label();byId('offer-league')?.addEventListener('change',()=>{label();out.hidden=true;status.textContent='';last=null;});
 go.addEventListener('click',run);
 async function run(){
  const form=byId('offer-form');
  const a=byId('offer-a-salaries');const salaries=a?[...a.querySelectorAll('input')]:[];
  if(salaries.some(i=>!i.checkValidity())||!byId('offer-a-team')?.value){form?.reportValidity();status.textContent='Fill in Offer A\u2019s team and salaries first.';return;}
  const base=offerPayload();
  const payload={league:base.league,start_year:base.start_year,filing:base.filing,mlb_role:base.mlb_role,travel_days:base.travel_days,structure:'same_pattern',residence_rule:rule,offer_a:base.offer_a};
  const mine=++request;go.disabled=true;out.setAttribute('aria-busy','true');
  status.textContent='Ranking '+teamCount()+' teams with their own work locations\u2026 this takes about 10\u201315 seconds the first time.';
  try{
   const result=await getJson('/api/offers/rank',payload);if(mine!==request)return;
   last=result;selected=null;draw(result);out.hidden=false;
   status.textContent='Ranked '+result.rows.length+' teams \u00b7 '+(result.residence_rule==='team'?'each team\u2019s state as residence':'every team uses '+result.reference.residence_name+' as residence')+' \u00b7 fixed 2026 tax rules.';
  }catch(error){if(mine===request)status.textContent='Ranking unavailable: '+error.message;}
  finally{if(mine===request){go.disabled=false;out.setAttribute('aria-busy','false');}}
 }
 function draw(r){
  out.replaceChildren();
  const ref=r.reference,rows=r.rows,years=r.years,best=rows[0],worst=rows[rows.length-1];
  const refRow=rows.find(x=>x.is_reference);
  const bestGroup=rows.filter(x=>x.rank===1);
  // Summary
  const summary=el(out,'div','','viz-offer-summary');
  for(const [k,v,n] of [
   ['Offer A',usdShort(ref.gross/years)+' / yr',ref.team.name+' \u00b7 '+usdShort(ref.take_home)+' take-home'],
   ['Most take-home',bestGroup.length>1?bestGroup.map(x=>x.team.code).join(', '):best.team.name,usdShort(best.take_home)+' for the same salaries'+(bestGroup.length>1?' (tied)':'')],
   ['Least take-home',worst.team.name,usdShort(worst.take_home)+' for the same salaries'],
   ['Break-even range',usdShort(best.breakeven_annual)+' \u2013 '+usdShort(worst.breakeven_annual),'per year to match Offer A']]){
   const b=el(summary,'div','','viz-offer-stat');el(b,'small',k);el(b,'strong',v,v.length>22?'is-long':'');el(b,'span',n);
  }
  // Map
  const mapBox=el(out,'div','','viz-map-box');
  const mh=el(mapBox,'div','','viz-map-head');el(mh,'h3','Break-even map');
  el(mh,'p','Salary per year each team would need to offer for the same total take-home as Offer A ('+ref.team.code+'). Hover over, tap, or Tab to a team.','viz-intro');
  const legend=el(mapBox,'div','','viz-map-legend');
  const max=Math.max(...rows.map(x=>Math.abs(x.breakeven_annual_difference)),1);
  el(legend,'span','Can offer '+usdShort(max)+' less');const grad=el(legend,'span','','viz-map-gradient');grad.style.background='linear-gradient(90deg,'+divergingColor(-1)+','+divergingColor(0)+','+divergingColor(1)+')';el(legend,'span','Must offer '+usdShort(max)+' more');
  const wrap=el(mapBox,'div','','viz-map-wrap');
  const positions=OFFER_MAP.teams[r.league]||{};
  const svg=svgEl(wrap,'svg',{viewBox:'0 0 '+OFFER_MAP.w+' '+OFFER_MAP.h,class:'viz-map-svg',role:'group','aria-label':'Break-even salary map for '+rows.length+' teams'});
  svgEl(svg,'path',{d:OFFER_MAP.land,class:'viz-map-land'});svgEl(svg,'path',{d:OFFER_MAP.inner,class:'viz-map-borders'});
  const tip=el(wrap,'div','','viz-tooltip');tip.hidden=true;
  const detail=el(mapBox,'p','','viz-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  detail.textContent='Teal teams can offer less than Offer A and still match its take-home; orange teams must offer more.';
  const markers={};
  const describe=x=>{
   const d=x.breakeven_annual_difference;
   return x.team.name+' ('+x.residence+')'+(x.is_reference?' \u00b7 Offer A':'')+'\nSame salaries: '+usdShort(x.take_home)+' take-home ('+(x.take_home_difference>=0?'+':'\u2212')+usdShort(Math.abs(x.take_home_difference))+')\nBreak-even: '+usdShort(x.breakeven_annual)+' / yr'+(Math.abs(d)<1?'':' ('+(d>0?'+':'\u2212')+usdShort(Math.abs(d))+' / yr)');
  };
  for(const x of rows){
   const pos=positions[x.team.code];if(!pos)continue;
   const [px,py,ox,oy]=pos;
   if(Math.hypot(px-ox,py-oy)>4){svgEl(svg,'line',{x1:ox,y1:oy,x2:px,y2:py,class:'viz-map-leader'});svgEl(svg,'circle',{cx:ox,cy:oy,r:2.2,class:'viz-map-pin'});}
   const g=svgEl(svg,'g',{class:'viz-map-team'+(x.is_reference?' is-reference':''),tabindex:'0',role:'button','aria-label':describe(x).replace(/\n/g,'. ')});
   const t=x.breakeven_annual_difference/max;
   svgEl(g,'circle',{cx:px,cy:py,r:x.is_reference?17:14,fill:x.is_reference?'#152c46':divergingColor(t),class:'viz-map-dot'});
   const lbl=svgEl(g,'text',{x:px,y:py+3.5,'text-anchor':'middle',class:'viz-map-code'+(x.is_reference||Math.abs(t)>0.55?' is-light':'')});lbl.textContent=x.team.code;
   markers[x.team.id]=g;
   const show=()=>{const b=g.getBoundingClientRect(),h=wrap.getBoundingClientRect();tip.textContent=describe(x);tip.hidden=false;
    const below=b.top-h.top<90;tip.classList.toggle('is-below',below);tip.style.left=Math.min(Math.max(b.left-h.left+b.width/2,110),h.width-110)+'px';tip.style.top=((below?b.bottom:b.top)-h.top)+'px';};
   const pick=()=>{select(x.team.id);detail.textContent=describe(x).replace(/\n/g,' \u00b7 ');};
   g.addEventListener('mouseenter',show);g.addEventListener('mouseleave',()=>{tip.hidden=true;});
   g.addEventListener('focus',()=>{show();pick();});g.addEventListener('blur',()=>{tip.hidden=true;});
   g.addEventListener('click',pick);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick();}});
  }
  if(r.excluded.length)el(mapBox,'p','Not ranked: '+r.excluded.map(e=>e.team.name+' ('+e.reason.replace(/\.$/,'')+')').join(', ')+'.','viz-footnote');
  // Ranked list
  const listBox=el(out,'div','','viz-offer-list-box');
  el(listBox,'h3','Ranked by take-home for the same salaries');
  const head=el(listBox,'div','','viz-offer-row is-head');for(const h of ['#','Team','Take-home','Break-even per year','vs Offer A'])el(head,'span',h);
  const list=el(listBox,'div','','viz-offer-list');list.setAttribute('role','list');
  const rowEls={};
  for(const x of rows){
   const d=x.breakeven_annual_difference,tied=rows.filter(y=>y.rank===x.rank).length>1;
   const row=el(list,'button','','viz-offer-row'+(x.is_reference?' is-reference':''));row.type='button';row.setAttribute('role','listitem');
   row.setAttribute('aria-label',describe(x).replace(/\n/g,'. '));
   el(row,'span',(tied?'T':'')+x.rank,'viz-offer-rank-n');
   const nm=el(row,'span','','viz-offer-team');el(nm,'strong',x.team.name);el(nm,'em',x.residence+(x.is_reference?' \u00b7 Offer A':''));
   el(row,'span',usdShort(x.take_home),'viz-offer-num');
   const be=el(row,'span','','viz-offer-be');
   const track=el(be,'span','','viz-offer-track');el(track,'span','','viz-rank-axis viz-offer-axis');
   const bar=el(track,'span','','viz-offer-bar '+(d>0?'is-more':'is-less'));bar.style.setProperty('--w',(Math.abs(d)/max*50).toFixed(2)+'%');
   el(be,'span',usdShort(x.breakeven_annual),'viz-offer-num');
   el(row,'span',Math.abs(d)<1?'Offer A':(d>0?'+':'\u2212')+usdShort(Math.abs(d))+'/yr','viz-offer-diff '+(Math.abs(d)<1?'':d>0?'is-more':'is-less'));
   row.addEventListener('click',()=>{select(x.team.id);detail.textContent=describe(x).replace(/\n/g,' \u00b7 ');markers[x.team.id]?.scrollIntoView?.({block:'nearest'});});
   row.addEventListener('mouseenter',()=>markers[x.team.id]?.classList.add('is-hover'));row.addEventListener('mouseleave',()=>markers[x.team.id]?.classList.remove('is-hover'));
   rowEls[x.team.id]=row;
  }
  function select(id){selected=id;for(const [k,v] of Object.entries(rowEls))v.classList.toggle('is-selected',k===id);for(const [k,v] of Object.entries(markers))v.classList.toggle('is-selected',k===id);}
  requestAnimationFrame(()=>requestAnimationFrame(()=>list.classList.add('is-drawn')));
  el(out,'p',r.notes.join(' ')+(refRow?'':' Offer A\u2019s own team is not shown at zero because a different residence rule is applied to it.'),'viz-footnote');
 }
}

/* ---------------------------------------------------------------------------
 * 7. MLB DUTY-DAY CALENDAR (mlb.html player view)
 * Wraps comparisonValues(prefix, result) from mlb.js, which receives the
 * /api/mlb/taxes results; each known season carries a modeled day-by-day calendar.
 * ------------------------------------------------------------------------- */
const CANADA_COLOR='#b23a48';
function initMlbCalendar(){
 const anchor=byId('mlb-tax-breakdown');if(!anchor||typeof comparisonValues!=='function')return;
 const box=document.createElement('section');box.className='viz-card viz-calendar viz-mlb-calendar';box.setAttribute('aria-labelledby','viz-mlb-calendar-heading');box.hidden=true;
 const after=anchor.nextElementSibling&&anchor.nextElementSibling.classList.contains('viz-waterfall')?anchor.nextElementSibling:anchor;after.after(box);
 const seen={base:null,comparison:null};let year=null,focusKey=null,shownFor=null;
 wrapGlobal('comparisonValues',(prefix,result)=>{
  if(prefix!=='base'&&prefix!=='comparison')return;seen[prefix]=result||null;
  if(prefix!=='comparison')return;
  const r=seen.base||seen.comparison;
  if(!r){box.hidden=true;return;}
  if(shownFor!==r.player_id){year=null;focusKey=null;}shownFor=r.player_id;render(r);
 });
 const locKey=e=>e.state||e.country||'Unknown';
 const locName=k=>STATE_NAMES[k]?stateName(k):k;
 function kindOf(e){
  if(e.games&&e.games.length)return {kind:'game',text:e.games.length>1?'Doubleheader ('+e.games.length+' games)':'Game day'};
  const b=String(e.basis||'');
  if(/arrival|travel/i.test(b))return {kind:'travel',text:'Travel / arrival day'};
  if(/spring/i.test(b))return {kind:'service',text:'Spring training (no game)'};
  if(/off day/i.test(b))return {kind:'service',text:'Off day with the team'};
  return {kind:'service',text:b?b[0].toUpperCase()+b.slice(1):'Team service'};
 }
 function render(r){
  const seasons=(r.annual||[]).filter(a=>a.calendar&&a.calendar.length).sort((a,b)=>a.year-b.year);
  box.replaceChildren();
  if(!seasons.length){box.hidden=true;return;}box.hidden=false;
  if(!seasons.some(a=>a.year===year))year=seasons[seasons.length-1].year;
  const a=seasons.find(x=>x.year===year);
  el(box,'h3','Where he worked: the duty-day calendar').id='viz-mlb-calendar-heading';
  el(box,'p','Every modeled work day of the season, colored by where it happened. States tax visiting players on the days they work there (the \u201cjock tax\u201d). Hover over or tap a day; use the arrow keys to move through the calendar.','viz-intro');
  const controls=el(box,'div','','viz-controls');
  if(seasons.length>1)segmented(controls,'Season',seasons.map(x=>({label:String(x.year),value:x.year})),year,v=>{year=v;focusKey=null;render(r);});
  el(controls,'span',a.team+' \u00b7 '+a.regular_games+' regular-season, '+a.spring_games+' spring'+(a.postseason_games?', '+a.postseason_games+' postseason':'')+' games','viz-chip');
  const byDate=new Map(a.calendar.map(e=>[e.date,e]));
  const counts={};for(const e of a.calendar){const k=locKey(e);counts[k]=(counts[k]||0)+1;}
  const keys=Object.keys(counts).sort((x,y)=>counts[y]-counts[x]);
  const home=keys[0];
  const colors={};let ci=0;for(const k of keys)colors[k]=k===home?HOME_COLOR:(k==='Canada'?CANADA_COLOR:ROAD_COLORS[ci++%ROAD_COLORS.length]);
  const usStates=keys.filter(k=>STATE_NAMES[k]);
  const stats=el(box,'div','','viz-mini-stats');
  for(const [v,l] of [[a.calendar.length,'duty days'],[counts[home],'in '+locName(home)+' (most days)'],[a.calendar.length-counts[home],'elsewhere'],[usStates.length,'U.S. states with sourced income']]){const d=el(stats,'div');el(d,'strong',String(v));el(d,'span',l);}
  const legend=el(box,'div','','viz-legend');legend.setAttribute('aria-label','Filter calendar by location');
  for(const k of keys){
   const b=el(legend,'button','','viz-legend-item');b.type='button';b.setAttribute('aria-pressed',String(focusKey===k));
   const sw=el(b,'span','','viz-swatch');sw.style.background=colors[k];el(b,'span',locName(k)+(k==='Canada'?' (not modeled)':''));el(b,'strong',String(counts[k]));
   b.addEventListener('click',()=>{focusKey=focusKey===k?null:k;for(const x of legend.querySelectorAll('.viz-legend-item'))x.setAttribute('aria-pressed',String(x===b&&focusKey===k));applyFocus();});
  }
  const note=el(legend,'span','','viz-legend-note');note.innerHTML='<span class="viz-dot"></span> game day &nbsp; <span class="viz-swatch viz-swatch-faded"></span> travel day &nbsp; <span class="viz-swatch" style="background:'+OFF_COLOR+'"></span> no modeled duty';
  const wrap=el(box,'div','','viz-calendar-wrap');
  const dates=a.calendar.map(e=>e.date).sort();
  const first=new Date(dates[0]+'T12:00:00'),last=new Date(dates[dates.length-1]+'T12:00:00');
  const start=new Date(first.getFullYear(),first.getMonth(),1),end=new Date(last.getFullYear(),last.getMonth()+1,0);
  const cell=14,gap=3,step=cell+gap,leftPad=30,topPad=22;
  const weeks=Math.ceil((start.getDay()+Math.round((end-start)/864e5)+1)/7);
  const svg=svgEl(wrap,'svg',{viewBox:'0 0 '+(leftPad+weeks*step)+' '+(topPad+7*step+4),class:'viz-calendar-svg',role:'grid','aria-label':a.year+' duty-day calendar'});
  ['Sun','','Tue','','Thu','','Sat'].forEach((d,i)=>{if(d){const t=svgEl(svg,'text',{x:leftPad-6,y:topPad+i*step+cell-3,class:'viz-cal-axis','text-anchor':'end'});t.textContent=d;}});
  const tip=el(wrap,'div','','viz-tooltip');tip.hidden=true;
  const detail=el(box,'div','','viz-detail viz-cal-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');detail.textContent='Select a day to see what happened and where.';
  const cells=[];
  for(let d=new Date(start),i=0;d<=end;d.setDate(d.getDate()+1),i++){
   const date=iso(d),col=Math.floor((i+start.getDay())/7),row=d.getDay();
   if(d.getDate()===1){const t=svgEl(svg,'text',{x:leftPad+col*step,y:12,class:'viz-cal-axis'});t.textContent=d.toLocaleDateString('en-US',{month:'short'});}
   const e=byDate.get(date),k=e?locKey(e):null,kind=e?kindOf(e):null;
   const rect=svgEl(svg,'rect',{x:leftPad+col*step,y:topPad+row*step,width:cell,height:cell,rx:3,class:'viz-day'+(e?' is-'+kind.kind:' is-off'),fill:e?colors[k]:OFF_COLOR,tabindex:'-1',role:'gridcell'});
   if(kind&&kind.kind==='game')svgEl(svg,'circle',{cx:leftPad+col*step+cell/2,cy:topPad+row*step+cell/2,r:2.6,class:'viz-game-dot','pointer-events':'none'});
   const dateText=new Date(date+'T12:00:00').toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric',year:'numeric'});
   const text=!e?dateText+'\nNo modeled duty day':[dateText,kind.text,(e.city?e.city+', ':'')+locName(k)+(k==='Canada'?' \u00b7 Canadian taxes not modeled':k===home?' \u00b7 most days':' \u00b7 nonresident work day')+(e.locality?' \u00b7 local tax: '+e.locality:'')].join('\n');
   rect.setAttribute('aria-label',text.replace(/\n/g,'. '));
   cells.push({rect,key:k,text,entry:e});
  }
  cells.forEach((c,i)=>{
   const show=()=>{const b=c.rect.getBoundingClientRect(),h=wrap.getBoundingClientRect();tip.textContent=c.text;tip.hidden=false;const below=b.top-h.top<70;tip.classList.toggle('is-below',below);tip.style.left=Math.min(Math.max(b.left-h.left+b.width/2,90),h.width-90)+'px';tip.style.top=((below?b.bottom:b.top)-h.top+wrap.scrollTop)+'px';};
   const pin=()=>{detail.replaceChildren();const lines=c.text.split('\n');el(detail,'strong',lines[0]);for(const l of lines.slice(1))el(detail,'span',l);if(c.entry)el(detail,'small','Basis: '+c.entry.basis+'. Modeled from published schedules; individual attendance is not verified.');};
   c.rect.addEventListener('mouseenter',show);c.rect.addEventListener('mouseleave',()=>{tip.hidden=true;});
   c.rect.addEventListener('click',()=>{pin();c.rect.focus({preventScroll:true});});
   c.rect.addEventListener('focus',()=>{for(const o of cells)o.rect.setAttribute('tabindex','-1');c.rect.setAttribute('tabindex','0');show();pin();});
   c.rect.addEventListener('blur',()=>{tip.hidden=true;});
   c.rect.addEventListener('keydown',ev=>{const move={ArrowRight:7,ArrowLeft:-7,ArrowDown:1,ArrowUp:-1}[ev.key];if(move==null)return;ev.preventDefault();const t=cells[i+move];if(t)t.rect.focus();});
  });
  (cells.find(c=>c.entry)||cells[0]).rect.setAttribute('tabindex','0');
  function applyFocus(){for(const c of cells)c.rect.classList.toggle('is-dimmed',!!focusKey&&c.key!==focusKey);}
  applyFocus();
  el(box,'p','Known seasons from the historical cash estimate ('+seasons.map(x=>x.year).join(', ')+'). Venues, travel and off days are modeled from published schedules; individual attendance is not verified. Days in Canada are shown but Canadian taxes are not modeled.','viz-footnote');
 }
}

initCounters();
initRanking(NFL_RANKING);
initRanking(MLB_RANKING);
initWaterfall();
initMlbWaterfall();
initCalendar();
initMlbCalendar();
initMirror();
initOfferRanking();
})();