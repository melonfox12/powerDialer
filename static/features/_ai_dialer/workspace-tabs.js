import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export const AI_WORKSPACE_TABS = [
  { id: "desk", label: "Desk", closable: false },
  { id: "playbook", label: "Prompt", closable: false },
  { id: "sandbox", label: "Sandbox", closable: false },
];

const PANEL_IDS = {
  desk: "aiDialerAgent-panel-desk",
  playbook: "aiDialerAgent-panel-playbook",
  sandbox: "aiDialerAgent-panel-sandbox",
};

export function resetWorkspaceTabs() {
  S.aiWorkspaceTabs = AI_WORKSPACE_TABS.map((tab) => ({ ...tab }));
  S.aiWorkspaceActiveTab = "desk";
}

export function ensureWorkspaceTabs() {
  if (!Array.isArray(S.aiWorkspaceTabs) || !S.aiWorkspaceTabs.length) {
    resetWorkspaceTabs();
    return;
  }
  for (const tab of AI_WORKSPACE_TABS) {
    if (!S.aiWorkspaceTabs.some((item) => item.id === tab.id)) {
      S.aiWorkspaceTabs.push({ ...tab });
    }
  }
  if (!S.aiWorkspaceActiveTab) {
    S.aiWorkspaceActiveTab = "desk";
  }
}

export function activateWorkspaceTab(tabId) {
  if (!S.aiWorkspaceTabs?.some((tab) => tab.id === tabId)) return;
  S.aiWorkspaceActiveTab = tabId;
  paintWorkspaceTabs();
}

export function paintWorkspaceTabs() {
  const tablist = byId("aiDialerAgent-workspaceTablist");
  if (!tablist) return;
  ensureWorkspaceTabs();
  tablist.replaceChildren();
  for (const tab of S.aiWorkspaceTabs) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ai-workspace-tab";
    button.id = `aiDialerAgent-tab-${tab.id}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", S.aiWorkspaceActiveTab === tab.id ? "true" : "false");
    button.dataset.tabId = tab.id;
    const labelNode = document.createElement("span");
    labelNode.textContent = tab.label;
    button.append(labelNode);
    if (S.aiWorkspaceActiveTab === tab.id) {
      button.classList.add("is-active");
    }
    button.addEventListener("click", () => activateWorkspaceTab(tab.id));
    tablist.append(button);
  }
  for (const [tabId, panelId] of Object.entries(PANEL_IDS)) {
    const panel = byId(panelId);
    if (!panel) continue;
    const show = S.aiWorkspaceActiveTab === tabId;
    panel.hidden = !show;
    panel.classList.toggle("is-active", show);
  }
}

export function bindWorkspaceTabs() {
  resetWorkspaceTabs();
  paintWorkspaceTabs();
}
