const $ = (id) => document.getElementById(id);
const secretStorage = "ruffvi_admin_secret";
let selectedFile = null;
let parsedRows = [];

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];
    if (char === '"' && quoted && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      quoted = !quoted;
    } else if (char === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(cell);
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  row.push(cell);
  if (row.some((value) => value.trim())) rows.push(row);
  const headers = rows.shift() || [];
  return rows.map((values) => Object.fromEntries(headers.map((header, index) => [header.trim(), values[index] || ""])));
}

function renderPreview() {
  $("previewRows").innerHTML = parsedRows.slice(0, 5).map((row) => `
    <tr>
      <td>${row.occupation || ""}</td>
      <td>${row.term_set || ""}</td>
      <td>${row.narrator_position || ""}</td>
      <td>${row.distractor_level || ""}</td>
      <td>${(row.intro_vi || "").slice(0, 90)}</td>
      <td>${row.correct_answer || ""}</td>
    </tr>
  `).join("");
  $("importButton").textContent = `Import ${parsedRows.length} rows`;
  $("previewArea").classList.remove("hidden");
}

async function chooseFile(file) {
  selectedFile = file;
  parsedRows = parseCsv(await file.text());
  renderPreview();
}

async function importRows() {
  const secret = localStorage.getItem(secretStorage) || "";
  if (!secret) {
    $("importResult").innerHTML = `<div class="notice">Enter the admin secret before importing.</div>`;
    showImportGate(true);
    return;
  }
  const form = new FormData();
  form.append("file", selectedFile);
  const response = await fetch("/api/instances/import", {
    method: "POST",
    headers: { Authorization: `Bearer ${secret}` },
    body: form,
  });
  const result = await response.json();
  const ok = response.ok;
  const errors = result.errors || [];
  $("importResult").innerHTML = `
    <div class="${ok ? "success" : "notice"}">
      ${ok ? "✓" : "Import failed:"} ${result.inserted || 0} instances imported · ${result.skipped_duplicates || 0} duplicates skipped · ${errors.length} errors
    </div>
    ${errors.length ? `<details open><summary>Errors</summary><ul>${errors.map((error) => `<li>Row ${error.row} — ${error.field}: ${error.message}</li>`).join("")}</ul></details>` : ""}
  `;
}

function showImportGate(show) {
  $("importGate").classList.toggle("hidden", !show);
  $("importTools").classList.toggle("hidden", show);
}

function unlockImport(event) {
  event.preventDefault();
  const secret = $("adminSecret").value.trim();
  if (!secret) {
    $("secretError").textContent = "Enter the admin secret.";
    return;
  }
  localStorage.setItem(secretStorage, secret);
  $("secretError").textContent = "";
  showImportGate(false);
}

$("secretForm").addEventListener("submit", unlockImport);
$("lockImport").addEventListener("click", () => {
  localStorage.removeItem(secretStorage);
  $("adminSecret").value = "";
  showImportGate(true);
});
$("csvFile").addEventListener("change", (event) => chooseFile(event.target.files[0]));
$("dropZone").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("dropZone").classList.add("active");
});
$("dropZone").addEventListener("drop", (event) => {
  event.preventDefault();
  chooseFile(event.dataTransfer.files[0]);
});
$("importButton").addEventListener("click", importRows);
$("cancelPreview").addEventListener("click", () => {
  selectedFile = null;
  parsedRows = [];
  $("previewArea").classList.add("hidden");
});

if (localStorage.getItem(secretStorage)) {
  showImportGate(false);
} else {
  showImportGate(true);
}
