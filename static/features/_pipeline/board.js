import { postJson } from "../../_core/api.js";
import { applyMutationPayload } from "../../_core/sync-state.js";
import { state, S } from "../../_core/state.js";
import {
  CRM_STATUS_LABELS,
  PIPELINE_DIALED_STEP,
  PIPELINE_SEND_INFO_STEP,
  PIPELINE_STEP_KEYS,
  PIPELINE_STEPS,
  byId,
  callbackCountdown,
  initials,
  pipelineCountdown,
  pipelineReadyAt,
} from "../../_core/format.js";
import { renderTranscriptEntries } from "../../_core/transcript.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { leadNotes, persistLeadNotes } from "../../_core/notes.js";
import { createPipelineCrmStatusMenu, pipelineCrmStatusMenuOpen } from "./crm-status-menu.js";
import { showToast } from "../../_core/notify.js";
import { setDashboardTab } from "../../_core/navigation.js";
import { render } from "../../core.js";

let draggedLeadId = null;
let lastPipelineBoardSignature = null;

const PIPELINE_CARD_STATE_CLASSES = [
  "pipeline-card-state-ready",
  "pipeline-card-state-callback-ready",
  "pipeline-card-state-waiting",
  "pipeline-card-state-disqualified",
  "pipeline-card-state-booked",
];

function openPipelinePanelIds(className) {
  return new Set(
    [...document.querySelectorAll(`${className}[open]`)]
      .map((node) => node.closest(".pipeline-card")?.dataset.leadId)
      .filter(Boolean),
  );
}

function pipelineStepIndex(stepKey) {
  const index = PIPELINE_STEPS.findIndex((item) => item.key === stepKey);
  return index >= 0 ? index : -1;
}

function isForwardPipelineMove(fromStep, toStep) {
  const from = pipelineStepIndex(fromStep);
  const to = pipelineStepIndex(toStep);
  if (from < 0 || to < 0) return false;
  return to > from;
}

function forwardMoveBlocked(lead, fromStep, toStep) {
  if (!isForwardPipelineMove(fromStep, toStep)) return false;
  return pipelineCardVisualState(lead, fromStep) === "waiting";
}

function isWaitingForNextPipelineStep(lead, step, now = Date.now()) {
  if (step === PIPELINE_SEND_INFO_STEP) return false;
  if (step === PIPELINE_DIALED_STEP && lead?.status === "call" && lead.scheduled_until) {
    const callbackDue = Date.parse(lead.scheduled_until);
    if (!Number.isNaN(callbackDue) && now < callbackDue) return true;
    return false;
  }
  const enteredAt = pipelineStepEnteredAt(lead, step);
  const stepDue = Date.parse(pipelineReadyAt(step, enteredAt));
  return !Number.isNaN(stepDue) && now < stepDue;
}

export function pipelineCardVisualState(lead, step, now = Date.now()) {
  const status = lead?.status;
  if (status === "disqualified" || status === "no_answer_disqualified") return "disqualified";
  if (status === "booked") return "booked";
  if ((status === "send_info" || status === "call") && isWaitingForNextPipelineStep(lead, step, now)) {
    return "waiting";
  }
  if (status === "call") return "callback-ready";
  if (status === "send_info") return "ready";
  return "waiting";
}

function pipelineTimerLabel(lead, step, enteredAt, now = Date.now()) {
  if (step === PIPELINE_DIALED_STEP && lead.status === "call") {
    if (!lead.scheduled_until) return "Callback — ready to dial";
    const due = Date.parse(lead.scheduled_until);
    if (Number.isNaN(due)) return "Callback — ready to dial";
    if (now >= due) return "Callback — ready to dial";
    return `Callback ${callbackCountdown(lead.scheduled_until, now)}`;
  }
  return pipelineCountdown(step, enteredAt, now);
}

function applyPipelineCardState(card, lead, step, now = Date.now()) {
  const visual = pipelineCardVisualState(lead, step, now);
  card.classList.remove(...PIPELINE_CARD_STATE_CLASSES);
  card.classList.add(`pipeline-card-state-${visual}`);
  card.dataset.pipelineVisualState = visual;
}

function openProspectInTable(lead) {
  const search = byId("searchInput");
  if (search) search.value = lead.name || lead.phone || "";
  setDashboardTab("prospects");
  render();
}

function stopCardBubble(node) {
  for (const eventName of ["click", "mousedown", "pointerdown"]) {
    node.addEventListener(eventName, (event) => event.stopPropagation());
  }
  node.addEventListener("dragstart", (event) => event.stopPropagation());
}

function sendInfoEnteredAt(lead) {
  const history = lead.status_history || [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].to_status === "send_info") return history[index].changed_at;
  }
  return lead.created_at || null;
}

function callbackEnteredAt(lead) {
  const history = lead.status_history || [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].to_status === "call") return history[index].changed_at;
  }
  return lead.scheduled_until || lead.created_at || null;
}

export function effectivePipelineStep(lead) {
  if (lead.status === "call") return PIPELINE_DIALED_STEP;
  const stored = String(lead.pipeline_step || "").trim();
  if (PIPELINE_STEP_KEYS.includes(stored)) {
    if (lead.status === "send_info" && stored === PIPELINE_DIALED_STEP) {
      return PIPELINE_SEND_INFO_STEP;
    }
    return stored;
  }
  if (lead.status === "send_info") return PIPELINE_SEND_INFO_STEP;
  if (lead.status === "booked") {
    const history = lead.pipeline_history || [];
    if (history.length) return history[history.length - 1].step;
    return PIPELINE_SEND_INFO_STEP;
  }
  return null;
}

export function pipelineStepEnteredAt(lead, step) {
  const storedStep = String(lead.pipeline_step || "").trim();
  if (storedStep === step && lead.pipeline_step_entered_at) {
    return lead.pipeline_step_entered_at;
  }
  const history = lead.pipeline_history || [];
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (history[index].step === step) return history[index].entered_at;
  }
  if (step === PIPELINE_SEND_INFO_STEP && lead.status === "send_info") {
    return sendInfoEnteredAt(lead);
  }
  if (step === PIPELINE_DIALED_STEP && lead.status === "call") {
    return callbackEnteredAt(lead);
  }
  return null;
}

function pipelineLeads() {
  return state.leads.filter((lead) => {
    if (lead.status === "call") return true;
    if (lead.status === "send_info") return true;
    if (lead.status === "booked") return true;
    if (String(lead.pipeline_step || "").trim()) return true;
    if ((lead.pipeline_history || []).length > 0) return true;
    return false;
  });
}

export function pipelineBoardSignature() {
  return pipelineLeads().map((lead) => {
    const step = effectivePipelineStep(lead) || "";
    return [
      lead.id,
      lead.status,
      step,
      lead.pipeline_step_entered_at,
      lead.scheduled_until,
      pipelineStepEnteredAt(lead, step),
      leadNotes(lead),
      lead.transcript?.length || 0,
    ].join("|");
  }).join("\n");
}

function pipelineBoardBusy() {
  const board = byId("pipelineBoard");
  if (document.activeElement?.closest?.(".pipeline-card-notes-editor")) return true;
  if (pipelineCrmStatusMenuOpen()) return true;
  return false;
}

function sortLeadsInStep(leads, step) {
  return [...leads].sort((left, right) => {
    const leftAt = Date.parse(pipelineStepEnteredAt(left, step) || "") || 0;
    const rightAt = Date.parse(pipelineStepEnteredAt(right, step) || "") || 0;
    if (leftAt !== rightAt) return leftAt - rightAt;
    return String(left.name || left.phone).localeCompare(String(right.name || right.phone));
  });
}

function buildCard(lead, step, notesOpen, statusOpen, transcriptOpen) {
  const card = document.createElement("article");
  card.className = "pipeline-card";
  card.draggable = true;
  card.dataset.leadId = lead.id;
  card.dataset.pipelineStep = step;
  card.setAttribute("role", "listitem");

  const enteredAt = pipelineStepEnteredAt(lead, step);
  const readyAt = pipelineReadyAt(step, enteredAt);
  if (readyAt) card.dataset.pipelineReadyAt = readyAt;
  applyPipelineCardState(card, lead, step);

  const avatar = document.createElement("span");
  avatar.className = "pipeline-card-avatar";
  avatar.textContent = initials(lead.name || lead.business);

  const body = document.createElement("div");
  body.className = "pipeline-card-body";
  const title = document.createElement("strong");
  title.className = "pipeline-card-title";
  title.textContent = lead.name || lead.business || "Prospect";
  title.tabIndex = 0;
  title.setAttribute("role", "button");
  title.addEventListener("click", (event) => {
    event.stopPropagation();
    openProspectInTable(lead);
  });
  title.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openProspectInTable(lead);
    }
  });
  const meta = document.createElement("span");
  meta.className = "pipeline-card-meta";
  meta.textContent = [lead.business, formatPhoneNumber(lead.phone)].filter(Boolean).join(" · ");
  body.append(title, meta);

  const timer = document.createElement("span");
  timer.className = "pipeline-card-timer";
  timer.dataset.pipelineTimer = "true";
  timer.textContent = pipelineTimerLabel(lead, step, enteredAt);
  if (step === PIPELINE_DIALED_STEP && lead.status === "call" && lead.scheduled_until) {
    timer.dataset.callbackUntil = lead.scheduled_until;
    timer.dataset.callbackPrefix = "Callback ";
  }

  const entered = document.createElement("time");
  entered.className = "pipeline-card-entered";
  if (enteredAt) {
    entered.dateTime = enteredAt;
    const stamp = new Date(enteredAt);
    if (!Number.isNaN(stamp.getTime())) {
      entered.textContent = `In step ${stamp.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })}`;
    }
  }

  const statusLabel = CRM_STATUS_LABELS[lead.status] || lead.status || "Status";
  const statusDetails = document.createElement("details");
  statusDetails.className = "pipeline-card-status";
  statusDetails.open = statusOpen;
  const statusSummary = document.createElement("summary");
  statusSummary.textContent = `Status · ${statusLabel}`;
  const statusBody = document.createElement("div");
  statusBody.className = "pipeline-card-status-body";
  const statusMenu = createPipelineCrmStatusMenu(lead, card);
  statusBody.append(statusMenu);
  statusDetails.append(statusSummary, statusBody);
  stopCardBubble(statusDetails);
  stopCardBubble(statusSummary);
  stopCardBubble(statusMenu);

  const notesText = leadNotes(lead);
  const notesDetails = document.createElement("details");
  notesDetails.className = "pipeline-card-notes";
  notesDetails.open = notesOpen;
  const notesSummary = document.createElement("summary");
  notesSummary.textContent = notesText ? "Notes" : "Notes (empty)";

  const notesContent = document.createElement("div");
  notesContent.className = "pipeline-card-notes-content";

  const notesView = document.createElement("p");
  notesView.className = "pipeline-card-notes-body";
  notesView.textContent = notesText || "No notes yet.";

  const notesActions = document.createElement("div");
  notesActions.className = "pipeline-card-notes-actions";

  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "button button-quiet pipeline-card-notes-edit";
  editButton.textContent = "Edit";

  const freshLead = () => state.leads.find((item) => item.id === lead.id) || lead;

  const clearEditor = () => {
    for (const node of notesContent.querySelectorAll(".pipeline-card-notes-editor, .pipeline-card-notes-edit-actions")) {
      node.remove();
    }
  };

  const showReadNotes = () => {
    clearEditor();
    const text = leadNotes(freshLead());
    notesView.textContent = text || "No notes yet.";
    notesSummary.textContent = text ? "Notes" : "Notes (empty)";
    notesView.hidden = false;
    editButton.hidden = false;
  };

  const startEditNotes = () => {
    clearEditor();
    notesView.hidden = true;
    editButton.hidden = true;

    const editor = document.createElement("textarea");
    editor.className = "pipeline-card-notes-editor";
    editor.value = leadNotes(freshLead());
    editor.rows = 3;
    editor.placeholder = "Add notes…";
    editor.setAttribute("aria-label", `Notes for ${lead.name || lead.business || "prospect"}`);

    const editActions = document.createElement("div");
    editActions.className = "pipeline-card-notes-edit-actions";

    const saveButton = document.createElement("button");
    saveButton.type = "button";
    saveButton.className = "button button-primary";
    saveButton.textContent = "Save";

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "button button-quiet";
    cancelButton.textContent = "Cancel";

    cancelButton.addEventListener("click", () => showReadNotes());
    saveButton.addEventListener("click", async () => {
      saveButton.disabled = true;
      cancelButton.disabled = true;
      const ok = await persistLeadNotes(freshLead(), editor.value, editor);
      if (ok) {
        showReadNotes();
        render();
      } else {
        saveButton.disabled = false;
        cancelButton.disabled = false;
      }
    });

    editActions.append(saveButton, cancelButton);
    notesContent.append(editor, editActions);
    stopCardBubble(editor);
    stopCardBubble(editActions);
    for (const button of [saveButton, cancelButton]) stopCardBubble(button);
    editor.focus();
  };

  editButton.addEventListener("click", () => startEditNotes());
  notesActions.append(editButton);
  notesContent.append(notesView, notesActions);

  notesDetails.addEventListener("toggle", () => {
    if (!notesDetails.open) showReadNotes();
  });

  notesDetails.append(notesSummary, notesContent);
  stopCardBubble(notesDetails);
  stopCardBubble(notesSummary);
  stopCardBubble(notesContent);
  stopCardBubble(notesView);
  stopCardBubble(notesActions);
  stopCardBubble(editButton);

  const transcriptCount = lead.transcript?.length || 0;
  const transcriptDetails = document.createElement("details");
  transcriptDetails.className = "pipeline-card-transcript";
  transcriptDetails.open = transcriptOpen;
  const transcriptSummary = document.createElement("summary");
  transcriptSummary.textContent = transcriptCount
    ? `Call transcript · ${transcriptCount}`
    : "Call transcript (empty)";
  const transcriptBody = document.createElement("div");
  transcriptBody.className = "pipeline-card-transcript-body";
  renderTranscriptEntries(
    transcriptBody,
    lead.transcript || [],
    "No transcript has been captured for this prospect.",
  );
  transcriptDetails.append(transcriptSummary, transcriptBody);
  stopCardBubble(transcriptDetails);
  stopCardBubble(transcriptSummary);
  stopCardBubble(transcriptBody);

  card.append(avatar, body, timer, entered, statusDetails, transcriptDetails, notesDetails);

  card.addEventListener("dragstart", (event) => {
    if (event.target.closest(".pipeline-card-notes, .pipeline-card-status, .pipeline-card-transcript, .pipeline-crm-status-list")) {
      event.preventDefault();
      return;
    }
    draggedLeadId = lead.id;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", lead.id);
  });
  card.addEventListener("dragend", () => {
    draggedLeadId = null;
    card.classList.remove("is-dragging");
    for (const column of document.querySelectorAll(".pipeline-column")) {
      column.classList.remove("is-drop-target");
    }
  });
  return card;
}

function bindColumnDrop(column, stepKey) {
  column.addEventListener("dragover", (event) => {
    if (!draggedLeadId) return;
    const lead = state.leads.find((item) => item.id === draggedLeadId);
    const fromStep = lead ? effectivePipelineStep(lead) : null;
    if (lead && fromStep && forwardMoveBlocked(lead, fromStep, stepKey)) {
      event.dataTransfer.dropEffect = "none";
      column.classList.remove("is-drop-target");
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    column.classList.add("is-drop-target");
  });
  column.addEventListener("dragleave", (event) => {
    if (event.currentTarget.contains(event.relatedTarget)) return;
    column.classList.remove("is-drop-target");
  });
  column.addEventListener("drop", async (event) => {
    event.preventDefault();
    column.classList.remove("is-drop-target");
    const leadId = event.dataTransfer.getData("text/plain") || draggedLeadId;
    if (!leadId) return;
    const lead = state.leads.find((item) => item.id === leadId);
    if (!lead) return;
    const storedStep = String(lead.pipeline_step || "").trim();
    const previous = effectivePipelineStep(lead);
    if (previous === stepKey && storedStep === stepKey) return;
    if (!storedStep && stepKey === PIPELINE_SEND_INFO_STEP && previous === PIPELINE_SEND_INFO_STEP && lead.status === "send_info") {
      return;
    }
    if (stepKey === PIPELINE_DIALED_STEP && lead.status === "call" && previous === PIPELINE_DIALED_STEP) {
      return;
    }
    const fromStep = effectivePipelineStep(lead);
    if (forwardMoveBlocked(lead, fromStep, stepKey)) {
      showToast("Finish the step timer before moving forward.", true);
      return;
    }
    column.classList.add("is-saving");
    try {
      const result = await postJson(`/api/leads/${encodeURIComponent(leadId)}/pipeline`, { step: stepKey });
      await applyMutationPayload(result);
      render();
      const label = PIPELINE_STEPS.find((item) => item.key === stepKey)?.label || stepKey;
      showToast(`${lead.name || lead.phone}: ${label}`);
    } catch (error) {
      showToast(error.message, true);
    } finally {
      column.classList.remove("is-saving");
    }
  });
}

export function renderPipelineBoard() {
  if (S.dashboardTab !== "pipeline") return;
  const board = byId("pipelineBoard");
  const empty = byId("pipelineBoardEmpty");
  if (!board) return;

  const leads = pipelineLeads();
  const openNotes = openPipelinePanelIds(".pipeline-card-notes");
  const openStatus = openPipelinePanelIds(".pipeline-card-status");
  const openTranscript = openPipelinePanelIds(".pipeline-card-transcript");
  byId("pipelineBoardSummary").textContent = leads.length === 1 ? "1 on board" : `${leads.length} on board`;
  empty.hidden = leads.length > 0;
  board.hidden = leads.length === 0;
  board.replaceChildren();

  for (const step of PIPELINE_STEPS) {
    const column = document.createElement("section");
    column.className = "pipeline-column";
    column.dataset.pipelineStep = step.key;

    const head = document.createElement("header");
    head.className = "pipeline-column-head";
    const title = document.createElement("h3");
    title.textContent = step.label;
    const count = document.createElement("span");
    count.className = "pipeline-column-count";
    const inStep = sortLeadsInStep(
      leads.filter((lead) => effectivePipelineStep(lead) === step.key),
      step.key,
    );
    count.textContent = String(inStep.length);
    const wait = document.createElement("span");
    wait.className = "pipeline-column-wait";
    wait.textContent = step.key === "any_channel"
      ? "~60–90 day cycle"
      : step.key === PIPELINE_DIALED_STEP
        ? "2h callback queue"
        : step.key === PIPELINE_SEND_INFO_STEP
          ? "No wait to Email 1"
          : "~1–2 days to next step";
    head.append(title, count, wait);

    const list = document.createElement("div");
    list.className = "pipeline-column-list";
    list.setAttribute("role", "list");
    for (const lead of inStep) {
      list.append(buildCard(
        lead,
        step.key,
        openNotes.has(lead.id),
        openStatus.has(lead.id),
        openTranscript.has(lead.id),
      ));
    }

    column.append(head, list);
    bindColumnDrop(list, step.key);
    bindColumnDrop(column, step.key);
    board.append(column);
  }
}

export function tickPipelineTimers() {
  const now = Date.now();
  for (const node of document.querySelectorAll("[data-pipeline-timer]")) {
    const card = node.closest(".pipeline-card");
    if (!card) continue;
    const step = card.dataset.pipelineStep;
    const lead = state.leads.find((item) => item.id === card.dataset.leadId);
    if (!lead) continue;
    const enteredAt = pipelineStepEnteredAt(lead, step);
    if (step === PIPELINE_DIALED_STEP && lead.status === "call" && lead.scheduled_until) {
      node.textContent = pipelineTimerLabel(lead, step, enteredAt, now);
      node.dataset.callbackUntil = lead.scheduled_until;
      node.dataset.callbackPrefix = "Callback ";
    } else {
      delete node.dataset.callbackUntil;
      delete node.dataset.callbackPrefix;
      node.textContent = pipelineTimerLabel(lead, step, enteredAt, now);
    }
    const readyAt = pipelineReadyAt(step, enteredAt);
    if (readyAt) card.dataset.pipelineReadyAt = readyAt;
    const visual = pipelineCardVisualState(lead, step, now);
    if (card.dataset.pipelineVisualState !== visual) applyPipelineCardState(card, lead, step, now);
  }
}

export function renderPipelineIfStale() {
  if (S.dashboardTab !== "pipeline") return;
  if (pipelineBoardBusy()) return;
  const board = byId("pipelineBoard");
  const signature = pipelineBoardSignature();
  if (signature === lastPipelineBoardSignature && board?.childElementCount > 0) return;
  renderPipelineBoard();
  lastPipelineBoardSignature = signature;
}

export function renderPipelineBoardAndRemember() {
  renderPipelineBoard();
  lastPipelineBoardSignature = pipelineBoardSignature();
}
