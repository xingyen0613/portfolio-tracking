import type { Route } from './App'

// 預覽模式（免登入展示）有自己的網址，例如 /preview/settings，
// 方便把特定分頁的連結直接分享出去（如金流服務商審核訂閱頁）。
const PREFIX = '/preview'

const ALIASES: Record<string, Route> = {
  dashboard: 'dashboard',
  sources: 'sources',
  source: 'sources',
  alerts: 'alerts',
  alert: 'alerts',
  settings: 'settings',
  setting: 'settings',
}

/** /preview 或 /preview/<route> → 對應分頁；非預覽網址回 null。 */
export function previewRouteForPath(pathname: string): Route | null {
  const clean = pathname.replace(/\/+$/, '')
  if (clean !== PREFIX && !clean.startsWith(`${PREFIX}/`)) return null
  const seg = clean.slice(PREFIX.length + 1).toLowerCase()
  return ALIASES[seg] ?? 'dashboard'
}

export function previewPath(route: Route): string {
  return `${PREFIX}/${route}`
}

export function isPreviewPath(pathname: string): boolean {
  return previewRouteForPath(pathname) !== null
}
