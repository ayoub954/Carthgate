import { useState } from 'react'
import { Download } from 'lucide-react'
import { api, fmt } from '../api.js'
import { AIBadge } from '../components/ai.jsx'
import { Card, EvidenceButton, ExportMenu } from '../components/ui.jsx'

export function BriefView({ b, onClose }) {
  const [busy, setBusy] = useState(false)
  const download = async () => {
    setBusy(true)
    try {
      const r = await api.stream(`/reports/stream?window=${b.window || '30d'}`, {}, () => {})
      await api.download(`/api/reports/${r.id}/download`, 'brief.pdf')
    } finally { setBusy(false) }
  }
  const ch = b.what_changed || {}
  return (
    <Card title={`Brief douanier IA — ${fmt.date(b.date)}`} right={<><AIBadge />{onClose && <button className="btn small" onClick={onClose}>Fermer</button>}</>}>
      <div className="grid g2">
        <div>
          <div className="eyebrow">Les 3 priorités</div>
          <ol className="brief-list">{b.priorities.map((p) => <li key={p.rank}><b>{p.what}</b><div className="small muted">{p.why[0]}</div></li>)}</ol>
          <div className="eyebrow" style={{ marginTop: 16 }}>Ce qui a changé</div>
          {ch.available ? <ul className="why">{(ch.changes || []).slice(0, 4).map((c, i) => (
            <li key={i}>{c.subject} : {c.change_pct != null ? fmt.signed(c.change_pct) : 'nouveau flux'}</li>))}</ul>
            : <p className="small muted">{ch.message || 'Aucun changement important.'}</p>}
        </div>
        <table className="t"><tbody>
          <tr><td className="muted">Produit à surveiller</td><td>{b.product_to_watch?.name || '—'}</td></tr>
          <tr><td className="muted">Catégorie à surveiller</td><td>{b.category_to_watch || '—'}</td></tr>
          <tr><td className="muted">Mode d'entrée à analyser</td><td>{b.entry_mode_to_watch}</td></tr>
          <tr><td className="muted">Point d'entrée à analyser</td><td>{b.entry_point_to_watch}</td></tr>
          <tr><td className="muted">Flux à analyser</td><td>{b.flow_to_watch ? `${b.flow_to_watch.flow} — ${b.flow_to_watch.reason}` : '—'}</td></tr>
          <tr><td className="muted">Recettes potentielles à vérifier</td><td>{b.revenue_to_verify.value != null ? `${fmt.money(b.revenue_to_verify.value, b.revenue_to_verify.unit)} — ${b.revenue_to_verify.label}` : '—'}
            {b.revenue_to_verify.caveat && <div className="tiny muted">{b.revenue_to_verify.caveat}</div>}</td></tr>
          <tr><td className="muted">Couverture des données</td><td>{fmt.pct(b.data_coverage)}</td></tr>
        </tbody></table>
      </div>
      <div className="row" style={{ marginTop: 16 }}>
        <button className="btn primary small" onClick={download} disabled={busy}><Download size={13} />{busy ? 'Préparation…' : 'Télécharger'}</button>
        <ExportMenu dataset="recommendations" />
        {b.priorities[0]?.id && <EvidenceButton id={`recommendation:${b.priorities[0].id}`} />}
      </div>
    </Card>
  )
}
