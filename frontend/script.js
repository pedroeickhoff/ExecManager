// ====== Config ======
const apiBase = "http://192.168.56.10:5000";

const $ = (sel, parent = document) => parent.querySelector(sel);

function toast(msg, type = "ok", timeout = 2600) {
  const box = $("#toasts");
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  box.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateY(4px)";
    setTimeout(() => t.remove(), 220);
  }, timeout);
}

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const text = await res.text();
  let json;
  try {
    json = text ? JSON.parse(text) : {};
  } catch {
    json = { error: text };
  }
  if (!res.ok) {
    const e = json?.error || res.statusText || "Erro desconhecido";
    throw new Error(e);
  }
  return json;
}

function setApiHealth(state, msg) {
  const pill = $("#api-health");
  pill.classList.remove("ok", "err");
  if (state === "ok") pill.classList.add("ok");
  if (state === "err") pill.classList.add("err");
  pill.innerHTML = `<span class="pulse"></span> ${msg}`;
}

let watchTimer = null;
let envsTimer = null;

function resetUI() {
  if (watchTimer) {
    clearInterval(watchTimer);
    watchTimer = null;
  }
  if (envsTimer) {
    clearInterval(envsTimer);
    envsTimer = null;
  }
  const autoChk = $("#auto-refresh");
  if (autoChk) autoChk.checked = false;

  document.querySelectorAll("form").forEach((f) => f.reset());

  const cpuInp = $("#cpu"),
    memInp = $("#memory"),
    ioInp = $("#io");
  if (cpuInp) $("#cpu-val").textContent = cpuInp.value || "1.0";
  if (memInp) $("#memory-val").textContent = memInp.value || "512";
  if (ioInp) $("#io-val").textContent = ioInp.value || "5";

  const outLog = $("#output-log");
  if (outLog) outLog.textContent = "";
  const statOut = $("#status-output");
  if (statOut) statOut.textContent = "";

  const dl = $("#download-output");
  if (dl) {
    dl.removeAttribute("href");
    dl.removeAttribute("download");
  }

  const cards = $("#status-cards");
  if (cards) cards.hidden = true;
  const setToDash = (id) => {
    const el = $(id);
    if (el) el.textContent = "—";
  };
  setToDash("#st-state");
  setToDash("#st-cpu");
  setToDash("#st-mem");
  setToDash("#st-unit");
  setToDash("#st-pid");

  const tbody = $("#env-table tbody");
  if (tbody) tbody.innerHTML = "";

  const toasts = $("#toasts");
  if (toasts) toasts.innerHTML = "";
}

(async function init() {
  try {
    setApiHealth("", "verificando API…");
    const res = await fetchJSON(`${apiBase}/resources`);
    $("#cpu").max = res.cpu_available ?? 8;
    $("#memory").max = res.memory_available ?? 16384;
    $("#cpu-free").textContent = `${res.cpu_available ?? "—"} núcleos`;
    $("#mem-free").textContent = `${res.memory_available ?? "—"} MB`;
    setApiHealth("ok", "API online");
  } catch (e) {
    setApiHealth("err", "API offline");
    toast("Não foi possível conectar à API.", "err");
  }
  try {
    await loadEnvironments();
  } catch {}
})();

$("#cpu").oninput = (e) => ($("#cpu-val").textContent = e.target.value);
$("#memory").oninput = (e) => ($("#memory-val").textContent = e.target.value);
$("#io").oninput = (e) => ($("#io-val").textContent = e.target.value);

$("#load-demo").onclick = () => {
  $("#command").value =
    "python3 - <<'PY'\nimport time,sys\nfor i in range(1,11):\n    print(f'Passo {i}/10')\n    sys.stdout.flush()\n    time.sleep(0.5)\nprint('Finalizado!')\nPY";
  toast("Script de demonstração carregado.");
};

$("#clear-output").onclick = () => {
  resetUI();
  toast("Página limpa.");
};

$("#create-form").onsubmit = async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  try {
    await fetchJSON(`${apiBase}/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    toast("Ambiente criado com sucesso.", "ok");
    await loadEnvironments();
  } catch (err) {
    toast(`Erro ao criar: ${err.message}`, "err");
  }
};

$("#execute-form").onsubmit = async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  try {
    const res = await fetchJSON(`${apiBase}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    toast(`Execução iniciada (${res.unit || "unit n/d"})`, "ok");
    await loadEnvironments();
  } catch (err) {
    toast(`Erro ao executar: ${err.message}`, "err");
  }
};

$("#status-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace").trim();
  if (!ns) return;
  await loadStatus(ns, true);
  await loadEnvironments();
};

$("#output-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace").trim();
  if (!ns) return;
  try {
    const res = await fetch(`${apiBase}/output/${encodeURIComponent(ns)}`);
    if (!res.ok) throw new Error("Output não encontrado");
    const text = await res.text();
    $("#output-log").textContent = text || "(sem saída)";
    const blob = new Blob([text], { type: "text/plain" });
    $("#download-output").href = URL.createObjectURL(blob);
    $("#download-output").download = `${ns}-output.log`;
    toast("Output carregado.", "ok");
  } catch (err) {
    toast(`Erro ao obter output: ${err.message}`, "err");
  }
};

$("#copy-output").onclick = async () => {
  const txt = $("#output-log").textContent || "";
  if (!txt) return toast("Nada para copiar.", "err");
  try {
    await navigator.clipboard.writeText(txt);
    toast("Output copiado para a área de transferência.");
  } catch {
    toast("Não foi possível copiar.", "err");
  }
};

$("#terminate-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace").trim();
  if (!ns) return;
  if (!confirm(`Encerrar e remover o ambiente "${ns}"?`)) return;
  try {
    await fetchJSON(`${apiBase}/terminate/${encodeURIComponent(ns)}`, {
      method: "DELETE",
    });
    toast(`Ambiente ${ns} encerrado.`, "ok");
    await loadEnvironments();
  } catch (err) {
    toast(`Erro ao encerrar: ${err.message}`, "err");
  }
};

$("#watch-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = $("#watch-ns").value.trim();
  if (!ns) return toast("Informe um namespace para monitorar.", "err");
  if (watchTimer) clearInterval(watchTimer);
  await loadStatus(ns, true);
  await loadEnvironments();
  watchTimer = setInterval(async () => {
    await loadStatus(ns, false);
    await loadEnvironments();
  }, 2000);
  toast(`Monitorando "${ns}"…`);
};

$("#stop-watch").onclick = () => {
  if (watchTimer) {
    clearInterval(watchTimer);
    watchTimer = null;
    toast("Monitoramento pausado.");
  }
};

$("#refresh-envs").onclick = async () => {
  await loadEnvironments();
};

$("#auto-refresh").onchange = (e) => {
  if (e.target.checked) {
    envsTimer = setInterval(loadEnvironments, 5000);
    toast("Auto-refresh ativo.");
  } else if (envsTimer) {
    clearInterval(envsTimer);
    envsTimer = null;
    toast("Auto-refresh desativado.");
  }
};

async function loadEnvironments() {
  const tbody = $("#env-table tbody");
  try {
    const data = await fetchJSON(`${apiBase}/environments`);
    tbody.innerHTML = "";
    for (const row of data) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="mono">${row.namespace}</td>
        <td><span class="pill ${pillClass(row.last_status)}">${
        row.last_status || "—"
      }</span></td>
        <td class="mono">${row.last_pid ?? "—"}</td>
        <td class="mono">${row.cpu ?? "—"}</td>
        <td class="mono">${row.memory ?? "—"}</td>
        <td class="mono">${row.unit_name || "—"}</td>
        <td>${fmtDate(row.created_at)}</td>
      `;
      tbody.appendChild(tr);
    }
  } catch (err) {
    toast(`Erro ao listar ambientes: ${err.message}`, "err");
  }
}

function pillClass(status) {
  switch ((status || "").toLowerCase()) {
    case "running":
      return "ok";
    case "finished":
      return "muted";
    case "terminated":
      return "muted";
    case "error":
      return "err";
    case "starting":
      return "warn";
    default:
      return "muted";
  }
}

function fmtDate(s) {
  if (!s) return "—";
  return ("" + s).replace("T", " ");
}

async function loadStatus(ns, revealCards) {
  try {
    const json = await fetchJSON(`${apiBase}/status/${encodeURIComponent(ns)}`);
    if (revealCards) $("#status-cards").hidden = false;
    $("#st-state").textContent = json.status ?? "—";
    $("#st-cpu").textContent = json.cpu_requested ?? "—";
    $("#st-mem").textContent = json.memory_requested ?? "—";
    $("#st-unit").textContent = json.unit ?? "—";
    $("#st-pid").textContent = json.pid ?? "—";
    $("#status-output").textContent = JSON.stringify(json, null, 2);
  } catch (err) {
    toast(`Erro no status: ${err.message}`, "err");
  }
}
