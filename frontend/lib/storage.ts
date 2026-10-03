/** Read a browser storage item as React state that stays in sync (useSyncExternalStore).
 *  The server render (static export) sees `serverValue`; the client switches to the stored value after hydration. */
import { useSyncExternalStore } from "react";

const EVT = "tahqaq-storage";

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(EVT, onChange);
  return () => { window.removeEventListener("storage", onChange); window.removeEventListener(EVT, onChange); };
}

/** Tell subscribers in this tab that storage changed (the native "storage" event only fires in other tabs). */
export function notifyStorage() { window.dispatchEvent(new Event(EVT)); }

export function useStorageItem(area: "local" | "session", key: string, serverValue: string | null): string | null {
  return useSyncExternalStore(
    subscribe,
    () => { try { return (area === "local" ? window.localStorage : window.sessionStorage).getItem(key); } catch { return null; } },
    () => serverValue,
  );
}
