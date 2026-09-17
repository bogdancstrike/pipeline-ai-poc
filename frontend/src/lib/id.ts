/**
 * A unique id, on every origin this app is served from.
 *
 * `crypto.randomUUID` exists only in a **secure context** — HTTPS, or
 * `localhost`. The dashboard is served over plain HTTP on a LAN port
 * (`PORT_FRONTEND`, 5697 by default), so it is there on a developer's
 * `localhost:5697` and simply missing on `http://<host>:5697`, where the call
 * throws `crypto.randomUUID is not a function` and takes the page down with it.
 *
 * The ids this returns name a correlation header and the nodes of a query tree.
 * Neither is a security boundary and neither outlives the tab, so falling back
 * to `getRandomValues` — and, on an ancient browser, to `Math.random` — costs
 * nothing that matters here.
 */
export function randomId(): string {
  const cryptoApi = typeof crypto !== "undefined" ? crypto : undefined;

  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID().replace(/-/g, "");
  }

  // Available in every context, secure or not, since IE11.
  if (cryptoApi && typeof cryptoApi.getRandomValues === "function") {
    const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  return `${Math.random().toString(16).slice(2)}${Math.random().toString(16).slice(2)}`
    .slice(0, 32)
    .padEnd(32, "0");
}
