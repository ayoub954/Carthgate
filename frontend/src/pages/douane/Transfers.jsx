import { Link } from 'react-router-dom'
import { fmt } from '../../api.js'
import { Card, Empty, ErrorBox, Level, Loading, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

export default function Transfers() {
  const { data, error, loading } = useApi('/douane/transfers')
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Dossiers transmis" sub="Suivi des dossiers transmis à Finance et de leur statut de traitement." />
      <PageGuide purpose="Cette page permet de suivre l'avancement, côté Finance, des dossiers que vous avez transmis."
        steps={['Repérez les dossiers reçus, en analyse ou traités.', 'Ouvrez un dossier pour revoir ce qui a été transmis.']}
        why="Le statut est mis à jour par l'Espace Finance. Les outils et notes internes de Finance ne sont pas visibles depuis la Douane." />
      <Card>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data.items.length ? (
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Dossier</th><th>Produit</th><th>Catégorie</th><th>Priorité</th><th>Transmis le</th><th>Motif</th><th>Statut Finance</th><th /></tr></thead>
            <tbody>{data.items.map((t) => (
              <tr key={t.id}><td className="mono"><b>{t.ref}</b></td><td>{t.product}</td><td>{t.category}</td><td><Level value={t.classification} /></td>
                <td className="nowrap">{fmt.datetime(t.transferred_at)}</td><td className="small">{t.motif}</td><td><Level value={t.finance_status} /></td>
                <td><Link className="btn small" to={`/douane/dossiers/${t.case_id}`}>Voir le dossier</Link></td></tr>))}</tbody>
          </table></div>
        ) : <Empty title="Aucun dossier transmis">Les dossiers apparaissent ici après leur transmission depuis une fiche « Anomalie ».</Empty>}
      </Card>
    </div>
  )
}
