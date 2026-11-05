import { registerRenderer } from "../core.js";
import {
  renderPipelineBoardAndRemember,
  renderPipelineIfStale,
  tickPipelineTimers,
} from "./_pipeline/board.js";

registerRenderer(renderPipelineIfStale);

export { renderPipelineBoardAndRemember, tickPipelineTimers };
