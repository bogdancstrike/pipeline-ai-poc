/**
 * The reader's own date, time and number formats (§40).
 *
 * These are a *user preference*, stored on the server, and they have to reach
 * every rendered value — a table cell, a chart axis, an audit row, a CSV
 * column heading. Threading a formatter through forty components as a prop
 * would mean forty chances to forget one, and the one that is forgotten is the
 * one somebody screenshots.
 *
 * So the active settings live in this module and every formatter reads them.
 * That is deliberate shared mutable state, with two rules that keep it honest:
 *
 * * exactly one writer — `PreferencesProvider`, which owns the profile;
 * * a working default before it writes, so a value rendered during the first
 *   paint is correct rather than blank.
 *
 * The alternative — a React context read by a hook — was rejected because the
 * consumers are not all components: `lib/time.ts` is imported by plain
 * functions, and a hook cannot be called from one.
 */

export type DateFormat = "YYYY-MM-DD" | "DD/MM/YYYY" | "MM/DD/YYYY";
export type TimeFormat = "24h" | "12h";
export type NumberFormat = "1 234,56" | "1,234.56";

export interface FormatSettings {
  date: DateFormat;
  time: TimeFormat;
  number: NumberFormat;
}

/** ISO first, because it is unambiguous and sorts. */
export const DEFAULT_FORMATS: FormatSettings = {
  date: "YYYY-MM-DD",
  time: "24h",
  number: "1,234.56",
};

let active: FormatSettings = { ...DEFAULT_FORMATS };

/** Called once by `PreferencesProvider` whenever the profile changes. */
export function applyFormats(next: Partial<FormatSettings>): void {
  active = { ...active, ...next };
}

export function currentFormats(): FormatSettings {
  return active;
}

/**
 * The locale that renders a chosen pattern.
 *
 * `Intl` has no "give me exactly this pattern" mode, and hand-rolling one is
 * how applications end up printing "13/13/2026" for somebody in a timezone the
 * author did not have. Picking the locale whose conventions *are* the pattern
 * keeps `Intl` in charge of the parts that are genuinely hard — month names,
 * era, timezone — while still honouring the choice.
 */
const DATE_LOCALE: Record<DateFormat, string> = {
  "YYYY-MM-DD": "en-CA",
  "DD/MM/YYYY": "en-GB",
  "MM/DD/YYYY": "en-US",
};

const NUMBER_LOCALE: Record<NumberFormat, string> = {
  "1,234.56": "en-GB",
  "1 234,56": "fr-FR",
};

/**
 * The locale that renders the *clock*, chosen by the clock setting alone.
 *
 * It used to come from the date pattern's locale, which coupled two
 * independent choices: picking `YYYY-MM-DD` made a 12-hour clock read
 * "03:42 p.m." (en-CA's convention) while picking `MM/DD/YYYY` made the same
 * setting read "03:42 PM". A reader who changes the date should not find the
 * clock a different shape.
 */
const TIME_LOCALE: Record<TimeFormat, string> = {
  "24h": "en-GB",
  "12h": "en-US",
};

/**
 * Two digits for the day and the month, always.
 *
 * The patterns are *labelled* `DD/MM/YYYY` and `MM/DD/YYYY`, and `en-US`
 * renders an unpadded `9/6/2026` left to itself — so the option promised a
 * shape it did not deliver, and a column of dates did not line up. Asking for
 * the parts keeps `Intl` in charge of the order and this file in charge of the
 * width.
 */
const DATE_PARTS: Intl.DateTimeFormatOptions = {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
};

export function formatDate(value: Date): string {
  return value.toLocaleDateString(DATE_LOCALE[active.date], DATE_PARTS);
}

export function formatDateTime(value: Date): string {
  return `${formatDate(value)} ${value.toLocaleTimeString(TIME_LOCALE[active.time], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: active.time === "12h",
  })}`;
}

export function formatTime(value: Date): string {
  return value.toLocaleTimeString(TIME_LOCALE[active.time], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: active.time === "12h",
  });
}

export function formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
  return value.toLocaleString(NUMBER_LOCALE[active.number], options);
}

/** A worked example of every current setting, for the preferences page. */
export function formatSample(settings: FormatSettings = active): {
  date: string;
  time: string;
  number: string;
} {
  const moment = new Date(2026, 8, 6, 15, 42, 8);
  return {
    date: moment.toLocaleDateString(DATE_LOCALE[settings.date], DATE_PARTS),
    time: moment.toLocaleTimeString(TIME_LOCALE[settings.time], {
      hour: "2-digit",
      minute: "2-digit",
      hour12: settings.time === "12h",
    }),
    number: (1234.56).toLocaleString(NUMBER_LOCALE[settings.number], {
      minimumFractionDigits: 2,
    }),
  };
}
