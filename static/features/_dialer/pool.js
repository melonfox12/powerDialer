import { postJson } from "../../_core/api.js";
import { applyMutationPayload } from "../../_core/sync-state.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../core.js";

export async function selectTimezone(timezone) {
  try {
    await applyMutationPayload({ state: await postJson("/api/timezone", { timezone: timezone || "" }) });
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}

export async function selectDialPoolStatus(poolStatus) {
  try {
    await applyMutationPayload({ state: await postJson("/api/timezone", { pool_status: poolStatus }) });
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}
