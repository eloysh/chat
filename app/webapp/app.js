const statusEl = document.getElementById("status");

function tgId() {
  try {
    const tg = window.Telegram?.WebApp;
    const id = tg?.initDataUnsafe?.user?.id;
    return id ? Number(id) : 0;
  } catch { return 0; }
}

async function api(path, opts={}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  const txt = await r.text();
  let data;
  try { data = JSON.parse(txt); } catch { data = { raw: txt }; }
  if (!r.ok) throw new Error((data && (data.detail || data.error)) ? JSON.stringify(data) : `HTTP ${r.status}`);
  return data;
}

function fillSelect(sel, items) {
  sel.innerHTML = "";
  for (const it of items || []) {
    const opt = document.createElement("option");
    opt.value = it.id;
    opt.textContent = `${it.title} (${it.id})`;
    sel.appendChild(opt);
  }
}

async function pollJob(jobId, onUpdate) {
  const deadline = Date.now() + 30 * 60 * 1000; // 30 минут вместо "690 секунд"
  while (Date.now() < deadline) {
    const j = await api(`/api/job/${jobId}`);
    onUpdate(j);
    if (j.status === "done" || j.status === "error") return j;
    await new Promise(r => setTimeout(r, 2000));
  }
  throw new Error("Тайм-аут ожидания результата (30 минут).");
}

// Tabs
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const tab = btn.dataset.tab;
    document.querySelectorAll(".panel").forEach(p => p.classList.add("hidden"));
    document.getElementById(`panel-${tab}`).classList.remove("hidden");
  });
});

(async function init() {
  statusEl.textContent = "Подключение…";

  const id = tgId();
  if (!id) {
    statusEl.textContent = "⚠️ Открой Mini App внутри Telegram (иначе tg_id=0).";
  } else {
    statusEl.textContent = `tg_id: ${id} ✅`;
    await api(`/api/me?tg_id=${id}`);
  }

  const models = await api("/api/models");
  fillSelect(document.getElementById("model-chat"), models.chat);
  fillSelect(document.getElementById("model-image"), models.image);
  fillSelect(document.getElementById("model-video"), models.video);
  fillSelect(document.getElementById("model-music"), models.music);

  statusEl.textContent = "Готово ✅";
})().catch(err => {
  statusEl.textContent = "Ошибка инициализации: " + err.message;
});

// Chat
document.getElementById("btn-chat").addEventListener("click", async () => {
  const out = document.getElementById("out-chat");
  out.textContent = "";
  try {
    const body = {
      tg_id: tgId(),
      model: document.getElementById("model-chat").value,
      message: document.getElementById("input-chat").value
    };
    const res = await api("/api/chat", { method:"POST", body: JSON.stringify(body) });
    out.textContent = `Создан job: ${res.job_id}\nОжидаю ответ…`;
    const job = await pollJob(res.job_id, (j) => out.textContent = `job ${j.id}: ${j.status}…`);
    if (job.status === "done") {
      out.textContent = job.result?.text || JSON.stringify(job.result, null, 2);
    } else {
      out.textContent = "Ошибка: " + (job.error || "unknown");
    }
  } catch (e) {
    out.textContent = "Ошибка: " + e.message;
  }
});

// Image
document.getElementById("btn-image").addEventListener("click", async () => {
  const out = document.getElementById("out-image");
  out.innerHTML = "";
  try {
    const body = {
      tg_id: tgId(),
      model: document.getElementById("model-image").value,
      prompt: document.getElementById("input-image").value
    };
    const res = await api("/api/image/submit", { method:"POST", body: JSON.stringify(body) });
    out.textContent = `Создан job: ${res.job_id}\nОжидаю…`;
    const job = await pollJob(res.job_id, (j) => out.textContent = `job ${j.id}: ${j.status}…`);
    if (job.status === "done") {
      const url = job.result?.url;
      out.innerHTML = `<div>Готово ✅</div><a href="${url}" target="_blank">${url}</a><img src="${url}" />`;
    } else out.textContent = "Ошибка: " + (job.error || "unknown");
  } catch (e) {
    out.textContent = "Ошибка: " + e.message;
  }
});

// Video
document.getElementById("btn-video").addEventListener("click", async () => {
  const out = document.getElementById("out-video");
  out.innerHTML = "";
  try {
    const body = {
      tg_id: tgId(),
      model: document.getElementById("model-video").value,
      prompt: document.getElementById("input-video").value
    };
    const res = await api("/api/video/submit", { method:"POST", body: JSON.stringify(body) });
    out.textContent = `Создан job: ${res.job_id}\nОжидаю…`;
    const job = await pollJob(res.job_id, (j) => out.textContent = `job ${j.id}: ${j.status}…`);
    if (job.status === "done") {
      const url = job.result?.url;
      out.innerHTML = `<div>Готово ✅</div><a href="${url}" target="_blank">${url}</a><video controls src="${url}"></video>`;
    } else out.textContent = "Ошибка: " + (job.error || "unknown");
  } catch (e) {
    out.textContent = "Ошибка: " + e.message;
  }
});

// Music
document.getElementById("btn-music").addEventListener("click", async () => {
  const out = document.getElementById("out-music");
  out.innerHTML = "";
  try {
    const body = {
      tg_id: tgId(),
      model: document.getElementById("model-music").value,
      lyrics: document.getElementById("input-music").value,
      style: document.getElementById("style-music").value
    };
    const res = await api("/api/music/submit", { method:"POST", body: JSON.stringify(body) });
    out.textContent = `Создан job: ${res.job_id}\nОжидаю…`;
    const job = await pollJob(res.job_id, (j) => out.textContent = `job ${j.id}: ${j.status}…`);
    if (job.status === "done") {
      const url = job.result?.url;
      out.innerHTML = `<div>Готово ✅</div><a href="${url}" target="_blank">${url}</a><audio controls src="${url}"></audio>`;
    } else out.textContent = "Ошибка: " + (job.error || "unknown");
  } catch (e) {
    out.textContent = "Ошибка: " + e.message;
  }
});
