'use client'

import { useState, useEffect, useCallback } from 'react'

interface VersionInfo {
  currentVersion: string
  latestVersion: string
  updateAvailable: boolean
  lastChecked: string
  dockerHubUrl: string
}

interface CachedCheck {
  timestamp: number
  latestVersion: string
  data: VersionInfo
}

const DOCKER_HUB_IMAGE = 'bunkeriot/bunkerm'
const DOCKER_HUB_URL = `https://hub.docker.com/r/${DOCKER_HUB_IMAGE}`
const DOCKER_HUB_TAGS_URL = `https://hub.docker.com/v2/repositories/${DOCKER_HUB_IMAGE}/tags`
const CACHE_KEY = 'bunkerm_version_check'
const DISMISS_KEY = 'bunkerm_version_dismissed' // stores the version string the user dismissed
const CACHE_DURATION_MS = 24 * 60 * 60 * 1000 // 24 hours
const CURRENT_VERSION = process.env.NEXT_PUBLIC_CURRENT_VERSION || 'v2.0.0'

/** Returns true only if latestVersion is newer AND the user hasn't dismissed it. */
function shouldShowUpdate(latestVersion: string): boolean {
  if (compareVersions(latestVersion, CURRENT_VERSION) <= 0) return false
  const dismissed = localStorage.getItem(DISMISS_KEY)
  return dismissed !== latestVersion
}

function compareVersions(v1: string, v2: string): number {
  const parse = (v: string) => v.replace(/^v/, '').split('.').map(Number)
  const parts1 = parse(v1)
  const parts2 = parse(v2)

  for (let i = 0; i < 3; i++) {
    const diff = (parts1[i] || 0) - (parts2[i] || 0)
    if (diff !== 0) return diff
  }
  return 0
}

export function useVersionCheck() {
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const checkForUpdates = useCallback(async () => {
    setLoading(true)
    setError(false)

    try {
      let data: { results?: { name: string }[] } | null = null

      try {
        const corsProxy = 'https://api.allorigins.win/raw?url='
        const encodedUrl = encodeURIComponent(DOCKER_HUB_TAGS_URL)
        const response = await fetch(`${corsProxy}${encodedUrl}`)
        if (response.ok) {
          data = await response.json()
        }
      } catch {
        // CORS proxy failed, try cached data
      }

      if (!data) {
        const cached = localStorage.getItem(CACHE_KEY)
        if (cached) {
          const parsed: CachedCheck = JSON.parse(cached)
          setVersionInfo(parsed.data)
          setError(true)
        } else {
          setError(true)
        }
        setLoading(false)
        return
      }

      let latestVersion = CURRENT_VERSION
      if (data.results && data.results.length > 0) {
        const versionTags = data.results
          .filter((tag) => /^v\d+\.\d+/.test(tag.name))
          .map((tag) => tag.name)
          .sort((a, b) => compareVersions(b, a))

        if (versionTags.length > 0) {
          latestVersion = versionTags[0]
        }
      }

      const updateAvailable = shouldShowUpdate(latestVersion)
      const info: VersionInfo = {
        currentVersion: CURRENT_VERSION,
        latestVersion,
        updateAvailable,
        lastChecked: new Date().toISOString(),
        dockerHubUrl: DOCKER_HUB_URL,
      }

      setVersionInfo(info)
      localStorage.setItem(
        CACHE_KEY,
        JSON.stringify({ timestamp: Date.now(), latestVersion, data: info })
      )
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [])

  const dismiss = useCallback(() => {
    if (versionInfo) {
      // Persist the dismissed version string — not just a boolean flag.
      // This way a newer version in the future will still trigger the alert.
      localStorage.setItem(DISMISS_KEY, versionInfo.latestVersion)
      setVersionInfo({ ...versionInfo, updateAvailable: false })
    }
  }, [versionInfo])

  const clearCacheAndCheck = useCallback(() => {
    localStorage.removeItem(CACHE_KEY)
    localStorage.removeItem(DISMISS_KEY)
    checkForUpdates()
  }, [checkForUpdates])

  useEffect(() => {
    try {
      const cached = localStorage.getItem(CACHE_KEY)
      if (cached) {
        const parsed: CachedCheck = JSON.parse(cached)
        if (Date.now() - parsed.timestamp < CACHE_DURATION_MS) {
          // Respect dismiss state: only show if the user hasn't dismissed this exact version.
          const updateAvailable = shouldShowUpdate(parsed.latestVersion)
          setVersionInfo({
            ...parsed.data,
            currentVersion: CURRENT_VERSION,
            updateAvailable,
          })
          return
        }
      }
    } catch {
      // Invalid cache, ignore
    }
    checkForUpdates()
  }, [checkForUpdates])

  // Periodic check
  useEffect(() => {
    const interval = setInterval(checkForUpdates, CACHE_DURATION_MS)
    return () => clearInterval(interval)
  }, [checkForUpdates])

  return {
    versionInfo,
    loading,
    error,
    checkForUpdates,
    dismiss,
    clearCacheAndCheck,
    currentVersion: CURRENT_VERSION,
  }
}
