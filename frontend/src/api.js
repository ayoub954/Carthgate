// Client HTTP : toutes les analyses passent par le serveur local. Le mode (réel / démonstration)
// est transmis à chaque requête ; les deux jeux de données ne sont jamais mélangés.
let currentMode = 'REAL'
try { currentMode = localStorage.getItem('diwana-mode') || 'REAL' } catch { /* stockage indisponible */ }
try {
  const q = new URLSearchParams(window.location.search).get('mode')
  if (q) currentMode = q.toLowerCase() === 'demo' ? 'DEMO' : 'REAL'
} catch { /* ignore */ }

export const getMode = () => currentMode
export const setMode = (m) => {
  currentMode = m
  try { localStorage.setItem('diwana-mode', m) } catch { /* ignore */ }
}

const headers = (json) => ({ 'X-Data-Mode': currentMode, ...(json ? { 'Content-Type': 'application/json' } : {}) })

async function req(path, opts = {}) {
  const r = await fetch(`/api${path}`, { ...opts, headers: { ...headers(opts.body && !(opts.body instanceof FormData)), ...(opts.headers || {}) } })
  if (!r.ok) {
    let msg = 'Le service est momentanément indisponible.'
    try { const j = await r.json(); if (typeof j.detail === 'string') msg = j.detail } catch { /* ignore */ }
    throw new Error(msg)
  }
  return r.json()
}

export const api = {
  get: (p) => req(p),
  post: (p, body) => req(p, { method: 'POST', body: body instanceof FormData ? body : JSON.stringify(body || {}) }),
  exportUrl: (dataset, format, params = {}) =>
    `/api/export?${new URLSearchParams({ dataset, format, ...Object.fromEntries(Object.entries(params).filter(([, v]) => v)) })}`,
  // Téléchargement avec le mode courant (en-tête requis → fetch + blob)
  download: async (url, fallbackName = 'export') => {
    const r = await fetch(url, { headers: headers(false) })
    if (!r.ok) throw new Error('Téléchargement impossible')
    const blob = await r.blob()
    const cd = r.headers.get('content-disposition') || ''
    const name = (cd.match(/filename="?([^"]+)"?/) || [])[1] || fallbackName
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = name
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  },
  open: async (url) => {
    const r = await fetch(url, { headers: headers(false) })
    const blob = await r.blob()
    window.open(URL.createObjectURL(blob), '_blank')
  },
  // Flux d'événements (une ligne JSON par événement) émis au fil des calculs réels
  stream: async (path, body, onEvent) => {
    const r = await fetch(`/api${path}`, { method: 'POST', headers: headers(true), body: JSON.stringify(body || {}) })
    if (!r.ok || !r.body) throw new Error("L'analyse n'a pas pu démarrer.")
    const reader = r.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    let result = null
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let i
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim()
        buf = buf.slice(i + 1)
        if (!line) continue
        const ev = JSON.parse(line)
        if (ev.type === 'result') result = ev.data
        if (ev.type === 'error') throw new Error(ev.message)
        onEvent?.(ev)
      }
    }
    return result
  },
}

export const fmt = {
  num: (v, d = 0) => (v === null || v === undefined || Number.isNaN(v) ? '—' : Number(v).toLocaleString('fr-FR', { maximumFractionDigits: d, minimumFractionDigits: d })),
  pct: (v, d = 0) => (v === null || v === undefined ? '—' : `${(v * 100).toLocaleString('fr-FR', { maximumFractionDigits: d, minimumFractionDigits: d })} %`),
  signed: (v, d = 0) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: d })} %`),
  money: (v, unit = 'TND') => {
    if (v === null || v === undefined) return '—'
    const u = unit === 'USD' ? '$' : 'DT'
    if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} M ${u}`
    if (Math.abs(v) >= 1e3) return `${(v / 1e3).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} k ${u}`
    return `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} ${u}`
  },
  mdt: (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('fr-FR', { maximumFractionDigits: 0 })} M DT`),
  date: (s) => { try { return new Date(s).toLocaleDateString('fr-FR') } catch { return s } },
}

export const WINDOWS = [['today', "Aujourd'hui"], ['7d', '7 jours'], ['30d', '30 jours'], ['90d', '90 jours']]
