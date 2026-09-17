/**
 * State that survives a refresh, without pretending to be saved (§72).
 *
 * Some of what a page holds belongs on the server: a dashboard's layout, its
 * name, who it is shared with. Some of it belongs in the URL: which dashboard
 * is open, which record is being previewed — because that is what makes an
 * address describe what is on screen (§69).
 *
 * And some of it is neither. Whether *you* had the layout editor open, which
 * period *you* were reading a colleague's dashboard over, which tab *you* left
 * a widget on: nobody else should see it, it should not change a shared
 * object, and it should still be there when you come back — which is exactly
 * what `localStorage` is for and exactly what neither of the other two does.
 *
 * Three rules the wrapper enforces, each of which is a bug it has already
 * prevented somewhere:
 *
 * * **Reading never throws.** `localStorage` throws on access in a private
 *   window with site data blocked, and it throws again on a value that is not
 *   the JSON it was last time. A preference that cannot be read is a
 *   preference that was not set — never a page that fails to render.
 * * **Writing never throws either.** A full quota is not a reason to lose a
 *   drag.
 * * **Keys are namespaced and versioned.** `nu:1:` in front of everything, so
 *   a value whose shape changes can be abandoned wholesale rather than
 *   migrated, and so nothing collides with anything else on the origin.
 */

const PREFIX = "nu:1:";

/** What a stored value may be. Anything JSON round-trips. */
export type Sticky = string | number | boolean | null | Sticky[] | { [key: string]: Sticky };

export function readSticky<T extends Sticky>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    // A blocked store, or a value written by an older shape of this key.
    // Either way the answer is the same: this reader has no preference.
    return fallback;
  }
}

export function writeSticky(key: string, value: Sticky): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Quota, or a store that refuses writes. Losing a preference is a smaller
    // failure than losing the interaction that produced it.
  }
}

export function clearSticky(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key);
  } catch {
    // As above.
  }
}
