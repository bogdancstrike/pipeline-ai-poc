/**
 * `useState`, but the initial value is what this reader last chose (§72).
 *
 * The signature is `useState`'s on purpose, so adopting it at a call site is
 * one line and reading it needs no explanation. Two differences worth knowing:
 *
 * * **The key may change.** A per-dashboard preference is keyed on the
 *   dashboard, and switching to another one has to load *that* one's value
 *   rather than carry the last one across. So the key is watched, and the
 *   value is re-read when it changes.
 * * **It is a preference, not a source of truth.** Nothing here is sent
 *   anywhere, nothing is shared, and a reader whose browser refuses storage
 *   gets the fallback and a page that works. Anything a colleague has to see
 *   belongs on the server; anything an address should describe belongs in the
 *   URL (§69).
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { readSticky, writeSticky, type Sticky } from "@/lib/sticky";

export function useSticky<T extends Sticky>(
  key: string,
  // Widened deliberately. Without it `useSticky("x", false)` infers the
  // *literal* `false`, and the setter then refuses `true` — which is a type
  // error at every call site that actually toggles something.
  fallback: T,
): [T, (next: T | ((current: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readSticky(key, fallback));

  // The key this state currently holds a value for. Compared rather than
  // listed as a dependency of an effect that writes, because writing on every
  // key change would copy the old dashboard's preference onto the new one.
  const loaded = useRef(key);
  useEffect(() => {
    if (loaded.current === key) return;
    loaded.current = key;
    setValue(readSticky(key, fallback));
    // `fallback` is deliberately not a dependency: callers pass it inline, so
    // depending on it would re-read the store on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = useCallback(
    (next: T | ((current: T) => T)) => {
      setValue((current) => {
        const resolved = typeof next === "function" ? next(current) : next;
        writeSticky(key, resolved);
        return resolved;
      });
    },
    [key],
  );

  return [value, set];
}
