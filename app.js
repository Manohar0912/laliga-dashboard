const COMPS=[
{id:"epl",name:"Premier League",short:"EPL",country:"England",historyCode:"en.1",type:"league"},
{id:"laliga",name:"LaLiga",short:"LAL",country:"Spain",historyCode:"es.1",type:"league"},
{id:"bundesliga",name:"Bundesliga",short:"BUN",country:"Germany",historyCode:"de.1",type:"league"},
{id:"seriea",name:"Serie A",short:"SEA",country:"Italy",historyCode:"it.1",type:"league"},
{id:"ligue1",name:"Ligue 1",short:"L1",country:"France",historyCode:"fr.1",type:"league"},
{id:"ucl",name:"UEFA Champions League",short:"UCL",country:"Europe",type:"uefa"},
{id:"uel",name:"UEFA Europa League",short:"UEL",country:"Europe",type:"uefa"},
{id:"uecl",name:"UEFA Conference League",short:"UECL",country:"Europe",type:"uefa"},
{id:"copa",name:"Copa del Rey",short:"CDR",country:"Spain",type:"cup"},
{id:"eflcup",name:"Carabao Cup (EFL Cup)",short:"EFL",country:"England",type:"cup"},
{id:"facup",name:"FA Cup",short:"FAC",country:"England",type:"cup"}
];

const S={comp:"all",season:null,view:"overview",data:null,global:[],filter:"all",q:"",cache:new Map()};
const $=q=>document.querySelector(q),$$=q=>[...document.querySelectorAll(q)];
const esc=v=>String(v??"").replace(/[&<>'"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const seasonLabel=y=>y+"/"+String((y+1)%100).padStart(2,"0");
const seasonPath=y=>y+"-"+String((y+1)%100).padStart(2,"0");
const currentSeason=()=>{const d=new Date();return d.getMonth()>=6?d.getFullYear():d.getFullYear()-1};
const comp=id=>COMPS.find(c=>c.id===id);
const initials=n=>String(n||"").split(/\s+/).filter(Boolean).slice(0,3).map(x=>x[0]).join("").toUpperCase();
const pct=v=>Number.isFinite(v)?Math.round(v)+"%":"—";
const one=v=>Number.isFinite(v)?v.toFixed(2):"—";
const fmtDate=d=>{try{return new Intl.DateTimeFormat(undefined,{day:"numeric",month:"short",year:"numeric"}).format(new Date(d+"T12:00:00Z"))}catch{return d}};
const fmtTime=iso=>{if(!iso)return"";try{return new Intl.DateTimeFormat(undefined,{hour:"2-digit",minute:"2-digit"}).format(new Date(iso))}catch{return""}};
const updatedText=iso=>{if(!iso)return"Update time unavailable";const ms=Date.now()-new Date(iso).getTime();if(ms<0)return"Updated just now";const mins=Math.floor(ms/60000);if(mins<2)return"Updated just now";if(mins<60)return"Updated "+mins+" min ago";const h=Math.floor(mins/60);if(h<24)return"Updated "+h+"h ago";return"Updated "+Math.floor(h/24)+"d ago"};

function teamVisual(name,logo=""){
 if(logo)return '<span class="team-avatar"><img src="'+esc(logo)+'" alt="" loading="lazy" referrerpolicy="no-referrer"></span>';
 return '<span class="team-avatar">'+esc(initials(name))+"</span>";
}
const badge=c=>'<span class="badge-logo">'+esc(c.short)+"</span>";

function setLoading(v){$("#loading").classList.toggle("hidden",!v);$("#refreshBtn").disabled=v}
function showError(m=""){const e=$("#errorBanner");e.textContent=m;e.classList.toggle("hidden",!m)}

async function fetchJSON(url,force=false){
 const cacheKey=url.replace(/[?&]_=[^&]+/,"");
 if(!force&&S.cache.has(cacheKey))return S.cache.get(cacheKey);
 const r=await fetch(url,{cache:force?"no-store":"default",headers:{Accept:"application/json"}});
 if(!r.ok)throw new Error("Data file unavailable (HTTP "+r.status+").");
 const d=await r.json();S.cache.set(cacheKey,d);return d;
}

function rawUrl(c,y){return "https://raw.githubusercontent.com/openfootball/football.json/master/"+seasonPath(y)+"/"+c.historyCode+".json"}

function normOpen(c,m,i){
 const ft=m.score&&Array.isArray(m.score.ft)?m.score.ft:null;
 return{id:c.id+"-open-"+i,date:m.date||"",dateTime:(m.date||"")+(m.time?"T"+m.time+":00":"T12:00:00"),time:m.time||"",round:m.round||"",league:c.name,home:m.team1||"TBD",away:m.team2||"TBD",hg:ft?Number(ft[0]):null,ag:ft?Number(ft[1]):null,finished:!!ft,state:ft?"post":"pre",status:ft?"Full Time":"Scheduled",homeLogo:"",awayLogo:"",venue:""};
}
function normSnapshot(c,m){
 return{id:String(m.id||""),date:m.date||"",dateTime:m.dateTime||"",time:fmtTime(m.dateTime),round:String(m.round||""),league:c.name,home:m.home||"TBD",away:m.away||"TBD",hg:Number.isFinite(m.homeScore)?m.homeScore:null,ag:Number.isFinite(m.awayScore)?m.awayScore:null,finished:!!m.completed,state:m.state||"",status:m.statusDetail||m.status||"",homeLogo:m.homeLogo||"",awayLogo:m.awayLogo||"",venue:m.venue||""};
}

function calc(fixtures){
 const T=new Map(),ensure=n=>{if(!T.has(n))T.set(n,{name:n,p:0,w:0,d:0,l:0,gf:0,ga:0,pts:0,form:[]});return T.get(n)};
 let goals=0,hw=0,aw=0,dr=0,btts=0,o25=0,done=0;
 for(const f of fixtures){const h=ensure(f.home),a=ensure(f.away);if(!f.finished||!Number.isFinite(f.hg)||!Number.isFinite(f.ag))continue;done++;h.p++;a.p++;h.gf+=f.hg;h.ga+=f.ag;a.gf+=f.ag;a.ga+=f.hg;goals+=f.hg+f.ag;if(f.hg>f.ag){h.w++;a.l++;h.pts+=3;h.form.push("W");a.form.push("L");hw++}else if(f.hg<f.ag){a.w++;h.l++;a.pts+=3;h.form.push("L");a.form.push("W");aw++}else{h.d++;a.d++;h.pts++;a.pts++;h.form.push("D");a.form.push("D");dr++}if(f.hg>0&&f.ag>0)btts++;if(f.hg+f.ag>=3)o25++}
 const table=[...T.values()].map(x=>({...x,gd:x.gf-x.ga,last:x.form.slice(-5).join("")})).sort((a,b)=>b.pts-a.pts||b.gd-a.gd||b.gf-a.gf||a.name.localeCompare(b.name));table.forEach((x,i)=>x.rank=i+1);
 const recent=fixtures.filter(x=>x.finished).slice().sort((a,b)=>(b.dateTime||b.date).localeCompare(a.dateTime||a.date)).slice(0,10);
 const upcoming=fixtures.filter(x=>!x.finished).slice().sort((a,b)=>(a.dateTime||a.date).localeCompare(b.dateTime||b.date)).slice(0,10);
 return{table,done,total:fixtures.length,goals,gpm:done?goals/done:NaN,hw:done?hw/done*100:NaN,aw:done?aw/done*100:NaN,dr:done?dr/done*100:NaN,btts:done?btts/done*100:NaN,o25:done?o25/done*100:NaN,recent,upcoming,teams:[...T.keys()].sort()};
}

function mapSnapshotStandings(rows=[]){
 return rows.map((r,i)=>({rank:Number(r.rank)||i+1,name:r.team||"",logo:r.logo||"",p:Number(r.played)||0,w:Number(r.wins)||0,d:Number(r.draws)||0,l:Number(r.losses)||0,gf:Number(r.gf)||0,ga:Number(r.ga)||0,gd:Number(r.gd)||0,pts:Number(r.points)||0,last:r.form||"",group:r.group||""}));
}

async function loadCurrent(c,force=false){
 const stamp=force?Date.now():Math.floor(Date.now()/300000);
 const body=await fetchJSON("./data/current/"+c.id+".json?v="+stamp,force);
 if(Number(body.season)!==currentSeason())throw new Error("Current snapshot has not rolled over to this season yet.");
 const fixtures=(body.matches||[]).map(m=>normSnapshot(c,m));
 const stats=calc(fixtures);
 const standings=mapSnapshotStandings(body.standings||[]);
 const teams=(body.teams||[]).map(t=>({name:t.name||"",logo:t.logo||"",short:t.short||""})).filter(t=>t.name);
 return{c,available:true,current:true,source:body.source||"Current snapshot",updatedAt:body.updatedAt||"",fixtures,stats,standings,teams};
}

async function loadHistorical(c,force=false){
 if(!c.historyCode)return{c,available:false,reason:"Historical open-data source is not configured for this competition yet."};
 const body=await fetchJSON(rawUrl(c,S.season)+(force?"?v="+Date.now():""),force);
 const fixtures=(body.matches||[]).map((m,i)=>normOpen(c,m,i));
 return{c,available:true,current:false,source:"OpenFootball historical dataset",updatedAt:"",name:body.name||c.name,fixtures,stats:calc(fixtures),standings:[],teams:[]};
}

async function loadComp(c,force=false){
 if(S.season===currentSeason()){
  try{return await loadCurrent(c,force)}
  catch(e){
   if(c.historyCode){
    try{const fallback=await loadHistorical(c,force);fallback.fallback=true;fallback.reason="Current snapshot unavailable: "+e.message;return fallback}catch{}
   }
   return{c,available:false,reason:e.message};
  }
 }
 try{return await loadHistorical(c,force)}catch(e){return{c,available:false,reason:e.message}}
}

async function load(force=false){
 setLoading(true);showError("");
 try{
  if(S.comp==="all")S.global=await Promise.all(COMPS.map(c=>loadComp(c,force)));
  else S.data=await loadComp(comp(S.comp),force);
  render();
 }catch(e){showError(e.message||String(e))}
 finally{setLoading(false)}
}

function kpi(v,l){return '<div class="kpi"><b>'+esc(v)+'</b><span>'+esc(l)+'</span></div>'}

function matchHTML(f){
 const score=f.finished&&Number.isFinite(f.hg)&&Number.isFinite(f.ag)?esc(f.hg+"–"+f.ag):esc(f.time||fmtTime(f.dateTime)||"—");
 const status=f.finished?"Full time":(f.state==="in"?(f.status||"Live"):(f.status||"Scheduled"));
 return '<div class="match"><div class="club">'+teamVisual(f.home,f.homeLogo)+'<span>'+esc(f.home)+'</span></div><div class="score">'+score+'</div><div class="club away"><span>'+esc(f.away)+'</span>'+teamVisual(f.away,f.awayLogo)+'</div><div class="meta">'+esc(status)+' · '+esc(f.round||f.league)+' · '+esc(fmtDate(f.date))+(f.venue?" · "+esc(f.venue):"")+"</div></div>";
}
function matchesBlock(title,list){return '<div class="card panel"><div class="section-head"><h3>'+esc(title)+'</h3><span>'+list.length+' matches</span></div><div class="match-list">'+(list.length?list.map(matchHTML).join(""):'<div class="empty">No matches here yet.</div>')+"</div></div>"}

function tableHTML(rows){
 if(!rows.length)return '<div class="empty">No league table is available for this competition/stage.</div>';
 const groups=[...new Set(rows.map(r=>r.group).filter(Boolean))],showGroup=groups.length>1;
 return '<div class="table-wrap"><table class="data-table"><thead><tr><th>#</th><th>Team</th>'+(showGroup?'<th>Group</th>':'')+'<th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th><th>Form</th></tr></thead><tbody>'+rows.map(r=>'<tr><td><span class="rank">'+r.rank+'</span></td><td><div class="team-cell">'+teamVisual(r.name,r.logo)+'<span>'+esc(r.name)+'</span></div></td>'+(showGroup?'<td>'+esc(r.group)+'</td>':'')+'<td>'+r.p+'</td><td>'+r.w+'</td><td>'+r.d+'</td><td>'+r.l+'</td><td>'+r.gf+'</td><td>'+r.ga+'</td><td>'+(r.gd>0?"+":"")+r.gd+'</td><td><b>'+r.pts+'</b></td><td class="form">'+esc(r.last||"—")+'</td></tr>').join("")+"</tbody></table></div>";
}

function unavailable(d){return '<div class="card page-card"><div class="page-title"><div><h2>'+esc(d.c.name)+'</h2><p>'+esc(seasonLabel(S.season))+'</p></div><span class="status-badge">Data unavailable</span></div><div class="notice"><b>This feed has not loaded yet.</b><br>'+esc(d.reason||"Unknown data-source error.")+'</div></div>'}

function sourceLine(d){
 if(d.current)return '<span class="source-pill">Current GitHub snapshot</span><span class="status-badge">'+esc(updatedText(d.updatedAt))+'</span>';
 return '<span class="source-pill">OpenFootball history</span>'+(d.fallback?'<span class="status-badge">Current snapshot fallback</span>':'');
}

function bestTable(d){return d.standings&&d.standings.length?d.standings:d.stats.table}

function renderOverview(){
 const root=$("#overviewView");
 if(S.comp==="all"){
  const ok=S.global.filter(x=>x.available),all=ok.flatMap(x=>x.fixtures),st=calc(all);
  const now=Date.now()-12*3600000;
  const next=all.filter(x=>!x.finished&&(!x.dateTime||new Date(x.dateTime).getTime()>=now)).sort((a,b)=>(a.dateTime||a.date).localeCompare(b.dateTime||b.date)).slice(0,12);
  const freshness=ok.filter(x=>x.current&&x.updatedAt).sort((a,b)=>new Date(b.updatedAt)-new Date(a.updatedAt))[0];
  root.innerHTML='<div class="card hero"><div class="eyebrow">Auto-refreshed current data</div><h2>European Football Command Centre</h2><p>Current-season competitions are refreshed into this GitHub site automatically. Historical league seasons continue to use OpenFootball as the fallback archive.</p><div class="hero-meta"><span class="source-pill">GitHub-hosted snapshots</span><span class="status-badge">'+seasonLabel(S.season)+'</span>'+(freshness?'<span class="status-badge">'+esc(updatedText(freshness.updatedAt))+'</span>':'')+'</div></div><div class="grid4">'+kpi(ok.length,"Available competitions")+kpi(st.done,"Completed matches cached")+kpi(st.goals,"Goals in cached matches")+kpi(one(st.gpm),"Goals / match")+'</div><div class="grid2">'+matchesBlock("Upcoming across competitions",next)+'<div class="card panel"><div class="section-head"><h3>Competition feeds</h3><span>'+COMPS.length+' configured</span></div>'+COMPS.map(c=>{const d=S.global.find(x=>x.c.id===c.id);return'<div class="stat-row"><span>'+esc(c.name)+'</span><b>'+(d?.available?(d.current?"Current":"History"):"Unavailable")+'</b></div>'}).join("")+"</div></div>";
 }else{
  const d=S.data;if(!d){root.innerHTML="";return}if(!d.available){root.innerHTML=unavailable(d);return}const s=d.stats,table=bestTable(d);
  root.innerHTML='<div class="card hero"><div class="eyebrow">'+esc(d.c.country)+' · '+seasonLabel(S.season)+'</div><h2>'+esc(d.c.name)+'</h2><p>'+(d.current?'The current season is served from an automatically refreshed GitHub snapshot, so the table and recent results are no longer dependent on stale OpenFootball upstream files.':'Historical season data is loaded from OpenFootball.')+'</p><div class="hero-meta">'+sourceLine(d)+'<span class="status-badge">'+s.done+' completed cached</span></div></div><div class="grid4">'+kpi(s.done,"Completed matches")+kpi(s.goals,"Goals in match cache")+kpi(one(s.gpm),"Goals / match")+kpi(pct(s.btts),"BTTS")+'</div><div class="grid2"><div class="card panel"><div class="section-head"><h3>'+(d.c.type==="league"?"Standings":"Stage / standings")+'</h3><span>'+(d.standings.length?"Current source table":"Calculated where possible")+'</span></div>'+tableHTML(table)+'</div>'+matchesBlock("Next fixtures",s.upcoming)+"</div>";
 }
}

function renderMatches(){
 const root=$("#matchesView");let list=[];
 if(S.comp==="all")list=S.global.filter(x=>x.available).flatMap(x=>x.fixtures);
 else if(S.data?.available)list=S.data.fixtures;
 else{root.innerHTML=S.data?unavailable(S.data):"";return}
 const q=S.q.toLowerCase().trim();
 list=list.filter(f=>(S.filter==="all"||(S.filter==="finished"&&f.finished)||(S.filter==="upcoming"&&!f.finished))&&(!q||(f.home+" "+f.away+" "+f.league+" "+f.round).toLowerCase().includes(q))).sort((a,b)=>(a.dateTime||a.date).localeCompare(b.dateTime||b.date));
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Match centre</h2><p>'+esc(S.comp==="all"?"All available competitions":comp(S.comp).name)+'</p></div><span class="status-badge">'+list.length+' matches cached</span></div><div class="toolbar"><input id="matchSearch" placeholder="Search team or round" value="'+esc(S.q)+'"><div class="segment">'+["all","upcoming","finished"].map(x=>'<button data-f="'+x+'" class="'+(S.filter===x?"active":"")+'">'+x[0].toUpperCase()+x.slice(1)+'</button>').join("")+'</div></div><div class="match-list">'+(list.length?list.slice(0,350).map(matchHTML).join(""):'<div class="empty">No matches match the filter.</div>')+'</div><div class="note">Current-season snapshots refresh automatically on GitHub. This is not intended as second-by-second live scoring.</div></div>';
 $("#matchSearch").oninput=e=>{S.q=e.target.value;renderMatches()};$$("[data-f]").forEach(b=>b.onclick=()=>{S.filter=b.dataset.f;renderMatches()});
}

function compCard(c){
 const d=S.comp==="all"?S.global.find(x=>x.c.id===c.id):null;
 const state=d?(d.available?(d.current?"● Current snapshot":"● Historical feed"):"○ Unavailable"):(S.season===currentSeason()?"● Current snapshot":"● Historical when supported");
 return '<div class="comp-card" data-comp="'+c.id+'"><div class="comp-top">'+badge(c)+'<div><b>'+esc(c.name)+'</b><small>'+esc(c.country)+'</small></div></div><div class="comp-status '+(state.includes("Unavailable")?"pending":"")+'">'+state+"</div></div>";
}
function renderCompetitions(){$("#competitionsView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Competitions</h2><p>Current-season feeds are stored on this GitHub Pages site and refreshed automatically.</p></div><span class="status-badge">'+COMPS.length+' configured</span></div><div class="competition-grid">'+COMPS.map(compCard).join("")+'</div></div>';bindCards()}

function renderTeams(){
 const root=$("#teamsView");if(S.comp==="all"){root.innerHTML='<div class="card page-card"><div class="empty">Select a competition to view its teams.</div></div>';return}const d=S.data;if(!d?.available){root.innerHTML=d?unavailable(d):"";return}
 const sourceTeams=d.teams.length?d.teams:bestTable(d).map(x=>({name:x.name,logo:x.logo||"",short:""}));
 const seen=new Map();sourceTeams.forEach(t=>{if(t.name)seen.set(t.name,t)});
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>'+esc(d.c.name)+' teams</h2><p>'+esc(seasonLabel(S.season))+'</p></div><span class="status-badge">'+seen.size+' teams</span></div><div class="team-grid">'+[...seen.values()].sort((a,b)=>a.name.localeCompare(b.name)).map(t=>'<div class="team-card">'+teamVisual(t.name,t.logo)+'<div><b>'+esc(t.name)+'</b><span>'+esc(d.c.country)+'</span></div></div>').join("")+"</div></div>";
}

function renderPlayers(){$("#playersView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Players</h2><p>Player/event enrichment is the next data layer.</p></div><span class="status-badge">Next phase</span></div><div class="notice"><b>The current-data fix is focused first on accurate fixtures, results and standings.</b><br>Player scorers, assists, cards and lineups need additional endpoints and will be added after the competition feeds are stable.</div></div>'}

function renderStats(){
 const root=$("#statisticsView");if(S.comp==="all"){root.innerHTML='<div class="card page-card"><div class="empty">Select a competition to see its statistics.</div></div>';return}const d=S.data;if(!d?.available){root.innerHTML=d?unavailable(d):"";return}const s=d.stats;
 const rows=[["Goals / cached match",one(s.gpm)],["BTTS",pct(s.btts)],["Over 2.5",pct(s.o25)],["Home wins",pct(s.hw)],["Draws",pct(s.dr)],["Away wins",pct(s.aw)],["Goals cached",s.goals],["Completed cached",s.done]];
 root.innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Competition statistics</h2><p>Calculated from the match history currently cached by the dashboard.</p></div></div><div class="metric-grid">'+rows.map(x=>'<div class="metric-card"><strong>'+esc(x[1])+'</strong><span>'+esc(x[0])+'</span></div>').join("")+'</div><div class="note">'+(d.current?'The standings come from the current feed. Calculated match percentages become season-complete as the GitHub snapshot accumulates the season history.':'Historical figures depend on OpenFootball source completeness.')+'</div></div>';
}

function renderCompare(){
 const opts=COMPS.filter(c=>c.type==="league").map(c=>'<option value="'+c.id+'">'+esc(c.name)+'</option>').join("");
 $("#compareView").innerHTML='<div class="card page-card"><div class="page-title"><div><h2>Compare leagues</h2><p>Compare cached season metrics.</p></div></div><div class="compare-controls"><label>League A<select id="cmpA">'+opts+'</select></label><label>League B<select id="cmpB">'+opts+'</select></label><button class="ghost" id="cmpBtn">Compare</button></div><div id="cmpResult"><div class="empty">Choose two leagues and compare.</div></div></div>';
 $("#cmpA").value=S.comp!=="all"&&comp(S.comp)?.type==="league"?S.comp:"epl";$("#cmpB").value=$("#cmpA").value==="laliga"?"epl":"laliga";
 $("#cmpBtn").onclick=async()=>{setLoading(true);showError("");try{const[a,b]=await Promise.all([loadComp(comp($("#cmpA").value)),loadComp(comp($("#cmpB").value))]);if(!a.available||!b.available)throw new Error("One selected dataset is unavailable.");$("#cmpResult").innerHTML='<div class="compare-result">'+compareSide(a)+'<div class="vs">VS</div>'+compareSide(b)+'</div>'}catch(e){showError(e.message)}finally{setLoading(false)}};
}
function compareSide(d){const s=d.stats;return '<div class="compare-side"><div class="compare-head">'+badge(d.c)+'<div><b>'+esc(d.c.name)+'</b><span>'+(d.current?esc(updatedText(d.updatedAt)):seasonLabel(S.season))+'</span></div></div>'+[["Goals / match",one(s.gpm)],["BTTS",pct(s.btts)],["Over 2.5",pct(s.o25)],["Home wins",pct(s.hw)],["Draws",pct(s.dr)]].map(x=>'<div class="delta"><span>'+x[0]+'</span><b>'+x[1]+'</b></div>').join("")+"</div>"}

function bindCards(){$$("[data-comp]").forEach(x=>x.onclick=async()=>{S.comp=x.dataset.comp;$("#competitionSelect").value=S.comp;await load();switchView("overview")})}
function switchView(v){S.view=v;$$(".view").forEach(x=>x.classList.add("hidden"));$("#"+v+"View").classList.remove("hidden");$$("#mainNav button").forEach(x=>x.classList.toggle("active",x.dataset.view===v));if(v==="compare")renderCompare()}
function render(){
 $("#pageTitle").textContent=S.comp==="all"?"All Competitions":comp(S.comp).name;
 renderOverview();renderMatches();renderCompetitions();renderTeams();renderPlayers();renderStats();if(S.view==="compare")renderCompare();bindCards();
}
async function init(){
 S.season=currentSeason();for(let y=S.season;y>=S.season-4;y--)$("#seasonSelect").insertAdjacentHTML("beforeend",'<option value="'+y+'">'+seasonLabel(y)+"</option>");
 COMPS.forEach(c=>$("#competitionSelect").insertAdjacentHTML("beforeend",'<option value="'+c.id+'">'+esc(c.name)+"</option>"));
 $$("#mainNav button").forEach(b=>b.onclick=()=>switchView(b.dataset.view));
 $("#competitionSelect").onchange=async e=>{S.comp=e.target.value;S.q="";S.filter="all";await load();switchView("overview")};
 $("#seasonSelect").onchange=async e=>{S.season=Number(e.target.value);await load()};
 $("#refreshBtn").onclick=async()=>{S.cache.clear();await load(true)};
 await load();
}
document.addEventListener("DOMContentLoaded",init);
