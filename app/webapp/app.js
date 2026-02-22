const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }

const $ = (id)=>document.getElementById(id);
const state = { tab: "chat", tg_id: null, models: null };

function setTab(tab){
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active", b.dataset.tab === tab));
  $("chatPane").classList.toggle("hidden", tab !== "chat");
  $("imagePane").classList.toggle("hidden", tab !== "image");
  $("videoPane").classList.toggle("hidden", tab !== "video");
  $("musicPane").classList.toggle("hidden", tab !== "music");
  rebuildModelSelect();
}
document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click", ()=>setTab(b.dataset.tab)));

function modelsForTab(){
  const m = state.models || {};
  if (state.tab === "chat") return m.chat || [];
  if (state.tab === "image") return m.image || [];
  if (state.tab === "video") return m.video || [];
  if (state.tab === "music") return m.music || [];
  return [];
}
function rebuildModelSelect(){
  const list = modelsForTab();
  const sel = $("model");
  sel.innerHTML = "";
  list.forEach((x)=>{
    const opt = document.createElement("option");
    opt.value = x.id;
    opt.textContent = x.title;
    if (x.is_default) opt.selected = true;
    sel.appendChild(opt);
  });
  if (!list.length){
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "Модели не загружены";
    sel.appendChild(opt);
  }
}
async function api(path, opts={}){
  const r = await fetch(path, {headers: {"Content-Type":"application/json"}, ...opts});
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok){
    const msg = (body && body.detail) ? JSON.stringify(body.detail) : (typeof body === "string" ? body : JSON.stringify(body));
    throw new Error(msg || ("HTTP "+r.status));
  }
  return body;
}
async function init(){
  const u = tg?.initDataUnsafe?.user;
  state.tg_id = u?.id ? String(u.id) : null;
  $("who").textContent = "tg: " + (state.tg_id || "нет");
  state.models = await api("/api/models");
  rebuildModelSelect();
  if (state.tg_id){ try { await api("/api/me?tg_id="+encodeURIComponent(state.tg_id)); } catch(e){} }
}
init().catch(e=>{ console.error(e); alert("Ошибка инициализации: " + e.message); });

async function submitJob(kind, payload, statusEl){
  statusEl.textContent = "Создаю задачу…";
  const body = await api(`/api/${kind}/submit`, {method:"POST", body: JSON.stringify(payload)});
  const job_id = body.job_id;
  statusEl.textContent = "Задача создана: " + job_id + " • ожидаю…";
  const started = Date.now();
  while(true){
    await new Promise(r=>setTimeout(r, 2000));
    const res = await api(`/api/${kind}/result/`+job_id);
    if (res.status === "done") { statusEl.textContent = "Готово ✅"; return res; }
    if (res.status === "error") { statusEl.textContent = "Ошибка ❌"; throw new Error(res.error || "error"); }
    const sec = Math.floor((Date.now()-started)/1000);
    statusEl.textContent = `Ожидание… ${sec}s`;
  }
}

$("chatBtn").addEventListener("click", async ()=>{
  $("chatOut").textContent = ""; $("chatStatus").textContent = "";
  const message = $("chatText").value.trim(); const model = $("model").value;
  if (!message) return;
  try{
    $("chatBtn").disabled = true;
    const res = await api("/api/chat", {method:"POST", body: JSON.stringify({tg_id: state.tg_id, message, model})});
    $("chatOut").textContent = res.text || JSON.stringify(res, null, 2);
    $("chatStatus").textContent = "OK";
  }catch(e){ $("chatStatus").textContent = "Ошибка: " + e.message; }
  finally{ $("chatBtn").disabled = false; }
});

$("imageBtn").addEventListener("click", async ()=>{
  $("imageOut").innerHTML = ""; $("imageStatus").textContent = "";
  const prompt = $("imagePrompt").value.trim(); const model = $("model").value;
  if (!prompt) return;
  try{
    $("imageBtn").disabled = true;
    const res = await submitJob("image", {tg_id: state.tg_id, prompt, model}, $("imageStatus"));
    const url = res.url;
    $("imageOut").innerHTML = url ? `<img src="${url}"/><p><a target="_blank" href="${url}">Открыть</a></p>` : `<pre>${JSON.stringify(res,null,2)}</pre>`;
  }catch(e){ $("imageStatus").textContent = "Ошибка: " + e.message; }
  finally{ $("imageBtn").disabled = false; }
});

$("videoBtn").addEventListener("click", async ()=>{
  $("videoOut").innerHTML = ""; $("videoStatus").textContent = "";
  const prompt = $("videoPrompt").value.trim(); const model = $("model").value;
  if (!prompt) return;
  try{
    $("videoBtn").disabled = true;
    const res = await submitJob("video", {tg_id: state.tg_id, prompt, model}, $("videoStatus"));
    const url = res.url;
    $("videoOut").innerHTML = url ? `<video controls src="${url}"></video><p><a target="_blank" href="${url}">Открыть</a></p>` : `<pre>${JSON.stringify(res,null,2)}</pre>`;
  }catch(e){ $("videoStatus").textContent = "Ошибка: " + e.message; }
  finally{ $("videoBtn").disabled = false; }
});

$("musicBtn").addEventListener("click", async ()=>{
  $("musicOut").innerHTML = ""; $("musicStatus").textContent = "";
  const lyrics = $("musicLyrics").value.trim();
  const style = $("musicStyle").value.trim() || null;
  const model = $("model").value;
  if (!lyrics) return;
  try{
    $("musicBtn").disabled = true;
    const res = await submitJob("music", {tg_id: state.tg_id, lyrics, style, model}, $("musicStatus"));
    const url = res.url;
    $("musicOut").innerHTML = url ? `<audio controls src="${url}"></audio><p><a target="_blank" href="${url}">Открыть</a></p>` : `<pre>${JSON.stringify(res,null,2)}</pre>`;
  }catch(e){ $("musicStatus").textContent = "Ошибка: " + e.message; }
  finally{ $("musicBtn").disabled = false; }
});
