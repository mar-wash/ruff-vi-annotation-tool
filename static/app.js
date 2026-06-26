const terms = ["anh", "chị", "cô", "chú", "ông", "bà", "em", "nó", "hắn", "chanh"];
const storage = {
  queue: (username) => `ruffvi_queue_${username}`,
  skipWarning: "ruffvi_skip_warning_shown",
};

let username = "";
let instances = [];
let instanceById = new Map();
let queue = [];
let completed = [];
let counts = { total: 0, saved: 0, submitted: 0, remaining: 0 };
let position = 0;
let sessionStarted = new Date();

const $ = (id) => document.getElementById(id);

function api(path, options = {}) {
  return fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }).then(async (response) => {
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
  });
}

function show(el, visible = true) {
  el.classList.toggle("hidden", !visible);
}

function setProgress() {
  const total = counts.total || 0;
  const saved = counts.saved || 0;
  const submitted = counts.submitted || 0;
  const remaining = Math.max(total - saved - submitted, 0);
  const annotated = saved + submitted;
  $("progressLabel").textContent = `${annotated} of ${total} annotated`;
  $("progressCounts").textContent = `${submitted} submitted · ${saved} saved · ${remaining} remaining`;
  $("submittedSegment").style.width = total ? `${(submitted / total) * 100}%` : "0";
  $("savedSegment").style.width = total ? `${(saved / total) * 100}%` : "0";
  $("remainingSegment").style.width = total ? `${(remaining / total) * 100}%` : "100%";
  document.querySelector(".segmented").title = `${remaining} remaining · Session started ${sessionStarted.toLocaleString()}`;
  show($("submitButton"), annotated > 0);
}

function renderTerms() {
  $("answerOptions").innerHTML = terms.map((term) => `
    <label class="termOption">
      <input type="radio" name="answer" value="${term}" required>
      ${term}
    </label>
  `).join("");
}

function renderInstance() {
  const id = queue[position];
  const instance = instanceById.get(id);
  if (!instance) {
    $("introVi").textContent = counts.total ? "All visible instances are complete." : "No instances loaded.";
    $("introEn").textContent = "";
    $("instanceMeta").textContent = "";
    $("distractors").innerHTML = "";
    $("targetVi").textContent = "";
    $("targetEn").textContent = "";
    return;
  }
  $("instanceMeta").textContent = `${position + 1} of ${queue.length} · ${instance.occupation} / ${instance.participant_role} · ${instance.term_set} · D${instance.distractor_level}`;
  $("introVi").textContent = instance.intro_vi;
  $("introEn").textContent = instance.intro_en;
  $("targetVi").textContent = instance.target_vi;
  $("targetEn").textContent = instance.target_en;
  const distractors = [];
  for (let i = 1; i <= Number(instance.distractor_level); i += 1) {
    const vi = instance[`distractor_${i}_vi`];
    const en = instance[`distractor_${i}_en`];
    if (vi) distractors.push(`<div class="distractor"><strong>${vi}</strong><div class="muted">${en || ""}</div></div>`);
  }
  $("distractors").innerHTML = distractors.join("");
  $("annotationForm").reset();
}

function mergeQueue(serverQueue, serverCompleted) {
  const local = JSON.parse(localStorage.getItem(storage.queue(username)) || "[]");
  const serverSet = new Set([...serverQueue, ...serverCompleted]);
  const completedSet = new Set(serverCompleted);
  const kept = local.filter((id) => serverSet.has(id) && !completedSet.has(id));
  const keptSet = new Set(kept);
  const additions = serverQueue.filter((id) => !keptSet.has(id));
  if (local.length && additions.length) {
    $("newInstancesNotice").textContent = `${additions.length} new instances added since your last session.`;
    show($("newInstancesNotice"), true);
  }
  const merged = local.length ? [...kept, ...additions, ...serverCompleted] : [...serverQueue, ...serverCompleted];
  localStorage.setItem(storage.queue(username), JSON.stringify(merged));
  return merged;
}

async function loadForUser() {
  const [queueData, instanceData] = await Promise.all([
    api(`/api/instances/queue?username=${encodeURIComponent(username)}`),
    api("/api/instances"),
  ]);
  instances = instanceData.instances;
  instanceById = new Map(instances.map((item) => [item.id, item]));
  completed = queueData.completed;
  counts = queueData.counts;
  queue = mergeQueue(queueData.queue, queueData.completed);
  position = Math.min(Number(localStorage.getItem(`${storage.queue(username)}_position`) || 0), Math.max(queue.length - 1, 0));
  $("returningBanner").textContent = `Welcome back, ${username}. You have ${counts.remaining} instances remaining.`;
  setProgress();
  renderInstance();
}

async function beginWithUsername(nextUsername) {
  username = nextUsername;
  show($("welcomeModal"), false);
  await loadForUser();
}

async function enterUsername(event) {
  event.preventDefault();
  const nextUsername = $("usernameInput").value.trim();
  $("usernameError").textContent = "";
  if (!/^[a-zA-Z0-9_]{3,24}$/.test(nextUsername)) {
    $("usernameError").textContent = "Use 3-24 letters, numbers, or underscores.";
    return;
  }
  const check = await api("/api/annotators/check", {
    method: "POST",
    body: JSON.stringify({ username: nextUsername }),
  });
  if (check.available) {
    await api("/api/annotators/register", {
      method: "POST",
      body: JSON.stringify({ username: nextUsername }),
    });
  }
  await beginWithUsername(nextUsername);
}

async function saveAnnotation(event) {
  event.preventDefault();
  const instance = instanceById.get(queue[position]);
  if (!instance) return;
  const answer = new FormData($("annotationForm")).get("answer");
  const reasoning = $("reasoning").value.trim();
  const result = await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({ username, instance_id: instance.id, answer, reasoning }),
  });
  counts = result.counts;
  completed = [...new Set([...completed, instance.id])];
  setProgress();
  position = Math.min(position + 1, Math.max(queue.length - 1, 0));
  localStorage.setItem(`${storage.queue(username)}_position`, String(position));
  renderInstance();
}

async function submitAnnotations() {
  const total = counts.total || 0;
  const completedCount = counts.saved + counts.submitted;
  $("submitBody").textContent = `You have completed ${completedCount} of ${total} instances. Submitted annotations are locked and cannot be changed. Unsubmitted work is saved automatically — you can always come back and submit more later.`;
  show($("submitModal"), true);
}

async function confirmSubmit() {
  const result = await api("/api/annotations/submit", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
  counts = result.counts;
  setProgress();
  show($("submitModal"), false);
  $("successBanner").textContent = `✓ ${result.submitted_count} annotations submitted. Thank you, ${username}!`;
  show($("successBanner"), true);
}

renderTerms();
$("usernameForm").addEventListener("submit", enterUsername);
$("annotationForm").addEventListener("submit", saveAnnotation);
$("submitButton").addEventListener("click", submitAnnotations);
$("confirmSubmit").addEventListener("click", confirmSubmit);
$("cancelSubmit").addEventListener("click", () => show($("submitModal"), false));
$("prevInstance").addEventListener("click", () => {
  position = Math.max(0, position - 1);
  localStorage.setItem(`${storage.queue(username)}_position`, String(position));
  renderInstance();
});
$("nextInstance").addEventListener("click", () => {
  position = Math.min(queue.length - 1, position + 1);
  localStorage.setItem(`${storage.queue(username)}_position`, String(position));
  renderInstance();
});
show($("welcomeModal"), true);
