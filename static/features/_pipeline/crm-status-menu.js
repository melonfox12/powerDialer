import { state } from "../../_core/state.js";
import {
  CRM_STATUS_LABELS,
  PIPELINE_CRM_STATUS_KEYS,
  STATUS_STYLES,
  crmStatusOptionText,
} from "../../_core/format.js";
import { changeLeadStatus } from "../_prospects/records.js";

let openMenu = null;

function closeOpenMenu() {
  if (!openMenu) return;
  openMenu.list.hidden = true;
  openMenu.wrap.classList.remove("is-open");
  openMenu.trigger.setAttribute("aria-expanded", "false");
  openMenu.card.draggable = true;
  if (openMenu.list.parentElement === document.body) {
    openMenu.wrap.append(openMenu.list);
  }
  openMenu = null;
}

function statusTriggerClass(status) {
  const className = STATUS_STYLES[status]?.className || "neutral";
  return `pipeline-crm-status-trigger status-select status-${className}`;
}

function positionList(trigger, list) {
  const rect = trigger.getBoundingClientRect();
  list.hidden = false;
  document.body.append(list);
  list.style.position = "fixed";
  list.style.left = `${Math.max(8, rect.left)}px`;
  list.style.top = `${rect.bottom + 4}px`;
  list.style.minWidth = `${Math.max(rect.width, 160)}px`;
  const listRect = list.getBoundingClientRect();
  if (listRect.bottom > window.innerHeight - 8) {
    list.style.top = `${Math.max(8, rect.top - listRect.height - 4)}px`;
  }
  if (listRect.right > window.innerWidth - 8) {
    list.style.left = `${Math.max(8, window.innerWidth - listRect.width - 8)}px`;
  }
}

function bindOutsideClose() {
  const onPointerDown = (event) => {
    if (event.target.closest(".pipeline-crm-status-trigger, .pipeline-crm-status-list")) return;
    closeOpenMenu();
  };
  document.addEventListener("pointerdown", onPointerDown);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeOpenMenu();
  });
}

let outsideCloseBound = false;

export function pipelineCrmStatusMenuOpen() {
  return openMenu !== null;
}

/** CRM status control for pipeline cards (native select breaks inside Kanban scroll regions). */
export function createPipelineCrmStatusMenu(lead, card) {
  if (!outsideCloseBound) {
    outsideCloseBound = true;
    bindOutsideClose();
  }

  const wrap = document.createElement("div");
  wrap.className = "pipeline-crm-status";

  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = statusTriggerClass(lead?.status || "new");
  trigger.textContent = CRM_STATUS_LABELS[lead?.status] || lead?.status || "New";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const list = document.createElement("ul");
  list.className = "pipeline-crm-status-list";
  list.hidden = true;
  list.setAttribute("role", "listbox");
  list.setAttribute("aria-label", "CRM status");

  const freshLead = () => state.leads.find((item) => item.id === lead.id) || lead;

  const paintTrigger = () => {
    const current = freshLead();
    const status = current?.status || "new";
    trigger.className = statusTriggerClass(status);
    trigger.textContent = CRM_STATUS_LABELS[status] || status;
  };

  const paintOptions = () => {
    const current = freshLead();
    const currentStatus = current?.status || "new";
    list.replaceChildren();
    for (const value of PIPELINE_CRM_STATUS_KEYS) {
      const item = document.createElement("li");
      item.setAttribute("role", "none");
      const option = document.createElement("button");
      option.type = "button";
      option.className = "pipeline-crm-status-option";
      option.setAttribute("role", "option");
      option.dataset.status = value;
      option.textContent = crmStatusOptionText(value, current);
      option.setAttribute("aria-selected", String(value === currentStatus));
      if (value === currentStatus) option.classList.add("is-current");
      option.addEventListener("click", async (event) => {
        event.stopPropagation();
        if (value === currentStatus) {
          closeOpenMenu();
          return;
        }
        closeOpenMenu();
        card.draggable = true;
        const stub = {
          _value: currentStatus,
          get value() { return this._value; },
          set value(next) { this._value = next; },
          disabled: false,
        };
        await changeLeadStatus(freshLead(), value, stub);
        paintTrigger();
        paintOptions();
        const summary = card.querySelector(".pipeline-card-status summary");
        if (summary) {
          const next = freshLead();
          summary.textContent = `Status · ${CRM_STATUS_LABELS[next?.status] || next?.status || "Status"}`;
        }
      });
      item.append(option);
      list.append(item);
    }
  };

  trigger.addEventListener("pointerdown", (event) => event.stopPropagation());
  trigger.addEventListener("mousedown", (event) => event.stopPropagation());
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    if (openMenu?.wrap === wrap) {
      closeOpenMenu();
      return;
    }
    closeOpenMenu();
    paintOptions();
    positionList(trigger, list);
    wrap.classList.add("is-open");
    trigger.setAttribute("aria-expanded", "true");
    card.draggable = false;
    openMenu = { wrap, list, trigger, card };
    list.querySelector(".pipeline-crm-status-option:not([disabled])")?.focus();
  });

  trigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      trigger.click();
    }
  });

  wrap.append(trigger, list);
  paintTrigger();
  return wrap;
}
