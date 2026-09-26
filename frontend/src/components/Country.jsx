import { ISO3, NAMES } from '../countries.js'

/** Resolve the ISO2 code from the data's ISO3 code or, failing that, the country name. Display only. */
export function iso2Of(name, iso3) {
  if (iso3 && ISO3[iso3]) return ISO3[iso3]
  if (!name) return null
  return NAMES[String(name).trim().toLowerCase()] || null
}

export const flagUrl = (name, iso3) => {
  const c = iso2Of(name, iso3)
  return c ? `/flags/${c}.svg` : null
}

/** Drapeau + nom du pays (le nom affiché reste celui des données). */
export function Country({ name, iso3, className = '' }) {
  if (!name) return null
  const url = flagUrl(name, iso3)
  return (
    <span className={`country ${className}`}>
      {url && <img className="flag" src={url} alt="" loading="lazy" />}
      <span>{name}</span>
    </span>
  )
}

/** Same, as an HTML string (map popups). */
export function countryHtml(name, iso3) {
  if (!name) return ''
  const url = flagUrl(name, iso3)
  const esc = String(name).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))
  return url ? `<img class="flag" src="${url}" alt="" /> ${esc}` : esc
}

/** Recharts Y-axis tick: flag + label (falls back to the label alone). */
export function CountryTick({ x, y, payload }) {
  const url = flagUrl(payload.value)
  const label = String(payload.value)
  return (
    <g transform={`translate(${x},${y})`}>
      {url && <image href={url} x={-150} y={-6} width={16} height={12} preserveAspectRatio="xMidYMid slice" />}
      <text x={url ? -128 : -6} y={4} textAnchor={url ? 'start' : 'end'} fontSize={11.5} fill="var(--ink-2)">{label.length > 22 ? label.slice(0, 21) + '…' : label}</text>
    </g>
  )
}
