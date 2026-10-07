import { postJson } from "../api/client.js";
import { state } from "../store/state.js";
import { STATUS_LABELS, byId } from "../utils/format.js";
import { showToast } from "../utils/notify.js";
import { render } from "../views/render.js";
import { importedColumns } from "../views/prospects-table/query.js";

const TIMEZONES = ["Eastern", "Central", "Mountain", "Pacific", "Alaska", "Hawaii", "Unknown"];
const STATUSES = ["new", "call", "booked", "interested", "disqualified", "do_not_call"];

function fieldLabel(label, control) {
  const wrap = document.createElement("label");
  wrap.className = "form-field";
  const title = document.createElement("span");
  title.textContent = label;
  wrap.append(title, control);
  return wrap;
}

function textInput(id, options = {}) {
  const input = document.createElement("input");
  input.id = id;
  input.autocomplete = "off";
  if (options.required) input.required = true;
  if (options.placeholder) input.placeholder = options.placeholder;
  if (options.type) input.type = options.type;
  return input;
}

function selectInput(id, options, selected) {
  const select = document.createElement("select");
  select.id = id;
  for (const option of options) {
    const item = document.createElement("option");
    item.value = option.value;
    item.textContent = option.label;
    item.selected = option.value === selected;
    select.append(item);
  }
  return select;
}

function timezoneChoices() {
  const extras = [];
  for (const lead of state.leads) {
    const zone = String(lead.timezone || "").trim();
    if (zone && !TIMEZONES.includes(zone) && !extras.includes(zone)) extras.push(zone);
  }
  return [...TIMEZONES, ...extras];
}

function buildFields() {
  const fields = byId("newProspectFields");
  fields.replaceChildren();
  fields.append(
    fieldLabel("Prospect", textInput("newProspectName", { placeholder: "Full name" })),
    fieldLabel("Company", textInput("newProspectCompany", { placeholder: "Company" })),
    fieldLabel("Phone Number", textInput("newProspectPhone", { type: "tel", placeholder: "(555) 555-0100", required: true })),
    fieldLabel("Timezone", selectInput("newProspectTimezone", timezoneChoices().map((zone) => ({ value: zone, label: zone })), "Unknown")),
  );
  for (const column of importedColumns()) {
    const input = textInput("", { placeholder: column });
    input.dataset.extra = column;
    fields.append(fieldLabel(column, input));
  }
  fields.append(
    fieldLabel("Call status", selectInput("newProspectStatus", STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] })), "new")),
  );
  const transcript = document.createElement("textarea");
  transcript.id = "newProspectTranscript";
  transcript.rows = 3;
  transcript.maxLength = 4000;
  transcript.placeholder = "Optional notes from a previous conversation";
  fields.append(fieldLabel("Call transcript", transcript));
}

function extraFields() {
  const fields = {};
  for (const input of byId("newProspectFields").querySelectorAll("[data-extra]")) {
    fields[input.dataset.extra] = input.value;
  }
  return fields;
}

export function openNewProspect() {
  buildFields();
  byId("newProspectDialog").showModal();
  byId("newProspectName").focus();
}

async function submitNewProspect(event) {
  event.preventDefault();
  const submit = byId("saveNewProspect");
  submit.disabled = true;
  try {
    const result = await postJson("/api/leads", {
      name: byId("newProspectName").value,
      business: byId("newProspectCompany").value,
      phone: byId("newProspectPhone").value,
      timezone: byId("newProspectTimezone").value,
      status: byId("newProspectStatus").value,
      transcript: byId("newProspectTranscript").value,
      fields: extraFields(),
    });
    Object.assign(state, result.state || {});
    byId("newProspectDialog").close();
    render();
    const lead = result.lead || {};
    showToast(`${lead.name || lead.phone || "Prospect"} added`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submit.disabled = false;
  }
}

export function bindNewProspect() {
  byId("newProspectButton").addEventListener("click", openNewProspect);
  byId("closeNewProspect").addEventListener("click", () => byId("newProspectDialog").close());
  byId("cancelNewProspect").addEventListener("click", () => byId("newProspectDialog").close());
  byId("newProspectForm").addEventListener("submit", submitNewProspect);
}
