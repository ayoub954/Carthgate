import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowRight, ArrowUpRight, Bell, ChevronDown, Download, ExternalLink, FileSearch, MapPin } from 'lucide-react'
import { api, fmt } from '../api.js'
import { useMode } from '../mode.jsx'

export function useApi(path, deps = []) {
  const { mode } = useMode()
  const [state, set] = useState({ data: null, error: null, loading: true })
  useEffect(() => {
    if (!path) return
    let alive = true
    set((s) => ({ ...s, loading: true }))
    api.get(path).then((d) => alive && set({ data: d, error: null, loading: false }))
      .catch((e) => alive && set({ data: null, error: e.message, loading: false }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, mode, ...deps])
  return state
}

export function PageHead({ eyebrow, title, sub, children }) {
  return (
    <div className="page-head">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 style={{ marginTop: eyebrow ? 6 : 0 }}>{title}</h1>
        {sub && <p>{sub}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  )
}

export function Card({ title, sub, right, children, style, className = '' }) {
  return (
    <section className={`card ${className}`} style={style}>
      {(title || right) && (
        <div className="card-head">
          <div>{title && <h2>{title}</h2>}{sub && <div className="card-sub">{sub}</div>}</div>
          {right && <div className="row">{right}</div>}
        </div>
      )}
      {children}
    </section>
  )
}

export function Loading({ label = 'Chargement des données…' }) {
  return <div className="row muted small"><div className="spinner" />{label}</div>
}

export function ErrorBox({ error }) {
  return <div className="empty"><strong>Service momentanément indisponible</strong>{error}</div>
}

export function Empty({ title = 'Données insuffisantes pour cette analyse', children }) {
  return <div className="empty"><strong>{title}</strong>{children}</div>
}

export function Note({ children }) {
  return <p className="note">{children}</p>
}

const LEVEL = {
  Prioritaire: 'var(--critical)', Élevé: 'var(--serious)', Modéré: 'var(--warning)', Faible: 'var(--good)',
  'Comportement inhabituel': 'var(--critical)', 'À surveiller': 'var(--warning)', 'Comportement habituel': 'var(--good)',
  'Fragmentation possible': 'var(--critical)', Connectée: 'var(--good)', Vérifiée: 'var(--good)',
}

export function Level({ value, children }) {
  if (!value) return <span className="badge na">—</span>
  return <span className="badge"><span className="dot" style={{ background: LEVEL[value] || 'var(--muted)' }} />{children || value}</span>
}

export function levelOf(score) {
  if (score === null || score === undefined) return null
  return score >= 75 ? 'Prioritaire' : score >= 60 ? 'Élevé' : score >= 40 ? 'Modéré' : 'Faible'
}

export function Seg({ value, options, onChange }) {
  return (
    <div className="seg">
      {options.map(([v, l]) => <button key={v} className={value === v ? 'on' : ''} onClick={() => onChange(v)}>{l}</button>)}
    </div>
  )
}

export function SourceLine({ sources }) {
  const list = (Array.isArray(sources) ? sources : [sources]).filter(Boolean)
  if (!list.length) return null
  return (
    <div className="tiny muted" style={{ marginTop: 12 }}>
      Source : {list.map((s, i) => (
        <span key={i}>{i > 0 && ' · '}{typeof s === 'string' ? s : s.source_url ? <a href={s.source_url} target="_blank" rel="noreferrer">{s.source_name}</a> : s.source_name}
          {s.period ? ` (${s.period})` : ''}</span>
      ))}
    </div>
  )
}

const FORMATS = [['xlsx', 'Tableur Excel'], ['csv', 'Fichier CSV'], ['json', 'Fichier de données']]

export function ExportMenu({ dataset, params, label = 'Exporter' }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [])
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="btn small" onClick={() => setOpen(!open)}><Download size={13} />{label}<ChevronDown size={12} /></button>
      {open && (
        <div className="menu">
          {FORMATS.map(([f, l]) => <button key={f} onClick={() => { setOpen(false); api.download(api.exportUrl(dataset, f, params)) }}>{l}</button>)}
        </div>
      )}
    </div>
  )
}

export function OpenLink({ href, children = 'Consulter la source' }) {
  if (!href) return null
  return <a className="btn small" href={href} target="_blank" rel="noreferrer"><ExternalLink size={13} />{children}</a>
}

export function Modal({ title, onClose, children }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ marginBottom: 12 }}><h2>{title}</h2><button className="btn small" onClick={onClose}>Fermer</button></div>
        {children}
      </div>
    </div>
  )
}

/** VOIR LES PREUVES — sources, données utilisées, traitement, résultat (vocabulaire métier). */
export function EvidenceButton({ id, evidence, label = 'Voir les preuves' }) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const show = () => {
    setOpen(true)
    if (id) api.get(`/evidence/${id}`).then(setData).catch((e) => setErr(e.message))
  }
  return (
    <>
      <button className="btn small" onClick={show}><FileSearch size={13} />{label}</button>
      {open && (
        <Modal title="Preuves et sources" onClose={() => setOpen(false)}>
          {evidence && (
            <table className="t" style={{ marginBottom: 16 }}><tbody>
              {evidence.sources?.length > 0 && <tr><td className="muted">Sources consultées</td><td>{evidence.sources.join(' · ')}</td></tr>}
              {evidence.period && <tr><td className="muted">Période analysée</td><td>{evidence.period}</td></tr>}
              {evidence.observations !== undefined && <tr><td className="muted">Observations</td><td>{fmt.num(evidence.observations)}</td></tr>}
              {evidence.records > 0 && <tr><td className="muted">Enregistrements analysés</td><td>{fmt.num(evidence.records)}</td></tr>}
              {evidence.updated && <tr><td className="muted">Mise à jour</td><td>{evidence.updated}</td></tr>}
              {evidence.data_used?.length > 0 && <tr><td className="muted">Analyses réalisées</td><td>{evidence.data_used.join(' · ')}</td></tr>}
              {evidence.insufficient?.length > 0 && <tr><td className="muted">Données insuffisantes</td><td>{evidence.insufficient.join(' · ')}</td></tr>}
              {evidence.links?.length > 0 && <tr><td className="muted">Liens originaux</td><td>{evidence.links.map((l) => <div key={l}><a href={l} target="_blank" rel="noreferrer">{l}</a></div>)}</td></tr>}
              {evidence.data_mode === 'DEMO' && <tr><td className="muted">Nature des données</td><td><b>Données simulées de démonstration</b></td></tr>}
            </tbody></table>
          )}
          {id && !data && !err && <Loading />}
          {err && <Empty title="Preuves indisponibles">{err}</Empty>}
          {data?.chain?.map((s, i) => (
            <div key={i}>
              {i > 0 && <div className="lineage-arrow">↓</div>}
              <div className="lineage-step">
                <div className="eyebrow">{s.stage}</div>
                {s.name && <div style={{ fontWeight: 600, marginTop: 4 }}>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</div>}
                {(s.period || s.updated) && <div className="small muted">{s.period && `Période : ${s.period}`}{s.updated && ` · mise à jour le ${s.updated}`}</div>}
                {s.detail && <div className="small" style={{ marginTop: 4 }}>{s.detail}</div>}
                {s.why?.length > 0 && <ul className="why">{s.why.map((w, j) => <li key={j}>{w}</li>)}</ul>}
              </div>
            </div>
          ))}
        </Modal>
      )}
    </>
  )
}

export function WatchButton({ target, label = 'Créer une surveillance' }) {
  const [done, setDone] = useState(false)
  return (
    <button className={`btn small ${done ? 'primary' : ''}`} disabled={done}
      onClick={() => api.post('/feedback', { target_type: 'watch', target_id: target, verdict: 'WATCH', comment: target }).then(() => setDone(true))}>
      <Bell size={13} />{done ? 'Surveillance créée' : label}
    </button>
  )
}

export function Feedback({ targetType, targetId }) {
  const [sent, setSent] = useState(null)
  const send = (verdict) => api.post('/feedback', { target_type: targetType, target_id: targetId, verdict }).then(() => setSent(verdict))
  return (
    <div className="row" style={{ gap: 6 }}>
      <span className="tiny muted">Votre avis :</span>
      {[['USEFUL', 'Utile'], ['NOT_USEFUL', 'Peu utile'], ['INVESTIGATE', 'À approfondir'], ['FALSE_POSITIVE', 'Faux signal']].map(([v, l]) => (
        <button key={v} className={`btn tiny-btn ${sent === v ? 'primary' : ''}`} onClick={() => send(v)}>{l}</button>
      ))}
    </div>
  )
}

export function Trend({ value }) {
  if (!value) return <span className="muted">—</span>
  const up = value === 'hausse'
  const Icon = up ? ArrowUpRight : value === 'baisse' ? ArrowDownRight : ArrowRight
  return <span className="row" style={{ gap: 4 }}><Icon size={14} />{value.charAt(0).toUpperCase() + value.slice(1)}</span>
}

export function PriorityCard({ p, compact = false }) {
  const [open, setOpen] = useState(!compact)
  const level = p.level || levelOf(p.priority_score)
  return (
    <div className="card priority">
      <div className="row between">
        <span className="rank">PRIORITÉ {p.rank}</span>
        <Level value={level}>{level}</Level>
      </div>
      <div className="kv"><span>Quoi ?</span><b>{p.what}</b></div>
      <div className="kv"><span>Où ?</span><div>{p.where}</div></div>
      {open && (
        <>
          <div className="kv"><span>Pourquoi ?</span><ul className="why">{p.why.map((w, i) => <li key={i}>{w}</li>)}</ul></div>
          <div className="grid g3 mini-stats">
            <div><div className="eyebrow">Évolution</div><Trend value={p.trend} /></div>
            <div><div className="eyebrow">Indice de priorité</div><b>{fmt.num(p.priority_score)} / 100</b></div>
            <div><div className="eyebrow">Fiabilité des données</div><b>{fmt.pct(p.data_coverage)}</b></div>
          </div>
          <div className="kv"><span>Action suggérée</span><div>{p.recommended_review}</div></div>
        </>
      )}
      <div className="row" style={{ marginTop: 12, gap: 6 }}>
        {compact && <button className="btn small" onClick={() => setOpen(!open)}>{open ? 'Réduire' : 'Pourquoi ?'}</button>}
        {p.id && <EvidenceButton id={`recommendation:${p.id}`} />}
        {p.product_id && <Link className="btn small" to={`/intelligence/produits/${p.product_id}`}>Analyser plus en détail</Link>}
        {!compact && <Link className="btn small" to={`/intelligence/carte?produit=${p.product_id || ''}`}><MapPin size={13} />Voir sur la carte</Link>}
      </div>
      {!compact && p.id && <div style={{ marginTop: 12 }}><Feedback targetType="recommendation" targetId={p.id} /></div>}
    </div>
  )
}

export function Bar({ value, max = 1, color }) {
  return <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.max(2, Math.min(100, (value / max) * 100))}%`, background: color }} /></div>
}
