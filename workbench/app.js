"use strict";
const $ = id => document.getElementById(id);
const modes = {
  query: ["规则查询","按项目和日期查询事实，沿证据追溯每个结论。","运行查询"],
  validate: ["数据校验","核对事实文件的结构、概念引用、来源和时间范围。","开始校验"],
  optimize: ["优化对比","比较四天逐日重建与复用索引的实际耗时，逐日核对结果与证据。","运行对比"]
};
let program = "query", doc, result, session, busy = false, codex = false;
const node = (tag, text, cls) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};
function reset() {
  result = null; session = null;
  $("download").disabled = true;
  $("followup").hidden = true;
  $("log").replaceChildren(node("div","等待运行","empty"));
  $("output").replaceChildren(node("p","运行后在这里查看结论与依据。","empty"));
  setState("就绪");
}
function setState(value, error=false) {
  $("state").textContent = value;
  $("state").className = error ? "state error" : "state";
}
function mode(value) {
  program = value;
  document.querySelectorAll("[data-program]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.program === value)));
  const [title, subtitle, action] = modes[value];
  $("title").textContent = title; $("subtitle").textContent = subtitle; $("runLabel").textContent = action;
  $("queryFields").hidden = value === "validate";
  $("dayLabel").textContent = value === "optimize" ? "起始日期（连续四天）" : "查询日期（可留空）";
  const opt = $("engine").querySelector('[value="codex"]');
  opt.disabled = !codex || value !== "query";
  if (opt.disabled) $("engine").value = "ncsc";
  $("modelFields").hidden = $("engine").value !== "codex";
  reset();
}
function populate(data, name) {
  doc = data;
  const concepts = Array.isArray(data?.concepts) ? data.concepts.filter(c=>c && typeof c.id === "string") : [];
  const facts = Array.isArray(data?.assertions) ? data.assertions.filter(a=>a && typeof a === "object") : [];
  for (const [slot, def] of [["subject","c:task:release"],["relation","r:status:blocked"],["object","c:value:true"]]) {
    const choices = data?.version === "0.1" ? concepts : concepts.filter(c => slot === "relation" ? c.kind === "relation" : c.kind !== "relation");
    const el = $(slot);
    el.replaceChildren(...choices.map(c => new Option((c.aliases?.[0] || c.id) + " · " + c.id, c.id)));
    const defaultId = choices.some(c=>c.id===def) ? def : facts[0]?.roles?.[slot];
    if (choices.some(c=>c.id === defaultId)) el.value = defaultId;
  }
  const contexts = [...new Set(facts.map(a=>a.context).filter(s=>typeof s === "string"))];
  $("contexts").replaceChildren(...contexts.map(s=>new Option(s,s)));
  $("context").value = contexts[0] || "";
  $("day").value = facts[0]?.valid_at || facts[0]?.valid_during?.from || "";
  $("irInfo").textContent = "IR " + (data?.version ?? "?");
  $("fileName").textContent = name; $("fileName").title = name;
  reset();
}
function lock(flag) {
  busy = flag;
  $("fields").disabled = flag; $("restore").disabled = flag;
  $("run").disabled = flag || doc === undefined;
  document.querySelectorAll("[data-program], #followup input, #followup button").forEach(el=>el.disabled=flag);
}
async function restore() {
  lock(true);
  try {
    const r = await fetch("/example.json");
    if (!r.ok) throw Error("示例文件加载失败");
    populate(await r.json(),"发布就绪示例.json");
  } catch (e) { fail(e.message); }
  finally { lock(false); }
}
function fail(message) {
  setState("失败",true);
  for (const label of $("log").querySelectorAll("li small")) {
    if (label.textContent === "执行中") label.textContent = "失败";
  }
  $("output").replaceChildren(node("h3","运行未完成"),node("p",message));
}
function details(title, data) {
  const d = node("details");
  d.append(node("summary",title), node("pre", typeof data === "string" ? data : JSON.stringify(data,null,2)));
  return d;
}
function panel(title, desc, style="") {
  const el = node("div",undefined,"hero "+style);
  el.append(node("strong",title),node("p",desc));
  return el;
}
function showResult(value) {
  const out = $("output");
  out.replaceChildren();
  const a = value.answer || value;
  if (a.status && a.query) {
    const explanations = {"支持":"当前分区有正向证据，可展开来源核实。","反对":"当前分区有明确反向证据。","冲突":"正反证据同时存在，请分别核查。","未知":a.reason === "premise_conflict" ? "前提证据冲突，规则暂停推导。" : "当前分区缺少足够证据。"};
    out.append(panel(a.status,explanations[a.status],a.status==="冲突"||a.status==="未知"?"warn":""));
    if (a.evidence?.length) out.append(node("h3","原始来源与推导"));
    for (const ev of a.evidence || []) {
      const direction = ev.polarity === "negative" ? "反向" : "正向";
      const section = node("div");
      for (const s of ev.sources || []) section.append(node("div",direction+" · "+s.description+" （"+s.id+"）","source"));
      section.append(details(ev.derived_by ? "展开规则推导 · "+ev.derived_by : "查看原始断言 · "+ev.assertion_id,ev));
      out.append(section);
    }
    if (a.suppressed?.length) out.append(details("查看被抑制的规则",a.suppressed));
  } else if (a.valid === true) {
    out.append(panel("校验通过","IR "+a.version+" · "+a.concepts+" 个概念 · "+a.assertions+" 条断言"));
  } else if (a.days) {
    out.append(panel(a.verified?"四日结果一致":"比对失败","两次执行逐日比较了完整答案和证据。"));
    out.append(node("p","逐日重建："+a.baseline_ms.toFixed(3)+" ms"),node("p","复用索引："+a.reuse_ms.toFixed(3)+" ms"));
    for (const d of a.days) out.append(node("div",d.day+"　"+d.status,"source"));
  }
  if (Object.hasOwn(value,"model_text")) {
    out.append(node("h3","Codex 回答"),node("pre",value.model_text || "未返回回答"));
    if (typeof value.verified === "boolean") out.append(node("p",value.verified ? "已确认 Codex 调用工具并取得本轮证据。" : "未取得匹配的工具收据，请以本页内核结果为准。"));
  }
  out.append(details("查看原始 JSON",value));
  $("download").disabled=false;
  session = value.session || null;
  $("followup").hidden = !session;
}
function eventLine(evt) {
  const list = $("log");
  if (evt.kind === "start" || evt.kind === "note") {
    const li = node("li",evt.name || evt.message || "执行中");
    if (evt.kind === "start") { li.dataset.phase = evt.name; li.append(node("small","执行中")); }
    list.append(li);
  } else if (evt.kind === "done") {
    const phase = [...list.children].reverse().find(li=>li.dataset.phase===evt.name);
    if (phase) phase.querySelector("small").textContent = "完成 · "+Number(evt.ms).toFixed(2)+" ms";
  }
}
async function run(follow=false) {
  if (busy || doc === undefined) return;
  const query = Object.fromEntries(["subject","relation","object","context","day"].map(k=>[k,$(k).value]));
  if (program !== "validate" && (!query.subject || !query.relation || !query.object || !query.context.trim() || (program==="optimize"&&!query.day))) {
    reset(); fail("请填写完整查询对象、关系和项目；四日对比还需要起始日期。"); return;
  }
  const oldSession = session;
  const question = follow ? $("followText").value.trim() : $("question").value.trim();
  const engine = $("engine").value;
  if (engine==="codex" && !question) { (follow ? $("followText") : $("question")).focus(); return; }
  reset(); lock(true); setState("运行中");
  $("log").replaceChildren(); $("output").replaceChildren(node("p","等待执行结果…"));
  try {
    const request={program,document:doc,query,engine};
    if (engine === "codex") { request.question=question; if(follow)request.session=oldSession; }
    const response=await fetch("/run",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(request)});
    if (!response.ok) throw Error(response.status===413?"请求超出大小限制。":"服务请求失败 · HTTP "+response.status);
    const reader=response.body.getReader(), decoder=new TextDecoder();
    let pending="", finalSeen=false;
    function parse(line) {
      if (!line.trim()) return;
      const evt=JSON.parse(line);
      if (evt.kind==="error") throw Error(evt.message || "运行失败");
      if (evt.kind==="result") {result=evt.value;showResult(result);finalSeen=true;return;}
      eventLine(evt);
    }
    for (;;) {
      const {done,value}=await reader.read();
      pending+=decoder.decode(value,{stream:!done});
      const lines=pending.split("\n"); pending=lines.pop(); lines.forEach(parse);
      if(done) break;
    }
    parse(pending);
    if(!finalSeen)throw Error("连接已结束，未收到完整结果。");
    setState("已完成"); $("followText").value="";
  } catch(e) { fail(e.message); }
  finally { lock(false); }
}
document.querySelectorAll("[data-program]").forEach(b=>b.onclick=()=>mode(b.dataset.program));
$("config").onsubmit=e=>{e.preventDefault();run();};
$("followup").onsubmit=e=>{e.preventDefault();run(true);};
$("config").addEventListener("input",e=>{
  if (e.target === $("file")) return;
  if(e.target === $("engine")) $("modelFields").hidden=e.target.value!=="codex";
  reset();
});
$("restore").onclick=restore;
$("fileButton").onclick=()=>$("file").click();
$("file").onchange=async e=>{
  const f=e.target.files[0]; if(!f) return;
  lock(true);
  try {
    if(f.size>2*1024*1024)throw Error("请选择不超过 2 MiB 的文件。");
    populate(JSON.parse(await f.text()),f.name);
  } catch(err) { reset();fail("未能载入文件，当前仍为原文件。"+err.message); }
  finally {e.target.value="";lock(false);}
};
$("download").onclick=()=>{
  if(!result)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
  const a=node("a"); a.href=url;a.download="ncsc-"+program+"-"+($("day").value||"undated")+".json";a.click();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
};
(async()=>{
  lock(true);
  try {
    const r=await fetch("/capabilities");
    if(r.ok) codex=(await r.json()).codex===true;
  } catch { codex=false; }
  $("engine").querySelector('[value="codex"]').textContent=codex?"Codex CLI · 本机入口":"Codex CLI · 当前不可用";
  mode("query"); await restore();
})();
