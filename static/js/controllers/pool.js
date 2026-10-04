import { postJson } from "../api/client.js";
import { state } from "../store/state.js";
import { showToast } from "../utils/notify.js";
import { render } from "../views/render.js";

export async function selectTimezone(timezone) {
  try {
    Object.assign(state, await postJson("/api/timezone", { timezone: timezone || "" }));
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}
