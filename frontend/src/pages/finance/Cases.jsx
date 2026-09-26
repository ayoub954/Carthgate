import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../../api.js'
import { Card, Empty, ErrorBox, Level, Loading, PageGuide, PageHead, Select, useApi } from '../../components/ui.jsx'

export function CaseRows({ rows, compact }) {
  return (
    <div className="table-wrap"><table className="t">
      <thead><tr><th>Dossier</th><th>Produit</th>{!compact && <th>Catégorie</th>}<th>Montant concerné</th>{!compact && <th>Priorité</th>}{!compact && <th>Reçu le</th>}<th>Statut</th><th /></tr></thead>
      <tbody>{rows.map((r) => (
        <tr key={r.transfer_id} className={r.status === 'TRANSMIS' ? 'unread-row' : ''}>
          <td className="mono nowrap"><b>{r.ref}</b>{r.status === 'TRANSMIS' && <span className="new-dot" title="Nouveau" />}</td>
          <td>{r.product}</td>{!compact && <td>{r.category}</td>}
          <td className="nowrap">{r.value_concerned != null ? fmt.money(r.value_concerned, r.amount_unit) : <span className="muted">Information non disponible</span>}</td>
          {!compact && <td><Level value={r.classification} /></td>}{!compact && <td className="nowrap">{fmt.date(r.transferred_at)}</td>}<td><Level value={r.status_label} /></td>
          <td><Link className="btn small primary nowrap" to={`/finance/dossiers/${r.case_id}`}>Ouvrir</Link></td>
        </tr>))}</tbody>
    </table></div>
  )
}

export default function Cases() {
  const [f, setF] = useState({})
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const { data, error, loading } = useApi(`/finance/cases${qs ? `?${qs}` : ''}`)
  const set = (k) => (v) => setF({ ...f, [k]: v })
  const o = data?.filters
  return (
    <div>
      <PageHead eyebrow="Espace Finance" title="Dossiers reçus" sub="Dossiers transmis par la Douane après vérification humaine." />
      <PageGuide purpose="Cette page liste tous les dossiers transmis à Finance, avec leur montant, leur priorité et leur statut."
        steps={['Filtrez par catégorie, zone, pays ou statut.', 'Ouvrez un dossier : il passe automatiquement au statut « Reçu ».', 'Faites-le avancer vers « En analyse » puis « Traité ».']} />
      <Card>
        <div className="filters">
          <Select value={f.category} onChange={set('category')} options={o?.category || []} placeholder="Toutes les catégories" />
          <Select value={f.zone} onChange={set('zone')} options={o?.zone || []} placeholder="Toutes les zones" />
          <Select value={f.country} onChange={set('country')} options={o?.country || []} placeholder="Tous les pays" />
          <Select value={f.status} onChange={set('status')} options={o?.status || []} placeholder="Tous les statuts" />
        </div>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data.items.length ? <CaseRows rows={data.items} /> :
          <Empty title="Aucun dossier">Aucun dossier transmis ne correspond à ces critères.</Empty>}
      </Card>
    </div>
  )
}
