import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

const DESK_TAB = { id: "desk", label: "Desk", closable: false };
const PLAYBOOK_TAB = { id: "playbook", label: "Prompt", closable: true };

export function resetWorkspaceTabs() {
  S.aiWorkspaceTabs = [DESK_TAB];
  S.aiWorkspaceActiveTab = "desk";
  S.aiWorkspacePlaybookOpen = false;
}

export function ensureDeskTab() {
  if (!Array.isArray(S.aiWorkspaceTabs) || !S.aiWorkspaceTabs.length) {
    resetWorkspaceTabs();
  }
  if (!S.aiWorkspaceTabs.some((tab) => tab.id === "desk")) {
    S.aiWorkspaceTabs.unshift(DESK_TAB);
  }
  if (!S.aiWorkspaceActiveTab) {
    S.aiWorkspaceActiveTab = "desk";
  }
}

export function openPlaybookTab() {
  ensureDeskTab();
  S.aiWorkspacePlaybookOpen = true;
  if (!S.aiWorkspaceTabs.some((tab) => tab.id === "playbook")) {
    S.aiWorkspaceTabs.push(PLAYBOOK_TAB);
  }
  S.aiWorkspaceActiveTab = "playbook";
  paintWorkspaceTabs();
}

export function activateWorkspaceTab(tabId) {
  if (!S.aiWorkspaceTabs?.some((tab) => tab.id === tabId)) return;
  S.aiWorkspaceActiveTab = tabId;
  paintWorkspaceTabs();
}

export function closeWorkspaceTab(tabId) {
  if (tabId === "desk") return;
  S.aiWorkspaceTabs = (S.aiWorkspaceTabs || []).filter((tab) => tab.id !== tabId);
  if (tabId === "playbook") {
    S.aiWorkspacePlaybookOpen = false;
  }
  if (S.aiWorkspaceActiveTab === tabId) {
    S.aiWorkspaceActiveTab = "desk";
  }
  paintWorkspaceTabs();
}

export function paintWorkspaceTabs() {
  const tablist = byId("aiDialerAgent-workspaceTablist");
  const deskPanel = byId("aiDialerAgent-panel-desk");
  const playbookPanel = byId("aiDialerAgent-panel-playbook");
  if (!tablist) return;
  ensureDeskTab();
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
    tablist.append(button);
    if (tab.closable) {
      const close = document.createElement("span");
      close.className = "ai-workspace-tab-close";
      close.setAttribute("aria-label", `Close ${tab.label}`);
      close.textContent = "×";
      close.addEventListener("click", (event) => {
        event.stopPropagation();
        closeWorkspaceTab(tab.id);
      });
      button.append(close);
    }
    button.addEventListener("click", () => activateWorkspaceTab(tab.id));
  }
  if (deskPanel) {
    const show = S.aiWorkspaceActiveTab === "desk";
    deskPanel.hidden = !show;
    deskPanel.classList.toggle("is-active", show);
  }
  if (playbookPanel) {
    const showPlaybook = S.aiWorkspacePlaybookOpen && S.aiWorkspaceActiveTab === "playbook";
    playbookPanel.hidden = !showPlaybook && S.aiWorkspaceActiveTab !== "playbook";
    const visible = S.aiWorkspaceTabs.some((t) => t.id === "playbook") && S.aiWorkspaceActiveTab === "playbook";
    playbookPanel.hidden = !visible;
    playbookPanel.classList.toggle("is-active", visible);
  }
}

export function bindWorkspaceTabs() {
  resetWorkspaceTabs();
  paintWorkspaceTabs();
}
