'use strict';
let offerCatalog=null,offerMode='compare',offerRequest=0,offerController=null;
const offerForm=$('offer-form');
const exactMoney=v=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:2}).format(v);
function offerDirty(){offerRequest++;offerController?.abort();$('offer-output').hidden=true;$('offer-submit').disabled=!offerCatalog;$('offer-status').textContent='Inputs changed. Calculate again to update the estimates.';}
function offerTeam(side){return offerCatalog.teams[$('offer-league').value].find(t=>t.id===$('offer-'+side+'-team').value);}
function offerSalaryInputs(){
 const count=Number($('offer-years').value),start=Number($('offer-start').value);if(!Number.isInteger(count)||count<1||count>10||!Number.isInteger(start))return;
 for(const side of ['a','b']){const root=$('offer-'+side+'-salaries'),old=[...root.querySelectorAll('input')].map(i=>i.value);root.replaceChildren();
  for(let i=0;i<count;i++){const label=text(root,'label','USD salary · '+(start+i));label.htmlFor='offer-'+side+'-salary-'+i;const input=text(label,'input','');input.id=label.htmlFor;input.type='number';input.min='0';input.max='1000000000';input.step='0.01';input.value=old[i]??old[0]??'30000000';input.required=true;input.disabled=side==='b'&&offerMode==='breakeven';}
 }
}
function offerResidenceDefault(side){
 const t=offerTeam(side);$('offer-'+side+'-residence').value=t.base_state||'';
 $('offer-'+side+'-location-note').textContent=t.base_state?'Defaults to the team’s saved base state; this residence assumption is editable.':'Canadian-resident taxes are not modeled. Choose an explicit U.S. residence to calculate U.S. components only.';
}
function offerLeagueTeams(){
 const league=$('offer-league').value;
 for(const side of ['a','b']){const select=$('offer-'+side+'-team');select.replaceChildren();for(const t of offerCatalog.teams[league])text(select,'option',t.name).value=t.id;
  select.value=league==='NFL'?(side==='a'?'NFL_BUF':'NFL_MIA'):(side==='a'?'147':'119');offerResidenceDefault(side);
 }
 $('offer-nfl-setting').hidden=league!=='NFL';$('offer-mlb-setting').hidden=league!=='MLB';
}
function setOfferMode(mode){
 offerMode=mode;for(const value of ['compare','breakeven'])$('mode-'+value).setAttribute('aria-pressed',String(value===mode));
 $('offer-b-salary-panel').hidden=mode==='breakeven';$('offer-b-solver-panel').hidden=mode!=='breakeven';
 $('offer-a-legend').textContent=mode==='breakeven'?'Reference offer A':'Offer A';$('offer-b-legend').textContent=mode==='breakeven'?'Target team B':'Offer B';
 $('offer-submit').textContent=mode==='breakeven'?'Find break-even offer':'Compare offers';
 for(const input of $('offer-b-salaries').querySelectorAll('input'))input.disabled=mode==='breakeven';
 offerDirty();
}
for(const mode of ['compare','breakeven'])$('mode-'+mode).addEventListener('click',()=>setOfferMode(mode));
offerForm.addEventListener('input',offerDirty);
offerForm.addEventListener('change',event=>{
 if(event.target.id==='offer-league')offerLeagueTeams();
 for(const side of ['a','b'])if(event.target.id==='offer-'+side+'-team')offerResidenceDefault(side);
 if(['offer-years','offer-start'].includes(event.target.id))offerSalaryInputs();offerDirty();
});
for(const button of document.querySelectorAll('.offer-copy'))button.addEventListener('click',()=>{const inputs=[...$('offer-'+button.dataset.side+'-salaries').querySelectorAll('input')];for(const input of inputs)input.value=inputs[0].value;offerDirty();});
function offerPayload(){
 const offer=side=>({team_id:$('offer-'+side+'-team').value,residence:$('offer-'+side+'-residence').value,annual_salaries:[...$('offer-'+side+'-salaries').querySelectorAll('input')].map(i=>Number(i.value))});
 return {league:$('offer-league').value,mode:offerMode,start_year:Number($('offer-start').value),filing:$('offer-filing').value,mlb_role:$('offer-role').value,travel_days:Number($('offer-travel').value),structure:$('offer-structure').value,offer_a:offer('a'),offer_b:offer('b')};
}
function renderOfferResult(result){
 const a=result.offer_a,b=result.offer_b,solved=result.mode==='breakeven';
 $('offer-result-title').textContent=solved?'The break-even offer':'Two offers, after estimated taxes';
 const outcome=$('offer-outcome');outcome.replaceChildren();outcome.classList.toggle('approximate',!!result.solver&&!result.solver.converged);
 if(solved){const s=result.solver;text(outcome,'strong',money(b.gross)+' total salary from '+b.team.name);text(outcome,'p','Estimated to match the reference offer’s '+money(a.remaining)+' total take-home across '+result.years+' salary years. '+(s.structure==='flat'?'Target salary is equal in each year.':'Target salaries preserve the reference offer’s annual proportions.'));
  text(outcome,'p',money(Math.abs(s.gross_difference))+' '+(s.gross_difference>=0?'more':'less')+' total salary than Offer A. Average annual salary: '+money(b.gross/result.years)+'.');
  text(outcome,'p',(s.converged?'Matched within the $1 model tolerance.':'Approximate result: the $1 model tolerance was not reached.')+' Take-home difference: '+exactMoney(s.residual)+'. Matching whole-contract take-home does not guarantee identical annual take-home.');
 }else{text(outcome,'strong',Math.abs(result.take_home_difference)<1?'The offers produce approximately equal estimated take-home.':(result.take_home_difference>0?'Offer B':'Offer A')+' leaves '+money(Math.abs(result.take_home_difference))+' more estimated take-home.');text(outcome,'p','Comparison covers '+result.start_year+'–'+(result.start_year+result.years-1)+' using each selected team’s work locations and the entered residence assumptions. Different salary amounts and work locations both affect the outcome.');}
 if(result.league==='NFL')text(outcome,'p','NFL take-home uses the mean of modeled opponent scenarios. A break-even match of that mean does not guarantee a match under every future schedule.');
 const cards=$('offer-result-cards');cards.replaceChildren();
 for(const [row,label] of [[a,'OFFER A · REFERENCE'],[b,solved?'OFFER B · BREAK-EVEN':'OFFER B']]){
  const card=text(cards,'article','','offer-card');card.style.setProperty('--offer-accent',teamColors[row.team.code]||'#28796b');const header=text(card,'div','','offer-card-header');
  const logo=document.createElement('img');logo.src=row.team.logo_url;logo.alt=row.team.name+' logo';logo.addEventListener('error',()=>logo.remove(),{once:true});header.append(logo);const identity=text(header,'div','');text(identity,'small',label);text(identity,'h3',row.team.name);text(identity,'p',row.residence_name+' · assumed residence');
  const dl=text(card,'dl','');for(const [label,key,format] of [['Total salary','gross',money],['Estimated take-home','remaining',money],['Estimated U.S. taxes','total_tax',money],['Take-home percentage','take_home_percentage',v=>v.toFixed(1)+'%'],['Average annual take-home','annual_take_home',money]]){const cell=text(dl,'div','',key==='remaining'?'offer-net':'');text(cell,'dt',label);text(cell,'dd',format(row[key]));}
 }
 TaxBreakdown.render($('offer-tax-bars'),[{name:a.team.name+' · '+a.residence_name,result:a,grossKey:'gross',coverage_text:'Covers all entered salary years. Hypothetical salary scenario, not a reported contract.'},{name:b.team.name+' · '+b.residence_name,result:b,grossKey:'gross',coverage_text:'Covers all entered or solved salary years. Hypothetical salary scenario, not a reported contract.'}]);
 $('offer-annual').replaceChildren();for(let i=0;i<a.annual.length;i++){const x=a.annual[i],y=b.annual[i],tr=text($('offer-annual'),'tr','');for(const [j,v] of [x.year,x.cash,x.total_tax,x.remaining,y.cash,y.total_tax,y.remaining].entries())text(tr,'td',j===0?String(v):money(v));}
 const work=$('offer-work-locations');work.replaceChildren();
 for(const row of [a,b]){text(work,'h3',row.team.name+' · '+row.residence_name);for(const year of row.annual){const section=text(work,'div','','offer-work-year');text(section,'h4',year.year+' · '+year.schedule_basis);text(section,'p',year.duty_days.toFixed(1)+' expected duty days · '+year.foreign_days.toFixed(1)+' outside U.S. states · '+year.scenarios+' weighted schedule combinations.');const wrap=text(section,'div','','table-wrap'),table=text(wrap,'table',''),head=text(text(table,'thead',''),'tr','');for(const h of ['Work state','Expected duty days','Salary allocation share'])text(head,'th',h);const body=text(table,'tbody','');for(const [state,share] of Object.entries(year.state_shares).sort()){const tr=text(body,'tr','');text(tr,'td',offerCatalog.states.find(s=>s.code===state)?.name||state);text(tr,'td',year.state_days[state].toFixed(1));text(tr,'td',(100*share).toFixed(2)+'%');}if(year.foreign_days){const tr=text(body,'tr','');text(tr,'td','Outside U.S. states · foreign taxes excluded');text(tr,'td',year.foreign_days.toFixed(1));const foreignShare=1-Object.values(year.state_shares).reduce((s,v)=>s+v,0);text(tr,'td',(100*foreignShare).toFixed(2)+'%');}}}
 $('offer-assumptions').replaceChildren();result.notes.forEach(note=>text($('offer-assumptions'),'p',note));
 const sources=$('offer-sources');sources.replaceChildren();const seen=new Set();for(const row of [a,b])for(const source of row.sources){if(seen.has(source.source))continue;seen.add(source.source);sourceLink(text(sources,'p',''),source.state+' tax source',source.source);}
 sourceLink(text(sources,'p',''),result.league==='NFL'?'NFL scheduling formula':'MLB published reference schedules',result.league==='NFL'?'https://operations.nfl.com/calendar-events/nfl-schedule/making-the-schedule':'https://statsapi.mlb.com/api/v1/schedule?sportId=1&season=2026&gameTypes=S,R&hydrate=venue(location)');
 $('offer-output').hidden=false;
}
offerForm.addEventListener('submit',async event=>{
 event.preventDefault();if(!offerCatalog||!offerForm.reportValidity())return;
 const request=++offerRequest;offerController?.abort();offerController=new AbortController();$('offer-output').hidden=true;$('offer-submit').disabled=true;$('offer-status').textContent=offerMode==='breakeven'?'Solving the equivalent salary using the target team’s work locations…':'Calculating both offers using their team-specific work locations…';
 try{const response=await fetch('/api/offers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(offerPayload()),signal:offerController.signal});const result=await response.json();if(!response.ok)throw new Error(result.error||'Offer calculation unavailable.');if(request!==offerRequest)return;renderOfferResult(result);$('offer-status').textContent='Ready · salary-only estimates · fixed 2026 tax rules.';}
 catch(error){if(request===offerRequest&&error.name!=='AbortError')$('offer-status').textContent=error.message;}
 finally{if(request===offerRequest)$('offer-submit').disabled=false;}
});
(async()=>{try{const response=await fetch('/api/offers/catalog');if(!response.ok)throw new Error('Teams could not be loaded.');offerCatalog=await response.json();for(const side of ['a','b']){const select=$('offer-'+side+'-residence');text(select,'option','Choose a U.S. residence assumption').value='';for(const state of offerCatalog.states)text(select,'option',state.name).value=state.code;}
 $('offer-league').value=new URLSearchParams(location.search).get('league')?.toUpperCase()==='MLB'?'MLB':'NFL';offerLeagueTeams();offerSalaryInputs();$('offer-submit').disabled=false;$('offer-status').textContent='Choose teams and enter yearly salaries, then select a mode.';
 }catch(error){$('offer-status').textContent=error.message;}})();
