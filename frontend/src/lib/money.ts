/**
 * Money formatting for exact decimal strings.
 *
 * The API sends money as strings so the engine's `Decimal` precision
 * survives transport (see `schemas.py`). This module is the only place
 * allowed to turn one into something else, and it keeps that promise by
 * formatting the STRING rather than a parsed float wherever the platform
 * allows it.
 */

import type { Money } from '@/api/types';

/** Indian digit grouping: 9,62,626.14, not 962,626.14. */
const INR = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** What the API promises a money field looks like. */
const DECIMAL_STRING = /^-?\d+(\.\d+)?$/;

/**
 * Format an exact decimal string for display.
 *
 * `Intl.NumberFormat.format` accepts a string argument in every browser
 * this app targets, and formatting the string avoids a float round-trip
 * entirely.
 *
 * The shape is validated first because `Intl` does NOT throw on a
 * non-numeric string -- it quietly returns "NaN", which would put the
 * literal text "NaN" where a rupee figure belongs. Backend responses are
 * untrusted input; a malformed field degrades to showing the raw value,
 * which is inspectable, rather than to a number-shaped lie.
 *
 * The catch is still not dead code: on an engine without string support the
 * call throws, and falling back to `Number` costs at most a rounding
 * artefact in the last decimal place rather than a broken page.
 */
export function formatAmount(value: Money | string): string {
  const raw = String(value).trim();
  if (!DECIMAL_STRING.test(raw)) return raw;
  try {
    return INR.format(raw as unknown as number);
  } catch {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? INR.format(parsed) : raw;
  }
}

/** With the rupee sign. Used for headline figures, not dense table cells. */
export function formatRupees(value: Money | string): string {
  const negative = isNegative(value);
  const body = formatAmount(negative ? stripSign(value) : value);
  return `${negative ? '−' : ''}₹${body}`;
}

/**
 * Signed, for bridge lines where direction is the point.
 * Uses a true minus sign (U+2212) rather than a hyphen so figures align
 * optically in a mono column.
 */
export function formatSigned(value: Money | string): string {
  if (isZero(value)) return `₹${formatAmount(value)}`;
  const negative = isNegative(value);
  return `${negative ? '−' : '+'}₹${formatAmount(stripSign(value))}`;
}

function stripSign(value: string): string {
  return value.startsWith('-') ? value.slice(1) : value;
}

export function isNegative(value: Money | string): boolean {
  return value.trim().startsWith('-') && !isZero(value);
}

/**
 * True when the value is exactly zero.
 *
 * Compares digits rather than `Number(value) === 0` so that '0.00',
 * '-0.00', and '0' all read as nil. This is what the nil-variance proof
 * hangs on, so it is deliberately string-exact.
 */
export function isZero(value: Money | string): boolean {
  return /^-?0*(\.0*)?$/.test(value.trim());
}

/**
 * Parse for sorting and chart geometry ONLY.
 *
 * Named to make review easy: any call site using this to produce a figure
 * that is then displayed has reintroduced the float problem the string
 * encoding exists to prevent.
 */
export function toNumberForLayout(value: Money | string): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Comparator for table sorting. */
export function compareMoney(a: Money | string, b: Money | string): number {
  return toNumberForLayout(a) - toNumberForLayout(b);
}

/** Absolute magnitude, for bar widths. Layout only. */
export function magnitude(value: Money | string): number {
  return Math.abs(toNumberForLayout(value));
}

/** '2024-04-01' -> '01 Apr 2024'. Dates come from the API as ISO strings. */
export function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

/** Full timestamp for the reproducibility panel. */
export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(date);
}

/** Bytes -> human size, for the upload dropzones. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
