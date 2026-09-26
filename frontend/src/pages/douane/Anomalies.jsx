import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { fmt } from '../../api.js'
import { Card, Empty, ErrorBox, Level, Loading, PageGuide, PageHead, Select, useApi } from '../../components/ui.jsx'

export function CaseTable({ rows, compact }) {
  return (
    <div className="table-wrap">
      <table className="t cases">
        <thead><tr>
          <th>Dossier</th><th>Produit</th>{!compact && <><th>Catégorie</th><th>Zone</th><th>Point d'entrée</th><th>Date</th></>}
          {!compact && <th>Motif</th>}<th>Indice de priorité</th>{!compact && <th>Statut</th>}<th />
        </tr></thead>
        <tbody>{rows.map((c) => (
          <tr key={c.id}>
            <td className="mono nowrap"><b>{c.ref}</b></td>
            <td>{c.product}</td>
            {!compact && <><td>{c.category}</td><td>{c.zone || <span className="muted">Information non disponible</span>}</td>
              <td>{c.entry_point || <span className="muted">Information non disponible</span>}</td><td className="nowrap">{c.date}</td></>}
            {!compact && <td className="small">{c.kind}</td>}
            <td><div className="prio"><b>{fmt.num(c.priority_score)}</b><Level value={c.classification} /></div></td>
            {!compact && <td><Level value={c.status_label} /></td>}
            <td><Link className="btn small primary nowrap" to={`/douane/dossiers/${c.id}`}>{compact ? 'Voir' : 'Voir le dossier'}</Link></td>
          </tr>))}</tbody>
      </table>
    </div>
  )
}

export default function Anomalies() {
  const [params] = useSearchParams()
  const [f, setF] = useState({ status: null, classification: null, category: params.get('category'), q: '' })
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const { data, error, loading } = useApi(`/douane/cases${qs ? `?${qs}` : ''}`)
  const set = (k) => (v) => setF({ ...f, [k]: v })
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Anomalies détectées" sub="Situations détectées par l'analyse qui méritent une vérification — jamais des conclusions." />
      <PageGuide purpose="Cette page regroupe les situations détectées par l'analyse qui méritent une vérification."
        steps={['Consultez les dossiers prioritaires.', 'Ouvrez un dossier pour comprendre pourquoi il a été signalé.', 'Après vérification, transmettez-le à Finance si nécessaire.']}
        why="Un dossier est créé lorsque l'indice de priorité d'une situation dépasse le seuil « anomalie à vérifier » (55/100). L'indice combine l'intensité du signal, l'importance économique des opérations concernées, leur actualité et les signaux concordants sur le même produit." />
      <Card>
        <div className="filters">
          <input className="input" placeholder="Rechercher un produit, un dossier…" value={f.q} onChange={(e) => set('q')(e.target.value)} style={{ maxWidth: 280 }} />
          <Select value={f.classification} onChange={set('classification')} options={data?.classifications || []} placeholder="Tous les niveaux" />
          <Select value={f.status} onChange={set('status')} options={data?.statuses || []} placeholder="Tous les statuts" />
          <Select value={f.category} onChange={set('category')} options={data?.categories || []} placeholder="Toutes les catégories" />
          {data && <span className="small muted">{data.items.length} dossier(s)</span>}
        </div>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data.items.length ? <CaseTable rows={data.items} /> :
          <Empty title="Aucun dossier">Aucune situation ne correspond à ces critères. Lancez une analyse depuis la vue d'ensemble pour actualiser les résultats.</Empty>}
      </Card>
    </div>
  )
}
