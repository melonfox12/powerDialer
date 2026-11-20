import { state } from "../../_core/state.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { showToast } from "../../_core/notify.js";

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

  function closeMenu() {
    menu.hidden = true;
    lead = null;
    document.querySelectorAll(".prospect-menu-target").forEach((row) => row.classList.remove("prospect-menu-target"));
  }

  function openMenu(nextLead, x, y, row) {
    lead = nextLead;
    const blocked = nextLead.status === "closed";
    const missing = !nextLead.phone;
    button.disabled = blocked || missing;
    label.textContent = blocked ? "Disqualified" : "Phone";
    phone.textContent = missing ? "No number" : formatPhoneNumber(nextLead.phone);
    button.setAttribute("aria-label", blocked ? "Disqualified" : missing ? "No number on file" : formatPhoneNumber(nextLead.phone));
    document.querySelectorAll(".prospect-menu-target").forEach((item) => item.classList.remove("prospect-menu-target"));
    row.classList.add("prospect-menu-target");
    const sortMenu = document.getElementById("columnSortMenu");
    if (sortMenu) sortMenu.hidden = true;
    menu.hidden = false;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - rect.height - 8))}px`;
    if (!button.disabled) button.focus();
  }

  document.addEventListener("contextmenu", (event) => {
    if (event.target instanceof Element && event.target.closest("input, textarea, select")) {
      if (!menu.hidden) closeMenu();
      return;
    }
    const row = event.target instanceof Element
      ? event.target.closest("#tableBody tr[data-lead-id]")
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

  button.addEventListener("click", () => {
    const chosen = lead;
    closeMenu();
    if (!chosen?.phone || chosen.status === "closed") return;
    void navigator.clipboard.writeText(chosen.phone).then(
      () => showToast("Phone number copied."),
      () => showToast("Could not copy phone number.", true),
    );
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