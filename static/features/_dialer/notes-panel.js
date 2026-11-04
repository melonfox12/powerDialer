import { state } from "../../_core/state.js";
import { byId, setText } from "../../_core/format.js";
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

export function renderProspectNotesPanel() {
  bindNotesPanelOnce();
  const panel = byId("prospectNotesPanel");
  const editor = byId("prospectNotesEditor");
  if (!panel || !editor) return;

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
