import { registerRenderer } from "../core.js";
import {
  renderPipelineBoardAndRemember,
  renderPipelineIfStale,
  tickPipelineTimers,
} from "./_pipeline/board.js";
import {
  bindPipelineEditor,
  refreshPipelineEditorIfStale,
  renderPipelineEditor,
} from "./_pipeline/pipeline-editor.js";

registerRenderer(refreshPipelineEditorIfStale);
registerRenderer(renderPipelineIfStale);

bindPipelineEditor();

export { renderPipelineBoardAndRemember, tickPipelineTimers, renderPipelineEditor };
