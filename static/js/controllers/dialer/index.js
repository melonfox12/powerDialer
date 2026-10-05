import { setStartNewSession } from "../../views/dialogs/index.js";
import { bindDialer } from "./bindings.js";
import { dialLead } from "./lead.js";
import { startDialing } from "./session.js";

setStartNewSession(startDialing);

export { bindDialer, dialLead, startDialing };
