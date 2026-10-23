/* Dashboard interactions: native controls, local exports, and URL-backed views. */
(() => {
'use strict';
let records=[], revisionHistory={updates:[]}, ready=false, restoring=false;
const chart = kind => [...document.querySelectorAll('.js-plotly-plot')].find(p=>p.layout?.meta?.kind===kind);
const select = kind => document.querySelector(`[data-chart-select="${kind}"]`);
const iso = value => value == null ? '' : String(value).slice(0,10);
const fmt = value => value == null ? 'Unavailable' : Number(value).toLocaleString(undefined,{maximumFractionDigits:2});
const status = text => { const el=document.getElementById('explorer-status'); if(el)el.textContent=text; };
const selectedDisease = () => select('disease')?.selectedOptions[0]?.textContent.replace(/ \(last reported .*\)$/,'');
const diseaseRows = () => records.filter(r=>r.disease===selectedDisease());
function setupExplorerLayout(){
 const plot=chart('disease'),detail=document.getElementById('disease-detail');
 if(!plot||!detail||document.querySelector('.explorer-layout'))return;
 const body=plot.closest('.card-body'),plotOutput=plot.closest('.cell-output-display'),detailOutput=detail.closest('.cell-output-display');
 if(!body||!plotOutput||!detailOutput||plotOutput===detailOutput)return;
 const layout=document.createElement('div');layout.className='explorer-layout';
 detail.tabIndex=0;detail.setAttribute('aria-label','Selected disease details');
 layout.append(plotOutput,detail);
 const advanced=document.createElement('details');advanced.className='explorer-extra';
 const summary=document.createElement('summary');summary.textContent='Download data, copy links and save views';advanced.append(summary,detailOutput);
 body.append(layout,advanced);
}
async function redrawVisiblePlots(){
 if(!window.Plotly)return;
 for(const el of document.querySelectorAll('.js-plotly-plot')){
  if(el.offsetParent===null)continue;
  const updates={width:Math.round(el.getBoundingClientRect().width),'legend.entrywidth':150};
  if(el.layout?.meta?.kind==='disease' && el.closest('.explorer-layout')){
   const h=window.innerWidth>900?390:440;el.parentElement.style.height=h+'px';
   Object.assign(updates,{height:h,'margin.t':25,'margin.b':25});
  }
  await Plotly.relayout(el,updates);
 }
}
function updateCoverage(){
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 document.querySelectorAll('[data-coverage-end]').forEach(el=>{
  const stale=(Date.parse(today+'T00:00:00Z')-Date.parse(el.dataset.coverageEnd+'T00:00:00Z'))/86400000>14;
  el.dataset.stale=String(stale);el.textContent=stale?'Behind expected weekly coverage':'Within 14 days of week end';
 });
}
function currentRange(){return [document.getElementById('export-start').value,document.getElementById('export-end').value];}
function saveUrl(){
 if(!ready || restoring)return;
 const url=new URL(location.href), range=currentRange();
 url.searchParams.set('disease',selectedDisease());
 url.searchParams.set('start',range[0]);url.searchParams.set('end',range[1]);
 for(const kind of ['haze','scatter','evaluation'])if(select(kind))url.searchParams.set(kind,select(kind).value);
 url.searchParams.set('years',document.getElementById('season-years').value);
 history.replaceState(null,'',url);
}
function cell(row,value,header=false){const el=document.createElement(header?'th':'td');if(header)el.scope='col';el.textContent=value;row.append(el);}
function renderDetail(){
 if(!ready)return;
 const rows=diseaseRows(), host=document.getElementById('disease-detail');host.replaceChildren();
 const last=rows.at(-1), valid=rows.filter(r=>r.cases!=null), lastReported=valid.at(-1);
 if(!last)return;
 const prior=rows.find(r=>Date.parse(last.week_start)-Date.parse(r.week_start)===604800000);
 const heading=document.createElement('h3');heading.textContent=selectedDisease();host.append(heading);
 const metrics=document.createElement('dl');metrics.className='detail-metrics';
 const change=last.cases!=null && prior?.cases!=null ? last.cases-prior.cases : null;
 const threshold=last.hl_threshold??last.c2_threshold, expected=last.hl_threshold!=null?last.hl_expected:last.c2_expected;
 const metricsList=[['Latest count',fmt(last.cases)],['Previous week',fmt(prior?.cases)],['Weekly change',change==null?'Unavailable':`${change>0?'+':''}${fmt(change)}${prior.cases>0?' ('+(change/prior.cases*100).toFixed(1)+'%)':''}`],['Expected',fmt(expected)],['Signal threshold',fmt(threshold)],['Signal state',last.signal_state]];
 for(const [label,value] of metricsList){const pair=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;pair.append(dt,dd);metrics.append(pair);}host.append(metrics);
 const text=document.createElement('p');
 let explanation=last.cases==null?'The latest observation is unavailable.':threshold==null?'There is insufficient baseline history to assess this observation.':last.cases<5?'The count is below the five-case minimum for a statistical signal.':last.any_alert?`The count exceeds the ${last.hl_threshold!=null?'seasonal':'EARS C2 fallback'} threshold. This is a prompt for review, not a confirmed outbreak.`:`The count does not exceed the applicable ${last.hl_threshold!=null?'seasonal':'EARS C2 fallback'} threshold.`;
 if(last.signal_run_weeks)explanation+=` This signal has persisted for ${last.signal_run_weeks} consecutive week${last.signal_run_weeks===1?'':'s'}, beginning ${iso(last.episode_start)}.`;
 const globalLatest=records.reduce((a,r)=>r.week_start>a?r.week_start:a,'');
 if(last.week_start<globalLatest)explanation+=' Historical series: no observation in the dashboard’s latest reporting week.';
 text.textContent=`Week starting ${iso(last.week_start)}. ${explanation}`;host.append(text);
 const coverage=document.createElement('p');coverage.className='muted';coverage.textContent=`Reported coverage: ${iso(valid[0]?.week_start)} to ${iso(lastReported?.week_start)}; ${valid.length.toLocaleString()} observed weeks and ${rows.length-valid.length} unavailable observations within the series.`;host.append(coverage);
 const updates=revisionHistory.updates||[], latest=updates.at(-1), revisions=latest?.changes?.filter(r=>r.disease===selectedDisease())||[];
 const revision=document.createElement('p');revision.className='revision-note';revision.textContent=latest?`${revisions.length} case-count revisions for this disease in the latest retained snapshot comparison. Tracking began ${iso(revisionHistory.started_at)}.`:'Revision tracking starts with the next retained snapshot.';host.append(revision);
 const [start,end]=currentRange(), episodes=new Map();
 for(const r of rows)if(r.any_alert && iso(r.week_start)>=start && iso(r.week_start)<=end)episodes.set(iso(r.episode_start),r);
 const recent=[...episodes.values()].slice(-5).reverse();
 if(recent.length){const p=document.createElement('p');p.className='muted';p.textContent='Recent signal episodes intersecting the selected period: '+recent.map(r=>`${iso(r.episode_start)} (${r.signal_run_weeks} consecutive weeks through ${iso(r.week_start)})`).join('; ')+'. Runs break on a non-signal, unavailable observation, or missing calendar week.';host.append(p);}
}
function renderSeason(){
 if(!ready)return;
 const rows=diseaseRows(), all=[...new Set(rows.map(r=>r.year))].sort((a,b)=>a-b), count=Number(document.getElementById('season-years').value), years=count?all.slice(-count):all;
 const colors=['#94a3b8','#0891b2','#a16207','#7c3aed','#64748b','#1d4ed8'];
 const traces=years.map((year,i)=>{const points=rows.filter(r=>r.year===year).sort((a,b)=>a.week-b.week);return {type:'scatter',mode:'lines',x:points.map(r=>r.week),y:points.map(r=>r.cases),name:String(year),connectgaps:false,line:{color:year===all.at(-1)?'#1d4ed8':colors[i%colors.length],width:year===all.at(-1)?3:1.5,dash:[2020,2021].includes(year)?'dot':'solid'}};});
 const target=chart('seasonal');if(target){const perRow=Math.max(1,Math.floor((target.clientWidth-90)/135)),legendRows=Math.ceil(years.length/perRow);Plotly.react(target,traces,{...target.layout,height:460+Math.max(0,legendRows-3)*22,margin:{l:65,r:25,t:30,b:65+legendRows*22},legend:{orientation:'h',x:0,y:-.24,entrywidth:135},xaxis:{...target.layout.xaxis,range:[1,53],autorange:false,tickmode:'array',tickvals:[1,13,26,39,52]},yaxis:{...target.layout.yaxis,autorange:true}},{responsive:true,displaylogo:false});}
 document.getElementById('season-caption').textContent=`${selectedDisease()}: ${years.join(', ')} by epidemiological week. ${all.at(-1)} is emphasised. Missing observations remain gaps; 2020–2021 use dotted lines. Disease definitions and reporting can change between years.`;
 const container=document.getElementById('season-table');container.replaceChildren();const table=document.createElement('table');table.className='table table-sm';const thead=document.createElement('thead'),tr=document.createElement('tr');cell(tr,'Epi week',true);years.forEach(y=>cell(tr,y,true));thead.append(tr);table.append(thead);const body=document.createElement('tbody');
 for(let week=1;week<=53;week++){const tr=document.createElement('tr');cell(tr,week);years.forEach(year=>cell(tr,fmt(rows.find(r=>r.year===year&&r.week===week)?.cases)));body.append(tr);}table.append(body);container.append(table);
}
function setDates(start,end){document.getElementById('export-start').value=iso(start);document.getElementById('export-end').value=iso(end);}
function validRange(start,end){return /^\d{4}-\d{2}-\d{2}$/.test(start)&&/^\d{4}-\d{2}-\d{2}$/.test(end)&&Number.isFinite(Date.parse(start))&&Number.isFinite(Date.parse(end))&&start<=end;}
async function applyRange(start,end){
 if(!validRange(start,end)){status('Choose a valid start date on or before the end date.');return false;}
 setDates(start,end);await Plotly.relayout(chart('disease'),{'xaxis.range':[start,end+' 23:59:59'],'xaxis.autorange':false});renderDetail();saveUrl();status('Date filter applied. The CSV uses this same date range.');return true;
}
async function applyDisease(i,range){
 const target=chart('disease'), button=target.layout.updatemenus[0].buttons[i];if(!button)return;
 select('disease').value=String(i);await Plotly.update(target,button.args[0],{...button.args[1],'xaxis.autorange':false,'yaxis.autorange':true,'updatemenus[0].active':i});
 const dates=range||button.args[1]['xaxis.range'];setDates(...dates);if(range)await applyRange(...range);renderDetail();renderSeason();saveUrl();
}
function applyOther(kind,index){const target=chart(kind),button=target?.layout.updatemenus?.[0]?.buttons[index];if(!button)return;select(kind).value=String(index);if(button.method==='relayout')Plotly.relayout(target,button.args[0]);else Plotly.update(target,button.args[0],{...(button.args[1]||{}),'updatemenus[0].active':index});}
function downloadCsv(){
 const [start,end]=currentRange();if(!validRange(start,end)){status('Choose valid dates before downloading.');return;}
 const rows=diseaseRows().filter(r=>iso(r.week_start)>=start&&iso(r.week_start)<=end);if(!rows.length){status('No observations fall within this date range.');return;}
 const columns=Object.keys(rows[0]);const quote=value=>value==null?'':typeof value==='string'?'"'+value.replaceAll('"','""')+'"':String(value);
 const csv=[columns.join(','),...rows.map(row=>columns.map(k=>quote(row[k])).join(','))].join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),link=document.createElement('a');link.href=url;link.download=`${selectedDisease().replace(/[^a-z0-9]+/gi,'-')}_${start}_${end}.csv`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);status(`Downloaded ${rows.length} disease-week observations, including unavailable counts as blank fields.`);
}
function getSaved(){try{return JSON.parse(localStorage.getItem('sgsurv.savedViews')||'[]').filter(v=>typeof v.name==='string'&&typeof v.url==='string');}catch{return [];}}
function renderSaved(){const target=document.getElementById('saved-views');target.replaceChildren(new Option('Choose a saved view',''));getSaved().forEach((v,i)=>target.add(new Option(v.name,String(i))));}
async function restoreUrl(){
 const params=new URL(location.href).searchParams;restoring=true;
 const requested=params.get('disease'), options=[...select('disease').options], i=options.findIndex(o=>o.textContent===requested||o.textContent.startsWith(requested+' (last reported'));
 const start=params.get('start'),end=params.get('end');
 if(params.has('years')&&['0','3','6'].includes(params.get('years')))document.getElementById('season-years').value=params.get('years');
 await applyDisease(i>=0?i:Number(select('disease').value),validRange(start||'',end||'')?[start,end]:null);
 for(const kind of ['haze','scatter','evaluation'])if(params.has(kind)){const value=Number(params.get(kind));if(Number.isInteger(value)&&value>=0&&value<select(kind).options.length){select(kind).value=String(value);applyOther(kind,value);}}
 restoring=false;
}
document.addEventListener('change',async e=>{
 if(!ready)return;const kind=e.target.dataset.chartSelect;
 if(kind==='disease')await applyDisease(Number(e.target.value));else if(kind){applyOther(kind,Number(e.target.value));saveUrl();}
 if(e.target.id==='season-years'){renderSeason();saveUrl();}
});
document.addEventListener('click',async e=>{
 const link=e.target.closest('[data-disease]');
 if(link){e.preventDefault();if(!ready){status('Details are still loading.');return;}const i=[...select('disease').options].findIndex(o=>o.textContent===link.dataset.disease||o.textContent.startsWith(link.dataset.disease+' (last reported'));if(i>=0)await applyDisease(i);chart('disease').closest('.card').scrollIntoView({behavior:'smooth',block:'start'});return;}
 const period=e.target.closest('[data-months]');
 if(period&&ready){const rows=diseaseRows(),stop=iso(rows.at(-1).week_start),end=new Date(stop+'T00:00:00Z');end.setUTCDate(end.getUTCDate()+6);const months=Number(period.dataset.months),start=new Date(end);if(months)start.setUTCMonth(start.getUTCMonth()-months);await applyRange(months?iso(start.toISOString()):iso(rows[0].week_start),iso(end.toISOString()));return;}
 if(!ready)return;
 if(e.target.id==='apply-dates')await applyRange(...currentRange());
 if(e.target.id==='download-disease')downloadCsv();
 if(e.target.id==='share-view'){saveUrl();try{await navigator.clipboard.writeText(location.href);status('View link copied. Localhost links open only on the computer hosting this app.');}catch{status('Copy the current browser address to share this view.');}}
 if(e.target.id==='save-view'){const name=document.getElementById('saved-view-name').value.trim();if(!name){status('Enter a name for the saved view.');return;}saveUrl();const views=getSaved().filter(v=>v.name!==name);views.push({name,url:location.pathname+location.search+location.hash});try{localStorage.setItem('sgsurv.savedViews',JSON.stringify(views));renderSaved();status('View saved in this browser.');}catch{status('This browser could not save the view. You can bookmark its URL instead.');}}
 if(e.target.id==='load-view'){const value=document.getElementById('saved-views').value;if(value==='')return;const view=getSaved()[Number(value)];if(view){const target=new URL(view.url,location.origin);if(target.origin===location.origin&&target.pathname===location.pathname){location.assign(target.href);}}}
 if(e.target.id==='delete-view'){const value=document.getElementById('saved-views').value;if(value==='')return;const views=getSaved();views.splice(Number(value),1);try{localStorage.setItem('sgsurv.savedViews',JSON.stringify(views));renderSaved();status('Saved view removed.');}catch{status('This browser could not update saved views.');}}
});
window.addEventListener('load',async()=>{
 updateCoverage();setupExplorerLayout();setTimeout(redrawVisiblePlots,200);
 try{
  const response=await fetch('chart-assets/explorer.json');if(!response.ok)throw new Error('Data unavailable');const data=await response.json();records=data.records;revisionHistory=data.revisions;ready=true;
  await restoreUrl();renderSaved();status('Ready. Downloads and links follow the selected disease and dates.');
  chart('disease').on('plotly_relayout',event=>{
   if(!Object.keys(event).some(k=>k.startsWith('xaxis.range')||k==='xaxis.autorange'))return;
   const range=chart('disease').layout.xaxis.range;if(range?.length===2){setDates(...range);renderDetail();saveUrl();}
  });
 }catch{status('Explorer details could not load. Reload the page through its local web server.');}
});
window.addEventListener('popstate',()=>{if(ready)restoreUrl();});
window.addEventListener('resize',redrawVisiblePlots);
document.addEventListener('shown.bs.tab',()=>setTimeout(redrawVisiblePlots,100));
document.addEventListener('radar-chart-ready',e=>{const kind=e.detail;if(['haze','scatter','evaluation'].includes(kind))applyOther(kind,Number(select(kind).value));});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateCoverage();});
})();

/* Independent illness, reference, briefing and regional controls. No API keys in browser. */
(() => {
'use strict';
let data, illnessRows=[], initial=true;
const byId=id=>document.getElementById(id);
const date=value=>String(value).slice(0,10);
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!=null)el.textContent=text;if(cls)el.className=cls;return el;};
const plotLayout={template:'plotly_white',height:480,margin:{l:75,r:25,t:25,b:65},hovermode:'x unified',font:{size:13},yaxis:{rangemode:'tozero'},legend:{orientation:'h'}};
function link(title,url){const a=node('a',title);if(/^https:\/\//.test(url)){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;}
async function lazyCharts(){
 for(const el of document.querySelectorAll('[data-plot-spec]')){
  if(el.offsetParent===null||el.dataset.loading)continue;
  el.dataset.loading='true';
  try{const response=await fetch(el.dataset.plotSpec);if(!response.ok)throw Error();const spec=await response.json();el.replaceChildren();await Plotly.newPlot(el,spec.data,spec.layout,{responsive:true,displaylogo:false});document.dispatchEvent(new CustomEvent('radar-chart-ready',{detail:el.dataset.kind}));}
  catch{el.dataset.loading='';el.replaceChildren(node('p','Chart could not load. Reopen this tab to retry.'));}
 }
}
function illnessOptions(){
 const group=byId('illness-group').value,source=byId('illness-source').value,select=byId('illness-select'),previous=select.value;
 select.replaceChildren();data.series.filter(s=>(group==='all'||s.respiratory)&&(!source||s.source===source)).forEach(s=>select.add(new Option(`${s.name} · ${s.source}`,s.id)));
 if([...select.options].some(o=>o.value===previous))select.value=previous;
 else if([...select.options].some(o=>o.value.includes('Polyclinic:Acute Upper')))select.value=[...select.options].find(o=>o.value.includes('Polyclinic:Acute Upper')).value;
 drawIllness(true);
}
function card(name,target){
 target.replaceChildren();
 const reference=data.pathogens.find(p=>p.name===name||p.aliases.includes(name));
 if(!reference){target.append(node('p',`A sourced quick-reference card for ${name} is not yet available.`),link('Browse WHO health topics','https://www.who.int/health-topics'));return;}
 target.append(node('h3',reference.name),node('p',reference.agent));
 const dl=node('dl');dl.className='wiki-facts';
 for(const [key,label] of [['symptoms','Symptoms'],['incubation','Incubation period'],['infectious','Infectious period'],['transmission','Transmission']])dl.append(node('dt',label),node('dd',reference[key]));
 target.append(dl,node('p',`Reference checked ${reference.checked}. Ranges vary with the person, pathogen and setting.`));
 target.append(link('Primary reference',reference.source));
 for(const url of reference.sources||[])target.append(node('span',' · '),link('Additional reference',url));
 const notices=data.briefing.items.filter(i=>i.kind==='Official outbreak notice'&&i.topics.includes(reference.name)).slice(0,3);
 target.append(node('h4','Recent WHO notices in the retained feed'));
 if(!notices.length)target.append(node('p','No matching notice in the retained feed; this does not establish that there is no advisory.'));
 for(const item of notices)target.append(node('p',item.published+' · '),link(item.title,item.url));
 target.append(node('p'),link('Check WHO Disease Outbreak News for current recommendations','https://www.who.int/emergencies/disease-outbreak-news'));
}
function drawIllness(reset=false){
 if(!data||byId('illness-explorer')?.offsetParent===null)return;
 const series=data.series.find(s=>s.id===byId('illness-select').value),target=byId('illness-plot');
 if(!series){target.replaceChildren(node('p','No series matches these filters.'));return;}
 if(reset||!byId('illness-start').value){const end=series.dates.at(-1),start=new Date(end+'T00:00:00Z');start.setUTCFullYear(start.getUTCFullYear()-2);byId('illness-end').value=end;byId('illness-start').value=date(start.toISOString());}
 const start=byId('illness-start').value,end=byId('illness-end').value;
 if(!start||!end||start>end){illnessRows=[];byId('illness-note').textContent='Choose a start date on or before the end date.';return;}
 illnessRows=series.dates.map((d,i)=>({week_start:d,value:series.values[i]})).filter(r=>r.week_start>=start&&r.week_start<=end);
 for(const row of illnessRows){const stop=new Date(row.week_start+'T00:00:00Z');stop.setUTCDate(stop.getUTCDate()+6);const periods=data.school.filter(s=>['vacation','closure'].includes(s.type)&&s.start_date<=date(stop.toISOString())&&s.end_date>=row.week_start);row.school_period=data.school_years.includes(Number(row.week_start.slice(0,4)))?(periods.map(s=>s.name+' ('+s.type+')').join('; ')||'No recorded vacation/closure'):'Unknown calendar coverage';}
 const shapes=[];const relevant=data.school.filter(s=>['vacation','closure'].includes(s.type)&&s.start_date<=end&&s.end_date>=start);
 if(byId('illness-holidays').checked)for(const holiday of relevant){const stop=new Date(holiday.end_date+'T00:00:00Z');stop.setUTCDate(stop.getUTCDate()+1);shapes.push({type:'rect',xref:'x',yref:'paper',x0:holiday.start_date,x1:date(stop.toISOString()),y0:0,y1:1,fillcolor:'#b4c6e7',opacity:.28,line:{width:0},layer:'below'});}
 const minYear=Math.min(...data.school_years),maxYear=Math.max(...data.school_years);
 byId('illness-note').textContent=`${series.units}. ${illnessRows.length} reporting weeks selected. ${byId('illness-holidays').checked?'Blue bands: school vacations/closures.':'School-holiday shading is off.'} School calendar: ${minYear}–${maxYear}. `+(Number(start.slice(0,4))<minYear||Number(end.slice(0,4))>maxYear?'Calendar coverage is UNKNOWN outside those years; unshaded dates there must not be read as term time.':byId('illness-holidays').checked?'Unshaded dates are outside the recorded vacation/closure periods.':'');
 Plotly.react(target,[{x:illnessRows.map(r=>r.week_start),y:illnessRows.map(r=>r.value),customdata:illnessRows.map(r=>r.school_period),type:'scatter',mode:'lines',connectgaps:false,name:series.name,line:{color:'#2458a6',width:2},hovertemplate:'%{x}<br>%{y:,.1f}<br>%{customdata}<extra></extra>'}],{...plotLayout,shapes,xaxis:{title:'Week starting (Sunday)',range:[start,end]},yaxis:{title:series.units,rangemode:'tozero'}},{responsive:true,displaylogo:false});
 byId('calendar-note').textContent=`Curated reference years ${minYear}–${maxYear}. Only vacation and closure periods are shaded; primary-school-only special days are excluded. Dates are descriptive context, not a causal analysis.`;
 byId('calendar-sources').replaceChildren(...[...new Set(relevant.map(s=>s.source))].map(url=>{const li=node('li');li.append(link(url,url));return li;}));
 card(series.name,byId('illness-reference'));
}
function regionalControls(){
 if(!data)return;
 const selected=new Set([...byId('region-countries').querySelectorAll('input:checked')].map(e=>e.value));
 if(byId('region-singapore').checked)selected.add('Singapore');else selected.delete('Singapore');
 for(const kind of ['region-flu','region-tb']){
  const plot=[...document.querySelectorAll('.js-plotly-plot')].find(p=>p.layout?.meta?.kind===kind);if(!plot)continue;
  Plotly.restyle(plot,{visible:plot.data.map(t=>selected.has(t.name))});
  if(kind==='region-flu'){
   const dates=data.flu.map(r=>date(r.week_start)).sort(),stop=dates.at(-1),months=Number(byId('region-period').value),start=new Date(stop+'T00:00:00Z');start.setUTCMonth(start.getUTCMonth()-months);
   Plotly.relayout(plot,{'xaxis.range':[months?date(start.toISOString()):dates[0],stop],'xaxis.autorange':false});
  }
 }
}
function briefing(){
 const query=byId('news-search').value.toLowerCase(),region=byId('news-region').value,kind=byId('news-kind').value;
 const items=data.briefing.items.filter(i=>(!region||i.scope===region)&&(!kind||i.kind===kind)&&`${i.title} ${i.topics.join(' ')}`.toLowerCase().includes(query));
 byId('news-list').replaceChildren();
 for(const item of items.slice(0,60)){const box=node('article',null,'headline-card');box.append(node('p',`${item.published} · ${item.source} · ${item.scope}`,'muted'),link(item.title,item.url),node('p',item.kind+' · '+item.topics.join(', '),'muted'));byId('news-list').append(box);}
 if(!items.length)byId('news-list').append(node('p','No matching headlines in the retained feed. Try another filter or check the original publisher.'));
 byId('news-status').textContent=`${items.length} matching links (up to 60 displayed). Feed checked ${data.briefing.checked_at||'not yet'}. Latest retained publication ${data.briefing.items[0]?.published||'unavailable'}.`;
}
function library(){
 const query=byId('library-search')?.value.toLowerCase()||'',family=byId('library-family')?.value||'',region=byId('library-region')?.value||'';let count=0;
 for(const el of document.querySelectorAll('.library-dataset')){el.hidden=!((!family||el.dataset.family===family)&&(!region||el.dataset.region===region)&&el.dataset.search.toLowerCase().includes(query));if(!el.hidden)count++;}
 if(byId('library-count'))byId('library-count').textContent=`${count} datasets match. Expand a dataset for its preview and download.`;
 const table=byId('data-library')?.querySelector('table');
 if(table){const states=new Map([...document.querySelectorAll('.library-dataset')].map(el=>[el.querySelector('summary').textContent.split(' · ')[0],el.hidden]));for(const row of table.tBodies[0]?.rows||[])row.hidden=states.get(row.cells[0]?.textContent.trim())||false;}
}
async function activated(){await lazyCharts();if(!data)return;drawIllness(initial);if(byId('illness-explorer')?.offsetParent!==null)initial=false;regionalControls();}
window.addEventListener('load',async()=>{
 await lazyCharts();
 try{
  const response=await fetch('chart-assets/enhancements.json');if(!response.ok)throw Error();data=await response.json();
  for(const p of data.pathogens)byId('wiki-select').add(new Option(p.name,p.name));
  card(data.pathogens[0].name,byId('wiki-card'));
  for(const name of Object.values(data.countries)){if(name==='Singapore')continue;const label=node('label'),input=node('input');input.type='checkbox';input.value=name;input.checked=true;label.append(input,document.createTextNode(name));byId('region-countries').append(label);}
  byId('news-sources').replaceChildren(...data.briefing.sources.map(s=>node('li',`${s.source}: ${s.status} · checked ${s.checked_at}`)));
  illnessOptions();briefing();library();await activated();
 }catch(err){for(const id of ['news-status','illness-note'])if(byId(id))byId(id).textContent='Explorer data could not load. Reload to retry.';console.error('Explorer data unavailable',err);}
 const signals=[...document.querySelectorAll('.card')].find(c=>c.querySelector('.card-header')?.textContent.includes('Signals for review'));
 if(signals){const body=signals.querySelector('.card-body');if(body){const details=node('details'),summary=node('summary','Show recent signal table');details.append(summary,...body.childNodes);body.append(details);}}
});
document.addEventListener('shown.bs.tab',activated);
document.addEventListener('radar-chart-ready',regionalControls);
document.addEventListener('input',e=>{if(!data)return;if(e.target.id.startsWith('news-'))briefing();if(e.target.id.startsWith('library-'))library();});
document.addEventListener('change',e=>{
 if(!data)return;const id=e.target.id;
 if(['illness-group','illness-source'].includes(id))illnessOptions();
 else if(id==='illness-select')drawIllness(true);
 else if(id.startsWith('illness-'))drawIllness();
 if(id==='wiki-select')card(e.target.value,byId('wiki-card'));
 if(e.target.closest('#region-countries')||id.startsWith('region-'))regionalControls();
 if(e.target.matches('[data-chart-select="disease"]')){const name=e.target.selectedOptions[0].textContent.replace(/ \(last reported .*\)$/,'');const p=data.pathogens.find(p=>p.aliases.includes(name));byId('wiki-select').value=p?.name||'';card(name,byId('wiki-card'));}
 if(id.startsWith('news-'))briefing();if(id.startsWith('library-'))library();
});
document.addEventListener('click',e=>{
 if(!data)return;
 if(['region-all','region-none'].includes(e.target.id)){byId('region-countries').querySelectorAll('input').forEach(i=>i.checked=e.target.id==='region-all');regionalControls();}
 if(e.target.id==='illness-download'){
  const s=data.series.find(s=>s.id===byId('illness-select').value);if(!s||!illnessRows.length)return;
  const quote=value=>'"'+String(value).replaceAll('"','""')+'"';const csv=['week_start,value,school_period,units',...illnessRows.map(r=>`${r.week_start},${r.value??''},${quote(r.school_period)},${quote(s.units)}`)].join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=node('a');a.href=url;a.download=`${s.name.replace(/[^a-z0-9]+/gi,'-')}-${s.source}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
});
})();
