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

// ====== Estado de timers ======
let watchTimer = null;
let envsTimer = null;
let resourceTimer = null; // atualiza só MEM dinâmica

// ====== Limpeza ======

// limpa inputs[type="text"] sem apagar áreas de output
function clearNamespaceFields(container) {
  if (!container) return;
  container.querySelectorAll('input[type="text"]').forEach((el) => {
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

// limpa tudo visualmente (botão "Limpar página")
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

  $("#cpu-val").textContent = $("#cpu").value || "1.0";
  $("#memory-val").textContent = $("#memory").value || "512";
  $("#io-val").textContent = $("#io").value || "5";

  $("#output-log").textContent = "";
  $("#status-output").textContent = "";

  const dl = $("#download-output");
  if (dl) {
    dl.removeAttribute("href");
    dl.removeAttribute("download");
  }

  $("#status-cards").hidden = true;
  ["#st-state", "#st-cpu", "#st-mem", "#st-unit", "#st-pid"].forEach(
    (id) => ($(id).textContent = "—")
  );

  $("#env-table tbody").innerHTML = "";
  $("#toasts").innerHTML = "";
}

// ====== Recursos (CPU/Mem) ======

// 1) roda só no início: seta CPU e Memória e ajusta sliders dos dois
async function loadInitialResources() {
  try {
    const res = await fetchJSON(`${apiBase}/resources`);

    // CPU inicial (fixa)
    $("#cpu-free").textContent = `${res.cpu_available ?? "—"}`;

    if ($("#cpu")) {
      $("#cpu").max = res.cpu_available ?? $("#cpu").max;
      if (parseFloat($("#cpu").value) > parseFloat($("#cpu").max)) {
        $("#cpu").value = $("#cpu").max;
        $("#cpu-val").textContent = $("#cpu").value;
      }
    }

    // Mem inicial
    $("#mem-free").textContent = `${res.memory_available ?? "—"} MB`;

    if ($("#memory")) {
      $("#memory").max = res.memory_available ?? $("#memory").max;
      if (parseInt($("#memory").value, 10) > parseInt($("#memory").max, 10)) {
        $("#memory").value = $("#memory").max;
        $("#memory-val").textContent = $("#memory").value;
      }
    }

    setApiHealth("ok", "API online");
  } catch (e) {
    setApiHealth("err", "API offline");
  }
}

// 2) roda em loop e depois de ações: ATUALIZA SÓ MEMÓRIA, não mexe na CPU
async function refreshMemoryOnly() {
  try {
    const res = await fetchJSON(`${apiBase}/resources`);

    // atualiza só a memória disponível em tempo real
    $("#mem-free").textContent = `${res.memory_available ?? "—"} MB`;

    if ($("#memory")) {
      $("#memory").max = res.memory_available ?? $("#memory").max;
      if (parseInt($("#memory").value, 10) > parseInt($("#memory").max, 10)) {
        $("#memory").value = $("#memory").max;
        $("#memory-val").textContent = $("#memory").value;
      }
    }

    // saúde da API
    setApiHealth("ok", "API online");
  } catch (e) {
    setApiHealth("err", "API offline");
  }
}

// ====== Boot ======
(async function init() {
  // carrega recursos iniciais (CPU + Mem uma vez)
  await loadInitialResources();

  // carrega tabela inicial
  try {
    await loadEnvironments();
  } catch {
    /* silencioso */
  }

  // começa atualização automática só da memória a cada 2s
  resourceTimer = setInterval(refreshMemoryOnly, 2000);
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

// botão que limpa toda a tela
$("#clear-output").onclick = () => {
  resetUI();
  toast("Página limpa.");
  // depois de limpar tudo, recarrega dados visuais
  loadEnvironments();
  refreshMemoryOnly();
};

// ====== Forms ======
$("#create-form").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));

  try {
    await fetchJSON(`${apiBase}/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });

    toast("Ambiente criado com sucesso.", "ok");
    await loadEnvironments();
    await refreshMemoryOnly(); // memória cai após reservar
  } catch (err) {
    toast(`Erro ao criar: ${err.message}`, "err");
  } finally {
    clearNamespaceFields(form.closest(".card") || form);
    // não limpamos o textarea do comando
  }
};

$("#execute-form").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = Object.fromEntries(new FormData(form));

  try {
    const res = await fetchJSON(`${apiBase}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    toast(`Execução iniciada (${res.unit || "unit n/d"})`, "ok");

    await loadEnvironments();
    await refreshMemoryOnly(); // memória impactada pelo running
  } catch (err) {
    toast(`Erro ao executar: ${err.message}`, "err");
  } finally {
    clearNamespaceFields(form.closest(".card") || form);
  }
};

$("#status-form").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const ns = new FormData(form).get("namespace").trim();
  if (!ns) return;

  try {
    await loadStatus(ns, true);
    await loadEnvironments();
    await refreshMemoryOnly(); // se terminou/liberou memória, reflete
  } catch (err) {
    toast(`Erro ao buscar status: ${err.message}`, "err");
  } finally {
    clearNamespaceFields(form.closest(".card") || form);
    // mantemos o resultado exibido nos cards e no <pre>
  }
};

$("#output-form").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const ns = new FormData(form).get("namespace").trim();
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

    await loadEnvironments();
    await refreshMemoryOnly(); // caso o processo tenha finalizado rápido
  } catch (err) {
    toast(`Erro ao obter output: ${err.message}`, "err");
  } finally {
    clearNamespaceFields(form.closest(".card") || form);
    // NÃO limpamos #output-log
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
  const form = e.target;
  const ns = new FormData(form).get("namespace").trim();
  if (!ns) return;
  if (!confirm(`Encerrar e remover o ambiente "${ns}"?`)) return;

  try {
    await fetchJSON(`${apiBase}/terminate/${encodeURIComponent(ns)}`, {
      method: "DELETE",
    });

    toast(`Ambiente ${ns} encerrado.`, "ok");

    await loadEnvironments();
    await refreshMemoryOnly(); // memória volta depois que mata
  } catch (err) {
    toast(`Erro ao encerrar: ${err.message}`, "err");
  } finally {
    clearNamespaceFields(form.closest(".card") || form);
  }
};

// ====== Monitoramento automático de um namespace ======
$("#watch-form").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target;
  const ns = $("#watch-ns").value.trim();
  if (!ns) return toast("Informe um namespace para monitorar.", "err");

  // cancela se já tinha um timer
  if (watchTimer) clearInterval(watchTimer);

  // atualiza imediatamente
  await loadStatus(ns, true);
  await loadEnvironments();
  await refreshMemoryOnly();

  // e passa a atualizar a cada 2s
  watchTimer = setInterval(async () => {
    await loadStatus(ns, false);
    await loadEnvironments();
    await refreshMemoryOnly();
  }, 2000);

  toast(`Monitorando "${ns}"…`);
  clearNamespaceFields(form.closest(".panel") || form);
};

$("#stop-watch").onclick = () => {
  if (watchTimer) {
    clearInterval(watchTimer);
    watchTimer = null;
    toast("Monitoramento pausado.");
  }
  clearNamespaceFields($("#watch-form").closest(".panel") || $("#watch-form"));
};

// ====== Lista de ambientes ======
$("#refresh-envs").onclick = async () => {
  await loadEnvironments();
  await refreshMemoryOnly();
};

// auto-refresh da tabela de ambientes
$("#auto-refresh").onchange = (e) => {
  if (e.target.checked) {
    envsTimer = setInterval(async () => {
      await loadEnvironments();
      await refreshMemoryOnly();
    }, 5000);
    toast("Auto-refresh ativo.");
  } else if (envsTimer) {
    clearInterval(envsTimer);
    envsTimer = null;
    toast("Auto-refresh desativado.");
  }
};

// ====== Funções principais ======
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
