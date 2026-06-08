// Session-token storage + refresh helpers.
//
// Owns the per-service `X-Session-ID` value used by every API request.
// Each backend (cache/catalog/results) maintains its own session table
// (review item #T1), so a single login mints three separate tokens.
// Tokens live in sessionStorage so closing the browser session drops them.
// Missing entries fall back to the build-time default in `config.ts`
// (typically "demo-session") for `--no-auth` development setups.

import { config } from '../config';

export type Service = 'cache' | 'catalog' | 'results';

const STORAGE_KEY = 'sim2l.sessionTokens';
const LEGACY_STORAGE_KEY = 'sim2l.sessions';

type SessionMap = Partial<Record<Service, string>>;

function readMap(): SessionMap {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === 'object') {
      return parsed as SessionMap;
    }
  } catch {
    // unparseable / unavailable; fall through
  }
  return {};
}

function writeMap(map: SessionMap): void {
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(map));
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // ignore (private mode / quota / SSR)
  }
}

function defaultFor(service: Service): string {
  return config.services[service].sessionId || 'demo-session';
}

export function getSessionId(service: Service = 'catalog'): string {
  const map = readMap();
  return map[service] || defaultFor(service);
}

export function setSessionId(service: Service, value: string): void {
  const map = readMap();
  map[service] = value;
  writeMap(map);
}

export function setSessionIds(values: Partial<Record<Service, string>>): void {
  const map = readMap();
  for (const [k, v] of Object.entries(values) as [Service, string][]) {
    if (v) map[k] = v;
  }
  writeMap(map);
}

export function clearSessionIds(): void {
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch {
    // ignore
  }
}

// Listeners invoked when the session becomes invalid (eg. 401 after refresh
// retry). The login page subscribes so it can navigate the user there.
type Listener = () => void;
const listeners = new Set<Listener>();

export function onSessionInvalid(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function notifySessionInvalid(): void {
  listeners.forEach(fn => {
    try {
      fn();
    } catch {
      // listeners shouldn't throw, but don't let one bad listener kill the others
    }
  });
}
