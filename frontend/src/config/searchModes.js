export const SEARCH_MODES = Object.freeze([
  { key: "text", searchMode: "semantic", label: "Semantic", description: "Visual meaning", shortcut: "Ctrl+1", code: "Digit1" },
  { key: "auto", searchMode: "auto", label: "Auto", description: "Detect query intent", shortcut: "Ctrl+3", code: "Digit3" },
]);

export const SEARCH_MODE_BY_CODE = Object.freeze(
  Object.fromEntries(SEARCH_MODES.map((mode) => [mode.code, mode]))
);

export const SEARCH_MODE_BY_KEY = Object.freeze(
  Object.fromEntries(SEARCH_MODES.map((mode) => [mode.key, mode]))
);

export function resolveSearchMode(modeKey) {
  return SEARCH_MODE_BY_KEY[modeKey]?.searchMode ?? "semantic";
}
