const byId = (id) => document.getElementById(id);
const parseForm = byId("parse-form");
const parseButton = byId("parse-button");
const resetButton = byId("reset-button");
const planButton = byId("plan-button");
const draftButton = byId("draft-button");
const finalizeButton = byId("finalize-button");
const jdInput = byId("jd");
const pastePanel = byId("paste-panel");
const parsedPanel = byId("parsed-panel");
const planPanel = byId("plan-panel");
const wordingPanel = byId("wording-panel");
const finalPanel = byId("final-panel");
const previewPanel = byId("preview-panel");
const layout = document.querySelector(".layout");
const details = byId("details");
const preview = byId("pdf-preview");
const pdfLink = byId("pdf-link");
const reviewFields = ["company", "role", "jd_text"];
const sectionLabels = { experience: "Work Experience", education: "Education", projects: "Academic Projects", skills: "Skills" };
let review = null;
let selectionDraft = null;
let openSuggestionId = null;
let openGroupKeys = new Set();
let previewRequestToken = 0;
const activeRequests = new Set();
let resetVersion = 0;
let hasParsedJob = false;
let parsedSourceText = "";

const stepDetails = {
  paste: [1, "Job description"],
  parsed: [2, "Review parsed job"],
  plan: [3, "Review structure"],
  wording: [4, "Review wording"],
  final: [5, "Finished resume"],
};

function showStep(step, scroll = true) {
  for (const [name, panel] of Object.entries({ paste: pastePanel, parsed: parsedPanel, plan: planPanel, wording: wordingPanel, final: finalPanel })) {
    panel.hidden = name !== step;
  }
  const [number, label] = stepDetails[step];
  byId("wizard-progress-label").textContent = `Step ${number} of 5 · ${label}`;
  byId("wizard-progress-fill").style.width = `${number * 20}%`;
  if (scroll) window.scrollTo({ top: 0, behavior: "smooth" });
}

function showPdf(url, caption) {
  previewRequestToken++;
  preview.src = url;
  pdfLink.href = url;
  byId("preview-caption").textContent = caption;
  previewPanel.hidden = false;
  layout.classList.add("has-preview");
}

function closePdf() {
  previewRequestToken++;
  previewPanel.hidden = true;
  layout.classList.remove("has-preview");
  preview.src = "about:blank";
  pdfLink.removeAttribute("href");
}

function setStatus(message, kind = "") {
  byId("status").textContent = message;
  byId("status").className = `status ${kind}`.trim();
  byId("status").hidden = false;
}

async function postJson(url, body) {
  const controller = new AbortController();
  activeRequests.add(controller);
  try {
    const response = await fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body), signal: controller.signal,
    });
    const result = await response.json();
    if (controller.signal.aborted) throw new DOMException("Request cancelled", "AbortError");
    if (!response.ok) throw new Error([result.error, result.details].filter(Boolean).join("\n\n"));
    return result;
  } finally {
    activeRequests.delete(controller);
  }
}

function showRequestError(error) {
  if (error.name !== "AbortError") setStatus(error.message, "error");
}

function node(tag, className = "", value = "") {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value) element.textContent = value;
  return element;
}

function replace(id, children) { byId(id).replaceChildren(...children); }
function fillParsedFields(parsed) {
  for (const field of reviewFields) byId(field).value = parsed[field] || "";
}
function reviewedFields() {
  return Object.fromEntries(reviewFields.map((field) => [field, byId(field).value.trim()]));
}
function clearReview(message) {
  review = null;
  selectionDraft = null;
  localStorage.removeItem("resumeTailorReviewId");
  localStorage.removeItem("resumeTailorPlanDraft");
  planButton.textContent = "Suggest resume structure";
  draftButton.textContent = "Approve structure and suggest wording";
  resetPreview();
  if (message) setStatus(message);
}
function resetWorkspace() {
  resetVersion++;
  for (const controller of activeRequests) controller.abort();
  clearReview();
  parseForm.reset();
  fillParsedFields({});
  hasParsedJob = false;
  parsedSourceText = "";
  openSuggestionId = null;
  openGroupKeys = new Set();
  byId("pending-only").checked = false;
  replace("review-board", []);
  replace("review-counts", []);
  jdInput.disabled = false;
  parseButton.disabled = false;
  parseButton.textContent = "Parse job posting";
  planButton.disabled = false;
  draftButton.disabled = false;
  finalizeButton.disabled = false;
  byId("preview-draft-button").disabled = false;
  showStep("paste");
  byId("status").hidden = true;
  jdInput.focus({ preventScroll: true });
}
resetButton.addEventListener("click", resetWorkspace);
function resetPreview() {
  closePdf();
  details.hidden = true;
}
function checkRow(text, checked, onChange) {
  const label = node("label", "check-row");
  const input = document.createElement("input");
  input.type = "checkbox";
  input.checked = checked;
  input.addEventListener("change", () => onChange(input.checked));
  label.append(input, node("span", "", text));
  return label;
}
function approvedSelection() {
  const selection = structuredClone(selectionDraft);
  selection.project_bullets = Object.fromEntries(
    selection.project_ids.map((id) => [id, selection.project_bullets[id] || []]),
  );
  return selection;
}
function canReuseWording() {
  return review && ["wording", "final"].includes(review.stage) && Array.isArray(review.suggestions)
    && JSON.stringify(approvedSelection()) === JSON.stringify(review.selection);
}
function updateContinueButtons() {
  planButton.textContent = review ? "Continue to structure" : "Suggest resume structure";
  draftButton.textContent = canReuseWording() ? "Continue to wording review" : "Approve structure and suggest wording";
}
function persistPlanDraft() {
  if (review && selectionDraft) {
    localStorage.setItem("resumeTailorPlanDraft", JSON.stringify({ run_id: review.run_id, selection: selectionDraft }));
  }
  updateContinueButtons();
}
planPanel.addEventListener("change", persistPlanDraft);

function renderPlan() {
  if (!review || !selectionDraft) return;
  const catalog = review.catalog;
  byId("plan-reason").textContent = typeof selectionDraft.plan_reason === "string"
    ? selectionDraft.plan_reason : "Review the proposed order and selections.";

  replace("section-order-controls", selectionDraft.section_order.map((section, index) => {
    const row = node("div", "select-row");
    const label = node("label", "", `${index + 1}. ${index === 3 ? "Fixed last" : "Section"}`);
    const select = document.createElement("select");
    for (const key of (index === 3 ? ["skills"] : ["experience", "education", "projects"])) {
      select.add(new Option(sectionLabels[key], key));
    }
    select.value = section;
    select.disabled = index === 3;
    select.addEventListener("change", () => {
      const old = selectionDraft.section_order[index];
      const other = selectionDraft.section_order.indexOf(select.value);
      selectionDraft.section_order[other] = old;
      selectionDraft.section_order[index] = select.value;
      renderPlan();
    });
    row.append(label, select);
    return row;
  }));

  replace("project-slots", selectionDraft.project_ids.map((projectId, index) => {
    const project = catalog.projects.find((item) => item.id === projectId);
    const card = node("div", "plan-card");
    const row = node("div", "select-row");
    const label = node("label", "", `Project ${index + 1}`);
    const select = document.createElement("select");
    for (const item of catalog.projects) select.add(new Option(`${item.heading} — ${item.name}`, item.id));
    select.value = projectId;
    select.addEventListener("change", () => {
      const chosen = select.value;
      const other = selectionDraft.project_ids.indexOf(chosen);
      if (other >= 0) selectionDraft.project_ids[other] = projectId;
      selectionDraft.project_ids[index] = chosen;
      if (!selectionDraft.project_bullets[chosen]) {
        selectionDraft.project_bullets[chosen] = catalog.projects
          .find((item) => item.id === chosen).bullets.slice(0, 4).map((item) => item.id);
      }
      renderPlan();
    });
    row.append(label, select);
    card.append(row);
    const rationale = selectionDraft.project_reasons?.[projectId];
    if (typeof rationale === "string" && rationale) card.append(node("p", "hint", rationale));
    for (const bullet of project.bullets) {
      card.append(checkRow(bullet.text, (selectionDraft.project_bullets[projectId] || []).includes(bullet.id), (checked) => {
        const current = selectionDraft.project_bullets[projectId] || [];
        selectionDraft.project_bullets[projectId] = checked
          ? [...current, bullet.id] : current.filter((id) => id !== bullet.id);
      }));
    }
    return card;
  }));

  const workRows = [];
  for (const entry of catalog.experience) {
    workRows.push(node("p", "group-label", `${entry.company} — ${entry.role}`));
    for (const bullet of entry.bullets) {
      workRows.push(checkRow(bullet.text, selectionDraft.experience_bullets.includes(bullet.id), (checked) => {
        selectionDraft.experience_bullets = checked
          ? [...selectionDraft.experience_bullets, bullet.id]
          : selectionDraft.experience_bullets.filter((id) => id !== bullet.id);
      }));
    }
  }
  replace("work-bullets", workRows);
  replace("skill-category-controls", catalog.skill_categories.map((name) => checkRow(
    name, selectionDraft.skill_categories.includes(name), (checked) => {
      selectionDraft.skill_categories = checked
        ? [...selectionDraft.skill_categories, name]
        : selectionDraft.skill_categories.filter((item) => item !== name);
    },
  )));
  replace("summary-sentences", catalog.summary_sentences.map((item, index) => {
    const row = checkRow(item.text, index === 0 || selectionDraft.summary_sentence_ids.includes(item.id), (checked) => {
      selectionDraft.summary_sentence_ids = checked
        ? [...selectionDraft.summary_sentence_ids, item.id]
        : selectionDraft.summary_sentence_ids.filter((id) => id !== item.id);
    });
    row.querySelector("input").disabled = index === 0;
    return row;
  }));
  updateContinueButtons();
}

function groupKey(item) {
  return `${item.kind.startsWith("work_") ? "work" : "project"}:${item.label.split(" · ")[0]}`;
}

function groupTitle(item) {
  return `${item.kind.startsWith("work_") ? "Work Experience" : "Project"} · ${item.label.split(" · ")[0]}`;
}

function itemTitle(item) {
  if (item.kind.endsWith("tech")) return "Technology list";
  if (item.kind === "project_title") return "Project title";
  const match = item.id.match(/-b(\d+)$/);
  return match ? `Bullet ${match[1]}` : "Bullet";
}

function changedText(original, suggested, isProposal) {
  const before = original.match(/\S+|\s+/g) || [];
  const after = suggested.match(/\S+|\s+/g) || [];
  const rows = Array.from({ length: before.length + 1 }, () => new Uint16Array(after.length + 1));
  for (let i = before.length - 1; i >= 0; i--) {
    for (let j = after.length - 1; j >= 0; j--) {
      rows[i][j] = before[i] === after[j] ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1]);
    }
  }
  const beforeShared = new Set();
  const afterShared = new Set();
  for (let i = 0, j = 0; i < before.length && j < after.length;) {
    if (before[i] === after[j]) { beforeShared.add(i++); afterShared.add(j++); }
    else if (rows[i + 1][j] >= rows[i][j + 1]) i++;
    else j++;
  }
  const container = node("p", `comparison-text ${isProposal ? "proposed" : ""}`.trim());
  const tokens = isProposal ? after : before;
  const shared = isProposal ? afterShared : beforeShared;
  tokens.forEach((token, index) => {
    if (shared.has(index) || !token.trim()) container.append(document.createTextNode(token));
    else container.append(node(isProposal ? "ins" : "del", "changed-token", token));
  });
  return container;
}

function suggestionRow(item) {
  const decision = review.decisions[item.id];
  const status = decision?.action === "accept" ? "Accepted"
    : decision?.action === "keep" ? "Kept master"
      : decision?.action === "edit" ? "Edited" : "Pending";
  const row = document.createElement("details");
  row.className = "edit-item";
  row.id = `suggestion-${item.id.replace(/[^a-z0-9]/gi, "-")}`;
  row.open = openSuggestionId === item.id;
  row.addEventListener("toggle", () => {
    if (row.open) openSuggestionId = item.id;
    else if (openSuggestionId === item.id) openSuggestionId = null;
  });
  const summary = node("summary", "edit-item-heading");
  const title = node("span", "edit-item-title", itemTitle(item));
  const excerpt = node("span", "edit-item-excerpt", item.reason);
  const badge = node("span", `decision-badge ${decision?.action || "pending"}`, status);
  summary.append(title, excerpt, badge);
  row.append(summary);
  const body = node("div", "edit-item-body");
  body.append(node("p", "field-caption", "Master wording"), changedText(item.original, item.suggested, false));
  body.append(node("p", "field-caption", "AI suggestion"), changedText(item.original, item.suggested, true));
  body.append(node("p", "suggestion-reason", item.reason));
  const evidence = node("details", "evidence");
  evidence.append(node("summary", "", `Supporting master text · ${item.evidence.length} source${item.evidence.length === 1 ? "" : "s"}`));
  for (const source of item.evidence) evidence.append(node("p", "", `${source.id}: ${source.text}`));
  body.append(evidence);
  if (decision?.action === "edit") body.append(node("p", "saved-decision", `Your saved edit: ${decision.text}`));
  const actions = node("div", "action-grid");
  for (const [action, label] of [["accept", "Accept suggestion"], ["keep", "Keep master wording"]]) {
    const button = node("button", action === "keep" ? "secondary-button" : "", label);
    button.type = "button";
    button.addEventListener("click", () => saveDecision(item.id, action));
    actions.append(button);
  }
  body.append(actions);
  const more = node("details", "edit-options");
  more.append(node("summary", "", "Edit wording or ask AI for another version"));
  const edit = document.createElement("textarea");
  edit.className = "edit-field";
  edit.value = decision?.action === "edit" ? decision.text : item.suggested;
  const saveEdit = node("button", "secondary-button", "Save my edit");
  saveEdit.type = "button";
  saveEdit.addEventListener("click", () => saveDecision(item.id, "edit", edit.value));
  more.append(node("label", "", "Your wording"), edit, saveEdit);
  const feedback = document.createElement("input");
  feedback.type = "text";
  feedback.maxLength = 1000;
  feedback.placeholder = "For example: emphasize deployment work";
  const revise = node("button", "text-button", "Suggest another version");
  revise.type = "button";
  revise.addEventListener("click", () => reviseCurrent(item.id, feedback.value));
  more.append(node("label", "", "Guidance for AI (optional)"), feedback, revise);
  body.append(more);
  row.append(body);
  return row;
}

function renderWording() {
  if (!review) return;
  const suggestions = review.suggestions || [];
  const decisions = review.decisions || {};
  const completed = suggestions.filter((item) => decisions[item.id]).length;
  const pending = suggestions.length - completed;
  byId("review-progress").textContent = suggestions.length
    ? `${completed} of ${suggestions.length} edits reviewed. Pending edits use master wording in draft previews.`
    : "The AI suggested no wording changes. Preview or build the approved structure as it stands.";
  const counts = [
    ["Pending", pending, "pending"],
    ["Accepted", Object.values(decisions).filter((item) => item.action === "accept").length, "accept"],
    ["Kept master", Object.values(decisions).filter((item) => item.action === "keep").length, "keep"],
    ["Edited", Object.values(decisions).filter((item) => item.action === "edit").length, "edit"],
  ];
  replace("review-counts", counts.map(([name, count, className]) => node("span", `count-chip ${className}`, `${count} ${name}`)));
  const groups = new Map();
  for (const item of suggestions) {
    const key = groupKey(item);
    if (!groups.has(key)) groups.set(key, { title: groupTitle(item), items: [] });
    groups.get(key).items.push(item);
  }
  if (!openGroupKeys.size && groups.size) openGroupKeys.add(groups.keys().next().value);
  const pendingOnly = byId("pending-only").checked;
  const board = [];
  for (const [key, group] of groups) {
    const shown = pendingOnly ? group.items.filter((item) => !decisions[item.id]) : group.items;
    if (!shown.length) continue;
    const box = document.createElement("details");
    box.className = "review-group";
    box.open = openGroupKeys.has(key) || shown.some((item) => item.id === openSuggestionId);
    box.addEventListener("toggle", () => {
      if (box.open) openGroupKeys.add(key);
      else {
        openGroupKeys.delete(key);
        if (group.items.some((item) => item.id === openSuggestionId)) openSuggestionId = null;
      }
    });
    const groupPending = group.items.filter((item) => !decisions[item.id]).length;
    const heading = node("summary", "review-group-heading");
    heading.append(node("span", "", group.title), node("span", "group-count", `${groupPending} pending · ${group.items.length} edits`));
    box.append(heading, ...shown.map(suggestionRow));
    board.push(box);
  }
  if (!board.length) board.push(node("p", "board-empty", pendingOnly ? "All suggestions have a decision. Show all to revisit them." : "No wording edits were proposed."));
  replace("review-board", board);
  finalizeButton.disabled = pending !== 0;
}

async function saveDecision(id, action, text = "") {
  try {
    const result = await postJson("/api/decision", { run_id: review.run_id, suggestion_id: id, action, text });
    resetPreview();
    review.stage = "wording";
    review.decisions = result.decisions;
    const currentIndex = review.suggestions.findIndex((item) => item.id === id);
    const remaining = review.suggestions.filter((item) => !review.decisions[item.id]);
    if (!remaining.length) byId("pending-only").checked = false;
    openSuggestionId = remaining.find((item) => review.suggestions.indexOf(item) > currentIndex)?.id
      || remaining[0]?.id || id;
    const nextItem = review.suggestions.find((item) => item.id === openSuggestionId);
    if (nextItem) openGroupKeys.add(groupKey(nextItem));
    renderWording();
    if (remaining.length && openSuggestionId) {
      document.getElementById(`suggestion-${openSuggestionId.replace(/[^a-z0-9]/gi, "-")}`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setStatus(remaining.length ? `Decision saved. ${remaining.length} edits remain.` : "All edits reviewed. Preview the draft or build the final PDF.", "success");
  } catch (error) { showRequestError(error); }
}

async function reviseCurrent(id, feedback) {
  setStatus("Requesting a new version for this item…");
  try {
    const result = await postJson("/api/revise", { run_id: review.run_id, suggestion_id: id, feedback });
    resetPreview();
    review.stage = "wording";
    const index = review.suggestions.findIndex((item) => item.id === id);
    review.suggestions[index] = result.suggestion;
    review.decisions = result.decisions;
    openSuggestionId = id;
    renderWording();
    setStatus("New suggestion ready for review.", "success");
  } catch (error) { showRequestError(error); }
}

function showFinal(result) {
  showPdf(result.pdf_url, "Final PDF built from your reviewed decisions.");
  byId("review-note").textContent = result.review_note || "PDF built from your reviewed decisions.";
  byId("summary").textContent = result.summary || "";
  replace("projects", (result.projects || []).map((project) => node("li", "", project.name)));
  replace("warnings", (result.warnings || []).map((warning) => node("p", "", warning)));
  details.hidden = false;
  showStep("final");
  setStatus("Reviewed PDF ready. Inspect the preview before using it.", "success");
}

jdInput.addEventListener("input", () => {
  if (hasParsedJob) {
    hasParsedJob = false;
    parsedSourceText = "";
    clearReview("The pasted text changed. Parse it again before tailoring.");
  }
});
for (const field of reviewFields) {
  byId(field).addEventListener("input", () => {
    if (review) clearReview("The reviewed JD changed. Suggest a new structure to use your edits.");
  });
}
parseForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const jd = jdInput.value.trim();
  if (!jd) { setStatus("Paste a job description first.", "error"); return; }
  if (hasParsedJob && jd === parsedSourceText) {
    closePdf();
    showStep("parsed");
    setStatus("Review the parsed job details before continuing.");
    return;
  }
  hasParsedJob = false;
  parsedSourceText = "";
  clearReview();
  parseButton.disabled = true;
  jdInput.disabled = true;
  parseButton.textContent = "Parsing…";
  setStatus("Extracting the company, job role, and cleaned description.");
  try {
    const result = await postJson("/api/parse", { jd });
    fillParsedFields(result.parsed_jd);
    hasParsedJob = true;
    parsedSourceText = jd;
    showStep("parsed");
    setStatus("Review the cleaned JD, then ask for a structure plan.", "success");
  } catch (error) { showRequestError(error); }
  finally {
    jdInput.disabled = false;
    parseButton.disabled = false;
    parseButton.textContent = hasParsedJob ? "Continue to parsed job" : "Parse job posting";
  }
});
byId("back-to-jd").addEventListener("click", () => {
  parseButton.textContent = hasParsedJob ? "Continue to parsed job" : "Parse job posting";
  closePdf();
  showStep("paste");
  setStatus("Your job posting is preserved. Edit it and parse again if needed.");
});
planButton.addEventListener("click", async () => {
  if (review && selectionDraft) {
    renderPlan();
    closePdf();
    showStep("plan");
    setStatus("Review the structure before continuing.");
    return;
  }
  planButton.disabled = true;
  setStatus("Choosing section order, five projects, and supporting master content. This AI step can take several minutes…");
  try {
    review = await postJson("/api/plan", { parsed_jd: reviewedFields() });
    selectionDraft = structuredClone(review.selection);
    localStorage.setItem("resumeTailorReviewId", review.run_id);
    renderPlan();
    showStep("plan");
    setStatus("Review the structure. Change the order or selections before approving.", "success");
  } catch (error) { showRequestError(error); }
  finally { planButton.disabled = false; }
});
byId("back-to-parsed").addEventListener("click", () => {
  updateContinueButtons();
  closePdf();
  showStep("parsed");
  setStatus("Review the extracted job details. Your structure choices are preserved.");
});
draftButton.addEventListener("click", async () => {
  if (canReuseWording()) {
    renderWording();
    closePdf();
    showStep("wording");
    setStatus("Continue reviewing your saved wording decisions.");
    return;
  }
  draftButton.disabled = true;
  setStatus("Drafting source-linked wording suggestions for your approved structure…");
  try {
    review = await postJson("/api/draft", { run_id: review.run_id, selection: approvedSelection() });
    selectionDraft = structuredClone(review.selection);
    localStorage.removeItem("resumeTailorPlanDraft");
    resetPreview();
    openSuggestionId = review.suggestions[0]?.id || null;
    openGroupKeys = new Set(review.suggestions[0] ? [groupKey(review.suggestions[0])] : []);
    byId("pending-only").checked = false;
    renderWording();
    showStep("wording");
    setStatus(`Review ${review.suggestions.length} wording suggestions by resume entry.`, "success");
  } catch (error) { showRequestError(error); }
  finally { draftButton.disabled = false; }
});
byId("pending-only").addEventListener("change", renderWording);
byId("preview-draft-button").addEventListener("click", async () => {
  const button = byId("preview-draft-button");
  const requestToken = previewRequestToken;
  button.disabled = true;
  setStatus("Building a draft PDF from your current decisions…");
  try {
    const result = await postJson("/api/preview", { run_id: review.run_id });
    if (requestToken !== previewRequestToken) return;
    const url = `${result.pdf_url}?v=${Date.now()}`;
    const caption = result.pending
      ? `Draft PDF · ${result.pending} pending edit${result.pending === 1 ? "" : "s"} still use master wording.`
      : "Draft PDF · all proposed edits have been reviewed.";
    showPdf(url, caption);
    setStatus(result.warnings?.length ? `Draft PDF ready. ${result.warnings.join(" ")}` : "Draft PDF ready for review.", "success");
  } catch (error) { showRequestError(error); }
  finally { button.disabled = false; }
});
byId("back-to-plan").addEventListener("click", () => {
  renderPlan();
  closePdf();
  showStep("plan");
  setStatus("Your wording decisions are preserved while you review the structure.");
});
byId("back-to-wording").addEventListener("click", () => {
  renderWording();
  closePdf();
  showStep("wording");
  setStatus("Your finished PDF and wording decisions are preserved.");
});
byId("view-final-pdf").addEventListener("click", () => {
  if (review?.pdf_url) showPdf(review.pdf_url, "Final PDF built from your reviewed decisions.");
});
byId("master-preview-button").addEventListener("click", () => {
  showPdf("/api/master.pdf", "Master resume for reference.");
});
byId("close-preview").addEventListener("click", closePdf);
finalizeButton.addEventListener("click", async () => {
  finalizeButton.disabled = true;
  setStatus("Building the PDF from your decisions and checking its layout…");
  try {
    const result = await postJson("/api/finalize", { run_id: review.run_id });
    review.stage = "final";
    review.pdf_url = result.pdf_url;
    review.warnings = result.warnings;
    showFinal(result);
  } catch (error) { showRequestError(error); }
  finally { finalizeButton.disabled = false; }
});
async function restoreReview() {
  const runId = localStorage.getItem("resumeTailorReviewId");
  if (!runId) return;
  const version = resetVersion;
  try {
    const response = await fetch(`/api/review/${encodeURIComponent(runId)}`);
    if (version !== resetVersion) return;
    if (response.status === 404) {
      localStorage.removeItem("resumeTailorReviewId");
      localStorage.removeItem("resumeTailorPlanDraft");
      setStatus("The saved review is no longer on the server. Start a new job description; free hosting may clear reviews when it sleeps.", "error");
      return;
    }
    if (!response.ok) throw new Error("Saved review unavailable. Refresh to try again.");
    const restored = await response.json();
    if (version !== resetVersion) return;
    review = restored;
    selectionDraft = structuredClone(review.selection);
    hasParsedJob = true;
    jdInput.value = review.parsed_jd.jd_text;
    parsedSourceText = jdInput.value.trim();
    parseButton.textContent = "Continue to parsed job";
    if (review.stage === "plan") {
      const saved = JSON.parse(localStorage.getItem("resumeTailorPlanDraft") || "null");
      if (saved?.run_id === review.run_id && saved.selection) selectionDraft = saved.selection;
    }
    fillParsedFields(review.parsed_jd);
    if (review.stage === "plan") {
      renderPlan();
      showStep("plan", false);
    }
    if (review.stage === "wording") {
      openSuggestionId = review.suggestions.find((item) => !review.decisions[item.id])?.id || review.suggestions[0]?.id || null;
      openGroupKeys = new Set(openSuggestionId ? [groupKey(review.suggestions.find((item) => item.id === openSuggestionId))] : []);
      renderWording();
      showStep("wording", false);
    }
    if (review.stage === "final" && review.pdf_url) showFinal(review);
    setStatus("Saved review restored. Continue where you left off.", "success");
  } catch (error) { if (version === resetVersion) setStatus(error.message, "error"); }
}
showStep("paste", false);
restoreReview();
