// Test-only globals: i18n.ts touches localStorage/navigator at module
// load; provide inert stand-ins when the runner is plain node.
const g = globalThis as unknown as Record<string, unknown>;
if (!g.localStorage) {
  const store = new Map<string, string>();
  g.localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  };
}
if (!g.navigator) {
  g.navigator = { language: "zh-CN" };
}
