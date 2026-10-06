const renderers = [];
let callerPoolRenderer = () => {};
let tableRenderer = () => {};

export function registerRenderer(fn, position = "end") {
  if (position === "start") renderers.unshift(fn);
  else renderers.push(fn);
}

export function runRenderers() {
  for (const fn of renderers) fn();
}

export function registerTable(fn) {
  tableRenderer = fn;
}

export function renderTable() {
  tableRenderer();
}

export function registerCallerPool(fn) {
  callerPoolRenderer = fn;
}

export function renderCallerPool() {
  callerPoolRenderer();
}
