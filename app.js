const COMPS=[
{id:"epl",name:"Premier League",short:"EPL",country:"England",code:"en.1",open:true},
{id:"laliga",name:"LaLiga",short:"LAL",country:"Spain",code:"es.1",open:true},
{id:"bundesliga",name:"Bundesliga",short:"BUN",country:"Germany",code:"de.1",open:true},
{id:"seriea",name:"Serie A",short:"SEA",country:"Italy",code:"it.1",open:true},
{id:"ligue1",name:"Ligue 1",short:"L1",country:"France",code:"fr.1",open:true},
{id:"ucl",name:"UEFA Champions League",short:"UCL",country:"Europe",open:false},
{id:"uel",name:"UEFA Europa League",short:"UEL",country:"Europe",open:false},
{id:"uecl",name:"UEFA Conference League",short:"UECL",country:"Europe",open:false},
{id:"copa",name:"Copa del Rey",short:"CDR",country:"Spain",open:false},
{id:"eflcup",name:"Carabao Cup (EFL Cup)",short:"EFL",country:"England",open:false},
{id:"facup",name:"FA Cup",short:"FAC",country:"England",open:false}
];
const S={comp:"all",season:null,view:"overview",data:null,global:[],filter:"all",q:"",cache:new Map()};
const $=q=>document.querySelector(q),$$=q=>[...document.querySelectorAll(q)];
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const seasonLabel=y=>y+"/"+String((y+1)%100).padStart(2,"0");
const seasonPath=y=>y+"-"+String((y+1)%100).padStart(2,"0");
const currentSeason=()=>{const d=new Date();return d.getMonth()>=6?d.getFullYear():d.getFullYear()-1};
const comp=id=>COMPS.find(c=>c.id===id);
const initials=n=>String(n||"").split(/\s+/).filter(Boolean).slice(0,3).map(x=>x[0]).join("").toUpperCase();
const avatar=n=>'<span class="team-avatar">'+esc(initials(n))+"</span>";
const badge=c=>'<span class="badge-logo">'+esc(c.short)+"</span>";
const pct=v=>Number.isFinite(v)?Math.round(v)+"%":"—",one=v=>Number.isFinite(v)?v.toFixed(2):"—";

function setLoading(v){$("#loading").classList.toggle("hidden",!v);$("#refreshBtn").disabled=v}
function showError(m=""){const e=$("#errorBanner");e.textContent=m;e.classList.toggle("hidden",!m)}
function rawUrl(c,y){return "https://raw.githubusercontent.com/openfootball/football.json/master/"+seasonPath(y)+"/"+c.code+".json"}
async function fetchJSON(url,force=false){
 if(!force&&S.cache.has(url))return S.cache.get(url);
 const key="fi:"+url;
 if(!force){try{const x=JSON.parse(localStorage.getItem(key)||"null");if(x&&Date.now()-x.t<900000){S.cache.set(url,x.d);return x.d}}catch{}}
 const r=await fetch(force?url+(url.includes("?")?"&":"?")+"_="+Date.now():url,{headers:{Accept:"application/json"}});
 if(!r.ok)throw new Error("OpenFootball does not currently publish this season file (HTTP "+r.status+").");
 const d=await r.json();S.cache.set(url,d);try{localStorage.setItem(key,JSON.stringify({t:Date.now(),d}))}catch{}return d;
}
function norm(c,m,i){
 const ft=m.score&&Array.isArray(m.score.ft)?m.score.ft:null;
 return{id:c.id+"-"+i,date:m.date||"",time:m.time||"",round:m.round||"",league:c.name,home:m.team1||"TBD",away:m.team2||"TBD",hg:ft?Number(ft[0]):null,ag:ft?Number(ft[1]):null,finished:!!ft};
}
function calc(fixtures){
 const T=new Map(),ensure=n=>{if(!T.has(n))T.set(n,{name:n,p:0,w:0,d:0,l:0,gf:0,ga:0,pts:0,form:[]});return T.get(n)};
 let goals=0,hw=0,aw=0,dr=0,btts=0,o25=0,done=0;
 for(const f of fixtures){const h=ensure(f.home),a=ensure(f.away);if(!f.finished)continue;done++;h.p++;a.p++;h.gf+=f.hg;h.ga+=f.ag;a.gf+=f.ag;a.ga+=f.hg;goals+=f.hg+f.ag;if(f.hg>f.ag){h.w++;a.l++;h.pts+=3;h.form.push("W");a.form.push("L");hw++}else if(f.hg<f.ag){a.w++;h.l++;a.pts+=3;h.form.push("L");a.form.push("W");aw++}else{h.d++;a.d++;h.pts++;a.pts++;h.form.push("D");a.form.push("D");dr++}if(f.hg&&f.ag)btts++;if(f.hg+f.ag>=3)o25++}
 const table=[...T.values()].map(x=>({...x,gd:x.gf-x.ga,last:x.form.slice(-5).join("")})).sort((a,b)=>b.pts-a.pts||b.gd-a.gd||b.gf-a.gf||a.name.localeCompare(b.name));table.forEach((x,i)=>x.rank=i+1);
 const recent=fixtures.filter(x=>x.finished).slice().sort((a,b)=>(b.date+b.time).localeCompare(a.date+a.time)).slice(0,10);
 const upcoming=fixtures.filter(x=>!x.finished).slice().sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time)).slice(0,10);
 return{table,done,total:fixtures.length,goals,gpm:done?goals/done:NaN,hw:done?hw/done*100:NaN,aw:done?aw/done*100:NaN,dr:done?dr/done*100:NaN,btts:done?btts/done*100:NaN,o25:done?o25/done*100:NaN,recent,upcoming,teams:[...T.keys()].sort()};
}
async function loadComp(c,force=false){
 if(!c.open)return{c,available:false,reason:"Current open-data source not wired yet."};
 try{const body=await fetchJSON(rawUrl(c,S.season),force),fixtures=(body.matches||[]).map((m,i)=>norm(c,m,i));return{c,available:true,name:body.name||c.name,fixtures,stats:calc(fixtures)}}catch(e){return{c,available:false,reason:e.message}}
}
async function load(force=false){
 setLoading(true);showError("");
 try{if(S.comp==="all")S.global=await Promise.all(COMPS.filter(c=>c.open).map(c=>loadComp(c,force)));else S.data=await loadComp(comp(S.comp),force);render()}catch(e){showError(e.message||String(e))}finally{setLoading(false)}
}
function kpi(v,l){return '<div class="kpi"><b>'+esc(v)+'</b><span>'+esc(l)+'</span></div>'}
function matchHTML(f){return '<div class="match"><div class="club">'+avatar(f.home)+'<span>'+esc(f.home)+'</span></div><div class="score">'+(f.finished?esc(f.hg+"–"+f.ag):esc(f.time||"—"))+'</div><div class="club away"><span>'+esc(f.away)+'</span>'+avatar(f.away)+'</div><div class="meta">'+esc(f.finished?"Full time":"Scheduled")+" · "+esc(f.round||f.league)+" · "+esc(f.date)+(f.time?" · "+esc(f.time):"")+"</div></div>"}
function matchesBlock(title,list){return '<div class="card panel"><div class="section-head"><h3>'+esc(title)+'</h3><span>'+list.length+' matches</span></div><div class="match-list">'+(list.length?list.map(matchHTML).join(""):'<div class="empty">No matches here yet.</div>')+"</div></div>"}
function tableHTML(rows){
 if(!rows.length)return '<div class="empty">No completed results yet.</div>';
 return '<div class="table-wrap"><table class="data-table"><thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th><th>Form</th></tr></thead><tbody>'+rows.map(r=>'<tr><td><span class="rank">'+r.rank+'</span></td><td><div class="team-cell">'+avatar(r.name)+'<span>'+esc(r.name)+'</span></div></td><td>'+r.p+'</td><td>'+r.w+'</td><td>'+r.d+'</td><td>'+r.l+'</td><td>'+r.gf+'</td><td>'+r.ga+'</td><td>'+(r.gd>0?"+":"")+r.gd+'</td><td><b>'+r.pts+'</b></td><td class="form">'+esc(r.last||"—")+'</td></tr>').join("")+"</tbody></table></div>";
}
function unavailable(d){return '<div class="card page-card"><div class="page-title"><div><h2>'+esc(d.c.name)+'</h2><p>'+esc(seasonLabel(S.season))+'</p></div><span class="status-badge">Source pending</span></div><div class="notice"><b>Data source not available in this build.</b><br>'+esc(d.reason)+'</div></div>'}
function renderOverview(){
 const root=$("#overviewView");
 if(S.comp==="all"){
  const ok=S.global.filter(x=>x.available),all=ok.flatMap(x=>x.fixtures),st=calc(all),next=all.filter(x=>!x.finished).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time)).slice(0,12);
  root.innerHTML='<div class="card hero"><div class="eyebrow">Open data · no API key</div><h2>European Football Command Centre</h2><p>One dashboard for the major European leagues, powered by public OpenFootball datasets on GitHub. Select a competition to drill into fixtures, tables, teams and calculated league statistics.</p><div class="hero-meta"><span class="source-pill">GitHub / OpenFootball</span><span class="status-badge">'+seasonLabel(S.season)+'</span></div></div><div class="grid4">'+kpi(ok.length,"Live league feeds")+kpi(st.done,"Completed matches")+kpi(st.goals,"Goals recorded")+kpi(one(st.gpm),"Goals / match")+'</div><div class="grid2">'+matchesBlock("Upcoming across leagues",next)+'<div class="card panel"><div class="section-head"><h3>Competition status</h3><span>'+COMPS.length+' configured</span></div>'+COMPS.map(c=>'<div class="stat-row"><span>'+esc(c.name)+'</span><b>'+(c.open?"Open feed":"Pending")+'</b></div>').join("")+"</div></div>";
 }else{
  const d=S.data;if(!d){root.innerHTML="";return}if(!d.available){root.innerHTML=unavailable(d);return}const s=d.stats;
  root.innerHTML='<div class="card hero"><div class="eyebrow">'+esc(d.c.country)+' · '+seasonLabel(S.season)+'</div><h2>'+esc(d.c.name)+'</h2><p>Standings and league metrics are calculated in your browser from OpenFootball fixture/result data. No API-Sports requests are used.</p><div class="hero-meta"><span class="source-pill">OpenFootball</span><span class="status-badge">'+s.done+' / '+s.total+' completed</span></div></div><div class="grid4">'+kpi(s.done,"Completed matches")+kpi(s.goals,"Total goals")+kpi(one(s.gpm),"Goals / match")+kpi(pct(s.btts),"BTTS")+'</div><div class="grid2"><div class="card panel"><div class="section-head"><h3>Standings</h3><span>Calculated table</span></div>'+tableHTML(s.table)+'</div>'+matchesBlock("Next fixtures",s.upcoming)+"</div>";
 }
}
function renderMatches(){
 const root=$("#matchesView");let list=[];
 if(S.comp==="all")list=S.global.filter(x=>x.available).flatMap(x=>x.fixtures);else if(S.data?.available)list=S.data.fixtures;else{root.innerHTML=S.data?unavailable(S.data):"";return}
 const q=S.q.toLowerCase().trim();list=list.filter(f=>(S.filter==="all"||(S.filter==="finished"&&f.finished)||(S.filter==="upcoming"&&!f.finished))&&(!q||(f.home+" "+f.away+" "+f.league+" "+f.round).toLowerCase().includes(q))).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time));
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Match centre</h2><p>'+esc(S.comp==="all"?"All open league feeds":comp(S.comp).name)+'</p></div><span class="status-badge">'+list.length+' matches</span></div><div class="toolbar"><input id="matchSearch" placeholder="Search team or round" value="'+esc(S.q)+'"><div class="segment">'+["all","upcoming","finished"].map(x=>'<button data-f="'+x+'" class="'+(S.filter===x?"active":"")+'">'+x[0].toUpperCase()+x.slice(1)+'</button>').join("")+'</div></div><div class="match-list">'+(list.length?list.slice(0,250).map(matchHTML).join(""):'<div class="empty">No matches match the filter.</div>')+'</div><div class="note">OpenFootball is a community-maintained fixture/result dataset, not a live-score service.</div></div>';
 $("#matchSearch").oninput=e=>{S.q=e.target.value;renderMatches()};$$("[data-f]").forEach(b=>b.onclick=()=>{S.filter=b.dataset.f;renderMatches()});
}
function compCard(c){return '<div class="comp-card" data-comp="'+c.id+'"><div class="comp-top">'+badge(c)+'<div><b>'+esc(c.name)+'</b><small>'+esc(c.country)+'</small></div></div><div class="comp-status '+(c.open?"":"pending")+'">'+(c.open?"● Open GitHub feed":"○ Source pending")+"</div></div>"}
function renderCompetitions(){$("#competitionsView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Competitions</h2><p>Choose any competition to open it.</p></div><span class="status-badge">'+COMPS.length+' configured</span></div><div class="competition-grid">'+COMPS.map(compCard).join("")+'</div></div>';bindCards()}
function renderTeams(){
 const root=$("#teamsView");if(S.comp==="all"){root.innerHTML='<div class="card page-card"><div class="empty">Select a competition to view its teams.</div></div>';return}const d=S.data;if(!d?.available){root.innerHTML=d?unavailable(d):"";return}
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>'+esc(d.c.name)+' teams</h2><p>Teams detected from the season fixture file.</p></div><span class="status-badge">'+d.stats.teams.length+' teams</span></div><div class="team-grid">'+d.stats.teams.map(n=>'<div class="team-card">'+avatar(n)+'<div><b>'+esc(n)+'</b><span>'+esc(d.c.country)+'</span></div></div>').join("")+"</div></div>";
}
function renderPlayers(){$("#playersView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Players</h2><p>Detailed player data requires a second source.</p></div><span class="status-badge">Not fabricated</span></div><div class="notice"><b>Player scorers, assists and cards are intentionally blank for now.</b><br>The free OpenFootball files used here focus on fixtures and results. We can later add a separate source just for player/event data without bringing back a 100-request daily dependency for the whole site.</div></div>'}
function renderStats(){
 const root=$("#statisticsView");if(S.comp==="all"){root.innerHTML='<div class="card page-card"><div class="empty">Select a competition to see its statistics.</div></div>';return}const d=S.data;if(!d?.available){root.innerHTML=d?unavailable(d):"";return}const s=d.stats,rows=[["Goals / match",one(s.gpm)],["BTTS",pct(s.btts)],["Over 2.5",pct(s.o25)],["Home wins",pct(s.hw)],["Draws",pct(s.dr)],["Away wins",pct(s.aw)],["Total goals",s.goals],["Completed fixtures",s.done]];
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Competition statistics</h2><p>Calculated from completed results.</p></div></div><div class="metric-grid">'+rows.map(x=>'<div class="metric-card"><strong>'+esc(x[1])+'</strong><span>'+esc(x[0])+'</span></div>').join("")+'</div><div class="note">These figures are descriptive and depend on source completeness.</div></div>';
}
function renderCompare(){
 const opts=COMPS.filter(c=>c.open).map(c=>'<option value="'+c.id+'">'+esc(c.name)+'</option>').join("");
 $("#compareView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Compare leagues</h2><p>Compare calculated season metrics.</p></div></div><div class="compare-controls"><label>League A<select id="cmpA">'+opts+'</select></label><label>League B<select id="cmpB">'+opts+'</select></label><button class="ghost" id="cmpBtn">Compare</button></div><div id="cmpResult"><div class="empty">Choose two leagues and compare.</div></div></div>';
 $("#cmpA").value=S.comp!=="all"&&comp(S.comp)?.open?S.comp:"epl";$("#cmpB").value=$("#cmpA").value==="laliga"?"epl":"laliga";
 $("#cmpBtn").onclick=async()=>{setLoading(true);try{const[a,b]=await Promise.all([loadComp(comp($("#cmpA").value)),loadComp(comp($("#cmpB").value))]);if(!a.available||!b.available)throw new Error("One selected dataset is unavailable.");$("#cmpResult").innerHTML='<div class="compare-result">'+compareSide(a)+'<div class="vs">VS</div>'+compareSide(b)+'</div>'}catch(e){showError(e.message)}finally{setLoading(false)}};
}
function compareSide(d){const s=d.stats;return '<div class="compare-side"><div class="compare-head">'+badge(d.c)+'<div><b>'+esc(d.c.name)+'</b><span>'+s.done+' completed</span></div></div>'+[["Goals / match",one(s.gpm)],["BTTS",pct(s.btts)],["Over 2.5",pct(s.o25)],["Home wins",pct(s.hw)],["Draws",pct(s.dr)]].map(x=>'<div class="delta"><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join("")+"</div>"}
function bindCards(){$$("[data-comp]").forEach(x=>x.onclick=async()=>{S.comp=x.dataset.comp;$("#competitionSelect").value=S.comp;await load();switchView("overview")})}
function switchView(v){S.view=v;$$(".view").forEach(x=>x.classList.add("hidden"));$("#"+v+"View").classList.remove("hidden");$$("#mainNav button").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="compare")renderCompare()}
function render(){
 $("#pageTitle").textContent=S.comp==="all"?"All Competitions":comp(S.comp).name;
 renderOverview();renderMatches();renderCompetitions();renderTeams();renderPlayers();renderStats();if(S.view==="compare")renderCompare();bindCards()
}
async function init(){
 S.season=currentSeason();for(let y=S.season;y>=S.season-4;y--)$("#seasonSelect").insertAdjacentHTML("beforeend",'<option value="'+y+'">'+seasonLabel(y)+"</option>");
 COMPS.forEach(c=>$("#competitionSelect").insertAdjacentHTML("beforeend",'<option value="'+c.id+'">'+esc(c.name)+"</option>"));
 $$("#mainNav button").forEach(b=>b.onclick=()=>switchView(b.dataset.view));
 $("#competitionSelect").onchange=async e=>{S.comp=e.target.value;S.q="";S.filter="all";await load();switchView("overview")};
 $("#seasonSelect").onchange=async e=>{S.season=Number(e.target.value);await load()};
 $("#refreshBtn").onclick=async()=>{S.cache.clear();try{Object.keys(localStorage).filter(k=>k.startsWith("fi:")).forEach(k=>localStorage.removeItem(k))}catch{}await load(true)};
 await load()
}
document.addEventListener("DOMContentLoaded",init);