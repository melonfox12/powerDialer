import { request } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../js/views/render.js";
import { setDashboardTab } from "../../js/controllers/navigation.js";
import { deleteSelectedProspects } from "./records.js";

export async function importCsv(file) {
  if (!file) return;
  const button = byId("importButton");
  button.disabled = true;
  byId("headingImportButton").disabled = true;
  button.textContent = "Importing…";
  try {
    const result = await request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    Object.assign(state, result.state || {});
    setDashboardTab("prospects");
    render();
    const imported = result.import || {};
    const added = imported.added || 0;
    const duplicates = imported.duplicates || 0;
    const skipped = imported.skipped || 0;
    if (!added) {
      const reason = skipped
        ? `${skipped} row${skipped === 1 ? "" : "s"} skipped because no usable phone number was found.`
        : "No prospect rows were found in that file.";
      showToast(`Import did not add anyone. ${reason}`, true);
      return;
    }
    const extra = [
      duplicates ? `${duplicates} duplicate${duplicates === 1 ? "" : "s"} skipped` : "",
      skipped ? `${skipped} row${skipped === 1 ? "" : "s"} without a phone skipped` : "",
    ].filter(Boolean).join(" · ");
    showToast(`${added} prospect${added === 1 ? "" : "s"} added${extra ? ` · ${extra}` : ""}`);
  } catch (error) {
    console.error("CSV import failed:", error);
    showToast(error?.message || "Import failed. Check the console for details.", true);
  } finally {
    button.disabled = false;
    byId("headingImportButton").disabled = false;
    button.innerHTML = '<span class="button-symbol" aria-hidden="true">↑</span>Import CSV';
    byId("csvInput").value = "";
  }
}

export function bindCsv() {
  byId("importButton").addEventListener("click", () => byId("csvInput").click());
  byId("headingImportButton").addEventListener("click", () => byId("csvInput").click());
  byId("deleteSelectedButton").addEventListener("click", deleteSelectedProspects);
  byId("csvInput").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) {
      console.warn("CSV file picker closed with no file selected.");
      return;
    }
    console.log(`CSV file selected: ${file.name} (${file.size} bytes, type "${file.type}")`);
    importCsv(file);
  });
}
