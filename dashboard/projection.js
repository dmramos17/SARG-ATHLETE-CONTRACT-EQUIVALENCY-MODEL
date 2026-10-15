let projectionRequest=0;
for(const [code,name] of Object.entries(states)){const o=document.createElement('option');o.value=code;o.textContent=name;$('projection-residence').append(o);}
$('projection-residence').value='NY';
function configureProjection(row){
 const eligible=row.player_id==='00-0034857';
 $('contract-views').hidden=!eligible;
 showContractView(false);
}
function showContractView(full){
 $('annual-view').hidden=full;$('full-contract-view').hidden=!full;
 $('annual-view-button').setAttribute('aria-pressed',String(!full));$('full-view-button').setAttribute('aria-pressed',String(full));
 if(full)loadProjection();
}
$('annual-view-button').addEventListener('click',()=>showContractView(false));
$('full-view-button').addEventListener('click',()=>showContractView(true));
$('update-projection').addEventListener('click',loadProjection);
for(const id of ['projection-residence','projection-filing','projection-bonus','projection-travel'])$(id).addEventListener('change',()=>{$('projection-output').hidden=true;$('projection-status').textContent='Assumptions changed. Update the contract projection to apply them.';projectionRequest++;$('update-projection').disabled=false;});
async function loadProjection(){
 const request=++projectionRequest;
 $('projection-status').textContent='Calculating six years and opponent scenarios…';$('projection-output').hidden=true;$('update-projection').disabled=true;
 try{
  const query=new URLSearchParams({player:'00-0034857',residence:$('projection-residence').value,filing:$('projection-filing').value,qualifying:$('projection-bonus').value,travel_days:$('projection-travel').value});
  const response=await fetch('/api/contract-projection?'+query);const out=await response.json();if(!response.ok)throw new Error(out.error);
  if(request!==projectionRequest)return;
  $('projection-gross').textContent=money(out.gross);$('projection-net').textContent=money(out.remaining);$('projection-tax').textContent=money(out.total_tax);
  $('projection-range').textContent='Schedule-based take-home range: '+money(out.low_remaining)+' – '+money(out.high_remaining);
  $('projection-guarantees').textContent='Reported at signing: '+money(out.fully_guaranteed_at_signing)+' fully guaranteed; '+money(out.reported_total_guarantees)+' total guarantees, including conditional/vesting amounts. The '+money(out.gross)+' scheduled total is not all fully guaranteed.';
  for(const id of ['projection-years','projection-cash','projection-opponents','projection-notes','projection-sources'])$(id).replaceChildren();
  for(const year of out.annual){
   const row=text($('projection-years'),'tr','');for(const v of [year.year,...['cash','federal','payroll','state','local','remaining'].map(k=>money(year[k])),year.schedule_basis])text(row,'td',v);
   const range=text(row.children[6],'small',money(year.low_remaining)+' – '+money(year.high_remaining));range.className='projection-year-range';
   row.title='Take-home range '+money(year.low_remaining)+' – '+money(year.high_remaining)+'; '+year.scenarios+' jurisdiction combinations; '+year.duty_days+' modeled duty days.';
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
