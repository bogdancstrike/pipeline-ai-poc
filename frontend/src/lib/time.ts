/**
 * Timestamps, the way this app writes them down.
 *
 * Every date the API sends is ISO-8601 in UTC (`clock.iso` on the backend).
 * What a reader wants is usually not that: a table wants "17 Sep 07:30", a
 * detail header wants the full moment, and a "3 minutes ago" is the only form
 * that answers "is this still running?" at a glance.
 */

import { formatDateTime, formatNumber } from "@/lib/formats";

export function parse(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function dateTime(value: string | null | undefined): string {
  const parsed = parse(value);
  return parsed ? formatDateTime(parsed) : "—";
}

export function day(value: string | null | undefined): string {
  const parsed = parse(value);
  if (!parsed) return "—";
  return parsed.toLocaleDateString(undefined, { day: "2-digit", month: "short" });
}

/** "just now", "4 min ago", "2 days ago" — relative, and never in the future. */
export function ago(value: string | null | undefined): string {
  const parsed = parse(value);
  if (!parsed) return "—";
  const seconds = Math.max(0, (Date.now() - parsed.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)} min ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)} h ago`;
  const days = hours / 24;
  if (days < 30) return `${Math.round(days)} days ago`;
  return dateTime(value);
}

/**
 * A duration in seconds, written for a reader.
 *
 * Milliseconds below a second, because the difference between 40 ms and 600 ms
 * is the difference between a mocked call and a real one.
 */
export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 90) return `${formatNumber(seconds, { maximumFractionDigits: 1 })} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

export function millis(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—";
  return ms < 1000
    ? `${formatNumber(ms, { maximumFractionDigits: 0 })} ms`
    : duration(ms / 1000);
}
