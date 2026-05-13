"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

let selectedJobId = null;
let ws = null;

function fmtScore(score) {
  if (score == null) return "-";
  let cls = "score-warn";
  if (score >= 8) cls = "score-good";
  else if (score < 6) cls = "score-bad";
  return `<span class="${cls}">${score}</span>`;
}

async function refreshHealth() {
  try {
    const r = await fetch("/api/health");
    const data = await r.json();
    const badge = $("#health-badge");
    if (data.provider_healthy) {
      badge.textContent = `${data.provider} ok` + (data.current_model ? ` · ${data.current_model}` : "");
      badge.className = "badge ok";
    } else {
      badge.textContent = `${data.provider} unreachable`;
      badge.className = "badge bad";
    }
  } catch (e) {
    $("#health-badge").textContent = "API down";
    $("#health-badge").className = "badge bad";
  }
}

async function refreshJobs() {
  const r = await fetch("/api/jobs");
  const jobs = await r.json();
  const ul = $("#jobs-list");
  ul.innerHTML = "";
  for (const j of jobs) {
    const li = document.createElement("li");
    li.className = "job-row" + (j.job_id === selectedJobId ? " selected" : "");
    li.innerHTML = `
      <div><span class="id">${j.job_id}</span>
        <span class="status">[${j.status}${j.score != null ? " · " + j.score : ""}]</span></div>
      <div>${escapeHtml(j.task)}</div>`;
    li.addEventListener("click", () => selectJob(j.job_id));
    ul.appendChild(li);
  }
}

async function selectJob(jobId) {
  selectedJobId = jobId;
  await Promise.all([refreshJobs(), refreshJobDetail()]);
}

async function refreshJobDetail() {
  if (!selectedJobId) return;
  const r = await fetch(`/api/jobs/${selectedJobId}`);
  if (!r.ok) return;
  const data = await r.json();

  const j = data.job;
  $("#job-summary").innerHTML = `
    <div><strong>${j.job_id}</strong> &middot; ${escapeHtml(j.workspace)}</div>
    <div>Status: <strong>${j.status}</strong> · Verdict: ${j.verdict || "-"} · Score: ${fmtScore(j.score)}</div>
    <div style="margin-top:0.4rem;color:#8892a6">${escapeHtml(j.task).slice(0, 600)}</div>`;

  const tbody = $("#phases-table tbody");
  tbody.innerHTML = "";
  for (const p of data.phases) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${p.phase}</td><td>${p.agent}</td><td>${p.cycle}</td>
      <td>${p.status}</td><td>${fmtScore(p.score)}</td>
      <td>${p.started_at ? p.started_at.slice(11, 19) : "-"}</td>
      <td>${p.finished_at ? p.finished_at.slice(11, 19) : "-"}</td>`;
    tbody.appendChild(tr);
  }

  const artifacts = collectArtifacts(data.phases);
  const aul = $("#artifacts-list");
  aul.innerHTML = "";
  for (const path of artifacts) {
    const li = document.createElement("li");
    li.textContent = path;
    li.addEventListener("click", () => loadArtifact(path));
    aul.appendChild(li);
  }
}

function collectArtifacts(phases) {
  const set = new Set();
  for (const p of phases) {
    const written = p.artifacts && p.artifacts.written;
    if (Array.isArray(written)) written.forEach((w) => set.add(w));
  }
  return Array.from(set).sort();
}

async function loadArtifact(path) {
  if (!selectedJobId) return;
  const r = await fetch(
    `/api/jobs/${selectedJobId}/artifact?path=${encodeURIComponent(path)}`,
  );
  if (!r.ok) {
    $("#artifact-view").textContent = `Failed to load ${path}: ${r.status}`;
    return;
  }
  const data = await r.json();
  $("#artifact-view").textContent = data.content;
}

function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/events`);
  ws.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data);
      appendEvent(ev);
      if (ev.event && ev.event.startsWith("phase.") || ev.event === "job.end") {
        if (ev.job_id === selectedJobId) refreshJobDetail();
        refreshJobs();
      }
    } catch (e) {
      /* ignore */
    }
  };
  ws.onclose = () => setTimeout(connectWs, 2000);
}

function appendEvent(ev) {
  const pre = $("#live-events");
  const line = document.createElement("span");
  line.className = "event-line";
  const kind = ev.event || "?";
  line.innerHTML =
    `<span class="event-kind">${escapeHtml(kind)}</span>` +
    escapeHtml(JSON.stringify(stripTs(ev)));
  pre.prepend(line);
  // cap log length
  while (pre.children.length > 200) pre.removeChild(pre.lastChild);
}

function stripTs(o) {
  const c = { ...o };
  delete c.event;
  return c;
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

$("#start-btn").addEventListener("click", async () => {
  const task = $("#task").value.trim();
  if (!task) {
    alert("Task description is required.");
    return;
  }
  const workspace_name = $("#workspace-name").value.trim() || null;
  const r = await fetch("/api/jobs", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ task, workspace_name, workflow: "full_pipeline" }),
  });
  if (!r.ok) {
    alert("Failed to start: " + r.status);
    return;
  }
  const data = await r.json();
  selectedJobId = data.job_id;
  await refreshJobs();
  await refreshJobDetail();
});

(async function init() {
  await refreshHealth();
  await refreshJobs();
  connectWs();
  setInterval(refreshHealth, 15000);
  setInterval(refreshJobs, 8000);
  setInterval(() => selectedJobId && refreshJobDetail(), 8000);
})();
