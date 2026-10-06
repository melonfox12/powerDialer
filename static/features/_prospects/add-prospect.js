import { postJson } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { STATUS_KEYS, STATUS_LABELS, byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { importedColumns } from "./query.js";
import { render } from "../../js/views/render.js";

const STANDARD_FIELDS = [
  ["name", "Prospect", "text", ""],
  ["business", "Company", "text", ""],
  ["phone", "Phone Number", "tel", ""],
  ["timezone", "Timezone", "text", "Eastern, Central, Pacific…"],
];

export function bindAddProspect() {
  byId("addProspectButton").addEventListener("click", openAddProspectDialog);
  byId("closeAddProspect").addEventListener("click", closeAddProspectDialog);
  byId("cancelAddProspect").addEventListener("click", closeAddProspectDialog);
  byId("addProspectDialog").addEventListener("click", (event) => {
    if (event.target === byId("addProspectDialog")) closeAddProspectDialog();
  });
  byId("addProspectForm").addEventListener("submit", (event) => {
    event.preventDefault();
    saveProspect();
  });
}

function openAddProspectDialog() {
  const fields = byId("addProspectFields");
  fields.replaceChildren();
  for (const [name, label, type, placeholder] of STANDARD_FIELDS) {
    fields.append(textField(name, label, { type, placeholder, required: name === "phone" }));
  }
  for (const column of importedColumns()) {
    fields.append(textField(`extra:${column}`, column, { extra: column }));
  }
  fields.append(statusField());
  fields.append(textField("transcript", "Call transcript", { multiline: true }));
  const error = byId("addProspectError");
  error.hidden = true;
  error.textContent = "";
  byId("addProspectDialog").showModal();
  fields.querySelector("input")?.focus();
}

function closeAddProspectDialog() {
  byId("addProspectDialog").close();
}

function textField(name, label, options = {}) {
  const wrap = document.createElement("label");
  wrap.className = "form-field";
  const title = document.createElement("span");
  title.textContent = label;
  const input = document.createElement(options.multiline ? "textarea" : "input");
  input.name = name;
  input.dataset.prospectField = name;
  if (options.extra) input.dataset.extra = options.extra;
  if (options.multiline) {
    input.rows = 3;
    input.maxLength = 4000;
    input.placeholder = "Optional";
  } else {
    input.type = options.type || "text";
    input.autocomplete = "off";
    if (options.placeholder) input.placeholder = options.placeholder;
    if (options.required) input.required = true;
  }
  wrap.append(title, input);
  return wrap;
}

function statusField() {
  const wrap = document.createElement("label");
  wrap.className = "form-field";
  const title = document.createElement("span");
  title.textContent = "Call status";
  const select = document.createElement("select");
  select.name = "status";
  select.dataset.prospectField = "status";
  for (const value of STATUS_KEYS) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = STATUS_LABELS[value];
    select.append(option);
  }
  wrap.append(title, select);
  return wrap;
}

function fieldValue(name) {
  const input = byId("addProspectForm").elements.namedItem(name);
  return input ? String(input.value || "").trim() : "";
}

async function saveProspect() {
  const button = byId("saveAddProspect");
  const error = byId("addProspectError");
  const fields = {};
  for (const input of byId("addProspectFields").querySelectorAll("[data-extra]")) {
    const value = input.value.trim();
    if (value) fields[input.dataset.extra] = value;
  }
  button.disabled = true;
  error.hidden = true;
  try {
    const result = await postJson("/api/leads", {
      name: fieldValue("name"),
      business: fieldValue("business"),
      phone: fieldValue("phone"),
      timezone: fieldValue("timezone"),
      status: fieldValue("status") || "new",
      transcript: fieldValue("transcript"),
      fields,
    });
    Object.assign(state, result.state || {});
    closeAddProspectDialog();
    render();
    const lead = result.lead || {};
    showToast(`${lead.name || lead.phone || "Prospect"} added`);
  } catch (saveError) {
    error.hidden = false;
    error.textContent = saveError?.message || "Could not add that prospect.";
  } finally {
    button.disabled = false;
  }
}
