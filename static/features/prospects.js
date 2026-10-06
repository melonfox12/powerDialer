import { registerRenderer, registerTable, registerTranscriptActions } from "../core.js";
import { renderTable, renderTableIfStale } from "./_prospects/table.js";
import { downloadTranscript, openTranscript } from "./_prospects/transcript.js";

registerTranscriptActions(openTranscript, downloadTranscript);
registerTable(renderTable);
registerRenderer(renderTableIfStale, "start");

export { bindAddProspect } from "./_prospects/add-prospect.js";
export { bindCsv } from "./_prospects/csv.js";
export { bindProspectMenu } from "./_prospects/menu.js";
export { bindProspects } from "./_prospects/records.js";
export { bindDialogs } from "./_prospects/transcript.js";
