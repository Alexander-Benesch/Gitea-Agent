from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from samuel.adapters.api.auth import APIKeyAuth
from samuel.adapters.api.rest import RestAPI
from samuel.adapters.api.webhooks import WebhookIngressAdapter
from samuel.core.bus import Bus
from samuel.slices.dashboard.handler import DashboardHandler
from samuel.slices.setup.handler import SetupHandler

log = logging.getLogger(__name__)

DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>S.A.M.U.E.L. Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#e2e8f0;padding:1.5rem;max-width:1200px;margin:0 auto}
header{display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;flex-wrap:wrap;gap:.5rem}
header h1{font-size:1.5rem;color:#38bdf8}
header h1 span{font-size:.75rem;color:#64748b;font-weight:400;margin-left:.5rem}
.meta{font-size:.75rem;color:#64748b;text-align:right}
.countdown{font-size:.7rem;color:#64748b}
.tabs{display:flex;gap:2px;margin-bottom:1rem;border-bottom:2px solid #334155;overflow-x:auto}
.tab{background:transparent;color:#94a3b8;border:none;padding:.75rem 1.25rem;cursor:pointer;font-size:.875rem;border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap}
.tab.active{color:#38bdf8;border-bottom-color:#38bdf8}
.tab:hover{color:#e2e8f0}
.tab-content{display:none}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:1rem;margin-bottom:1.5rem}
.card{background:#1e293b;border-radius:8px;padding:1rem;border:1px solid #334155;transition:border-color .2s}
.card:hover{border-color:#475569}
.card h3{font-size:.7rem;color:#94a3b8;margin-bottom:.4rem;text-transform:uppercase;letter-spacing:.05em}
.card .val{font-size:1.4rem;font-weight:700}
.ok{color:#4ade80}.warn{color:#fbbf24}.err{color:#f87171}
.section{background:#1e293b;border-radius:8px;padding:1rem;border:1px solid #334155;margin-bottom:1rem}
.section h2{font-size:.875rem;color:#94a3b8;margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.05em}
.health-row{display:flex;justify-content:space-between;padding:.4rem 0;border-bottom:1px solid #334155;font-size:.85rem}
.health-row:last-child{border-bottom:none}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:.4rem;vertical-align:middle}
.dot.g{background:#4ade80}.dot.r{background:#f87171}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:.5rem .75rem;border-bottom:1px solid #334155}
th{color:#94a3b8;font-size:.7rem;text-transform:uppercase}
td{font-size:.85rem}
.badge{display:inline-block;padding:.125rem .5rem;border-radius:9999px;font-size:.75rem;font-weight:600}
.badge-ok{background:#065f46;color:#6ee7b7}
.badge-warn{background:#78350f;color:#fcd34d}
.badge-err{background:#7f1d1d;color:#fca5a5}
.badge-info{background:#1e3a5f;color:#93c5fd}
.badge-ready{background:#065f46;color:#6ee7b7}
.badge-planned{background:#1e3a5f;color:#93c5fd}
.badge-implemented{background:#3b0764;color:#d8b4fe}
.badge-pr_created{background:#164e63;color:#67e8f9}
.badge-blocked{background:#7f1d1d;color:#fca5a5}
.filter-bar{display:flex;gap:.5rem;margin-bottom:1rem;flex-wrap:wrap}
.filter-bar select,.filter-bar input{background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:.5rem;border-radius:4px;font-size:.8rem}
.filter-bar input{flex:1;min-width:150px}
.warn-item{background:#422006;border:1px solid #92400e;border-radius:6px;padding:.75rem;margin-bottom:.5rem;font-size:.85rem}
.warn-item:last-child{margin-bottom:0}
.toggle{position:relative;display:inline-block;width:40px;height:22px;vertical-align:middle}
.toggle input{opacity:0;width:0;height:0}
.toggle .slider{position:absolute;cursor:default;inset:0;background:#475569;border-radius:11px;transition:.2s}
.toggle input:checked+.slider{background:#0ea5e9}
.toggle .slider::before{content:'';position:absolute;height:16px;width:16px;left:3px;bottom:3px;background:#e2e8f0;border-radius:50%;transition:.2s}
.toggle input:checked+.slider::before{transform:translateX(18px)}
.flag-row{display:flex;justify-content:space-between;align-items:center;padding:.6rem 0;border-bottom:1px solid #334155;font-size:.85rem}
.flag-row:last-child{border-bottom:none}
.empty{color:#64748b;font-style:italic;padding:1rem;text-align:center}
@media(max-width:600px){header{flex-direction:column;align-items:flex-start}.meta{text-align:left}.grid{grid-template-columns:1fr 1fr}}
</style>
</head>
<body>
<header>
 <h1>S.A.M.U.E.L.<span>v2.0.0-alpha</span></h1>
 <div class="meta">
  <div>Letztes Update: <span id="last-refresh">-</span>
   <button id="auto-refresh-btn" onclick="toggleAutoRefresh()" style="background:#1e293b;color:#e2e8f0;border:1px solid #475569;padding:.2rem .5rem;border-radius:4px;font-size:.7rem;cursor:pointer;margin-left:.5rem">auto-refresh: on</button>
  </div>
  <div class="countdown">Naechstes Update in <span id="countdown">10</span>s</div>
 </div>
</header>
<div id="toast" style="position:fixed;top:1rem;right:1rem;padding:.75rem 1rem;border-radius:6px;font-size:.85rem;display:none;z-index:1000;max-width:400px"></div>
<nav class="tabs">
 <button class="tab active" onclick="showTab('status')">Status</button>
 <button class="tab" onclick="showTab('llm')">LLM &amp; Kosten</button>
 <button class="tab" onclick="showTab('workflow')">Workflow</button>
 <button class="tab" onclick="showTab('logs')">Logs</button>
 <button class="tab" onclick="showTab('security')">Security</button>
 <button class="tab" onclick="showTab('settings')">Settings</button>
 <button class="tab" onclick="showTab('selfcheck')">Self-Check</button>
</nav>

<!-- TAB: STATUS -->
<div class="tab-content" id="tab-status">
 <div class="grid">
  <div class="card"><h3>Modus</h3><div class="val" id="s-mode">-</div></div>
  <div class="card"><h3>SCM</h3><div class="val" id="s-scm">-</div></div>
  <div class="card"><h3>Health</h3><div class="val" id="s-health">-</div></div>
  <div class="card"><h3>LLM</h3><div class="val" id="s-llm">-</div></div>
 </div>
 <div class="section"><h2>Health-Checks</h2><div id="s-health-details">-</div></div>
 <div class="section"><h2>Activity (Commands / Events)</h2>
  <table><thead><tr><th>Command/Event</th><th>Count</th><th>Errors</th><th>Avg ms</th></tr></thead>
  <tbody id="s-activity"></tbody></table>
 </div>
</div>

<!-- TAB: LLM & KOSTEN -->
<div class="tab-content" id="tab-llm">
 <div class="grid">
  <div class="card"><h3>Total Calls</h3><div class="val" id="l-calls">-</div></div>
  <div class="card"><h3>Total Tokens</h3><div class="val" id="l-tokens">-</div></div>
  <div class="card"><h3>Total Cost</h3><div class="val" id="l-cost">-</div></div>
  <div class="card"><h3>Provider</h3><div class="val" id="l-provider">-</div></div>
 </div>
 <div class="section"><h2>Token Usage per Task</h2>
  <table><thead><tr><th>Task</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr></thead>
  <tbody id="l-tasks"></tbody></table>
 </div>
 <div class="section"><h2>Routing pro Task</h2>
  <table><thead><tr><th>Task</th><th>Provider</th><th>Model</th></tr></thead>
  <tbody id="l-routing"></tbody></table>
 </div>
</div>

<!-- TAB: WORKFLOW -->
<div class="tab-content" id="tab-workflow">
 <div class="section"><h2>Issue Pipeline</h2>
  <table><thead><tr><th>Issue</th><th>Status</th><th>Last Event</th><th>Timestamp</th></tr></thead>
  <tbody id="w-issues"></tbody></table>
 </div>
 <div class="section"><h2>Branches</h2>
  <table><thead><tr><th>Branch</th><th>Issue</th><th>Status</th></tr></thead>
  <tbody id="w-branches"></tbody></table>
 </div>
</div>

<!-- TAB: LOGS -->
<div class="tab-content" id="tab-logs">
 <div class="filter-bar">
  <select id="log-cat"><option value="">Alle Kategorien</option></select>
  <select id="log-level"><option value="">Alle Level</option><option value="error">Error</option><option value="warn">Warn</option><option value="info">Info</option><option value="debug">Debug</option></select>
  <input type="text" id="log-search" placeholder="Textsuche...">
 </div>
 <div class="section" style="max-height:500px;overflow-y:auto">
  <table><thead><tr><th>Zeit</th><th>Level</th><th>Category</th><th>Event</th><th>Message</th><th>Issue</th></tr></thead>
  <tbody id="log-body"></tbody></table>
 </div>
</div>

<!-- TAB: SECURITY -->
<div class="tab-content" id="tab-security">
 <div class="grid">
  <div class="card"><h3>Total Events</h3><div class="val" id="sec-total">-</div></div>
  <div class="card"><h3>Classified</h3><div class="val" id="sec-classified">-</div></div>
  <div class="card"><h3>Active Risks</h3><div class="val" id="sec-risks">-</div></div>
 </div>
 <div class="section"><h2>OWASP Agentic AI Top 10</h2>
  <table><thead><tr><th>ID</th><th>Category</th><th>Events</th></tr></thead>
  <tbody id="sec-owasp"></tbody></table>
 </div>
 <div class="section"><h2>Barrier Log (letzte 30)</h2>
  <table><thead><tr><th>Zeit</th><th>Type</th><th>Detail</th></tr></thead>
  <tbody id="sec-barrier"></tbody></table>
 </div>
 <div class="section"><h2>Tamper-Alerts</h2>
  <table><thead><tr><th>Zeit</th><th>Event</th><th>OWASP</th><th>Detail</th><th>Issue</th></tr></thead>
  <tbody id="sec-tamper"></tbody></table>
 </div>
</div>

<!-- TAB: SETTINGS -->
<div class="tab-content" id="tab-settings">
 <div class="section"><h2>Feature Flags</h2><div id="set-flags"><div class="empty">Laden...</div></div></div>
 <div class="section"><h2>Setup</h2>
  <button id="btn-sync-labels" onclick="syncLabels()" style="background:#0ea5e9;color:#0f172a;border:none;padding:.5rem 1rem;border-radius:4px;font-size:.85rem;cursor:pointer;font-weight:600">Labels auf SCM synchronisieren</button>
  <div id="labels-result" style="margin-top:.75rem;font-size:.8rem;color:#94a3b8"></div>
 </div>
 <div class="section"><h2>LLM Configuration</h2><div id="set-llm-config"><div class="empty">Laden...</div></div></div>
 <div class="section" id="set-warnings-section" style="display:none"><h2>Transfer-Warnungen (DSGVO)</h2><div id="set-warnings"></div></div>
</div>

<!-- TAB: SELF-CHECK -->
<div class="tab-content" id="tab-selfcheck">
 <div class="grid">
  <div class="card"><h3>Modus</h3><div class="val" id="sc-mode">-</div></div>
  <div class="card"><h3>Status</h3><div class="val" id="sc-healthy">-</div></div>
 </div>
 <div class="section"><h2>Checks</h2>
  <table><thead><tr><th>Name</th><th>Status</th><th>Zeit</th><th>Detail</th></tr></thead>
  <tbody id="sc-body"></tbody></table>
 </div>
</div>

<script>
let currentTab=sessionStorage.getItem('tab')||'status';
const REFRESH_INTERVAL=10;
let cd=REFRESH_INTERVAL;
let autoRefresh=(sessionStorage.getItem('autoRefresh')||'on')==='on';
let allLogs=[];
const ts=()=>new Date().toLocaleTimeString('de-DE');
const esc=s=>{const d=document.createElement('div');d.textContent=s;return d.innerHTML};
const fmt=n=>typeof n==='number'?n.toLocaleString('de-DE'):(n||'-');

function apiHeaders(){
 const k=sessionStorage.getItem('apiKey')||'';
 return k?{'X-API-Key':k}:{};
}
function apiFetch(url,opts){
 opts=opts||{};
 const h=Object.assign({},opts.headers||{},apiHeaders());
 return fetch(url,Object.assign({},opts,{headers:h}));
}
function showToast(msg,kind){
 const el=document.getElementById('toast');
 el.textContent=msg;
 const bg=kind==='err'?'#7f1d1d':(kind==='warn'?'#78350f':'#065f46');
 el.style.background=bg;el.style.color='#e2e8f0';el.style.display='block';
 setTimeout(()=>{el.style.display='none';},5000);
}

function showTab(name){
 currentTab=name;sessionStorage.setItem('tab',name);
 document.querySelectorAll('.tab-content').forEach(t=>t.style.display='none');
 const el=document.getElementById('tab-'+name);if(el)el.style.display='block';
 document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
 if(typeof event!=='undefined'&&event&&event.target)event.target.classList.add('active');
 else{const btns=document.querySelectorAll('.tab');btns.forEach(b=>{if(b.getAttribute('onclick')==="showTab('"+name+"')")b.classList.add('active');});}
 loadTabData(name);
 cd=REFRESH_INTERVAL;
}

function toggleAutoRefresh(){
 autoRefresh=!autoRefresh;
 sessionStorage.setItem('autoRefresh',autoRefresh?'on':'off');
 document.getElementById('auto-refresh-btn').textContent='auto-refresh: '+(autoRefresh?'on':'off');
 cd=REFRESH_INTERVAL;
}

async function loadTabData(tab){
 try{
  if(tab==='status')await loadStatus();
  else if(tab==='llm')await loadLLM();
  else if(tab==='workflow')await loadWorkflow();
  else if(tab==='logs')await loadLogs();
  else if(tab==='security')await loadSecurity();
  else if(tab==='settings')await loadSettings();
  else if(tab==='selfcheck')await loadSelfCheck();
  document.getElementById('last-refresh').textContent=ts();
 }catch(e){console.error('Tab load failed:',tab,e)}
}

async function loadStatus(){
 const[sr,hr]=await Promise.all([
  apiFetch('/api/v1/dashboard/status').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/health').then(r=>r.json())
 ]);
 const hd=hr.data||hr;
 const modeEl=document.getElementById('s-mode');
 modeEl.textContent=(sr.mode||'?')+(sr.self_mode?' (self)':'');
 modeEl.className='val '+(sr.self_mode?'warn':'');
 const scm=document.getElementById('s-scm');
 scm.textContent=sr.scm_connected?'Verbunden':'Getrennt';
 scm.className='val '+(sr.scm_connected?'ok':'warn');
 const healthy=hd.healthy;
 const hEl=document.getElementById('s-health');
 hEl.textContent=healthy?'OK':'Fehler';hEl.className='val '+(healthy?'ok':'err');
 const checks=hd.checks||{};
 const llmOk=checks.llm;
 const lEl=document.getElementById('s-llm');
 if(llmOk===undefined){lEl.textContent='N/A';lEl.className='val warn'}
 else{lEl.textContent=llmOk?'OK':'Fehler';lEl.className='val '+(llmOk?'ok':'err')}
 const hDiv=document.getElementById('s-health-details');hDiv.innerHTML='';
 for(const[k,v]of Object.entries(checks)){
  hDiv.innerHTML+='<div class="health-row"><span><span class="dot '+(v?'g':'r')+'"></span>'+esc(k)+'</span><span>'+(v?'OK':'FAIL')+'</span></div>';
 }
 const m=sr.metrics||{};
 const counts=m.counts||{},errors=m.errors||{},tms=m.total_ms||{};
 const keys=new Set([...Object.keys(counts),...Object.keys(errors)]);
 const tb=document.getElementById('s-activity');tb.innerHTML='';
 [...keys].forEach(k=>{const c=counts[k]||0,e=errors[k]||0,a=c?(tms[k]||0)/c:0;
  tb.innerHTML+='<tr><td>'+esc(k)+'</td><td>'+c+'</td><td class="'+(e?'err':'')+'">'+e+'</td><td>'+a.toFixed(1)+'</td></tr>';
 });
 if(!keys.size)tb.innerHTML='<tr><td colspan="4" class="empty">Keine Events</td></tr>';
}

async function loadLLM(){
 const d=await apiFetch('/api/v1/dashboard/llm').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('l-calls').textContent=fmt(data.total_calls||0);
 document.getElementById('l-tokens').textContent=fmt(data.total_tokens||0);
 const cost=data.total_cost||0;
 document.getElementById('l-cost').textContent=typeof cost==='number'?cost.toFixed(4)+' EUR':String(cost);
 document.getElementById('l-provider').textContent=data.provider||data.current_provider||'-';
 const tb=document.getElementById('l-tasks');tb.innerHTML='';
 const tasks=data.per_task||data.tasks||data.by_task||[];
 if(Array.isArray(tasks)&&tasks.length){
  tasks.forEach(t=>{tb.innerHTML+='<tr><td>'+esc(t.task||t.name||'-')+'</td><td>'+fmt(t.calls||0)+'</td><td>'+fmt(t.tokens||0)+'</td><td>'+(t.cost!=null?Number(t.cost).toFixed(4):'-')+'</td></tr>';});
 }else if(typeof tasks==='object'&&!Array.isArray(tasks)){
  for(const[k,v]of Object.entries(tasks)){tb.innerHTML+='<tr><td>'+esc(k)+'</td><td>'+fmt(v.calls||0)+'</td><td>'+fmt(v.tokens||0)+'</td><td>'+(v.cost!=null?Number(v.cost).toFixed(4):'-')+'</td></tr>';}
 }
 if(!tb.innerHTML)tb.innerHTML='<tr><td colspan="4" class="empty">Keine LLM-Daten</td></tr>';
 const rb=document.getElementById('l-routing');rb.innerHTML='';
 const routing=data.routing||[];
 if(Array.isArray(routing)&&routing.length){
  routing.forEach(r=>{rb.innerHTML+='<tr><td>'+esc(r.task||'-')+'</td><td>'+esc(r.provider||'-')+'</td><td>'+esc(r.model||'-')+'</td></tr>';});
 }else{rb.innerHTML='<tr><td colspan="3" class="empty">Keine Routing-Daten</td></tr>';}
}

async function loadWorkflow(){
 const d=await apiFetch('/api/v1/dashboard/workflow').then(r=>r.json());
 const data=d.data||d;
 const issues=data.issues||[];
 const ib=document.getElementById('w-issues');ib.innerHTML='';
 if(issues.length){
  issues.forEach(i=>{const cls='badge badge-'+(i.status||'info');
   ib.innerHTML+='<tr><td>#'+esc(String(i.number||i.id||'-'))+'</td><td><span class="'+cls+'">'+esc(i.status||'-')+'</span></td><td>'+esc(i.last_event||'-')+'</td><td>'+esc(i.timestamp||i.updated_at||'-')+'</td></tr>';
  });
 }else{ib.innerHTML='<tr><td colspan="4" class="empty">Keine Issues</td></tr>';}
 const branches=data.branches||[];
 const bb=document.getElementById('w-branches');bb.innerHTML='';
 if(branches.length){
  branches.forEach(b=>{bb.innerHTML+='<tr><td>'+esc(b.name||'-')+'</td><td>'+(b.issue?'#'+esc(String(b.issue)):'-')+'</td><td>'+esc(b.status||'-')+'</td></tr>';});
 }else{bb.innerHTML='<tr><td colspan="3" class="empty">Keine Branches</td></tr>';}
}

async function loadLogs(){
 const d=await apiFetch('/api/v1/dashboard/logs').then(r=>r.json());
 allLogs=(d.data||d).entries||d.data||d.entries||[];
 if(!Array.isArray(allLogs))allLogs=[];
 const cats=new Set();allLogs.forEach(l=>cats.add(l.category||'unknown'));
 const sel=document.getElementById('log-cat');const cur=sel.value;
 sel.innerHTML='<option value="">Alle Kategorien</option>';
 [...cats].sort().forEach(c=>{sel.innerHTML+='<option value="'+esc(c)+'">'+esc(c)+'</option>';});
 sel.value=cur;
 filterLogs();
}
function filterLogs(){
 const cat=document.getElementById('log-cat').value.toLowerCase();
 const lvl=document.getElementById('log-level').value.toLowerCase();
 const txt=document.getElementById('log-search').value.toLowerCase();
 const tb=document.getElementById('log-body');tb.innerHTML='';
 let shown=0;
 allLogs.forEach(l=>{
  if(cat&&(l.category||'').toLowerCase()!==cat)return;
  if(lvl&&(l.level||'').toLowerCase()!==lvl)return;
  const str=JSON.stringify(l).toLowerCase();
  if(txt&&!str.includes(txt))return;
  if(++shown>200)return;
  const lc=(l.level||'').toLowerCase();
  const cls=lc==='error'?'err':lc==='warn'||lc==='warning'?'warn':'';
  tb.innerHTML+='<tr><td>'+esc(l.timestamp||l.time||'-')+'</td><td class="'+cls+'">'+esc(l.level||'-')+'</td><td>'+esc(l.category||'-')+'</td><td>'+esc(l.event||'-')+'</td><td>'+esc(l.message||l.msg||'-')+'</td><td>'+(l.issue?'#'+esc(String(l.issue)):'-')+'</td></tr>';
 });
 if(!shown)tb.innerHTML='<tr><td colspan="6" class="empty">Keine Logs</td></tr>';
}
document.getElementById('log-cat').addEventListener('change',filterLogs);
document.getElementById('log-level').addEventListener('change',filterLogs);
document.getElementById('log-search').addEventListener('input',filterLogs);

async function loadSecurity(){
 const d=await apiFetch('/api/v1/dashboard/security').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('sec-total').textContent=fmt(data.total_events||0);
 const pct=data.classified_pct!=null?data.classified_pct+'%%':'-';
 document.getElementById('sec-classified').textContent=pct;
 document.getElementById('sec-risks').textContent=fmt(data.active_risks||0);
 const owasp=data.owasp||[];
 const ob=document.getElementById('sec-owasp');ob.innerHTML='';
 if(owasp.length){owasp.forEach(o=>{ob.innerHTML+='<tr><td>'+esc(o.id||'-')+'</td><td>'+esc(o.category||o.name||'-')+'</td><td>'+fmt(o.count||0)+'</td></tr>';});}
 else{ob.innerHTML='<tr><td colspan="3" class="empty">Keine OWASP-Daten</td></tr>';}
 const barrier=data.barrier_log||data.barriers||[];
 const bb=document.getElementById('sec-barrier');bb.innerHTML='';
 if(barrier.length){barrier.slice(0,30).forEach(b=>{bb.innerHTML+='<tr><td>'+esc(b.timestamp||b.time||'-')+'</td><td>'+esc(b.type||b.event||'-')+'</td><td>'+esc(b.detail||b.message||'-')+'</td></tr>';});}
 else{bb.innerHTML='<tr><td colspan="3" class="empty">Keine Security-Events</td></tr>';}
 const tamper=data.tamper_events||[];
 const tb2=document.getElementById('sec-tamper');tb2.innerHTML='';
 if(tamper.length){tamper.forEach(t=>{tb2.innerHTML+='<tr><td>'+esc(t.ts||'-')+'</td><td>'+esc(t.event||'-')+'</td><td>'+esc(t.owasp||'-')+'</td><td>'+esc(t.detail||'-')+'</td><td>'+(t.issue?'#'+esc(String(t.issue)):'-')+'</td></tr>';});}
 else{tb2.innerHTML='<tr><td colspan="5" class="empty">Keine Tamper-Events</td></tr>';}
}

async function loadSettings(){
 const[sd,st]=await Promise.all([
  apiFetch('/api/v1/dashboard/settings').then(r=>r.json()),
  apiFetch('/api/v1/dashboard/status').then(r=>r.json())
 ]);
 const sdata=sd.data||sd;
 const flagsRaw=sdata.flags||sdata.feature_flags||[];
 const fDiv=document.getElementById('set-flags');fDiv.innerHTML='';
 let flagItems=[];
 if(Array.isArray(flagsRaw)){flagItems=flagsRaw.map(f=>({key:f.key,enabled:!!f.enabled,description:f.description||''}));}
 else if(typeof flagsRaw==='object'){flagItems=Object.keys(flagsRaw).map(k=>({key:k,enabled:!!flagsRaw[k],description:''}));}
 if(flagItems.length){flagItems.forEach(f=>{
  const desc=f.description?' <span style="color:#64748b;font-size:.75rem">'+esc(f.description)+'</span>':'';
  const row=document.createElement('div');row.className='flag-row';
  row.innerHTML='<span>'+esc(f.key)+desc+'</span><label class="toggle"><input type="checkbox" data-flag="'+esc(f.key)+'" '+(f.enabled?'checked':'')+'><span class="slider"></span></label>';
  fDiv.appendChild(row);
 });
 fDiv.querySelectorAll('input[data-flag]').forEach(inp=>{inp.addEventListener('change',async e=>{
  const name=e.target.getAttribute('data-flag');const enabled=e.target.checked;
  try{
   const r=await apiFetch('/api/v1/settings/flag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,enabled:enabled})});
   const j=await r.json();
   if(r.ok){showToast('Flag '+name+' = '+enabled,'ok');}
   else{showToast('Fehler: '+(j.error||JSON.stringify(j)),'err');e.target.checked=!enabled;}
  }catch(err){showToast('Netzwerk-Fehler: '+err,'err');e.target.checked=!enabled;}
 });});
 }else{fDiv.innerHTML='<div class="empty">Keine Feature Flags</div>';}
 const llmCfg=sdata.llm_config||sdata.llm||st.llm_config||{};
 const cDiv=document.getElementById('set-llm-config');cDiv.innerHTML='';
 const ckeys=Object.keys(llmCfg);
 if(ckeys.length){ckeys.forEach(k=>{
  cDiv.innerHTML+='<div class="flag-row"><span>'+esc(k)+'</span><span style="color:#94a3b8">'+esc(String(llmCfg[k]))+'</span></div>';
 });}else{cDiv.innerHTML='<div class="empty">Keine LLM-Config</div>';}
 const ws=st.transfer_warnings||[];
 const wDiv=document.getElementById('set-warnings');
 const wSec=document.getElementById('set-warnings-section');
 if(ws.length){wSec.style.display='';wDiv.innerHTML='';
  ws.forEach(w=>{wDiv.innerHTML+='<div class="warn-item">'+esc(w.provider||'?')+': '+esc(w.warning||w.message||JSON.stringify(w))+'</div>';});
 }else{wSec.style.display='none';}
}

async function syncLabels(){
 const btn=document.getElementById('btn-sync-labels');
 const out=document.getElementById('labels-result');
 btn.disabled=true;out.textContent='Synchronisiere...';
 try{
  const r=await apiFetch('/api/v1/setup/labels',{method:'POST',headers:{'Content-Type':'application/json'}});
  const j=await r.json();
  const d=j.data||j;
  if(r.ok&&d.synced!==false){
   const c=(d.created||[]).length,s=(d.skipped||[]).length,e=(d.errors||[]).length;
   out.textContent='Created='+c+', Skipped='+s+', Errors='+e;
   showToast('Labels synchronisiert: +'+c+' / skip '+s+(e?' / err '+e:''), e?'warn':'ok');
  }else{
   const msg=d.error||d.errors||JSON.stringify(d);
   out.textContent='Fehler: '+msg;
   showToast('Fehler beim Sync: '+msg,'err');
  }
 }catch(err){out.textContent='Fehler: '+err;showToast('Netzwerk-Fehler: '+err,'err');}
 finally{btn.disabled=false;}
}

async function loadSelfCheck(){
 const d=await apiFetch('/api/v1/dashboard/self_check').then(r=>r.json());
 const data=d.data||d;
 document.getElementById('sc-mode').textContent=data.mode||'-';
 const h=!!data.healthy;const el=document.getElementById('sc-healthy');
 el.textContent=h?'OK':'Fehler';el.className='val '+(h?'ok':'err');
 const tb=document.getElementById('sc-body');tb.innerHTML='';
 const checks=data.checks||[];
 if(checks.length){checks.forEach(c=>{const cls=c.status==='OK'?'ok':'err';
  tb.innerHTML+='<tr><td>'+esc(c.name||'-')+'</td><td class="'+cls+'">'+esc(c.status||'-')+'</td><td>'+esc(c.time||'-')+'</td><td>'+esc(c.detail||'-')+'</td></tr>';});}
 else{tb.innerHTML='<tr><td colspan="4" class="empty">Keine Self-Check-Daten</td></tr>';}
}

setInterval(()=>{
 if(!autoRefresh){document.getElementById('countdown').textContent='-';return;}
 cd--;document.getElementById('countdown').textContent=cd;
 if(cd<=0){cd=REFRESH_INTERVAL;loadTabData(currentTab)}
},1000);
document.getElementById('auto-refresh-btn').textContent='auto-refresh: '+(autoRefresh?'on':'off');
showTab(currentTab);
</script>
</body>
</html>
"""


class SAMUELRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format: str, *args: Any) -> None:
        log.debug(format, *args)

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # Paths that are reachable without API-key auth even when auth is enabled.
    # Webhook uses HMAC, not API key. Everything else (including the HTML
    # dashboard) requires the key when SAMUEL_API_KEY is set.
    _AUTH_EXEMPT_PATHS: set[str] = {"/api/v1/webhook"}

    def _auth_required(self) -> bool:
        """Return True if the current request must be rejected as unauthorized."""
        auth = getattr(self.__class__, "auth_middleware", None)
        if auth is None:
            return False
        if self.path in self._AUTH_EXEMPT_PATHS:
            return False
        return not auth.authenticate(dict(self.headers))

    def _send_unauthorized(self) -> None:
        self._send_json(401, {"error": "unauthorized"})

    def do_GET(self) -> None:
        if self._auth_required():
            self._send_unauthorized()
            return

        if self.path == "/" or self.path == "/dashboard":
            self._send_html(DASHBOARD_HTML)
            return

        if self.path == "/api/v1/dashboard/status":
            self._send_json(200, self.dashboard.get_status())
            return

        if self.path == "/api/v1/dashboard/metrics":
            self._send_json(200, self.dashboard.get_metrics())
            return

        if self.path == "/api/v1/dashboard/transfer_warnings":
            self._send_json(200, {"transfer_warnings": self.dashboard.get_transfer_warnings()})
            return

        if self.path == "/api/v1/dashboard/health":
            self._send_json(200, self.dashboard.get_health())
            return

        if self.path == "/api/v1/dashboard/logs":
            self._send_json(200, self.dashboard.get_logs())
            return

        if self.path == "/api/v1/dashboard/security":
            self._send_json(200, self.dashboard.get_security())
            return

        if self.path == "/api/v1/dashboard/workflow":
            self._send_json(200, self.dashboard.get_workflow())
            return

        if self.path == "/api/v1/dashboard/llm":
            self._send_json(200, self.dashboard.get_llm())
            return

        if self.path == "/api/v1/dashboard/settings":
            self._send_json(200, self.dashboard.get_settings())
            return

        if self.path == "/api/v1/dashboard/self_check":
            self._send_json(200, self.dashboard.get_self_check())
            return

        resp = self.rest_api.handle_request("GET", self.path, headers=dict(self.headers))
        self._send_json(resp.get("status", 200), resp.get("data", resp))

    def do_HEAD(self) -> None:  # noqa: N802
        if self._auth_required():
            self._send_unauthorized()
            return
        # Minimal HEAD: say 200 for known GET-paths, else 404
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_POST(self) -> None:
        if self._auth_required():
            self._send_unauthorized()
            return

        body = self._read_body()

        if self.path == "/api/v1/webhook":
            event_type = self.headers.get("X-Gitea-Event", "") or self.headers.get("X-GitHub-Event", "")
            signature = self.headers.get("X-Gitea-Signature", "") or self.headers.get("X-Hub-Signature-256", "")
            resp = self.webhook_adapter.handle_webhook(event_type, body, signature)
            self._send_json(resp.get("status", 200), resp)
            return

        resp = self.rest_api.handle_request("POST", self.path, body=body, headers=dict(self.headers))
        self._send_json(resp.get("status", 200), resp.get("data", resp))


def create_server(
    bus: Bus,
    host: str = "0.0.0.0",
    port: int = 7777,
    scm: Any = None,
    config: Any = None,
) -> HTTPServer:
    api_key = os.environ.get("SAMUEL_API_KEY", "")
    if api_key:
        _auth = APIKeyAuth([api_key])
        log.info("API key auth enabled for /api/* endpoints")
    else:
        _auth = None
        log.warning("SAMUEL_API_KEY not set — API endpoints have NO authentication")
    webhook_secret = os.environ.get("SLICE_HMAC_KEY", "")
    _webhooks = WebhookIngressAdapter(bus, secret=webhook_secret)
    # Build transfer warning function from privacy config
    transfer_warning_fn = None
    try:
        from pathlib import Path as _Path

        from samuel.slices.privacy.handler import TransferWarning
        _privacy_path = _Path("config/privacy.json")
        if _privacy_path.exists():
            _privacy_data = json.loads(_privacy_path.read_text(encoding="utf-8"))
        else:
            _privacy_data = {}
        _tw = TransferWarning(_privacy_data)
        transfer_warning_fn = _tw.check_all_providers
    except Exception as e:
        log.warning("Failed to load transfer warning config: %s", e)
    _dash = DashboardHandler(bus, scm=scm, config=config, transfer_warning_fn=transfer_warning_fn)
    _setup = SetupHandler(bus, config=config, scm=scm)
    _rest = RestAPI(bus, auth_middleware=_auth, setup_handler=_setup, dashboard_handler=_dash)

    class Handler(SAMUELRequestHandler):
        rest_api = _rest
        webhook_adapter = _webhooks
        dashboard = _dash
        auth_middleware = _auth

    server = HTTPServer((host, port), Handler)
    log.info("HTTP-Server auf %s:%d", host, port)
    return server
