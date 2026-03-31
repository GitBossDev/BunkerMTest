import { useEffect, useState } from 'react'
import { getStoredTimezone, TZ_CHANGE_EVENT } from '@/lib/timeUtils'

/**
 * Returns the currently selected timezone preference ('auto' or an IANA tz
 * string like 'Europe/Madrid'). Re-renders automatically whenever the user
 * changes the preference in the Settings page.
 */
export function useTimezone(): string {
  const [tz, setTz] = useState<string>(() => {
    if (typeof window === 'undefined') return 'auto'
    return getStoredTimezone()
  })

  useEffect(() => {
    const handler = (e: Event) => setTz((e as CustomEvent<string>).detail)
    window.addEventListener(TZ_CHANGE_EVENT, handler)
    return () => window.removeEventListener(TZ_CHANGE_EVENT, handler)
  }, [])

  return tz
}
