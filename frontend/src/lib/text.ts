/**
 * Render an unknown value as text a person can read.
 *
 * API responses carry JSON, and JSON includes objects and arrays: a JSONB
 * column, a list of tags, a nested payload. `String(value)` turns any of those
 * into `[object Object]`, which is not a value anybody can act on and is
 * indistinguishable from a bug in the field that produced it.
 *
 * So objects are serialised rather than stringified, and absence is empty
 * rather than the words "null" or "undefined" — a caller that wants to show a
 * placeholder can test for it.
 */
export function asText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  if (value instanceof Date) return value.toISOString();
  try {
    return JSON.stringify(value) ?? "";
  } catch {
    // Circular structures cannot come from JSON, but a caller could pass one.
    return "";
  }
}
