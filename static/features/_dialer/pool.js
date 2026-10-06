import { postJson } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../js/views/render.js";

export async function selectTimezone(timezone) {
  try {
    Object.assign(state, await postJson("/api/timezone", { timezone: timezone || "" }));
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}
