import { state } from "../../_core/state.js";
import { byId, setText } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { leadNotes, notesLeadLabel, persistLeadNotes } from "../../_core/notes.js";

let bound = false;
let saveTimer = null;

function inFlightDialLead() {
  const call = (state.in_flight || []).find((item) =>
    ["creating", "ringing", "live"].includes(item.state) && (item.lead || item.lead_id),
  );
  if (!call) return null;
  if (call.lead) return call.lead;
  return state.leads.find((item) => item.id === call.lead_id) || null;
}

export function notesPanelLead() {
  return state.active_lead
    || state.pending_outcome
    || inFlightDialLead()
    || state.leads.find((item) => item.id === state.active_lead_id)
    || state.leads.find((item) => item.id === state.pending_outcome_id)
    || null;
}

function bindNotesPanelOnce() {
  if (bound) return;
  bound = true;
  const editor = byId("prospectNotesEditor");
  if (!editor) return;
  editor.addEventListener("input", () => {
    clearTimeout(saveTimer);
    setText("prospectNotesSaveState", "Editing…");
    saveTimer = setTimeout(async () => {
      const lead = notesPanelLead();
      if (!lead || editor.dataset.leadId !== lead.id) return;
      const ok = await persistLeadNotes(lead, editor.value, editor);
      setText("prospectNotesSaveState", ok ? "Saved" : "Save failed");
    }, 700);
  });
  editor.addEventListener("blur", async () => {
    clearTimeout(saveTimer);
    const lead = notesPanelLead();
    if (!lead || editor.dataset.leadId !== lead.id) return;
    const trimmed = editor.value.trim();
    if (trimmed === editor.dataset.savedValue) return;
    setText("prospectNotesSaveState", "Saving…");
    const ok = await persistLeadNotes(lead, trimmed, editor);
    setText("prospectNotesSaveState", ok ? "Saved" : "Save failed");
  });
}

function sendInfoLeads() {
  return (state.leads || [])
    .filter((lead) => lead.status === "send_info")
    .sort((left, right) => {
      const leftLabel = (left.business || left.name || left.phone || "").toLowerCase();
      const rightLabel = (right.business || right.name || right.phone || "").toLowerCase();
      return leftLabel.localeCompare(rightLabel, undefined, { sensitivity: "base" });
    });
}

function sendInfoListFocused() {
  const list = byId("sendInfoProspectsList");
  return Boolean(list?.contains(document.activeElement));
}

function extraFieldLines(lead) {
  const lines = [];
  if (lead.phone) lines.push(`Phone: ${formatPhoneNumber(lead.phone)}`);
  if (lead.timezone) lines.push(`Timezone: ${lead.timezone}`);
  if (lead.business && lead.business !== lead.name) lines.push(`Business: ${lead.business}`);
  for (const [name, value] of Object.entries(lead.fields || {})) {
    if (/^notes?$/i.test(name.trim())) continue;
    const text = String(value || "").trim();
    if (!text) continue;
    lines.push(`${name}: ${text}`);
  }
  return lines;
}

function renderSendInfoProspectsList() {
  const list = byId("sendInfoProspectsList");
  if (!list || sendInfoListFocused()) return;

  const leads = sendInfoLeads();
  setText("sendInfoProspectsCount", leads.length ? `${leads.length} prospect${leads.length === 1 ? "" : "s"}` : "None");

  const openIds = new Set(
    [...list.querySelectorAll("details.send-info-prospect-item[open]")].map((node) => node.dataset.leadId),
  );

  list.replaceChildren();
  if (!leads.length) {
    const empty = document.createElement("p");
    empty.className = "send-info-prospects-empty";
    empty.textContent = "No Send info prospects in your CRM yet.";
    list.append(empty);
    return;
  }

  for (const lead of leads) {
    const item = document.createElement("details");
    item.className = "send-info-prospect-item";
    item.dataset.leadId = lead.id;
    item.open = openIds.has(lead.id);
    item.setAttribute("role", "listitem");

    const summary = document.createElement("summary");
    summary.className = "send-info-prospect-summary";
    const title = document.createElement("span");
    title.className = "send-info-prospect-title";
    title.textContent = lead.business || lead.name || formatPhoneNumber(lead.phone) || "Prospect";
    summary.append(title);
    if (lead.name && lead.business && lead.name !== lead.business) {
      const subtitle = document.createElement("span");
      subtitle.className = "send-info-prospect-subtitle";
      subtitle.textContent = lead.name;
      summary.append(subtitle);
    }
    const notesPreview = leadNotes(lead);
    if (notesPreview) {
      const preview = document.createElement("span");
      preview.className = "send-info-prospect-preview";
      preview.textContent = notesPreview.length > 72 ? `${notesPreview.slice(0, 72)}…` : notesPreview;
      summary.append(preview);
    }
    item.append(summary);

    const body = document.createElement("div");
    body.className = "send-info-prospect-body";
    const notesBlock = document.createElement("p");
    notesBlock.className = "send-info-prospect-notes";
    notesBlock.textContent = notesPreview || "No notes yet.";
    body.append(notesBlock);
    for (const line of extraFieldLines(lead)) {
      const row = document.createElement("p");
      row.className = "send-info-prospect-meta";
      row.textContent = line;
      body.append(row);
    }
    item.append(body);
    list.append(item);
  }
}

export function renderProspectNotesPanel() {
  bindNotesPanelOnce();
  const panel = byId("prospectNotesPanel");
  const editor = byId("prospectNotesEditor");
  if (!panel || !editor) return;
  renderSendInfoProspectsList();

  const lead = notesPanelLead();

  if (!lead) {
    setText("prospectNotesTarget", "No prospect on the line");
    editor.value = "";
    editor.disabled = true;
    editor.dataset.leadId = "";
    editor.dataset.savedValue = "";
    setText("prospectNotesSaveState", "");
    return;
  }

  const fresh = state.leads.find((item) => item.id === lead.id) || lead;
  setText("prospectNotesTarget", notesLeadLabel(fresh));
  editor.disabled = false;
  if (editor.dataset.leadId !== fresh.id) {
    editor.dataset.leadId = fresh.id;
    editor.value = leadNotes(fresh);
    editor.dataset.savedValue = editor.value;
    setText("prospectNotesSaveState", "");
  } else if (document.activeElement !== editor) {
    const stored = leadNotes(fresh);
    if (stored !== editor.dataset.savedValue && stored !== editor.value.trim()) {
      editor.value = stored;
      editor.dataset.savedValue = stored;
    }
  }
}
