const apiBase = "http://127.0.0.1:5000";

document.getElementById("cpu").oninput = (e) => {
  document.getElementById("cpu-val").textContent = e.target.value;
};
document.getElementById("memory").oninput = (e) => {
  document.getElementById("memory-val").textContent = e.target.value;
};
document.getElementById("io").oninput = (e) => {
  document.getElementById("io-val").textContent = e.target.value;
};

document.getElementById("create-form").onsubmit = async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  await fetch(`${apiBase}/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  alert("Ambiente criado!");
};

document.getElementById("execute-form").onsubmit = async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  await fetch(`${apiBase}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  alert("Execução iniciada!");
};

document.getElementById("status-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace");
  const res = await fetch(`${apiBase}/status/${ns}`);
  const json = await res.json();
  document.getElementById("status-output").textContent = JSON.stringify(
    json,
    null,
    2
  );
};

document.getElementById("output-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace");
  const res = await fetch(`${apiBase}/output/${ns}`);
  const text = await res.text();
  document.getElementById("output-log").textContent = text;
};

document.getElementById("terminate-form").onsubmit = async (e) => {
  e.preventDefault();
  const ns = new FormData(e.target).get("namespace");
  await fetch(`${apiBase}/terminate/${ns}`, { method: "DELETE" });
  alert("Ambiente encerrado!");
};
