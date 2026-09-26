import { useState } from 'react'

/** Visual identity per existing role (display only — access control is unchanged and enforced by the server). */
export const IDENTITY = {
  ROLE_DOUANE: { logo: 'diw', alt: 'Douane Tunisienne', title: 'Espace Douane', subtitle: 'Intelligence et contrôle des flux', institution: 'Douane Tunisienne' },
  ROLE_FINANCE: { logo: 'min', alt: 'Ministère des Finances', title: 'Espace Finance', subtitle: 'Intelligence et analyse financière', institution: 'Ministère des Finances' },
  ROLE_ADMIN: { logo: 'dcf', alt: 'DFC', title: 'Administration CarthaGate', subtitle: 'Pilotage et supervision', institution: 'Administration CarthaGate' },
}

/** Institutional logo from /public (dcf, min, diw, tun, back). Hidden if the file is absent — never replaced by a drawing. */
export function Logo({ name, alt = '', className = '', style }) {
  const [ok, setOk] = useState(true)
  if (!ok) return null
  return <img src={`/${name}.png`} alt={alt} className={`inst-logo ${className}`} style={style} onError={() => setOk(false)} />
}

export function Wordmark({ size = 'md', light }) {
  return (
    <span className={`wordmark ${size} ${light ? 'light' : ''}`}>
      Cartha<span className="wm-gold">Gate</span>
    </span>
  )
}

/** Balanced institutional strip: République Tunisienne, then Douane · Finances · DFC separated by fine gold rules. */
export function InstitutionStrip({ compact }) {
  return (
    <div className={`inst-strip ${compact ? 'compact' : ''}`}>
      <Logo name="tun" alt="République Tunisienne" className="inst-tun" />
      <i className="inst-sep" />
      <Logo name="diw" alt="Douane Tunisienne" />
      <i className="inst-sep" />
      <Logo name="min" alt="Ministère des Finances" />
      <i className="inst-sep" />
      <Logo name="dcf" alt="DFC" />
    </div>
  )
}

/** Dashboard banner with the institution's logo (identity from the existing role). */
export function SpaceBanner({ role, children }) {
  const id = IDENTITY[role]
  if (!id) return null
  return (
    <div className="space-banner">
      <Logo name={id.logo} alt={id.alt} className="banner-logo" />
      <div className="banner-text">
        <div className="banner-kicker">{id.institution} · <Wordmark size="xs" /></div>
        <div className="banner-title">{id.title}</div>
        <div className="banner-sub">{id.subtitle}</div>
      </div>
      {children && <div className="banner-extra">{children}</div>}
    </div>
  )
}
