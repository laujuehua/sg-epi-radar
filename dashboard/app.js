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
 for(const kind of ['haze','scatter','evaluation'])if(params.has(kind)){const value=Number(params.get(kind));if(Number.isInteger(value)&&value>=0&&value<select(kind).options.length)applyOther(kind,value);}
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
document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateCoverage();});
})();
