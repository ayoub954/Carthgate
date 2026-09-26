import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, CheckCircle2, Clock, Inbox, Wallet } from 'lucide-react'

const KPI_ICON = { received: Inbox, to_analyse: Clock, amounts: Wallet, done: CheckCircle2 }
import { fmt } from '../../api.js'
import { Card, Empty, ErrorBox, Kpi, Loading, PageGuide, useApi } from '../../components/ui.jsx'
import FinanceCharts, { GRANS } from './FinanceCharts.jsx'
import { CaseRows } from './Cases.jsx'
import { Seg } from '../../components/ui.jsx'
import { SpaceBanner } from '../../components/Brand.jsx'
import { useAuth } from '../../auth.jsx'

export default function Overview() {
  const { user } = useAuth()
  const ov = useApi('/finance/overview')
  const [g, setG] = useState('month')
  const an = useApi(`/finance/analytics?granularity=${g}`)
  return (
    <div>
      <SpaceBanner role={user?.role} />
      <div className="hello">
        <h1>Analyse des dossiers transmis et suivi financier</h1>
      </div>
      <PageGuide purpose="Cette page résume les dossiers transmis par la Douane et les montants qu'ils représentent."
        steps={['Consultez les indicateurs et les nouveaux dossiers.', 'Lisez les graphiques et demandez leur explication à l’IA.', 'Ouvrez un dossier ou lancez l’analyse financière complète.']}
        why="Finance ne voit que les dossiers effectivement transmis après vérification par la Douane. Les montants correspondent à la valeur des opérations concernées ; ce ne sont ni des créances ni des recettes." />
      {ov.loading ? <Loading /> : ov.error ? <ErrorBox error={ov.error} /> : (
        <>
          <div className="grid g4">
            {ov.data.kpis.map((k) => k.values ? (
              <Kpi key={k.key} icon={KPI_ICON[k.key]} label={k.label} accent value={k.values.length ? k.values.map((v) => <div key={v.unit} className="kpi-line">{fmt.money(v.value, v.unit)}</div>) : '—'}
                detail={k.values.length ? `${k.detail}${k.values.some((v) => v.gap) ? ` · écarts potentiels : ${k.values.filter((v) => v.gap).map((v) => fmt.money(v.gap, v.unit)).join(' · ')}` : ''}` : 'Aucun dossier en attente'} />
            ) : <Kpi key={k.key} icon={KPI_ICON[k.key]} label={k.label} value={fmt.num(k.value)} detail={k.detail} />)}
          </div>
          <div className="grid g-main section" style={{ alignItems: 'start' }}>
            <Card title="Derniers dossiers reçus" right={<Link className="btn small" to="/finance/dossiers">Tous les dossiers</Link>}>
              {ov.data.recent.length ? <CaseRows rows={ov.data.recent} compact /> : <Empty title="Aucun dossier reçu">Les dossiers apparaissent ici dès que la Douane les transmet.</Empty>}
            </Card>
            <div className="card cta-card">
              <div className="eyebrow">Analyse IA</div>
              <h2>Comprendre les données financières</h2>
              <p className="small">L'IA produit une synthèse, les tendances, les concentrations, les évolutions et les dossiers à examiner en priorité.</p>
              <Link className="btn ai" to="/finance/analyse">Générer l'analyse financière <ArrowRight size={14} /></Link>
            </div>
          </div>
          <div className="row between section"><h2 className="section-title" style={{ margin: 0 }}>Visualisations</h2><Seg value={g} onChange={setG} options={GRANS} /></div>
          <div style={{ marginTop: 14 }}>
            {an.loading ? <Loading /> : an.data && <FinanceCharts a={an.data} only={['amounts_time', 'categories', 'priority', 'status', 'origins', 'monthly']} />}
          </div>
        </>
      )}
    </div>
  )
}
