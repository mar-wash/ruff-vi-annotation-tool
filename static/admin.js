const $ = (id) => document.getElementById(id);
const keyStorage = "ruffvi_admin_secret";
let latestPayload = null;

function fmt(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString();
}

function pct(value) {
  return value === null || value === undefined ? "-" : `${value}%`;
}

async function fetchAdmin() {
  const key = localStorage.getItem(keyStorage) || "";
  const response = await fetch("/api/admin", {
    headers: { Authorization: `Bearer ${key}` },
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Admin request failed");
  return data;
}

function showGate(show) {
  $("adminGate").classList.toggle("hidden", !show);
}

function render(payload) {
  latestPayload = payload;
  const total = payload.annotations.length;
  const correct = payload.annotations.filter((row) => row.is_correct).length;
  const submitted = payload.annotations.filter((row) => row.submitted_at).length;
  $("overviewGrid").innerHTML = `
    <div class="summary"><strong>${payload.instances.length}</strong><span>instances</span></div>
    <div class="summary"><strong>${payload.annotators.length}</strong><span>annotators</span></div>
    <div class="summary"><strong>${total}</strong><span>annotations</span></div>
    <div class="summary"><strong>${total ? Math.round((correct / total) * 100) : 0}%</strong><span>accuracy</span></div>
    <div class="summary"><strong>${submitted}</strong><span>submitted</span></div>
  `;

  const agreement = payload.agreement;
  $("agreementGrid").innerHTML = `
    <div class="summary"><strong>${agreement.overall.annotators}</strong><span>annotators compared</span></div>
    <div class="summary"><strong>${agreement.overall.pair_count}</strong><span>annotator pairs</span></div>
    <div class="summary"><strong>${pct(agreement.overall.mean_percent_agreement)}</strong><span>mean agreement</span></div>
    <div class="summary"><strong>${agreement.overall.mean_cohen_kappa ?? "-"}</strong><span>mean Cohen's kappa</span></div>
  `;
  $("agreementPairs").innerHTML = agreement.pairs.map((row) => `
    <tr>
      <td>${row.annotator_a}</td>
      <td>${row.annotator_b}</td>
      <td>${row.shared_instances}</td>
      <td>${row.agreements}</td>
      <td>${pct(row.percent_agreement)}</td>
      <td>${row.cohen_kappa ?? "-"}</td>
    </tr>
  `).join("") || `<tr><td colspan="6">Need at least two annotators with overlapping annotations.</td></tr>`;
  $("instanceAgreement").innerHTML = agreement.instances.map((row) => `
    <tr>
      <td>#${row.instance_id}</td>
      <td>${row.annotations}</td>
      <td>${row.unique_answers}</td>
      <td>${row.unanimous ? "yes" : "no"}</td>
      <td>${row.majority_answer} (${row.majority_count})</td>
    </tr>
  `).join("") || `<tr><td colspan="5">No annotated instances yet.</td></tr>`;

  $("adminAnnotators").innerHTML = payload.annotators.map((row) => `
    <tr>
      <td><strong>${row.username}</strong></td>
      <td>${fmt(row.registered)}</td>
      <td>${fmt(row.last_seen_at)}</td>
      <td>${row.saved || 0}</td>
      <td>${row.submitted || 0}</td>
      <td>${row.accuracy ?? "-"}</td>
    </tr>
  `).join("") || `<tr><td colspan="6">No annotators yet.</td></tr>`;

  $("adminInstances").innerHTML = payload.instances.map((row) => `
    <tr>
      <td>#${row.id}</td>
      <td>${row.occupation}<br><span class="muted">${row.occupation_en}</span></td>
      <td>${row.participant_role}<br><span class="muted">${row.participant_role_en}</span></td>
      <td>${row.term_set}</td>
      <td>${row.narrator_position}</td>
      <td>${row.distractor_level}</td>
      <td>${row.correct_answer}</td>
      <td>${row.target_vi}<br><span class="muted">${row.target_en}</span></td>
    </tr>
  `).join("");

  $("adminAnnotations").innerHTML = payload.annotations.map((row) => `
    <tr>
      <td>${row.username}</td>
      <td>#${row.instance_id}<br><span class="muted">${row.occupation} · D${row.distractor_level}</span></td>
      <td>${row.answer}</td>
      <td>${row.correct_answer}</td>
      <td>${row.is_correct ? "yes" : "no"}</td>
      <td>${fmt(row.submitted_at)}</td>
      <td>${row.reasoning || "-"}</td>
    </tr>
  `).join("") || `<tr><td colspan="7">No annotations yet.</td></tr>`;
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function exportCsv() {
  if (!latestPayload) return;
  const headers = [
    "username",
    "instance_id",
    "occupation",
    "participant_role",
    "term_set",
    "distractor_level",
    "answer",
    "correct_answer",
    "is_correct",
    "reasoning",
    "created_at",
    "updated_at",
    "submitted_at",
  ];
  const rows = latestPayload.annotations.map((row) => headers.map((header) => csvCell(row[header])).join(","));
  const csv = [headers.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "ruffvi_annotations.csv";
  link.click();
  URL.revokeObjectURL(url);
}

async function load() {
  try {
    render(await fetchAdmin());
    showGate(false);
  } catch (error) {
    $("adminError").textContent = error.message;
    showGate(true);
  }
}

$("adminForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  localStorage.setItem(keyStorage, $("adminKey").value.trim());
  await load();
});

$("refreshAdmin").addEventListener("click", load);
$("exportCsv").addEventListener("click", exportCsv);
$("lockAdmin").addEventListener("click", () => {
  localStorage.removeItem(keyStorage);
  $("adminKey").value = "";
  showGate(true);
});

if (localStorage.getItem(keyStorage)) {
  load();
} else {
  showGate(true);
}
