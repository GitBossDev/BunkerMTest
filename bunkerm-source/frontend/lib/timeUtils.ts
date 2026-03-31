/**
 * Timezone-aware time formatting utilities.
 *
 * Backend timestamps come in two flavours:
 *   • UTC-naive ISO    "2026-06-10T12:30:00"      (smart-anomaly, post-fix: now has 'Z')
 *   • UTC-explicit ISO "2026-06-10T12:30:00Z"      (clientlogs, smart-anomaly after fix)
 *   • UTC offset ISO   "2026-06-10T12:30:00+00:00" (clientlogs)
 *
 * All helpers go through `toUTCDate()` which normalises the string before
 * creating a Date, so relative-time calculations are always correct regardless
 * of whether the server emitted a 'Z' suffix.
 */

export const TZ_STORAGE_KEY = 'bunkerm.timezone'
export const TZ_CHANGE_EVENT = 'bunkerm:timezone-change'

/** Return the user's saved timezone preference, or 'auto'. */
export function getStoredTimezone(): string {
  if (typeof window === 'undefined') return 'auto'
  return localStorage.getItem(TZ_STORAGE_KEY) ?? 'auto'
}

/** Persist the user's timezone preference and notify other components. */
export function setStoredTimezone(tz: string): void {
  if (typeof window === 'undefined') return
  localStorage.setItem(TZ_STORAGE_KEY, tz)
  window.dispatchEvent(new CustomEvent(TZ_CHANGE_EVENT, { detail: tz }))
}

/**
 * Parse a backend ISO string as UTC.
 * Appends 'Z' when there is no timezone designator so that JavaScript
 * never misinterprets a UTC-naive string as local time.
 */
function toUTCDate(str: string): Date {
  // Already has timezone info – parse as-is
  if (/Z$|[+-]\d{2}:\d{2}$/.test(str)) return new Date(str)
  // No TZ designator – assume UTC
  return new Date(str + 'Z')
}

/**
 * Turn a UTC ISO string into a human-friendly "X ago" label.
 * Works correctly for both '…Z' and naive '…' UTC strings.
 */
export function formatRelativeTime(iso: string): string {
  const diff = Date.now() - toUTCDate(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/**
 * Format a UTC ISO string as a localised date/time string.
 * Respects the timezone stored in localStorage (or falls back to the
 * browser's own timezone when the preference is 'auto').
 */
export function formatAbsoluteTime(iso: string): string {
  const d = toUTCDate(iso)
  const tz = getStoredTimezone()
  try {
    return d.toLocaleString(undefined, tz !== 'auto' ? { timeZone: tz } : undefined)
  } catch {
    // Unknown/unsupported timezone – fall back to browser default
    return d.toLocaleString()
  }
}
