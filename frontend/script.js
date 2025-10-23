// ====== Config ======
const apiBase = "http://192.168.56.10:5000";

// ====== Helpers ======
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

// ====== Boot ======
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
})();

// sliders live label
$("#cpu").oninput = (e) => ($("#cpu-val").textContent = e.target.value);
$("#memory").oninput = (e) => ($("#memory-val").textContent = e.target.value);
$("#io").oninput = (e) => ($("#io-val").textContent = e.target.value);

// demo & utils
$("#load-demo").onclick = () => {
  $("#command").value =
    "python3 - <<'PY'\nimport time,sys\nfor i in range(1,11):\n    print(f'Passo {i}/10')\n    sys.stdout.flush()\n    time.sleep(0.5)\nprint('Finalizado!')\nPY";
  toast("Script de demonstração carregado.");
};
$("#clear-output").onclick = () => {
  $("#output-log").textContent = "";
  toast("Output limpo.");
};

// ====== Forms ======
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
  } catch (err) {
    toast(`Erro ao executar: ${err.message}`, "err");
  }
};

$("#status-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace").trim();
  if (!ns) return;
  await loadStatus(ns, true);
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
  } catch (err) {
    toast(`Erro ao encerrar: ${err.message}`, "err");
  }
};

// ====== Status live ======
let watchTimer = null;

$("#watch-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = $("#watch-ns").value.trim();
  if (!ns) return toast("Informe um namespace para monitorar.", "err");
  if (watchTimer) clearInterval(watchTimer);
  await loadStatus(ns, true);
  watchTimer = setInterval(() => loadStatus(ns, false), 2000);
  toast(`Monitorando "${ns}"…`);
};

$("#stop-watch").onclick = () => {
  if (watchTimer) {
    clearInterval(watchTimer);
    watchTimer = null;
    toast("Monitoramento pausado.");
  }
};

async function loadStatus(ns, revealCards) {
  try {
    const json = await fetchJSON(`${apiBase}/status/${encodeURIComponent(ns)}`);
    // preencher cards resumidos
    if (revealCards) $("#status-cards").hidden = false;
    $("#st-state").textContent = json.status ?? "—";
    $("#st-cpu").textContent = json.cpu ?? "—";
    $("#st-mem").textContent = json.memory ?? "—";
    $("#st-unit").textContent = json.unit ?? "—";
    $("#st-pid").textContent = json.pid ?? "—";
    // mostrar payload bruto
    $("#status-output").textContent = JSON.stringify(json, null, 2);
  } catch (err) {
    toast(`Erro no status: ${err.message}`, "err");
  }
}
