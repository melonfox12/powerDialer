/** Indirection so feature modules never import `navigation.js` during its initial evaluation. */

/** @type {(name: string, moveFocus?: boolean) => void} */
let setDashboardTabImpl = () => {};

export function wireSetDashboardTab(fn) {
  setDashboardTabImpl = fn;
}

export function setDashboardTab(name, moveFocus = false) {
  setDashboardTabImpl(name, moveFocus);
}