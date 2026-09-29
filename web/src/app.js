import { hoursCycle } from './hours-cycle.js';
import { createIcons, Clock3, LayoutDashboard, ClipboardList, Settings2, CircleHelp, ChevronRight, ChevronDown, ChevronLeft, ArrowRight, ArrowDown, ArrowUpRight, RefreshCw, CalendarDays, Search, Download, FolderOpen, CheckCheck, ChartNoAxesColumnIncreasing, ShieldCheck, Info, X, Check, Sun, Moon, Menu, Building2, CircleCheck, SlidersHorizontal, ListFilter, MousePointer2, FileText, Plus, Trash2, ArrowLeft, AlertCircle, ExternalLink, LoaderCircle } from 'lucide';

const icons = {Clock3, LayoutDashboard, ClipboardList, Settings2, CircleHelp, ChevronRight, ChevronDown, ChevronLeft, ArrowRight, ArrowDown, ArrowUpRight, RefreshCw, CalendarDays, Search, Download, FolderOpen, CheckCheck, ChartNoAxesColumnIncreasing, ShieldCheck, Info, X, Check, Sun, Moon, Menu, Building2, CircleCheck, SlidersHorizontal, ListFilter, MousePointer2, FileText, Plus, Trash2, ArrowLeft, AlertCircle, ExternalLink, LoaderCircle};
const $ = s => document.querySelector(s);
const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name, cls='') => `<i data-lucide="${name}" class="${cls}" aria-hidden="true"></i>`;
const drawIcons = () => createIcons({icons});
const fmt = v => Number(v || 0).toLocaleString('zh-CN', {maximumFractionDigits:2});
const dayLabel = d => {const parts=d.split('-'); return `${parts[1]} 月 ${parts[2]} 日`;};
const weekday = d => ['周日','周一','周二','周三','周四','周五','周六'][new Date(`${d}T12:00:00+08:00`).getUTCDay()];
const shortDate = d => d?.replaceAll('-','.') ?? '';
const nowDate = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
const state = {profile:null,report:null,reportId:null,view:'workbench',tab:'public',selected:new Map(),targets:[{value:'',custom:''}],reason:'',search:'',page:1,busy:false,error:'',preview:null,creating:false,theme:'light',plans:[]};
let toastTimer;
let modalReturn;
let lastQuery;
let authTimer;
let authVersion=0;
let savedVersion=0;
let oaSaved={items:[],loading:false,error:'',checked:false};

let connection='checking';
let connectionEpoch=0;
function setConnection(value) {
  connection=value;
  const panel=$('#oa-connection');
  if(panel){panel.innerHTML=connectionPanel();drawIcons();}
}
function connectionPanel() {
  const connected=connection==='connected', missing=connection==='missing';
  return `<span class="connection-icon">${icon(connected?'shield-check':'building-2')}</span><h3>OA 登录管理</h3><p role="status">${connected?`<span class="status-badge green">已连接</span> ${e(state.profile.name)} · ${e(state.profile.employee_code)}`:missing?'未登录，请扫码连接 OA。':connection==='checking'?'正在检查 OA 登录状态…':'暂时无法确认连接状态，请重试。'}</p><p>${connected?'登录会话有效，可查询工时和管理调整流程。':'工作台使用独立的 OA 登录会话。'}</p>${missing?'<button class="btn btn-primary" data-action="oa-login">扫码登录 OA</button>':connection==='unknown'?'<button class="btn" data-action="check-saved">重新检查连接</button>':''}<div class="connection-clear"><button class="btn btn-clear-login" data-action="clear-login">${icon('trash-2')}清除登录态</button><p>账号数据保留，重新登录后恢复。</p></div>`;
}

let planTab='pending';
function flowCount(category) {return oaSaved.items.filter(item=>item.category===category).length;}
function savedFlowsPanel() {
  const message=oaSaved.loading?'正在检查已有流程…':oaSaved.error?'流程状态暂不可用，请到调整计划重试':oaSaved.checked?`审批中 ${flowCount('pending')} 条 · OA 已保存 ${flowCount('saved')} 条`:'登录后自动检查已有流程';
  return `<div class="flow-notice"><span class="flow-notice-icon">${icon('clipboard-list')}</span><div><strong>${e(message)}</strong><span>创建新调整前，可先核对已有流程。</span></div><button class="text-btn" data-action="view-flows">查看流程 ${icon('arrow-right')}</button></div>`;
}
function renderSavedFlows() {
  if($('#plan-count'))$('#plan-count').textContent=state.plans.length+oaSaved.items.length;
  const panel=$('#oa-saved-flows');
  if(panel){panel.innerHTML=savedFlowsPanel();drawIcons();}
  if(state.view==='plans')renderMain();
}
async function checkSavedFlows() {
  const version=++savedVersion;
  oaSaved={items:[],loading:true,error:'',checked:false};renderSavedFlows();
  try {
    const data=await api('/api/oa-saved',{});
    if(version!==savedVersion)return;
    oaSaved={items:data.items,loading:false,error:'',checked:true};
  } catch(err) {
    if(version!==savedVersion)return;
    if(connection==='checking')setConnection('unknown');
    oaSaved={items:[],loading:false,error:`调整流程检查失败：${err.message}`,checked:false};
  }
  renderSavedFlows();
}

async function api(path, body) {
  const epoch=connectionEpoch;
  const response = await fetch(path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if(epoch===connectionEpoch){
    if(data.code==='oa_login_required')setConnection('missing');
    else if(response.ok && (path==='/api/query'||path==='/api/oa-saved'||data.status==='authenticated'))setConnection('connected');
    else if(!response.ok && connection==='checking' && (path==='/api/query'||path==='/api/oa-saved'))setConnection('unknown');
  }
  if (!response.ok) throw new Error(data.error || '操作未完成，请重试');
  return data;
}
function toast(message) { clearTimeout(toastTimer);$('#toast').textContent=message;$('#toast').classList.add('show');toastTimer=setTimeout(()=>$('#toast').classList.remove('show'),4500); }
function destinations() { return state.targets.map(t=>t.value==='__custom'?t.custom.trim():t.value); }
function sumHours(values) { return values.reduce((sum,h)=>sum+Math.round(Number(h||0)*100),0)/100; }
function totalSelected() { return sumHours([...state.selected.values()].flat()); }
let selectedSources=null;
function defaultSources() {const name=state.profile?.public_project;return Number(state.report?.project_totals?.[name]||0)>0?[name]:[];}
function sourceProjects() {return selectedSources??defaultSources();}
function sourceProject() {return sourceProjects().join('、');}
function sourceHours(row) {return sumHours(sourceProjects().map(name=>row.hours[name]||0));}
function candidates() {return (state.report?.daily||[]).filter(row=>sourceHours(row)>0).map(row=>({date:row.date,hours:sourceHours(row)}));}
function selectSource(name,checked) {
  selectedSources=checked?[...new Set([...sourceProjects(),name])]:sourceProjects().filter(p=>p!==name);
  state.tab='public';state.search='';state.page=1;
  state.selected=new Map(candidates().map(row=>[row.date,initialAllocation(row.hours)]));
  state.targets.forEach(t=>{if(sourceProjects().includes(t.value==='__custom'?t.custom.trim():t.value)){t.value='';t.custom='';t.projectCheck=null;}});
  validationAttempted=false;renderMain();
}
function sameProject() { return state.profile.public_project === state.report?.public_project; }
function validTargets() { const names=destinations();return names.every(n=>n&&n.length<=180&&!sourceProjects().includes(n))&&new Set(names).size===names.length&&state.targets.every(t=>t.value!=='__custom'||(t.projectCheck?.name===t.custom.trim()&&t.projectCheck.status==='valid')); }
function validSelection() { return state.selected.size>0 && [...state.selected].every(([d,values])=>values.every(h=>Number.isFinite(Number(h))&&Number(h)>=0&&/^\d+(\.\d{1,2})?$/.test(String(h)))&&sumHours(values)>0&&sumHours(values)<=Number(candidates().find(r=>r.date===d)?.hours||0)); }
function canPreview() { return !state.busy && sameProject() && validSelection() && validTargets() && state.reason.trim(); }
function initialAllocation(hours) { return state.targets.map((_,i)=>i===0?hours:'0'); }
function allocationRows() { return [...state.selected].flatMap(([date,values])=>values.map((hours,i)=>({date,hours,target_project:destinations()[i]})).filter(r=>Number(r.hours)>0)); }
function planTargets(p) { return [...new Set(p.adjustments.map(r=>r.target_project||p.target_project))].join('、'); }
function planDays(p) { return new Set(p.adjustments.map(r=>r.date)).size; }
function renderPlan() { $('.plan-card').innerHTML=planPanel();updatePlanButton();drawIcons(); }
function readLocal(key, fallback) {try {return JSON.parse(localStorage.getItem(key)) ?? fallback;}catch{return fallback;}}
function persistPlans() {localStorage.setItem(`hours-plans-${state.profile.id}`, JSON.stringify(state.plans));}
function textDownload(filename, content, type) {
  const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function renderShell() {
  $('#app').innerHTML=`
    <div class="mobile-overlay" data-action="close-nav"></div>
    <aside class="sidebar" aria-label="侧边栏">
      <a class="brand" href="#" data-view="workbench" aria-label="时序工时工作台首页"><img src="/favicon.svg" alt=""><div><div class="brand-name">时序</div><div class="brand-sub">HOURS WORKSPACE</div></div></a>
      <div class="workspace-tag">${icon('building-2')}<span>个人工作空间</span></div>
      <div class="nav-caption">工作台</div>
      <nav aria-label="主导航">
        <button class="nav-item" data-view="workbench">${icon('layout-dashboard')}项目工时</button>
        <button class="nav-item" data-view="plans">${icon('clipboard-list')}调整计划<span class="nav-count" id="plan-count">${state.plans.length}</span></button>
      </nav>
      <div class="sidebar-bottom">
        <button class="nav-item" data-view="settings">${icon('settings-2')}个人设置</button>
        <button class="nav-item" data-action="help">${icon('circle-help')}使用指南${icon('arrow-up-right','ml-auto')}</button>
        <div class="sidebar-note"><strong>${icon('shield-check')}你的每一步，都可核对</strong><p>先查看工时，再整理计划。<br>预览后可创建 OA 草稿。</p></div>
        <div class="sidebar-footer"><span class="dot"></span>本地工作空间<span class="ml-auto">v0.1</span></div>
      </div>
    </aside>
    <div class="shell">
      <header class="topbar">
        <div class="breadcrumb"><button class="icon-btn mobile-menu" data-action="menu" aria-label="打开导航">${icon('menu')}</button><span class="root-crumb">工作空间</span>${icon('chevron-right')}<strong id="breadcrumb-name">项目工时</strong></div>
        <div class="top-actions"><button class="icon-btn" data-action="help" aria-label="查看使用指南">${icon('circle-help')}</button><button class="icon-btn" id="theme-button" data-action="theme" aria-label="切换深色模式">${icon(state.theme==='dark'?'sun':'moon')}</button><button class="user" data-view="settings"><span class="avatar">${e(state.profile.name.slice(-2,-1) || state.profile.name.slice(0,1))}</span><span class="user-name">${e(state.profile.name)}</span>${icon('chevron-down')}</button></div>
      </header>
      <main id="main" tabindex="-1"></main>
    </div>`;
  renderMain();
}
function heading(title, desc, action='') {
  return `<div class="page-heading"><div><div class="eyebrow">${state.view==='workbench'?'工时分配':state.view==='plans'?'流程管理':'工作空间'}</div><h1>${title}</h1><p>${desc}</p></div>${action}</div>`;
}
function renderMain() {
  document.querySelectorAll('.nav-item[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===state.view);b.setAttribute('aria-current',b.dataset.view===state.view?'page':'false');});
  $('#breadcrumb-name').textContent={workbench:'项目工时',plans:'调整计划',settings:'个人设置'}[state.view];
  $('#plan-count').textContent=state.plans.length+oaSaved.items.length;
  $('#main').innerHTML=state.view==='workbench'?workbench():state.view==='plans'?plansView():settingsView();
  if(state.view==='workbench') {renderTable();updatePlanButton();}
  drawIcons();
}
function workbench() {
  const r=state.report;
  const queryTime=r?.queried_at?new Intl.DateTimeFormat('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(r.queried_at)):'';
  const action=`<div class="heading-actions"><span class="sync-time">${icon('clock-3')}上次查询 ${queryTime || '—'}</span><button class="btn btn-primary" data-action="refresh" ${state.busy?'disabled':''}>${icon('refresh-cw',state.busy?'spinning':'')}<span>${state.busy?'正在查询…':'刷新工时'}</span></button></div>`;
  let html=heading('项目工时','选择调出项目，按实际投入重新分配工时。',action);
  html+=`<div id="oa-saved-flows">${savedFlowsPanel()}</div>`;
  if(state.error) html+=`<div class="query-error flex-wrap" role="alert">${icon('alert-circle')}<span><strong>工时查询失败</strong><br>${e(state.error)}<br>工作台需要单独扫码登录；在其他浏览器登录 OA 不会同步到这里。${r?'当前显示上次查询结果。':''}</span><div class="flex flex-wrap gap-2"><button class="btn btn-small" data-action="oa-login">扫码登录 OA</button><button class="btn btn-small" data-action="retry-query">重试查询 ${icon('refresh-cw')}</button></div><button class="icon-btn" data-action="clear-error" aria-label="关闭提示">${icon('x')}</button></div>`;
  if(!r) return html+`<div class="card empty-state">${icon('calendar-days')}<strong>从一次工时查询开始</strong><p>选择日期范围，读取当前 OA 账号的个人工时。</p><button class="btn btn-primary" data-action="date">选择日期并查询</button></div>`;
  if(!sameProject()) html+=`<div class="query-error">${icon('info')}<span>公共项目已更新为 ${e(state.profile.public_project)}。刷新工时后即可按新项目整理计划。</span></div>`;
  html+=`<section class="card source-picker"><strong>调出项目 · 可多选</strong><div class="source-options">${Object.keys(r.project_totals).filter(p=>p!=='合计').map(p=>`<label><input type="checkbox" data-source-project="${e(p)}" ${sourceProjects().includes(p)?'checked':''} ${state.busy?'disabled':''}><span>${e(p)}</span><small>${fmt(r.project_totals[p])} h</small></label>`).join('')}</div><p>按日期汇总可调工时；部分调出时，按当天各来源工时占比分摊，精确到 0.01 小时。预览可核对每个来源。</p></section>`;
  const total=Number(r.project_totals['合计'] || 0), pub=candidates().reduce((s,x)=>s+Number(x.hours),0), assigned=total-pub;
  const days=r.daily.filter(d=>Number(d.hours['合计'])>0).length;
  const ratio=total?assigned/total*100:0;
  html+=`<section class="metrics" aria-label="工时概览">
    <div class="metric"><div class="metric-label">区间总工时<span class="metric-icon">${icon('clock-3')}</span></div><div class="metric-value"><strong class="num">${fmt(total)}</strong><span>小时</span></div><div class="metric-foot">${icon('calendar-days','!w-3 !h-3')}有工时记录 ${days} 天</div></div>
    <div class="metric public"><div class="metric-label">所选来源工时<span class="metric-icon">${icon('folder-open')}</span></div><div class="metric-value"><strong class="num">${fmt(pub)}</strong><span>小时</span></div><div class="metric-foot"><span class="tag">${candidates().length} 天</span>可查看调整候选</div></div>
    <div class="metric"><div class="metric-label">其他项目工时<span class="metric-icon green">${icon('check-check')}</span></div><div class="metric-value"><strong class="num">${fmt(assigned)}</strong><span>小时</span></div><div class="metric-foot"><span class="mini-progress"><i style="width:${ratio}%"></i></span><span>占总工时 ${fmt(ratio)}%</span></div></div>
  </section>`;
  const cycle=hoursCycle(r.end_date);
  html+=`<p class="helper">${cycle.start===r.start_date&&cycle.end===r.end_date?e(cycle.label)+' · ':''}${e(r.start_date)} 至 ${e(r.end_date)} · 工时周期按上月 25 日至本月 24 日计算</p>`;
  html+=chart();
  html+=`<div class="workspace"><div class="min-w-0"><section class="card records" aria-label="工时记录"><div class="records-head"><div class="records-title-row"><h2><span class="step-tag">01</span> 核对并选择工时</h2><button class="text-btn" data-action="export-csv">${icon('download')}导出记录</button></div><div class="tabs" role="tablist" aria-label="工时类型"><button class="tab ${state.tab==='public'?'active':''}" role="tab" aria-selected="${state.tab==='public'}" data-tab="public">项目工时<span class="count">${candidates().length}</span></button><button class="tab ${state.tab==='all'?'active':''}" role="tab" aria-selected="${state.tab==='all'}" data-tab="all">全部记录<span class="count">${allRows().length}</span></button></div></div><div class="filter-row"><label class="search">${icon('search')}<span class="sr-only">搜索日期或项目</span><input id="record-search" type="search" placeholder="搜索日期或项目" value="${e(state.search)}"></label><button class="btn date-button" data-action="date">${icon('calendar-days')}<span>${e(r.start_date.slice(5).replace('-','.'))} — ${e(r.end_date.slice(5).replace('-','.'))}</span>${icon('chevron-down')}</button></div><div id="table-content"></div></section><div class="notice">${icon('info')}<span>仅可调出所选项目的已有工时；请同时核对已有调整流程，避免重复调整。</span></div></div><aside class="card plan-card" aria-label="新建调整计划">${planPanel()}</aside></div>`;
  html+=`<footer class="bottom-caption"><span>${icon('circle-check')}来源：OA 个人工时报表 · ${e(shortDate(r.start_date))} — ${e(shortDate(r.end_date))}</span><span>填写从核对开始，每一小时都有据可查。</span></footer>`;
  return html;
}
function chart() {
  const daily=state.report.daily;
  if(daily.length>62) return `<section class="card activity"><div class="card-head"><h2>区间工时分布</h2><button class="text-btn" data-action="date">缩小日期范围查看逐日图表 ${icon('arrow-right')}</button></div><p class="helper">当前区间 ${daily.length} 天，可在下方查看和筛选全部明细。</p></section>`;
  const max=Math.max(8,...daily.map(d=>Number(d.hours['合计'])));
  return `<section class="card activity" aria-label="逐日工时分布"><div class="card-head"><h2>工时分布<span class="sub">${e(state.report.start_date)} 至 ${e(state.report.end_date)} · 点击项目工时柱选择日期</span></h2><div class="legend"><span><i class="public-dot"></i>公共项目</span><span><i class="assigned-dot"></i>正式工时</span><span><i class="missing-dot"></i>未填工时</span></div></div><div class="chart"><div class="chart-axis"><span>${fmt(max)}h</span><span>0</span></div><div class="chart-bars">${daily.map(d=>{
    const pub=Number(d.hours[state.report.public_project]||0), other=Math.max(0,Number(d.hours['合计'])-pub),missing=Number(d.calendar?.missing_hours||0),chosen=state.selected.has(d.date);
    const label=`${d.date}：公共项目 ${fmt(pub)} 小时，正式工时 ${fmt(other)} 小时，${d.calendar?.known?`未填 ${fmt(missing)} 小时 · ${d.calendar.label}${d.calendar.future?'（未来日期）':''}`:'日历未知，未判断缺填'}`;
    return `<button class="bar-wrap ${chosen?'chosen':''}" data-chart-date="${d.date}" aria-label="${label}${sourceHours(d)?'，选择调整':'，查看明细'}" title="${label}"><span class="bar-space">${missing?`<span class="bar missing-bar" style="height:${missing/max*100}%"></span>`:''}${pub?`<span class="bar public-bar" style="height:${pub/max*100}%"></span>`:''}${other?`<span class="bar" style="height:${other/max*100}%"></span>`:''}${!other&&!pub&&!missing?'<span class="bar empty"></span>':''}</span><span class="bar-day num">${d.date.slice(8)}</span></button>`;
  }).join('')}</div></div><p class="helper">工作日应填 8 小时，按法定节假日及调休判断；未来日期不计缺填。${state.report.calendar_info?.unknown_years?.length?'部分年份日历未配置，暂不标记未填工时。':''}</p></section>`;
}
function allRows() {
  if(!state.report) return [];
  return state.report.daily.flatMap(r=>Object.entries(r.hours).filter(([name,h])=>name!=='合计'&&Number(h)>0).map(([name,h])=>({date:r.date,project:name,hours:h})));
}
function tableRows() {
  const rows=state.tab==='public'?candidates().map(r=>({...r,project:sourceProject()})):allRows();
  const q=state.search.toLowerCase().trim();
  return q?rows.filter(r=>`${r.date} ${r.project}`.toLowerCase().includes(q)):rows;
}
function renderTable() {
  const container=$('#table-content');if(!container) return;
  const rows=tableRows(),pages=Math.max(1,Math.ceil(rows.length/8));state.page=Math.min(state.page,pages);
  const show=rows.slice((state.page-1)*8,state.page*8),selectable=show.filter(r=>(r.project===sourceProject()||sourceProjects().includes(r.project)));
  const allChecked=selectable.length>0&&selectable.every(r=>state.selected.has(r.date));
  container.innerHTML=`<div class="table-scroll"><table class="hours-table"><thead><tr><th><input type="checkbox" id="select-page" aria-label="选择本页项目工时" ${allChecked?'checked':''} ${state.busy||!sameProject()||!selectable.length?'disabled':''}></th><th>日期</th><th>项目名称</th><th>工时</th><th class="status-col">归属</th></tr></thead><tbody>${show.map(r=>{
    const pub=(r.project===sourceProject()||sourceProjects().includes(r.project));
    return `<tr class="${pub&&state.selected.has(r.date)?'selected':''}"><td>${pub?`<input type="checkbox" data-row-date="${r.date}" aria-label="选择 ${r.date} 的 ${fmt(r.hours)} 小时" ${state.selected.has(r.date)?'checked':''} ${state.busy||!sameProject()?'disabled':''}>`:'<span class="muted">—</span>'}</td><td><div class="date-cell"><strong class="num">${dayLabel(r.date)}</strong><span>${weekday(r.date)}</span></div></td><td><span class="project-cell"><span class="project-symbol ${pub?'':'assigned'}">${icon(pub?'folder-open':'check')}</span>${e(r.project)}</span></td><td><span class="hours-value num">${fmt(r.hours)}<small>h</small></span></td><td class="status-col"><span class="status-badge ${pub?'':'green'}"><i></i>${pub?'调出项目':'其他项目'}</span></td></tr>`;
  }).join('')}</tbody></table>${!show.length?`<div class="empty-state">${icon(state.search?'search':'circle-check')}<strong>${state.search?'没有匹配的记录':'这段时间没有项目工时'}</strong><p>${state.search?'尝试其他日期或项目关键词。':'可以调整日期范围，或查看全部项目的工时记录。'}</p></div>`:''}</div><div class="table-footer"><span>共 ${rows.length} 条记录${state.selected.size?` · 已选 ${state.selected.size} 天`:''}</span><div class="pagination"><button data-action="prev-page" aria-label="上一页" ${state.page===1?'disabled':''}>${icon('chevron-left')}</button><span class="num">${state.page} / ${pages}</span><button data-action="next-page" aria-label="下一页" ${state.page===pages?'disabled':''}>${icon('chevron-right')}</button></div></div>`;
  const cb=$('#select-page');if(cb)cb.indeterminate=!allChecked&&selectable.some(r=>state.selected.has(r.date));
  drawIcons();
}
const reasonSuggestions=[
  ['忘填工时','因未及时填写工时，相关工时已计入公共项目，现按实际工作归属补充调整。'],
  ['按实际项目归属调整','将已计入公共项目的工时，按实际工作归属调整至对应项目。'],
  ['项目立项后补录','项目立项前工时暂记公共项目，现补录至正式项目。'],
  ['多项目工时分摊','根据实际参与各项目的工作情况，将项目工时分摊至对应项目。'],
  ['修正工时归属','原工时归属填写有误，现调整至实际投入的项目。'],
  ['工时迷路了','工时在公共项目里迷了路，现将其领回实际工作的项目。', 'fun'],
  ['人到了，工时没到','人已经在项目里干活了，工时还在公共项目门口排队，现办理入场。', 'fun'],
  ['记忆力请假了','活干了，工时忘填了，当天记忆力疑似请假，现补上项目归属。', 'fun'],
  ['工时认祖归宗','这几笔工时在公共项目暂住已久，现按实际工作归属认祖归宗。', 'fun'],
  ['量子工时','工时此前处于“干了但没填”的叠加态，现经本人观测，坍缩至实际工作的项目。', 'fun'],
];
function planPanel() {
  const projects=Object.keys(state.report?.project_totals||{}).filter(x=>x!=='合计'&&!sourceProjects().includes(x));
  return `<div class="plan-title"><div><h2><span class="step-tag">02</span> 整理调整计划</h2><p>添加实际归属项目，再按日期分配工时。</p></div><span>保存草稿 · 不提交审批</span></div>
  <div class="plan-content"><div class="plan-setup"><div class="transfer-source"><div class="transfer-label">${icon('folder-open')}从选定项目调出</div><div class="transfer-project">${e(sourceProject())}</div><div class="source-bottom"><span>${e(state.profile.name)}的调出项目</span></div></div>
  <div class="destinations-section"><div class="section-heading"><h3>调入项目</h3><button class="btn btn-small" data-action="add-target">+ 添加调入项目</button></div><div class="destination-grid">${state.targets.map((t,i)=>`<div class="field destination-card"><label for="target-project-${i}">项目 ${i+1}${state.targets.length>1?`<button class="text-btn" data-remove-target="${i}" aria-label="移除调入项目 ${i+1}">移除</button>`:''}</label><select id="target-project-${i}" data-target="${i}"><option value="">选择目标项目</option>${projects.map(p=>`<option value="${e(p)}" ${t.value===p?'selected':''}>${e(p)}</option>`).join('')}<option value="__custom" ${t.value==='__custom'?'selected':''}>其他项目…</option></select>${t.value==='__custom'?`<input class="mt-2" data-custom-target="${i}" aria-label="调入项目 ${i+1} 完整名称" placeholder="输入项目关键词，搜索 OA 项目" value="${e(t.custom)}">`:''}</div>`).join('')}</div></div></div>
  <div class="plan-amounts"><div class="section-heading allocation-heading"><div><h3>按日期分配工时</h3><p class="helper">平均分配保留每天当前调出总量；余数按 0.01 小时依次分配。</p></div><button id="average-button" class="btn" data-action="average-hours">平均调入工时</button></div><div id="quantity-area">${quantityArea()}</div></div>
  <div class="plan-finish"><div class="field"><label for="plan-reason">申请原因<span>必填</span></label><textarea id="plan-reason" maxlength="4000" placeholder="说明这部分工时的实际归属…">${e(state.reason)}</textarea><div class="reason-suggestions" hidden role="group" aria-label="申请原因候选"><span>按实际情况选择，可继续编辑</span><div>${reasonSuggestions.map(([label,,kind],i)=>kind!=='fun'?`<button type="button" class="reason-chip" data-reason-suggestion="${i}">${e(label)}</button>`:'').join('')}<div class="reason-fun-group" role="group" aria-label="搞怪原因">${reasonSuggestions.map(([label,,kind],i)=>kind==='fun'?`<button type="button" class="reason-chip" data-reason-suggestion="${i}">${e(label)}</button>`:'').join('')}</div></div></div></div><div class="plan-submit"><div class="selected-summary"><span>本次调整 <span id="selected-days" class="muted">${state.selected.size} 天</span></span><span><strong id="selected-hours" class="num">${fmt(totalSelected())}</strong><small>小时</small></span></div><p id="plan-error" class="error-text" role="status"></p><button id="preview-button" class="btn btn-primary" data-action="preview" ${state.busy||previewing?'disabled':''}>生成调整预览 ${icon('arrow-right')}</button><p class="plan-footnote">预览核对后，可创建 OA 草稿</p></div></div></div>`;
}
function quantityArea() {
  if(!state.selected.size)return `<div class="selection-prompt">${icon('mouse-pointer-2')}从上方明细中选择要调整的日期</div>`;
  return `<div class="allocation-scroll" role="region" aria-label="每日工时分配表，可横向滚动" tabindex="0"><table class="allocation-table"><thead><tr><th scope="col">日期</th><th scope="col">可调工时</th>${state.targets.map((t,i)=>`<th scope="col"><span>项目 ${i+1}</span><strong data-project-heading="${i}">${e(destinations()[i]||'待选择项目')}</strong></th>`).join('')}<th scope="col">调出合计</th></tr></thead><tbody>${[...state.selected].sort().map(([d,values])=>`<tr><th scope="row">${dayLabel(d)}<small>${weekday(d)}</small></th><td class="num">${fmt(candidates().find(r=>r.date===d).hours)} h</td>${state.targets.map((t,i)=>`<td><input type="number" aria-label="${d} 项目 ${i+1} 小时数" data-quantity="${d}" data-allocation="${i}" value="${e(values[i])}" min="0" max="${e(candidates().find(r=>r.date===d).hours)}" step="0.01"></td>`).join('')}<td class="num" data-day-total="${d}">${fmt(sumHours(values))} h</td></tr>`).join('')}</tbody></table></div>`;
}
function averageHours() {
  if(state.busy||!sameProject()||!validSelection())return;
  const count=state.targets.length;
  state.selected.forEach((values,day)=>{
    const cents=Math.round(sumHours(values)*100), base=Math.floor(cents/count), remainder=cents%count;
    state.selected.set(day,state.targets.map((_,i)=>((base+(i<remainder?1:0))/100).toFixed(2)));
  });
  selectionChanged();
  toast('已平均分配到各项目，每天调出总量保持不变');
}
let validationAttempted=false;
let previewing=false;
function fieldError(el, message, id) {
  if(!el)return;
  let hint=document.getElementById(id);
  if(!hint){hint=document.createElement('p');hint.id=id;hint.className='field-error';el.insertAdjacentElement('afterend',hint);}
  hint.textContent=message;hint.hidden=!message;
  el.setAttribute('aria-invalid',String(Boolean(message)));
  el.setAttribute('aria-describedby',id);
}
const projectTimers=new WeakMap();
function scheduleProjectCheck(target, immediate=false) {
  clearTimeout(projectTimers.get(target));
  const name=target.custom.trim();
  if(target.value!=='__custom'||!name||name.length>180||sourceProjects().includes(name)){target.projectCheck=null;updatePlanButton();return;}
  const check={name,status:'checking',message:'正在查询 OA 项目…'};
  target.projectCheck=check;updatePlanButton();
  projectTimers.set(target,setTimeout(async()=>{
    try {
      const result=await api('/api/projects/search',{name});
      if(target.projectCheck!==check)return;
      check.matches=result.items;check.total=result.total;
      const exact=result.items.filter(item=>item.name===name);
      if(exact.length===1&&result.total<=result.items.length){check.status='valid';check.message='已在 OA 中匹配到项目';}
      else {check.status='invalid';check.message=result.items.length?'请选择下方匹配的完整项目名称。':'未找到匹配项目，请更换关键词。';}

    } catch(err) {
      if(target.projectCheck!==check)return;
      check.status='invalid';check.message=err.message;
    }
    if(state.targets.includes(target))updatePlanButton();
  },immediate?0:600));
}
function validatePlanFields() {
  const names=destinations();
  names.forEach((name,i)=>{
    const duplicate=name&&names.some((other,j)=>i!==j&&other===name);
    let message=duplicate?'调入项目重复，请选择其他项目。':sourceProjects().includes(name)?'调入项目不能与调出项目相同。':validationAttempted&&!name?'请选择或填写调入项目。':validationAttempted&&name.length>180?'项目名称不能超过 180 个字符。':'';
    const select=$(`#target-project-${i}`),custom=$(`[data-custom-target="${i}"]`);
    const check=state.targets[i].projectCheck;
    if(custom&&!message){
      if(check?.name===name&&check.status==='invalid')message=check.message;
      else if(validationAttempted&&name&&(!check||check.name!==name||check.status==='checking'))message='请等待 OA 项目校验通过后再预览。';
    }
    fieldError(custom||select,message,`target-error-${i}`);
    if(custom){
      let status=document.getElementById(`project-status-${i}`);
      if(!status){status=document.createElement('p');status.id=`project-status-${i}`;status.className='helper';status.setAttribute('role','status');custom.parentElement.appendChild(status);}
      status.textContent=check?.name===name&&check.status!=='invalid'?check.message:'';
      let results=document.getElementById(`project-results-${i}`);
      if(!results){results=document.createElement('div');results.id=`project-results-${i}`;results.className='project-results';results.setAttribute('role','group');results.setAttribute('aria-label','匹配的 OA 项目');custom.parentElement.appendChild(results);}
      const matches=check?.name===name&&check.status!=='valid'?(check.matches||[]):[];
      results.hidden=!matches.length;
      results.innerHTML=matches.slice(0,20).map((item,j)=>{
        const blocked=sourceProjects().includes(item.name)||names.some((other,k)=>k!==i&&other===item.name);
        return `<button type="button" data-project-pick="${i}" data-match-index="${j}" ${blocked?'disabled':''}><strong>${e(item.name)}</strong><small>${e(item.code)}${blocked?' · 已选为调出或调入项目':''}</small></button>`;
      }).join('')+(matches.length>20||check?.total>matches.length?`<p class="helper">共 ${e(check.total)} 个匹配，当前展示 ${Math.min(matches.length,20)} 个，请输入更具体的关键词。</p>`:'');

    }
    if(custom&&select)select.setAttribute('aria-invalid',String(Boolean(message)));
    if(select)Array.from(select.options).forEach(option=>{option.disabled=option.value!==''&&option.value!=='__custom'&&names.some((other,j)=>j!==i&&other===option.value);});
  });
  fieldError($('#plan-reason'),validationAttempted&&!state.reason.trim()?'申请原因不能为空。':'','reason-error');
  const suggestions=$('.reason-suggestions');
  if(suggestions)suggestions.hidden=!(validationAttempted&&!state.reason.trim());
  for(const [day,values] of state.selected){
    const max=Number(candidates().find(r=>r.date===day)?.hours||0),total=sumHours(values);
    values.forEach((value,i)=>{
      let message='';
      if(validationAttempted){
        if(!/^\d+(\.\d{1,2})?$/.test(String(value))||!Number.isFinite(Number(value))||Number(value)<0)message='请输入非负工时，最多两位小数。';
        else if(total>max)message=`当天合计不能超过 ${fmt(max)} 小时。`;
        else if(total<=0)message='当天调出合计必须大于 0。';
      }
      fieldError($(`[data-quantity="${day}"][data-allocation="${i}"]`),message,`hours-error-${day}-${i}`);
    });
  }
  let message='';
  if(validationAttempted){
    if(!sameProject())message='公共项目已变更，请先重新查询工时。';
    else if(!state.selected.size)message='请先勾选至少一天项目工时。';
    else if(!validSelection()||!validTargets()||!state.reason.trim())message='请修正标红的填写项后再生成预览。';
  }
  if($('#plan-error'))$('#plan-error').textContent=message;
  const area=$('#quantity-area');if(area)area.classList.toggle('selection-invalid',validationAttempted&&!state.selected.size);
}
function updatePlanButton() {
  document.querySelectorAll('[data-day-total]').forEach(el=>el.textContent=`${fmt(sumHours(state.selected.get(el.dataset.dayTotal)||[]))} h`);
  document.querySelectorAll('[data-project-heading]').forEach(el=>el.textContent=destinations()[Number(el.dataset.projectHeading)]||'待选择项目');
  const average=$('#average-button');if(average)average.disabled=state.busy||!sameProject()||!validSelection();
  const btn=$('#preview-button');if(btn)btn.disabled=state.busy||previewing;
  if($('#selected-days'))$('#selected-days').textContent=`${state.selected.size} 天`;
  if($('#selected-hours'))$('#selected-hours').textContent=fmt(totalSelected());
  validatePlanFields();
}
function selectionChanged(focusDate) {
  renderTable();$('#quantity-area').innerHTML=quantityArea();updatePlanButton();
  document.querySelectorAll('[data-chart-date]').forEach(b=>b.classList.toggle('chosen',state.selected.has(b.dataset.chartDate)));
  if(focusDate)document.querySelector(`[data-row-date="${focusDate}"]`)?.focus();drawIcons();
}
function settingsView() {
  if(!state.profile.id)return heading('个人设置','扫码登录后自动识别员工身份。')+`<div class="settings-layout"><section class="card empty-state"><span class="connection-icon">${icon('shield-check')}</span><strong>尚未登录 OA</strong><p>登录后显示你的姓名、部门与默认调出项目。已有个人配置会在登录同一账号后恢复。</p></section><aside class="settings-tip"><section class="card connection-card" id="oa-connection">${connectionPanel()}</section></aside></div>`;
  return heading('个人设置','公共项目因人而异，使用与你对应的项目。')+`<div class="settings-layout"><section class="card settings-card"><h2>我的工时配置</h2><div class="profile-summary"><span class="avatar">${e(state.profile.name.slice(0,1))}</span><div><strong>${e(state.profile.name)}</strong><p>${e(state.profile.employee_code)} · ${e(state.profile.department)}</p></div><span class="status-badge green ml-auto">当前用户</span></div><form id="profile-form"><div class="field"><label for="public-project">默认调出项目（个人公共项目）</label><input id="public-project" value="${e(state.profile.public_project)}" required maxlength="180"><p class="helper">请填写 OA 中的完整项目名称。修改后，需重新查询工时。</p></div><div class="field"><label for="profile-identity">查询账号</label><input id="profile-identity" value="${e(state.profile.name)}（${e(state.profile.employee_code)}）" disabled><p class="helper">查询时会核对 OA 当前登录身份与此账号是否一致。</p></div><p id="settings-error" class="error-text" role="alert"></p><button class="btn btn-primary" type="submit" ${state.busy?'disabled':''}>保存个人配置 ${icon('check')}</button></form></section><aside class="settings-tip"><section class="card connection-card" id="oa-connection">${connectionPanel()}</section><h3>为什么需要公共项目？</h3><p>公共项目仅作为默认调出项目，也可在工时页选择其他已有工时的项目进行调整。</p><p>每位员工的公共项目独立配置。更换项目不会修改任何已记录工时。</p><button class="text-btn" data-action="help">查看完整操作指南 ${icon('arrow-right')}</button></aside></div>`;
}
function localPlansView() {
  return (state.plans.length?`<div class="plan-list">${state.plans.map((p,i)=>`<article class="card saved-plan"><span class="saved-plan-icon">${icon('file-text')}</span><div class="saved-plan-content"><h3>${e(planTargets(p))}</h3><p>${e(p.adjustments[0].date)}${p.adjustments.length>1?' — '+e(p.adjustments.at(-1).date):''} · ${planDays(p)} 天 · 本地预览</p></div><div class="saved-plan-total num">${fmt(p.total_hours)} <small>h</small></div><button class="btn btn-small" data-saved-preview="${i}">查看预览 ${icon('arrow-right')}</button><button class="icon-btn" data-remove-plan="${i}" aria-label="删除 ${e(planTargets(p))} 的本地计划">${icon('trash-2')}</button></article>`).join('')}</div>`:`<div class="card empty-state !py-20">${icon('clipboard-list')}<strong>还没有保存的调整计划</strong><p>选择项目工时、填写目标项目和原因，预览后可保存在本机或创建 OA 草稿。</p><button class="btn btn-primary" data-view="workbench">从项目工时开始 ${icon('arrow-right')}</button></div>`);
}
function plansView() {
  const tabs=[['pending','审批中',flowCount('pending')],['saved','OA 已保存',flowCount('saved')],['local','本地计划',state.plans.length]];
  const intro=heading('调整计划','从本地计划到 OA 流程，在这里跟进每一次调整。',`<button class="btn btn-primary" data-view="workbench">${icon('plus')}整理新计划</button>`);
  const nav=`<div class="flow-toolbar"><div class="flow-tabs" aria-label="流程分类">${tabs.map(([key,label,count])=>`<button data-plan-tab="${key}" aria-pressed="${planTab===key}" class="${planTab===key?'active':''}">${label}<span>${key==='local'||oaSaved.checked?count:'—'}</span></button>`).join('')}</div><button class="btn btn-small" data-action="check-saved" ${oaSaved.loading?'disabled':''}>${icon('refresh-cw',oaSaved.loading?'spinning':'')}刷新流程</button></div>`;
  if(planTab==='local')return intro+nav+`<p class="flow-description">保存在当前浏览器，尚未创建 OA 表单。</p>`+localPlansView();
  const description=planTab==='pending'?'已提交、尚未归档的流程。查看当前节点，继续跟进审批。':'处于创建节点的 OA 表单。打开后核对明细，再决定是否提交。';
  if(oaSaved.loading)return intro+nav+`<div class="card empty-state" role="status">${icon('loader-circle','spinning')}正在读取 OA 流程…</div>`;
  if(oaSaved.error)return intro+nav+`<div class="card empty-state" role="alert">${icon('alert-circle')}<strong>暂时无法读取流程</strong><p>${e(oaSaved.error)}</p><button class="btn" data-action="oa-login">扫码登录 OA</button></div>`;
  const items=oaSaved.items.filter(item=>item.category===planTab);
  return intro+nav+`<p class="flow-description">${description} 查询范围为全部日期。</p>`+(items.length?`<div class="flow-list">${items.map(item=>`<article class="card flow-item"><div class="flow-item-icon">${icon(planTab==='pending'?'clock-3':'file-text')}</div><div class="flow-item-main"><span class="flow-id">#${e(item.request_id)}</span><h2>${e(item.title)}</h2><p>创建于 ${e(item.created_at)}</p></div><div class="flow-node"><span>${planTab==='pending'?'当前审批节点':'当前节点'}</span><strong class="status-badge ${planTab==='pending'?'amber':'green'}">${e(item.node)}</strong></div><a class="btn btn-small" href="${e(item.url)}" target="_blank" rel="noopener noreferrer">打开表单 ${icon('arrow-up-right')}</a></article>`).join('')}</div>`:`<div class="card empty-state flow-empty">${icon(planTab==='pending'?'check-check':'folder-open')}<strong>${planTab==='pending'?'暂无审批中的调整':'暂无已保存的 OA 表单'}</strong><p>${planTab==='pending'?'新提交的调整流程会显示在这里。':'在项目工时页整理调整，预览后即可创建 OA 草稿。'}</p><button class="btn" data-view="workbench">前往项目工时 ${icon('arrow-right')}</button></div>`);
}
function openModal(title, subtitle, body, footer='') {
  modalReturn=document.activeElement;
  $('#modal').innerHTML=`<header class="modal-head"><div><h2 id="modal-title">${title}</h2><p>${subtitle}</p></div><button class="icon-btn" data-action="close-modal" aria-label="关闭弹窗">${icon('x')}</button></header><div class="modal-body">${body}</div><footer class="modal-foot">${footer}</footer>`;
  if(!$('#modal').open)$('#modal').showModal();drawIcons();
}
function closeModal() {if(state.creating){toast('正在创建 OA 表单，请等待结果');return;}$('#modal').close();if(modalReturn?.isConnected)modalReturn.focus();}
async function loginModal() {
  clearTimeout(authTimer);
  const version=++authVersion;
  openModal('连接工作台与 OA','请用飞书扫码，为当前工时工作台登录。',
    `<div class="text-center"><p id="auth-message" role="status" class="mb-4">正在准备登录二维码…</p><img id="auth-qr" alt="请用飞书扫描此二维码登录工作台的 OA 会话" hidden style="width:240px;max-width:100%;margin:0 auto;padding:12px;background:white;image-rendering:pixelated"><p class="helper mt-4">此登录与 Windows Chrome 中的 OA 登录独立。完成后会自动重新查询工时。</p></div>`,
    `<button class="btn" data-action="close-modal">关闭</button><button class="btn btn-primary" data-action="oa-login" id="auth-refresh" disabled>刷新二维码</button>`);
  const deadline=Date.now()+10*60*1000;
  async function poll(start) {
    try {
      const data=await api(start?'/api/auth/start':'/api/auth/status',{});
      if(version!==authVersion || !$('#modal').open || !$('#auth-message'))return;
      $('#auth-refresh').disabled=false;
      $('#auth-message').textContent=data.message;
      if(data.status==='authenticated'){
        closeModal();
        connectionEpoch++;savedVersion++;
        const previousId=state.profile.id;
        if(data.profile)state.profile=data.profile;
        if(previousId!==state.profile.id){
          state.report=null;state.reportId=null;state.selected.clear();state.targets=[{value:'',custom:''}];state.reason='';state.preview=null;selectedSources=null;lastQuery=null;
          state.plans=readLocal(`hours-plans-${state.profile.id}`,[]);oaSaved={items:[],loading:false,error:'',checked:false};
        }
        renderShell();setConnection('connected');
        if(!state.profile.public_project){navigate('settings');toast('已识别你的 OA 账号，请先填写个人公共项目');void checkSavedFlows();return;}
        toast('OA 登录成功，正在重新查询');
        void checkSavedFlows();
        const today=nowDate();
        await refresh(lastQuery?.start || state.report?.start_date || hoursCycle(today).start,lastQuery?.end || state.report?.end_date || hoursCycle(today).end);
        return;
      }
      if(data.qr?.startsWith('data:image/png;base64,')){$('#auth-qr').src=data.qr;$('#auth-qr').hidden=false;}
      else $('#auth-qr').hidden=true;
      if(data.status==='waiting' && Date.now()<deadline)authTimer=setTimeout(()=>poll(false),2500);
      else if(data.status==='waiting')$('#auth-message').textContent='登录等待已超时，请刷新二维码。';
    } catch(err) {
      if(version!==authVersion || !$('#auth-message'))return;
      $('#auth-message').textContent=err.message;$('#auth-refresh').disabled=false;
    }
  }
  await poll(true);
}
function dateModal() {
  const today=nowDate(), start=state.report?.start_date||hoursCycle(today).start,end=state.report?.end_date||hoursCycle(today).end;
  openModal('选择查询日期','工时周期：上月 25 日至本月 24 日，以结束月份命名。',`<div class="range-presets"><button class="btn btn-small" data-range="current">本月工时周期</button><button class="btn btn-small" data-range="previous">上月工时周期</button><button class="btn btn-small" data-range="recent">最近 7 天</button></div><form id="range-form"><div class="field"><label for="cycle-month">选择工时周期月份</label><input id="cycle-month" type="month" value="${hoursCycle(end).start===start&&hoursCycle(end).end===end?end.slice(0,7):''}"><p class="helper">选择月份后自动填入上月 25 日至所选月份 24 日，也可自定义下方日期。</p></div><div class="range-fields"><div class="field"><label for="range-start">开始日期</label><input id="range-start" type="date" value="${start}" required></div><div class="field"><label for="range-end">结束日期</label><input id="range-end" type="date" value="${end}" required></div></div><p id="range-error" class="error-text" role="alert"></p><p class="helper">查询将读取当前 OA 账号的工时，保留已有的本地计划。</p></form>`,`<button class="btn" data-action="close-modal">取消</button><button class="btn btn-primary" type="submit" form="range-form">查询工时 ${icon('arrow-right')}</button>`);
}
function helpModal() {
  openModal('从项目工时，到清晰的调整计划','可在有工时记录的项目之间重新分配工时。',`<div class="help-step"><span class="step-number">1</span><div><h3>核对调出项目与工时</h3><p>选择日期查询工时，再选择调出项目。登录过期时，在工作台扫码登录。</p></div></div><div class="help-step"><span class="step-number">2</span><div><h3>选择日期和目标项目</h3><p>勾选项目工时记录，可按天修改本次调整小时数。填写目标项目和真实申请原因。</p></div></div><div class="help-step"><span class="step-number">3</span><div><h3>预览并创建 OA 草稿</h3><p>工作台校验每天的调整量，展示调出和调入明细。后续在 OA 填写前，还需核实目标项目及在途审批。</p></div></div><div class="preview-alert">点击“创建 OA 表单”会自动填写并保存 OA 草稿，返回表单链接。不会提交审批。</div>`,`<button class="btn btn-primary" data-action="close-modal">明白了 ${icon('check')}</button>`);
}
function showPreview(p) {
  state.preview=p;
  openModal('调整计划预览',`${e(p.employee.name)} · ${planDays(p)} 天 · 尚未写入 OA`,
    `<div class="preview-route"><div class="preview-project source"><span>调出 · 来源项目</span><strong>${e((p.source_projects||[p.source_project||p.public_project]).join('、'))}</strong></div>${icon('arrow-right')}<div class="preview-project"><span>调入 · 目标项目</span><strong>${e(planTargets(p))}</strong></div></div>${p.source_withdrawals?`<h3>调出来源明细</h3><table class="preview-table"><thead><tr><th>日期</th><th>调出项目</th><th>调出工时</th></tr></thead><tbody>${p.source_withdrawals.map(r=>`<tr><td>${e(r.date)}</td><td>${e(r.source_project)}</td><td>${fmt(r.hours)} h</td></tr>`).join('')}</tbody></table><h3>调入分配明细</h3>`:''}<table class="preview-table"><thead><tr><th>日期</th><th>来源项目调出</th><th>调入项目</th><th>调入工时</th></tr></thead><tbody>${p.adjustments.map(r=>`<tr><td>${r.date} <span class="muted text-[10px]">${weekday(r.date)}</span></td><td class="num">−${fmt(r.hours)} h</td><td>${e(r.target_project||p.target_project)}</td><td class="num green">+${fmt(r.hours)} h</td></tr>`).join('')}</tbody></table><div class="text-[11px] muted mb-2">申请原因</div><div class="preview-reason">${e(p.application_reason)}</div><div class="preview-total"><span>合计转移工时<br><span class="muted text-[10px]">调出与调入平衡，总工时不变</span></span><strong class="num">${fmt(p.total_hours)} <span class="text-xs font-normal">小时</span></strong></div><div class="preview-alert">点击“创建 OA 表单”后，将核实项目、填写明细并保存为 OA 草稿。不会提交审批；在途审批仍需人工核对。<p id="oa-draft-result" role="status" class="mt-2"></p></div>`,
    `<button class="btn" data-action="save-plan">${icon('check')}保存到本地计划</button><button class="btn btn-primary" data-action="create-oa">${icon('file-text')}创建 OA 表单</button>`);
}
async function refresh(start, end) {
  if(state.busy)return;
  lastQuery={start,end};
  state.busy=true;state.error='';renderMain();
  try {
    const data=await api('/api/query',{start,end});
    state.report=data.report;state.reportId=data.report_id;
    selectedSources=defaultSources();
    state.selected=new Map(candidates().filter(row=>Number(row.hours)>0).map(row=>[row.date,initialAllocation(row.hours)]));
    state.search='';state.page=1;
    state.targets.forEach(t=>{if(t.value&&t.value!=='__custom'&&!Object.keys(data.report.project_totals).includes(t.value)){t.custom=t.value;t.value='__custom';}});
    toast(`查询完成，已勾选 ${state.selected.size} 天项目工时`);
  } catch(err) {state.error=err.message;toast('查询未完成，保留上一次结果');}
  finally {state.busy=false;renderMain();}
}
function navigate(view) {state.view=view;renderMain();$('.sidebar').classList.remove('open');$('.mobile-overlay').classList.remove('visible');$('#main').focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
function exportCSV() {
  const safe=v=>{let text=String(v);if(/^[=+\-@\t\r]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"';};
  const rows=[['日期','项目','工时'],...allRows().map(r=>[r.date,r.project,r.hours])];
  textDownload(`个人工时_${state.report.start_date}_${state.report.end_date}.csv`,'\ufeff'+rows.map(r=>r.map(safe).join(',')).join('\r\n'),'text/csv;charset=utf-8');toast('已导出查询区间的工时记录');
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button,a');if(!button)return;
  if(button.dataset.action==='average-hours'){averageHours();return;}
  if(button.dataset.action==='add-target'){state.targets.push({value:'',custom:''});state.selected.forEach(values=>values.push('0'));renderPlan();return;}
  if(button.dataset.removeTarget!==undefined){const i=Number(button.dataset.removeTarget);state.targets.splice(i,1);state.selected.forEach(values=>values.splice(i,1));renderPlan();return;}
  if(button.dataset.view){event.preventDefault();navigate(button.dataset.view);return;}
  if(button.dataset.tab){state.tab=button.dataset.tab;state.page=1;renderMain();return;}
  if(button.dataset.chartDate){
    const date=button.dataset.chartDate,c=candidates().find(r=>r.date===date);
    if(c&&!state.busy&&sameProject()){state.selected.has(date)?state.selected.delete(date):state.selected.set(date,initialAllocation(c.hours));selectionChanged();}
    else {state.tab='all';state.search=date;state.page=1;renderMain();$('#record-search')?.focus();}
    return;
  }
  if(button.dataset.range){const today=nowDate(),d=new Date(`${today}T12:00:00Z`);let start=today,end=today;
    if(button.dataset.range==='current')({start,end}=hoursCycle(today));
    if(button.dataset.range==='previous')({start,end}=hoursCycle(today,-1));
    if(button.dataset.range==='recent'){d.setUTCDate(d.getUTCDate()-6);start=d.toISOString().slice(0,10);}
    $('#range-start').value=start;$('#range-end').value=end;$('#cycle-month').value=button.dataset.range==='recent'?'':end.slice(0,7);return;
  }
  if(button.dataset.savedPreview!==undefined){showPreview(state.plans[Number(button.dataset.savedPreview)]);return;}
  if(button.dataset.removePlan!==undefined){
    const i=Number(button.dataset.removePlan),removed=state.plans[i];state.plans.splice(i,1);
    try{persistPlans();renderMain();toast('已移除本地计划');}catch{state.plans.splice(i,0,removed);toast('本地存储不可用，未删除计划');}return;
  }
  if(button.dataset.planTab){planTab=button.dataset.planTab;renderMain();document.querySelector(`[data-plan-tab="${planTab}"]`)?.focus();return;}
  if(button.dataset.reasonSuggestion!==undefined){
    const suggestion=reasonSuggestions[Number(button.dataset.reasonSuggestion)];
    if(suggestion){state.reason=suggestion[1];const field=$('#plan-reason');field.value=state.reason;updatePlanButton();field.focus();field.setSelectionRange(field.value.length,field.value.length);}
    return;
  }
  if(button.dataset.projectPick!==undefined){
    const i=Number(button.dataset.projectPick),target=state.targets[i],item=target?.projectCheck?.matches?.[Number(button.dataset.matchIndex)];
    if(item&&!sourceProjects().includes(item.name)&&!destinations().some((name,k)=>k!==i&&name===item.name)){
      target.custom=item.name;const input=$(`[data-custom-target="${i}"]`);input.value=item.name;input.focus();scheduleProjectCheck(target,true);
    }
    return;
  }
  switch(button.dataset.action){
    case 'view-flows':planTab=flowCount('pending')?'pending':'saved';navigate('plans');break;
    case 'menu':$('.sidebar').classList.toggle('open');$('.mobile-overlay').classList.toggle('visible');break;
    case 'close-modal':closeModal();break;
    case 'help':helpModal();break;
    case 'date':dateModal();break;
    case 'refresh':if(!state.report)dateModal();else await refresh(state.report.start_date,state.report.end_date);break;
    case 'retry-query':if(lastQuery)await refresh(lastQuery.start,lastQuery.end);break;
    case 'oa-login':await loginModal();break;
    case 'check-saved':await checkSavedFlows();break;
    case 'clear-login':
      if(state.busy||state.creating){toast('请等待当前操作完成后再清除登录态');break;}
      clearTimeout(authTimer);authVersion++;button.disabled=true;
      try {
        const cleared=await api('/api/auth/clear',{});
        connectionEpoch++;setConnection('missing');
        state.targets.forEach(t=>{clearTimeout(projectTimers.get(t));t.projectCheck=null;});
        state.profile=cleared.profile||{id:'',name:'未登录',employee_code:'',department:'',public_project:''};
        state.report=null;state.reportId=null;state.plans=[];state.selected.clear();state.targets=[{value:'',custom:''}];state.reason='';state.preview=null;state.error='';selectedSources=null;lastQuery=null;validationAttempted=false;

        savedVersion++;oaSaved={items:[],loading:false,error:'登录态已清除，登录后自动检查。',checked:false};
        closeModal();state.view='settings';renderShell();toast('已退出登录，个人数据将在重新登录后恢复');
      } catch(err) {toast(err.message);}
      finally {button.disabled=false;}
      break;
    case 'clear-error':state.error='';renderMain();break;
    case 'export-csv':exportCSV();break;
    case 'prev-page':state.page--;renderTable();break;
    case 'next-page':state.page++;renderTable();break;
    case 'theme':state.theme=state.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=state.theme;try{localStorage.setItem('hours-theme',JSON.stringify(state.theme));}catch{}$('#theme-button').innerHTML=icon(state.theme==='dark'?'sun':'moon');$('#theme-button').setAttribute('aria-label',state.theme==='dark'?'切换浅色模式':'切换深色模式');drawIcons();break;
    case 'preview':
      state.targets.forEach(t=>{if(t.value==='__custom'&&t.custom.trim()&&t.projectCheck?.status!=='valid'&&t.projectCheck?.status!=='checking')scheduleProjectCheck(t,true);});
      validationAttempted=true;updatePlanButton();
      if(!canPreview()){const invalid=$('.plan-card [aria-invalid="true"]');if(invalid){invalid.focus();invalid.scrollIntoView({block:'center',behavior:'auto'});}else{$('#plan-error').scrollIntoView({block:'center'});}return;}
      previewing=true;let previewError='';
      button.disabled=true;button.innerHTML=`${icon('loader-circle','spinning')}正在核对…`;drawIcons();
      try {const data=await api('/api/preview',{report_id:state.reportId,source_projects:sourceProjects(),reason:state.reason,rows:allocationRows()});showPreview(data.preview);}catch(err){previewError=err.message;}finally{previewing=false;button.innerHTML=`生成调整预览 ${icon('arrow-right')}`;updatePlanButton();if(previewError)$('#plan-error').textContent=previewError;drawIcons();}break;
    case 'create-oa': {
      if(state.creating)return;
      const plan=state.preview;state.creating=true;
      $('#modal').querySelectorAll('button').forEach(b=>b.disabled=true);
      button.innerHTML=`${icon('loader-circle','spinning')}正在填写并保存…`;drawIcons();
      $('#oa-draft-result').textContent='正在通过接口核实工时、准备明细并保存 OA 草稿。';
      let completed=false, polling=true;
      const pollProgress=async()=>{
        try {const status=await api('/api/oa-draft/status');if(polling&&status.active)$('#oa-draft-result').textContent=`${status.message} · 已用时 ${status.elapsed_seconds} 秒`;}
        catch {} finally {if(polling)setTimeout(pollProgress,1200);}
      };
      setTimeout(pollProgress,1200);
      try {
        const data=await api('/api/oa-draft',{report_id:plan.report_id,source_projects:plan.source_projects||[plan.source_project||plan.public_project],target_project:plan.target_project,reason:plan.application_reason,rows:plan.adjustments.map(r=>({date:r.date,hours:r.hours,target_project:r.target_project||plan.target_project}))});
        const draft=data.draft;
        const link=new URL(draft.url);
        if(link.protocol!=='https:'||link.hostname!=='i.thundersoft.com')throw new Error('返回的 OA 链接无效');
        $('#oa-draft-result').innerHTML=`<strong>OA 草稿已保存 · ${e(draft.request_id)}</strong><br>${e(draft.warning || '未提交审批，请打开表单核对。')}<br><a class="btn mt-2" href="${e(link.href)}" target="_blank" rel="noopener noreferrer">打开 OA 表单 ${icon('external-link')}</a>`;
        button.innerHTML=`${icon('check')}已创建`;completed=true;toast('OA 草稿已保存，未提交审批');
        void checkSavedFlows();
      } catch(err) {$('#oa-draft-result').textContent=err.message;button.innerHTML=`${icon('file-text')}创建 OA 表单`;}
      finally {polling=false;state.creating=false;$('#modal').querySelectorAll('button').forEach(b=>b.disabled=false);button.disabled=completed;drawIcons();}
      break;
    }
    case 'save-plan':{
      const key=p=>JSON.stringify([p.employee.id,p.public_project,p.target_project,p.application_reason,p.adjustments,p.source_withdrawals]);
      if(state.plans.some(p=>key(p)===key(state.preview))){toast('这个计划已保存，无需重复添加');return;}
      state.plans.unshift(state.preview);planTab='local';
      try{persistPlans();closeModal();navigate('plans');toast('已保存到当前浏览器的本地计划');}catch{state.plans.shift();toast('本地存储不可用，计划仍保留在当前预览中');}break;
    }
  }
});
document.addEventListener('click',event=>{if(event.target.classList.contains('mobile-overlay')){$('.sidebar').classList.remove('open');$('.mobile-overlay').classList.remove('visible');}});
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.dataset.sourceProject!==undefined){selectSource(el.dataset.sourceProject,el.checked);return;}
  if(el.id==='cycle-month'&&el.value){const cycle=hoursCycle(el.value+'-01');$('#range-start').value=cycle.start;$('#range-end').value=cycle.end;}
  if(el.id==='range-start'||el.id==='range-end'){const start=$('#range-start').value,end=$('#range-end').value;$('#cycle-month').value=end&&hoursCycle(end).start===start&&hoursCycle(end).end===end?end.slice(0,7):'';}
  if(el.dataset.rowDate){const d=el.dataset.rowDate;el.checked?state.selected.set(d,initialAllocation(candidates().find(r=>r.date===d).hours)):state.selected.delete(d);selectionChanged(d);}
  if(el.id==='select-page'){tableRows().slice((state.page-1)*8,state.page*8).filter(r=>(r.project===sourceProject()||sourceProjects().includes(r.project))).forEach(r=>{el.checked?state.selected.set(r.date,initialAllocation(candidates().find(c=>c.date===r.date).hours)):state.selected.delete(r.date);});selectionChanged();$('#select-page').focus();}
  if(el.dataset.target!==undefined){state.targets[Number(el.dataset.target)].value=el.value;renderPlan();if(el.value==='__custom')scheduleProjectCheck(state.targets[Number(el.dataset.target)]);}
});
document.addEventListener('input',event=>{
  const el=event.target;
  if(el.id==='record-search'){state.search=el.value;state.page=1;renderTable();}
  if(el.id==='plan-reason')state.reason=el.value;
  if(el.dataset.customTarget!==undefined){const target=state.targets[Number(el.dataset.customTarget)];target.custom=el.value;scheduleProjectCheck(target);}
  if(el.dataset.quantity)state.selected.get(el.dataset.quantity)[Number(el.dataset.allocation)]=el.value;
  updatePlanButton();
});
document.addEventListener('submit',async event=>{
  event.preventDefault();
  if(event.target.id==='range-form'){
    const start=$('#range-start').value,end=$('#range-end').value;
    if(!start||!end||start>end||(new Date(end)-new Date(start))/86400000>366){$('#range-error').textContent='请选择起止顺序正确、且不超过一年的日期范围。';return;}
    closeModal();await refresh(start,end);
  }
  if(event.target.id==='profile-form'){
    const public_project=$('#public-project').value.trim();const btn=event.target.querySelector('button');btn.disabled=true;
    try{const data=await api('/api/profile',{public_project});state.profile=data.profile;state.selected.clear();renderMain();toast('个人公共项目已保存，请重新查询工时');}catch(err){$('#settings-error').textContent=err.message;btn.disabled=false;}
  }
});
$('#modal').addEventListener('cancel',event=>{if(state.creating)event.preventDefault();});
$('#modal').addEventListener('close',()=>{clearTimeout(authTimer);authVersion++;});
$('#modal').addEventListener('click',event=>{if(event.target===$('#modal')){const r=$('#modal').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeModal();}});

async function boot() {
  try {
    const data=await api('/api/bootstrap');state.profile=data.profile;state.report=data.report;state.reportId=data.report_id;
    state.theme=readLocal('hours-theme','light');document.documentElement.dataset.theme=state.theme;
    const saved=readLocal(`hours-plans-${state.profile.id}`,[]);state.plans=Array.isArray(saved)?saved.filter(p=>p?.employee?.id===state.profile.id&&Array.isArray(p.adjustments)&&p.adjustments.length):[];
    renderShell();
    if(!state.profile.id){setConnection('missing');navigate('settings');return;}
    if(!state.profile.public_project){navigate('settings');void checkSavedFlows();return;}
    void checkSavedFlows();
    const today=nowDate();
    const cycle=hoursCycle(today);
    await refresh(cycle.start,cycle.end);
  } catch(err) {$('#app').innerHTML=`<div class="initial-load"><div class="text-center"><h1 class="text-xl mb-3">暂时无法打开工时工作台</h1><p class="muted mb-4">${e(err.message)}</p><a class="btn" href="/">重新加载</a></div></div>`;}
}
boot();
