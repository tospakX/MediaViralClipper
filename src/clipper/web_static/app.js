"use strict";

const form = document.querySelector("#job-form");
const source = document.querySelector("#source");
const output = document.querySelector("#output");
const sourceSummary = document.querySelector("#source-summary");
const sourceName = document.querySelector("#source-name");
const sourceNote = document.querySelector("#source-note");
const startButton = document.querySelector("#start-button");
const formError = document.querySelector("#form-error");
const ranker = document.querySelector("#ranker");
const batchTitle = document.querySelector("#batch-title");
const batchCount = document.querySelector("#batch-count");
const batchProgress = document.querySelector("#batch-progress");
const batchDetail = document.querySelector("#batch-detail");
const episodeList = document.querySelector("#episode-list");
const queueSearch = document.querySelector("#queue-search");
const queueFilter = document.querySelector("#queue-filter");
const previewEmpty = document.querySelector("#preview-empty");
const previewContent = document.querySelector("#preview-content");
const previewTitle = document.querySelector("#preview-title");
const selectedSource = document.querySelector("#selected-source");
const resultCount = document.querySelector("#result-count");
const previewPlayer = document.querySelector("#preview-player");
const playerShell = document.querySelector(".player-shell");
const previewMessage = document.querySelector("#preview-message");
const previewLinks = document.querySelector("#preview-links");
const previewClipNumber = document.querySelector("#preview-clip-number");
const previewScore = document.querySelector("#preview-score");
const previewReason = document.querySelector("#preview-reason");
const previewTranscript = document.querySelector("#preview-transcript");
const transcriptToggle = document.querySelector("#transcript-toggle");
const previousClip = document.querySelector("#previous-clip");
const nextClip = document.querySelector("#next-clip");
const clipPosition = document.querySelector("#clip-position");
const clipStrip = document.querySelector("#clip-strip");
const fileBrowser = document.querySelector("#file-browser");
const browserTitle = document.querySelector("#browser-title");
const browserPath = document.querySelector("#browser-path");
const browserList = document.querySelector("#browser-list");
const browserError = document.querySelector("#browser-error");
const browserUp = document.querySelector("#browser-up");
const browserHelp = document.querySelector("#browser-help");
const useFolder = document.querySelector("#use-folder");
const storageKey = "media-viral-clipper-settings-v5";
let pollingTimer = null;
let currentBatch = null;
let currentBrowserPath = null;
let browserMode = "source-folder";
let selectedSourceTotal = 0;
let selectedPreview = null;
let selectedClipIndex = 0;
let selectedFormat = "vertical";

restoreSettings();
toggleLlmFields();
loadSystemReadiness();
localStorage.removeItem("media-viral-clipper-last-batch");
resumeLastBatch();

ranker.addEventListener("change", toggleLlmFields);
form.addEventListener("input", saveSettings);
form.addEventListener("submit", startBatch);
source.addEventListener("change", () => source.value.trim() && selectSource(source.value.trim()));
queueSearch.addEventListener("input", renderQueue);
queueFilter.addEventListener("change", renderQueue);
document.querySelector("#select-folder").addEventListener("click", () => openFileBrowser("source-folder"));
document.querySelector("#select-video").addEventListener("click", () => openFileBrowser("source-video"));
document.querySelector("#change-source").addEventListener("click", () => openFileBrowser("source-folder"));
document.querySelector("#browse-output").addEventListener("click", () => openFileBrowser("output"));
document.querySelector("#close-browser").addEventListener("click", () => fileBrowser.close());
useFolder.addEventListener("click", chooseCurrentFolder);
browserUp.addEventListener("click", () => currentBrowserPath && loadDirectory(currentBrowserPath, true));
fileBrowser.addEventListener("click", (event) => { if (event.target === fileBrowser) fileBrowser.close(); });
document.querySelector("#format-switch").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-format]");
  if (button && !button.disabled) showClip(selectedClipIndex, button.dataset.format);
});
transcriptToggle.addEventListener("click", () => {
  setTranscriptVisible(transcriptToggle.getAttribute("aria-expanded") !== "true");
});
previousClip.addEventListener("click", () => showClip(selectedClipIndex - 1));
nextClip.addEventListener("click", () => showClip(selectedClipIndex + 1));
document.addEventListener("keydown", (event) => {
  if (!selectedPreview || ["INPUT", "SELECT", "TEXTAREA", "VIDEO", "BUTTON"].includes(event.target.tagName)) return;
  if (event.key === "ArrowLeft" && selectedClipIndex > 0) showClip(selectedClipIndex - 1);
  if (event.key === "ArrowRight" && selectedClipIndex < selectedPreview.clips.length - 1) showClip(selectedClipIndex + 1);
});
previewPlayer.addEventListener("error", () => {
  previewMessage.textContent = "This preview could not play. Try Original or download the clip.";
  previewMessage.hidden = false;
});
previewPlayer.addEventListener("loadedmetadata", () => { previewMessage.hidden = true; });

async function loadSystemReadiness() {
  const badge = document.querySelector("#system-badge");
  const label = document.querySelector("#system-label");
  try {
    const response = await fetch("/api/system", { cache: "no-store" });
    const report = await response.json();
    badge.dataset.ready = String(Boolean(report.ready));
    const ollama = (report.checks || []).find((check) => String(check.name).startsWith("Ollama"));
    label.textContent = ollama && ollama.ok ? "Ollama ready" : report.ready ? "Ready · fallback judge" : "Needs setup";
    badge.title = report.summary || label.textContent;
  } catch (_error) {
    badge.dataset.ready = "false";
    label.textContent = "Check unavailable";
  }
}

function restoreSettings() {
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || "{}");
    for (const [name, value] of Object.entries(stored)) {
      const control = form.elements.namedItem(name);
      if (!control) continue;
      if (control.type === "checkbox") control.checked = Boolean(value);
      else control.value = String(value);
    }
  } catch (_error) {
    localStorage.removeItem(storageKey);
  }
}

function saveSettings() {
  const values = {};
  for (const name of ["output", "min_duration", "max_duration", "vertical", "captions", "dry_run", "caption_style", "whisper_model", "language", "device", "hardware_encoding", "workers", "ranker", "llm_base_url", "llm_model"]) {
    const control = form.elements.namedItem(name);
    values[name] = control.type === "checkbox" ? control.checked : control.value;
  }
  localStorage.setItem(storageKey, JSON.stringify(values));
}

function toggleLlmFields() {
  const visible = ranker.value === "openai-compatible";
  document.querySelectorAll(".llm-field").forEach((field) => { field.hidden = !visible; });
}

async function openFileBrowser(mode) {
  browserMode = mode;
  const copy = {
    "source-folder": ["Choose a folder", "Open the folder containing your episodes."],
    "source-video": ["Choose one video", "Open folders, then choose an episode."],
    output: ["Choose output folder", "Choose where finished clips should go."],
  }[mode];
  browserTitle.textContent = copy[0];
  browserHelp.textContent = copy[1];
  useFolder.hidden = mode === "source-video";
  useFolder.textContent = mode === "source-folder" ? "Queue this folder" : "Use this folder";
  fileBrowser.showModal();
  const initial = mode === "output" ? output.value.trim() : source.value.trim();
  await loadDirectory(initial || null);
}

async function loadDirectory(path, useParent = false) {
  browserError.hidden = true;
  browserList.replaceChildren(element("p", "browser-loading", "Opening folder…"));
  try {
    const query = path ? `?path=${encodeURIComponent(path)}` : "";
    const response = await fetch(`/api/files${query}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await responseMessage(response));
    let listing = await response.json();
    if (useParent && listing.parent) {
      const parentResponse = await fetch(`/api/files?path=${encodeURIComponent(listing.parent)}`, { cache: "no-store" });
      if (!parentResponse.ok) throw new Error(await responseMessage(parentResponse));
      listing = await parentResponse.json();
    }
    renderDirectory(listing);
  } catch (error) {
    browserList.replaceChildren();
    browserError.textContent = error.message || "That folder could not be opened.";
    browserError.hidden = false;
  }
}

function renderDirectory(listing) {
  currentBrowserPath = listing.path;
  browserPath.textContent = listing.path;
  browserUp.disabled = !listing.parent;
  const fragment = document.createDocumentFragment();
  for (const directory of listing.directories) {
    const button = browserEntry("folder", directory.name, "Open");
    button.addEventListener("click", () => loadDirectory(directory.path));
    fragment.append(button);
  }
  if (browserMode === "source-video") {
    for (const file of listing.files) {
      const button = browserEntry("video", file.name, "Choose");
      button.addEventListener("click", () => choosePath(file.path));
      fragment.append(button);
    }
  }
  if (!fragment.childNodes.length) fragment.append(element("p", "browser-empty", browserMode === "source-video" ? "No folders or supported videos here." : "No folders here."));
  browserList.replaceChildren(fragment);
}

function browserEntry(kind, name, action) {
  const button = element("button", `browser-entry ${kind}`);
  button.type = "button";
  button.append(element("span", "entry-icon", kind === "folder" ? "▰" : "▶"), element("span", "entry-name", name), element("span", "entry-action", action));
  return button;
}

function chooseCurrentFolder() {
  if (currentBrowserPath) choosePath(currentBrowserPath);
}

async function choosePath(path) {
  if (browserMode === "output") {
    output.value = path;
    output.dispatchEvent(new Event("input", { bubbles: true }));
    fileBrowser.close();
    await loadLibrary();
    return;
  }
  fileBrowser.close();
  await selectSource(path);
}

async function selectSource(path) {
  clearError();
  source.value = path;
  sourceSummary.hidden = false;
  sourceName.textContent = basename(path);
  sourceNote.textContent = "Checking for supported videos…";
  startButton.disabled = true;
  try {
    const response = await fetch(`/api/scan?path=${encodeURIComponent(path)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await responseMessage(response));
    const scan = await response.json();
    source.value = scan.path;
    selectedSourceTotal = scan.total;
    sourceName.textContent = basename(scan.path);
    sourceNote.textContent = scan.kind === "folder" ? `${scan.total} ${scan.total === 1 ? "video" : "videos"} ready to queue` : "1 video ready to queue";
    startButton.disabled = false;
    setIdleButton();
  } catch (error) {
    selectedSourceTotal = 0;
    sourceNote.textContent = "No supported videos found";
    showError(error.message || "That source could not be opened.");
  }
}

async function startBatch(event) {
  event.preventDefault();
  clearError();
  const payload = formPayload();
  if (!payload.source) return showError("Choose a folder or video first.");
  if (payload.min_duration > payload.max_duration) return showError("Minimum length must be shorter than maximum length.");
  setRunning(true);
  batchTitle.textContent = "Building queue";
  batchDetail.textContent = "Adding supported videos in filename order.";
  try {
    const response = await fetch("/api/batches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!response.ok) throw new Error(await responseMessage(response));
    const batch = await response.json();
    sessionStorage.setItem("media-viral-clipper-current-batch", batch.id);
    await pollBatch(batch.id);
  } catch (error) {
    setRunning(false);
    showError(error.message || "The episodes could not be queued.");
    batchTitle.textContent = "Nothing queued";
    batchDetail.textContent = error.message || "Check the source and try again.";
  }
}

function formPayload() {
  const data = new FormData(form);
  const optional = (name) => String(data.get(name) || "").trim() || null;
  return {
    source: optional("source"), output: optional("output") || "~/Downloads/MediaViralClipper",
    min_duration: Number(data.get("min_duration")), max_duration: Number(data.get("max_duration")),
    vertical: data.has("vertical"), captions: data.has("captions"), dry_run: data.has("dry_run"),
    caption_style: data.get("caption_style"), whisper_model: data.get("whisper_model"), language: optional("language"),
    device: data.get("device"), hardware_encoding: data.get("hardware_encoding"), workers: Number(data.get("workers")),
    ranker: data.get("ranker"), llm_base_url: optional("llm_base_url"), llm_model: optional("llm_model"),
  };
}

async function pollBatch(id) {
  if (pollingTimer) clearTimeout(pollingTimer);
  try {
    const response = await fetch(`/api/batches/${encodeURIComponent(id)}`, { cache: "no-store" });
    if (!response.ok) throw new Error(await responseMessage(response));
    currentBatch = await response.json();
    renderBatch();
    if (currentBatch.status === "completed") {
      setRunning(false);
      return;
    }
    pollingTimer = setTimeout(() => pollBatch(id), 1200);
  } catch (error) {
    batchDetail.textContent = `${error.message} Retrying…`;
    pollingTimer = setTimeout(() => pollBatch(id), 2200);
  }
}

function renderBatch() {
  if (!currentBatch) return;
  batchProgress.value = currentBatch.progress;
  batchProgress.textContent = `${currentBatch.progress}%`;
  batchCount.textContent = `${currentBatch.completed + currentBatch.failed} / ${currentBatch.total}`;
  batchTitle.textContent = currentBatch.status === "completed" ? "Queue finished" : "Episodes in progress";
  batchDetail.textContent = currentBatch.failed ? `${currentBatch.completed} ready · ${currentBatch.failed} failed` : `${currentBatch.completed} ready · ${currentBatch.running} processing · ${currentBatch.queued} waiting`;
  renderQueue();
}

function renderQueue() {
  if (!currentBatch) return;
  const query = queueSearch.value.trim().toLowerCase();
  const filter = queueFilter.value;
  const visible = currentBatch.jobs.filter((job) => {
    const matchesText = basename(job.source).toLowerCase().includes(query);
    const matchesStatus = filter === "all" || job.status === filter || (filter === "active" && ["queued", "running"].includes(job.status));
    return matchesText && matchesStatus;
  });
  const fragment = document.createDocumentFragment();
  for (const job of visible) fragment.append(buildEpisodeRow(job));
  if (!visible.length) fragment.append(element("p", "empty-copy", "No episodes match this view."));
  episodeList.replaceChildren(fragment);
}

function buildEpisodeRow(job) {
  const row = element("article", "episode-row");
  row.dataset.status = job.status;
  const copy = element("div", "episode-copy");
  copy.append(element("p", "episode-name", basename(job.source)), element("p", "episode-message", job.error || job.message));
  row.append(element("i", "episode-strip"), copy);
  if (job.status === "completed") {
    const button = element("button", "episode-action", `${job.selections.length} clips · Preview`);
    button.type = "button";
    button.addEventListener("click", () => renderJobPreview(job));
    row.append(button);
  } else {
    row.append(element("span", "episode-meta", job.status === "running" ? `${job.progress}%` : job.status));
  }
  return row;
}

function renderJobPreview(job) {
  const clips = (job.selections || []).map((selection) => {
    const render = (job.renders || []).find((item) => item.clip === selection.rank) || {};
    return {
      rank: selection.rank, duration: selection.candidate.duration, overall: selection.score.overall,
      transcript: selection.candidate.transcript, explanation: selection.score.explanation,
      original: Boolean(render.original), vertical: Boolean(render.vertical), subtitles: Boolean(render.subtitles),
    };
  });
  openPreview({
    name: basename(job.source), detail: job.output_directory || "Analysis complete", clips,
    urlFor: (clip, kind, download = false) => `${artifactUrl(job.id, clip.rank, kind)}${download ? "?download=true" : ""}`,
  });
}

function openPreview(preview, shouldScroll = true) {
  selectedPreview = preview;
  selectedClipIndex = 0;
  previewTitle.textContent = preview.name;
  selectedSource.textContent = preview.detail;
  resultCount.textContent = `${preview.clips.length} ${preview.clips.length === 1 ? "clip" : "clips"}`;
  previewEmpty.hidden = true;
  previewContent.hidden = false;
  renderClipStrip();
  showClip(0);
  if (shouldScroll) document.querySelector("#results").scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
}

function renderClipStrip() {
  const fragment = document.createDocumentFragment();
  selectedPreview.clips.forEach((clip, index) => {
    const button = element("button", "clip-tab");
    button.type = "button";
    button.append(element("strong", "", `Clip ${String(clip.rank).padStart(2, "0")}`), element("span", "", `${Math.round(clip.duration)} sec · ${Math.round(clip.overall * 100)}/100`));
    button.addEventListener("click", () => showClip(index));
    fragment.append(button);
  });
  clipStrip.replaceChildren(fragment);
}

function showClip(index, requestedFormat = null) {
  if (!selectedPreview || !selectedPreview.clips[index]) return;
  selectedClipIndex = index;
  const clip = selectedPreview.clips[index];
  const availableFormat = requestedFormat && clip[requestedFormat] ? requestedFormat : clip.vertical ? "vertical" : clip.original ? "original" : null;
  selectedFormat = availableFormat;
  playerShell.dataset.format = availableFormat || "empty";
  previewPlayer.pause();
  previewMessage.hidden = true;
  if (availableFormat) {
    previewPlayer.hidden = false;
    previewPlayer.src = selectedPreview.urlFor(clip, availableFormat);
    previewPlayer.load();
  } else {
    previewPlayer.removeAttribute("src");
    previewPlayer.load();
    previewPlayer.hidden = true;
    previewMessage.textContent = "Analysis complete. Render video to play this clip.";
    previewMessage.hidden = false;
  }
  previewClipNumber.textContent = `Clip ${String(clip.rank).padStart(2, "0")} · ${Math.round(clip.duration)} sec`;
  previewScore.textContent = `${Math.round(clip.overall * 100)} / 100`;
  previewReason.textContent = clip.explanation;
  previewTranscript.textContent = clip.transcript;
  setTranscriptVisible(false);
  clipPosition.textContent = `${index + 1} / ${selectedPreview.clips.length}`;
  previousClip.disabled = index === 0;
  nextClip.disabled = index === selectedPreview.clips.length - 1;
  clipStrip.querySelectorAll(".clip-tab").forEach((button, buttonIndex) => button.setAttribute("aria-current", String(buttonIndex === index)));
  document.querySelectorAll("#format-switch button").forEach((button) => {
    button.disabled = !clip[button.dataset.format];
    button.setAttribute("aria-pressed", String(button.dataset.format === selectedFormat));
  });
  const links = [];
  if (clip.vertical) links.push(downloadLink(selectedPreview.urlFor(clip, "vertical", true), "Vertical"));
  if (clip.original) links.push(downloadLink(selectedPreview.urlFor(clip, "original", true), "Original"));
  if (clip.subtitles) links.push(downloadLink(selectedPreview.urlFor(clip, "subtitles", true), "SRT"));
  previewLinks.replaceChildren(...links);
}

function setTranscriptVisible(visible) {
  previewTranscript.hidden = !visible;
  transcriptToggle.setAttribute("aria-expanded", String(visible));
  transcriptToggle.querySelector("span").textContent = visible ? "Hide transcript" : "Show transcript";
  transcriptToggle.querySelector("i").textContent = visible ? "−" : "＋";
}

function setRunning(running) {
  startButton.disabled = running;
  startButton.querySelector("span").textContent = running ? "Queue in progress" : selectedSourceTotal ? queueButtonLabel() : "Choose episodes first";
}

function setIdleButton() {
  startButton.querySelector("span").textContent = queueButtonLabel();
}

function queueButtonLabel() {
  return selectedSourceTotal === 1 ? "Queue 1 video" : `Queue ${selectedSourceTotal} videos`;
}

async function resumeLastBatch() {
  const id = sessionStorage.getItem("media-viral-clipper-current-batch");
  if (!id) return;
  try {
    const response = await fetch(`/api/batches/${encodeURIComponent(id)}`, { cache: "no-store" });
    if (!response.ok) return sessionStorage.removeItem("media-viral-clipper-current-batch");
    currentBatch = await response.json();
    renderBatch();
    if (currentBatch.status !== "completed") { setRunning(true); await pollBatch(id); }
  } catch (_error) { /* Completed outputs are restored separately from disk. */ }
}

function artifactUrl(id, rank, kind) { return `/api/jobs/${encodeURIComponent(id)}/clips/${rank}/${kind}`; }
function downloadLink(href, label) { const link = document.createElement("a"); link.href = href; link.textContent = `↓ ${label}`; return link; }
function basename(path) { return String(path).replaceAll("\\", "/").split("/").filter(Boolean).pop() || String(path); }
function element(tag, className, content = null) { const node = document.createElement(tag); node.className = className; if (content !== null) node.textContent = content; return node; }
async function responseMessage(response) { try { const payload = await response.json(); return Array.isArray(payload.detail) ? payload.detail.map((item) => item.msg).join(" ") : payload.detail || `Request failed (${response.status})`; } catch (_error) { return `Request failed (${response.status})`; } }
function showError(message) { formError.textContent = message; formError.hidden = false; }
function clearError() { formError.hidden = true; formError.textContent = ""; }
