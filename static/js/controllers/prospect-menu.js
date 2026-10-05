import { state } from "../store/state.js";
import { formatPhoneNumber } from "../utils/phone.js";
import { dialLead } from "./dialer/index.js";
import { setDashboardTab } from "./navigation.js";

export function bindProspectMenu() {
  const menu = document.createElement("div");
  menu.id = "prospectMenu";
  menu.className = "prospect-menu";
  menu.hidden = true;
  menu.setAttribute("role", "menu");
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("role", "menuitem");
  const label = document.createElement("span");
  const phone = document.createElement("span");
  phone.className = "prospect-menu-phone";
  button.append(label, phone);
  menu.append(button);
  document.body.append(menu);

  let lead = null;
  let pending = false;

  function closeMenu() {
    menu.hidden = true;
    lead = null;
    document.querySelectorAll(".prospect-menu-target").forEach((row) => row.classList.remove("prospect-menu-target"));
  }

  function openMenu(nextLead, x, y, row) {
    lead = nextLead;
    const blocked = nextLead.status === "do_not_call";
    const missing = !nextLead.phone;
    button.disabled = blocked || missing;
    label.textContent = blocked ? "Do not call" : "Dial";
    phone.textContent = missing ? "No number" : formatPhoneNumber(nextLead.phone);
    button.setAttribute("aria-label", blocked ? "Do not call" : missing ? "No number to dial" : `Dial ${formatPhoneNumber(nextLead.phone)}`);
    document.querySelectorAll(".prospect-menu-target").forEach((item) => item.classList.remove("prospect-menu-target"));
    row.classList.add("prospect-menu-target");
    menu.hidden = false;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - rect.height - 8))}px`;
    if (!button.disabled) button.focus();
  }

  document.addEventListener("contextmenu", (event) => {
    const row = event.target instanceof Element
      ? event.target.closest("#tableBody tr[data-lead-id], #poolTableBody tr[data-lead-id]")
      : null;
    if (!row) {
      if (!(event.target instanceof Node) || !menu.contains(event.target)) closeMenu();
      return;
    }
    event.preventDefault();
    const next = state.leads.find((item) => item.id === row.dataset.leadId);
    if (!next) return;
    openMenu(next, event.clientX, event.clientY, row);
  });

  button.addEventListener("click", async () => {
    const chosen = lead;
    closeMenu();
    if (!chosen || pending) return;
    pending = true;
    try {
      await dialLead(chosen);
      setDashboardTab("dialer");
    } catch {
      // dialLead already reports the failure.
    } finally {
      pending = false;
    }
  });

  document.addEventListener("click", (event) => {
    if (menu.hidden || menu.contains(event.target)) return;
    closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (menu.hidden || event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    closeMenu();
  }, true);
  document.addEventListener("scroll", () => {
    if (!menu.hidden) closeMenu();
  }, true);
}
