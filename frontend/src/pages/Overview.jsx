import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../api.js'
import { AIButton, AIProgress, useAIRun, Reveal } from '../components/ai.jsx'
import { TradeChart } from '../components/charts.jsx'
import { TunisiaMap } from '../components/maps.jsx'
import { Card, Empty, ErrorBox, ExportMenu, Loading, PageHead, PriorityCard, SourceLine, useApi } from '../components/ui.jsx'
import { BriefView } from './Brief.jsx'

export default function Overview() {
  const { data, error, loading } = useApi('/dashboard')
  const brief = useAIRun()
  const [showBrief, setShowBrief] = useState(false)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const k = data.kpis
  return (
    <div>
      <PageHead eyebrow="Vue d'ensemble" title="Intelligence douanière du jour" sub="Quatre indicateurs, trois priorités, un graphique, une carte.">
        <AIButton onClick={() => { setShowBrief(true); brief.run('/brief/stream?window=30d') }} disabled={brief.status === 'running'}>GÉNÉRER LE BRIEF</AIButton>
      </PageHead>
      <div className="grid g4">
        <Kpi label="Produits suivis" value={fmt.num(k.products)} detail="positions tarifaires sous surveillance" />
        <Kpi label="Alertes à examiner" value={fmt.num(k.alerts)} detail="situations à vérifier par un agent" />
        <Kpi label="Couverture des données" value={fmt.pct(k.coverage)} detail="part des indicateurs alimentés par des données" />
        <Kpi label="Recettes potentielles à vérifier" value={k.revenue_to_verify.value != null ? fmt.money(k.revenue_to_verify.value, k.revenue_to_verify.unit) : '—'}
          detail={k.revenue_to_verify.value != null ? k.revenue_to_verify.label : 'Aucun écart de valeur détecté'} />
      </div>

      {showBrief && (
        <div className="section">
          <AIProgress steps={brief.steps} status={brief.status} title="Préparation du brief douanier" />
          {brief.result && <Reveal><BriefView b={brief.result} onClose={() => setShowBrief(false)} /></Reveal>}
        </div>
      )}

      <div className="section">
        <div className="row between" style={{ marginBottom: 14 }}>
          <div><h2>Brief douanier IA</h2><div className="card-sub">Trois priorités de vérification au maximum.</div></div>
          <Link className="btn" to="/risques">Voir l'analyse complète</Link>
        </div>
        {data.brief.length ? <div className="grid g3">{data.brief.map((p) => <PriorityCard key={p.rank} p={p} compact />)}</div>
          : <Empty>Lancez une analyse dans « Risques et alertes » pour obtenir les priorités.</Empty>}
      </div>

      <div className="grid g-main section">
        <Card title={data.graph.title} sub="Données officielles mensuelles" right={<ExportMenu dataset="economic_indicators" />}>
          {data.graph.series.length ? <TradeChart series={data.graph.series} /> : <Empty />}
          <SourceLine sources={data.graph.source} />
        </Card>
        <Card title="Carte de la Tunisie" sub="● commerces publics · ✈ ⚓ ◆ points d'entrée · zones d'attention IA"
          right={<Link className="btn small" to="/intelligence/carte">Ouvrir la carte</Link>}>
          <TunisiaMap data={data.map} layers={{ shops: true, entries: true, attention: true }} />
        </Card>
      </div>
    </div>
  )
}

function Kpi({ label, value, detail }) {
  return <div className="card kpi"><div className="label">{label}</div><div className="value">{value}</div><div className="detail">{detail}</div></div>
}
