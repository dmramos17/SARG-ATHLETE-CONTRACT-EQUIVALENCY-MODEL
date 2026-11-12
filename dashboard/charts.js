/* charts.js - interactive visuals added on top of the existing dashboard.
 * Load this file LAST on each page (after the page's own scripts).
 * It never edits existing code: it reads the same API endpoints and wraps
 * two existing render functions so it receives the same data they do.
 *   index.html   -> animated stat counters + "Same contract, 51 residences" ranking
 *   tax.html     -> paycheck waterfall + season duty-day calendar
 *   compare.html -> head-to-head mirrored bars
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
async function computeRanking(player,filing){
 const key=player.id+'|'+filing;
 if(rankingCache.has(key))return rankingCache.get(key);
 const job=(async()=>{
  const cash=player.estimate_cash??player.season_cash;
  if(!Number.isFinite(cash)||cash<=0)throw new Error('This player needs verified 2025 cash before states can be ranked.');
  const duty=await getJson('/api/duty-days',{player_id:player.id});
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
function initRanking(){
 const anchor=byId('recent-heading')?.closest('section');if(!anchor)return;
 const section=document.createElement('section');section.className='home-section viz-ranking';section.setAttribute('aria-labelledby','viz-ranking-heading');anchor.after(section);
 const title=el(section,'div','','section-title');const tl=el(title,'div');el(tl,'p','Across state lines','eyebrow');el(tl,'h2','Same contract, 51 residences').id='viz-ranking-heading';el(title,'span','2025 season cash \u00b7 2025 tax rules');
 el(section,'p','Search any NFL player with reported 2025 cash. The team, schedule, and 2025 duty days stay the same; only the player\u2019s home state changes. Bars show how much more or less he keeps compared with living in his team\u2019s state.','section-description');
 const card=el(section,'div','','viz-ranking-card');
 const controls=el(card,'div','','viz-ranking-controls');
 // Player search box (same /api/players endpoint as the search at the top of the page).
 const pickWrap=el(controls,'div','','viz-field viz-search');
 const searchLabel=el(pickWrap,'label','Player');searchLabel.htmlFor='viz-ranking-search';
 const search=el(pickWrap,'input');search.id='viz-ranking-search';search.type='search';search.autocomplete='off';search.spellcheck=false;search.placeholder='Search a player, e.g. Josh Allen';
 search.setAttribute('role','combobox');search.setAttribute('aria-autocomplete','list');search.setAttribute('aria-expanded','false');search.setAttribute('aria-controls','viz-ranking-options');
 const listbox=el(pickWrap,'div','','viz-options');listbox.id='viz-ranking-options';listbox.setAttribute('role','listbox');listbox.setAttribute('aria-label','Matching players');listbox.hidden=true;
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
 const cashOf=p=>p.estimate_cash??p.season_cash;
 function choose(player){current=player;search.value=player.name;closeOptions();expanded=false;load();}
 function closeOptions(){listbox.hidden=true;search.setAttribute('aria-expanded','false');search.removeAttribute('aria-activedescendant');active=-1;}
 function highlight(i){active=i;[...listbox.children].forEach((o,k)=>o.setAttribute('aria-selected',String(k===i)));const o=listbox.children[i];if(o){search.setAttribute('aria-activedescendant',o.id);o.scrollIntoView({block:'nearest'});}}
 async function findPlayers(){
  const q=search.value.trim(),mine=++searchRequest;if(q.length<2){closeOptions();return;}
  try{
   const data=await getJson('/api/players?q='+encodeURIComponent(q));if(mine!==searchRequest)return;
   matches=data.players||[];listbox.replaceChildren();
   if(!matches.length){el(listbox,'p','No players found.','viz-option-empty');}
   matches.forEach((p,i)=>{
    const ok=Number.isFinite(cashOf(p))&&cashOf(p)>0;
    const o=el(listbox,'div','','viz-option'+(ok?'':' is-disabled'));o.id='viz-ranking-option-'+i;o.setAttribute('role','option');o.setAttribute('aria-selected','false');if(!ok)o.setAttribute('aria-disabled','true');
    el(o,'strong',p.name);el(o,'span',p.team_code+' \u00b7 '+(p.position||'')+' \u00b7 '+(ok?usdShort(cashOf(p))+' 2025 cash':'needs verified cash'));
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
   const result=await computeRanking(player,filing);if(mine!==request)return;
   render(player,result);
  }catch(error){if(mine!==request)return;list.replaceChildren();summary.textContent=error.message;toggle.hidden=true;}
  finally{if(mine===request)list.setAttribute('aria-busy','false');}
 }
 // Name the actual states: full names for up to 3, postal codes (A-Z by name) for longer ties.
 function tieLabel(group){return group.length===1?stateName(group[0].code):group.length<=3?group.map(r=>stateName(r.code)).join(', '):group.map(r=>r.code).join(', ');}
 function render(player,{cash,duty,rows}){
  const home=duty.residence_default||player.home_state,base=rows.find(r=>r.code===home);
  if(!base){summary.textContent='The team state could not be calculated.';return;}
  const same=(a,b)=>Math.round(a.remaining)===Math.round(b.remaining);
  // Competition ranking: tied states share the best rank in their group (1, 1, 1, 4 ...).
  let shown=rows.map((r,i,all)=>{let first=i;while(first>0&&same(all[first-1],r))first--;let count=0;for(const x of all)if(same(x,r))count++;return {...r,rank:first+1,tied:count>1};});
  const bestGroup=shown.filter(r=>same(r,shown[0])),worstGroup=shown.filter(r=>same(r,shown[shown.length-1]));
  const best=bestGroup[0],worst=worstGroup[0],spread=best.remaining-worst.remaining;
  const away=Object.entries(duty.state_days||{}).filter(([s])=>s!==home).reduce((a,[,n])=>a+n,0);
  const allNoTax=g=>g.every(r=>r.residenceTax===0);
  summary.replaceChildren();
  for(const [label,value,note] of [['2025 cash',usdShort(cash),duty.total_days+' duty days \u00b7 '+away+' outside '+home],['Best residence',tieLabel(bestGroup),(bestGroup.length>1?'Tied \u00b7 ':'')+usdShort(best.remaining)+' take-home'+(bestGroup.length>1?(allNoTax(bestGroup)?' each \u00b7 no wage tax':' each'):'')],['Toughest residence',tieLabel(worstGroup),(worstGroup.length>1?'Tied \u00b7 ':'')+usdShort(worst.remaining)+' take-home'+(worstGroup.length>1?' each':'')],['Spread',usdShort(spread),'kept by picking the best over the worst state']]){
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
   item.setAttribute('aria-label',(row.tied?'Tied for '+row.rank:'Rank '+row.rank)+'. '+stateName(row.code)+': '+usd(row.remaining)+' take-home, '+(isHome?'team state baseline':signed(diff)+' versus '+stateName(home)));
   el(item,'span',rankText,'viz-rank-number');
   const name=el(item,'span','','viz-rank-name');el(name,'strong',stateName(row.code));
   if(isHome)el(name,'em','Team state','viz-tag');else if(row.residenceTax===0)el(name,'em','No wage tax','viz-tag viz-tag-soft');
   const track=el(item,'span','','viz-rank-track');el(track,'span','','viz-rank-axis');
   const bar=el(track,'span','','viz-rank-bar '+(diff>=0?'is-up':'is-down'));
   bar.style.setProperty('--w',(Math.abs(diff)/max*50).toFixed(2)+'%');
   el(item,'span',isHome?'Baseline':signed(diff),'viz-rank-diff '+(isHome?'':diff>=0?'is-up':'is-down'));
   el(item,'span',usdShort(row.remaining),'viz-rank-value');
   const explain=()=>{detail.textContent=stateName(row.code)+' residence'+(row.tied?' (tied for '+row.rank+')':'')+': '+usd(row.remaining)+' take-home ('+pct(row.remaining/cash*100)+'). Federal '+usdShort(row.federal)+' \u00b7 payroll '+usdShort(row.payroll)+' \u00b7 home-state tax '+usdShort(row.residenceTax)+(row.credit?' after a '+usdShort(row.credit)+' credit':'')+' \u00b7 tax to other states '+usdShort(row.nonresident)+'.';};
   item.addEventListener('mouseenter',explain);item.addEventListener('focus',explain);item.addEventListener('click',explain);
  }
  toggle.hidden=rows.length<=22;toggle.textContent=expanded?'Show top and bottom 10':'Show all '+rows.length+' states';
  if(!reduceMotion)requestAnimationFrame(()=>list.classList.add('is-drawn'));else list.classList.add('is-drawn');
 }
 // Start with the largest featured 2025 signing and offer the featured deals as one-click picks.
 getJson('/api/directory').then(data=>{
  const featured=(data.featured||[]).filter(p=>Number.isFinite(cashOf(p))&&cashOf(p)>0);
  for(const p of featured){const b=el(quick,'button',p.name,'viz-chip-button');b.type='button';b.addEventListener('click',()=>choose(p));}
  quick.hidden=!featured.length;
  if(!featured.length){summary.textContent='Search for a player to rank all 51 residences.';return;}
  current=featured[0];search.value=current.name;
  // Only start the 51 calculations when the section scrolls near the screen.
  const io=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){io.disconnect();load();}},{rootMargin:'300px'});io.observe(section);
 }).catch(()=>{summary.textContent='Search for a player to rank all 51 residences.';});
}

/* ---------------------------------------------------------------------------
 * 3. PAYCHECK WATERFALL (tax.html) - wraps renderComparison(out, baseline)
 * ------------------------------------------------------------------------- */
function waterfallAmounts(result,year){
 if(year==='all'){
  const s=window.TaxBreakdown?.summarize(result,'gross');
  return s&&s.available?{cash:s.income,...s.amounts,label:'Whole contract window \u00b7 '+s.years[0]+'\u2013'+s.years[s.years.length-1]}:{error:s?s.reason:'Not available.'};
 }
 const y=(result.annual||[]).find(a=>String(a.year)===String(year));
 if(!y||!Number.isFinite(y.remaining)||!Number.isFinite(y.cash))return {error:'Annual cash is needed before '+year+' can be shown.'};
 const local=Number.isFinite(y.local)?y.local:0;
 return {cash:y.cash,federal:y.federal,payroll:y.payroll,state:y.state,local,remaining:y.remaining,label:'Calendar year '+y.year+' \u00b7 '+(y.schedule_basis||'')};
}
function drawWaterfall(host,amounts,detail){
 host.replaceChildren();
 if(amounts.error){el(host,'p',amounts.error,'viz-empty');return;}
 const W=760,H=330,top=34,bottom=270,left=18,right=W-18,cols=6,slot=(right-left)/cols,barW=Math.min(84,slot*0.62);
 const y=v=>bottom-(v/amounts.cash)*(bottom-top);
 const svg=svgEl(host,'svg',{viewBox:'0 0 '+W+' '+H,class:'viz-waterfall-svg',role:'img','aria-label':'Paycheck waterfall: '+usd(amounts.cash)+' cash minus federal '+usd(amounts.federal)+', payroll '+usd(amounts.payroll)+', state '+usd(amounts.state)+', local '+usd(amounts.local)+' leaves '+usd(amounts.remaining)+' take-home.'});
 for(const f of [0.25,0.5,0.75,1])svgEl(svg,'line',{x1:left,x2:right,y1:y(amounts.cash*f),y2:y(amounts.cash*f),class:'viz-grid'});
 svgEl(svg,'line',{x1:left,x2:right,y1:bottom,y2:bottom,class:'viz-baseline'});
 let running=amounts.cash;
 const steps=[{key:'cash',label:'Reported cash',from:0,to:amounts.cash}];
 for(const key of ['federal','payroll','state','local']){steps.push({key,label:key[0].toUpperCase()+key.slice(1),from:running-amounts[key],to:running,drop:true});running-=amounts[key];}
 steps.push({key:'remaining',label:'Take-home',from:0,to:amounts.remaining});
 steps.forEach((s,i)=>{
  const cx=left+slot*i+slot/2,x=cx-barW/2,h=Math.max(1.5,y(s.from)-y(s.to)),value=s.to-s.from;
  const g=svgEl(svg,'g',{class:'viz-wf-step',tabindex:'0',role:'button','aria-label':s.label+': '+usd(value)+', '+pct(value/amounts.cash*100)+' of cash'});
  svgEl(g,'rect',{x:cx-slot/2,y:top-24,width:slot,height:bottom-top+24,fill:'transparent'});
  const rect=svgEl(g,'rect',{x,y:y(s.to),width:barW,height:h,rx:4,fill:TAX_COLORS[s.key],class:'viz-wf-bar'+(s.drop?' is-drop':'')});
  rect.style.animationDelay=(i*90)+'ms';
  if(i<steps.length-1){const nextTop=s.drop?y(s.from):y(s.to);svgEl(svg,'line',{x1:x+barW,x2:x+slot,y1:nextTop,y2:nextTop,class:'viz-connector'});}
  const t=svgEl(g,'text',{x:cx,y:y(s.to)-8,class:'viz-wf-value','text-anchor':'middle'});t.textContent=(s.drop?'\u2212':'')+usdShort(value);
  const n=svgEl(g,'text',{x:cx,y:bottom+20,class:'viz-wf-label','text-anchor':'middle'});n.textContent=s.label;
  const p=svgEl(g,'text',{x:cx,y:bottom+37,class:'viz-wf-pct','text-anchor':'middle'});p.textContent=pct(value/amounts.cash*100);
  const show=()=>{detail.textContent=s.label+': '+usd(value)+' \u00b7 '+pct(value/amounts.cash*100)+' of '+usd(amounts.cash)+' reported cash'+(s.key==='local'?' (supported local work taxes only).':'.');};
  g.addEventListener('mouseenter',show);g.addEventListener('focus',show);g.addEventListener('click',show);
 });
}
function initWaterfall(){
 const anchor=byId('projection-tax-breakdown');if(!anchor)return;
 const box=document.createElement('section');box.className='viz-card viz-waterfall';box.setAttribute('aria-labelledby','viz-waterfall-heading');anchor.after(box);
 let latest=null,who='comparison',year='all';
 function render(){
  if(!latest)return;const {out,baseline}=latest;box.replaceChildren();
  const different=out.residence!==baseline.residence;if(!different)who='base';
  const result=who==='base'?baseline:out;
  el(box,'h3','Paycheck waterfall').id='viz-waterfall-heading';
  el(box,'p','Start with reported cash, then watch each tax come out. Hover over, tap, or Tab to a bar for exact amounts.','viz-intro');
  const controls=el(box,'div','','viz-controls');
  if(different)segmented(controls,'Residence',[{label:stateName(baseline.residence)+' \u00b7 base',value:'base'},{label:stateName(out.residence)+' \u00b7 comparison',value:'comparison'}],who,v=>{who=v;render();});
  else el(controls,'span',stateName(baseline.residence)+' \u00b7 base state','viz-chip');
  const sel=el(controls,'select','','viz-select');sel.setAttribute('aria-label','Period');
  el(sel,'option','Whole contract window').value='all';
  for(const a of result.annual||[])el(sel,'option',String(a.year)).value=String(a.year);
  if(![...sel.options].some(o=>o.value===year))year='all';sel.value=year;sel.addEventListener('change',()=>{year=sel.value;render();});
  const amounts=waterfallAmounts(result,year);
  if(amounts.label)el(box,'p',amounts.label,'viz-caption');
  const chart=el(box,'div','','viz-waterfall-chart');
  const detail=el(box,'p','','viz-detail');detail.setAttribute('role','status');detail.setAttribute('aria-live','polite');
  drawWaterfall(chart,amounts,detail);
  if(!amounts.error)detail.textContent='Take-home: '+usd(amounts.remaining)+' \u00b7 '+pct(amounts.remaining/amounts.cash*100)+' of reported cash. Taxes: '+usd(amounts.cash-amounts.remaining)+'.';
 }
 wrapGlobal('renderComparison',(out,baseline)=>{if(!baseline)return;latest={out,baseline};who='comparison';render();});
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

initCounters();
initRanking();
initWaterfall();
initCalendar();
initMirror();
})();