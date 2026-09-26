import { fmt } from '../../api.js'
import { Country } from '../../components/Country.jsx'
import { Card, Empty, ErrorBox, Kpi, Level, Loading, PageGuide, PageHead, useApi } from '../../components/ui.jsx'
import FinanceCharts from './FinanceCharts.jsx'

export default function Statistics() {
  const { data, error, loading } = useApi('/finance/statistics')
  return (
    <div>
      <PageHead eyebrow="Espace Finance" title="Statistiques" sub="Chiffres clés du traitement des dossiers transmis." />
      <PageGuide purpose="Cette page présente les statistiques de réception et de traitement des dossiers."
        steps={['Consultez les délais de prise en charge et de traitement.', 'Comparez les répartitions par zone, pays et point d’entrée.', 'Utilisez le tableau pour un contrôle détaillé.']} />
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : !data.total ? <Empty title="Aucun dossier">Les statistiques s'afficheront dès réception des premiers dossiers.</Empty> : (
        <>
          <div className="grid g4">
            <Kpi label="Dossiers reçus" value={fmt.num(data.total)} />
            <Kpi label="Délai moyen de prise en charge" value={data.avg_reception_hours != null ? `${fmt.num(data.avg_reception_hours, 1)} h` : '—'} detail="entre transmission et réception" />
            <Kpi label="Délai moyen de traitement" value={data.avg_processing_days != null ? `${fmt.num(data.avg_processing_days, 1)} j` : '—'} detail="entre transmission et traitement" />
            <Kpi label="Montants concernés" value={data.by_unit.map((u) => <div key={u.unit} className="kpi-line">{fmt.money(u.value, u.unit)}</div>)} detail="toutes unités, sans conversion" />
          </div>
          <div className="section"><FinanceCharts a={{ charts: data.charts, unit: data.unit, granularity: 'month' }} only={['zones', 'origins', 'entry_points', 'category_amount', 'products', 'gaps_time']} /></div>
          <Card title="Tableau des dossiers" className="section">
            <div className="table-wrap"><table className="t">
              <thead><tr><th>Dossier</th><th>Produit</th><th>Zone</th><th>Pays</th><th>Montant</th><th>Écart potentiel</th><th>Priorité</th><th>Statut</th></tr></thead>
              <tbody>{data.table.map((r) => <tr key={r.transfer_id}><td className="mono">{r.ref}</td><td>{r.product}</td><td>{r.zone || '—'}</td><td>{r.country ? <Country name={r.country} /> : '—'}</td>
                <td className="nowrap">{fmt.money(r.value_concerned, r.amount_unit)}</td><td className="nowrap">{fmt.money(r.gap_to_verify, r.amount_unit)}</td>
                <td><Level value={r.classification} /></td><td><Level value={r.status_label} /></td></tr>)}</tbody>
            </table></div>
          </Card>
        </>
      )}
    </div>
  )
}
