import '@testing-library/jest-dom'
import { beforeEach } from 'vitest'

// Under this project's exact Node/jsdom/vitest version combination, jsdom's real
// window.localStorage resolves to `undefined` by the time vitest finishes wiring
// up the test globals (verified directly: raw `new JSDOM(...)` has a working
// localStorage; the same property read through vitest's globalThis does not).
// Rather than depend on that interaction being fixed upstream, install a small,
// spec-compliant in-memory Storage polyfill — everything code under test needs
// (getItem/setItem/removeItem/clear, and zustand's persist middleware) only
// requires this surface, not jsdom's exact quota/exception semantics.
class MemoryStorage implements Storage {
  private data = new Map<string, string>()
  get length() { return this.data.size }
  clear() { this.data.clear() }
  getItem(key: string) { return this.data.has(key) ? this.data.get(key)! : null }
  key(index: number) { return Array.from(this.data.keys())[index] ?? null }
  removeItem(key: string) { this.data.delete(key) }
  setItem(key: string, value: string) { this.data.set(key, String(value)) }
}

function installMemoryStorage(prop: 'localStorage' | 'sessionStorage') {
  const instance = new MemoryStorage()
  Object.defineProperty(globalThis, prop, {
    value: instance,
    writable: true,
    configurable: true,
  })
  return instance
}

// Installed once, as a singleton — modules like zustand's `persist` middleware
// resolve their default storage engine eagerly, exactly once, at module-import
// time (`createJSONStorage(() => localStorage)` calls `getStorage()` immediately
// and caches the result). Replacing `globalThis.localStorage` with a *new*
// instance in a per-test beforeEach orphans that captured reference — the store
// keeps writing to the old instance while tests read from the new one, and every
// persistence assertion sees an empty store. Clear the same instance instead.
const localStorageInstance = installMemoryStorage('localStorage')
const sessionStorageInstance = installMemoryStorage('sessionStorage')

beforeEach(() => {
  localStorageInstance.clear()
  sessionStorageInstance.clear()
})
