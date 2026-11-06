import { PIPELINE_DIALED_STEP, PIPELINE_SEND_INFO_STEP, setPipelineRuntimeSteps } from "../../_core/format.js";

function isValidPipelineCatalog(steps) {
  return Array.isArray(steps) && steps.length >= 2
    && steps[0]?.key === PIPELINE_DIALED_STEP
    && steps[1]?.key === PIPELINE_SEND_INFO_STEP;
}

/** Editable tail: steps after Contacted (engaged) (pipeline key call_1). */
export function pipelineCustomStepsFromCatalog(steps) {
  const full = Array.isArray(steps) ? steps : [];
  return full.filter((s) => s?.key !== PIPELINE_DIALED_STEP && s?.key !== PIPELINE_SEND_INFO_STEP);
}

let lastPipelineRevision = null;

export function ensurePipelineRuntimeFromCatalog(catalog) {
  const rev = catalog?.pipeline_revision;
  const steps = catalog?.pipeline_steps;
  if (!isValidPipelineCatalog(steps)) return;
  if (rev != null && rev === lastPipelineRevision) return;
  lastPipelineRevision = rev ?? null;
  setPipelineRuntimeSteps(steps);
}
