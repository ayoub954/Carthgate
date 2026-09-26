import { useState } from 'react'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, StreamText, useAIRun } from '../../components/ai.jsx'
import { OutlookChart, TimeChart } from '../../components/charts.jsx'
import { Card, ChartCard, Empty, ErrorBox, Loading, PageGuide, PageHead, Seg, useApi } from '../../components/ui.jsx'

const IND = { ins_imports: 'Importations', ins_exports: 'Exportations' }

export default function Economic() {
  const [ind, setInd] = useState('ins_imports')
  const { data, error, loading } = useApi('/finance/economic')
  const ai = useAIRun()
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const fc = data.forecast
  const f = fc.forecasts[ind]
  const actual = Object.fromEntries((fc.actual[ind] || []).map((a) => [a.year, a.value]))
  let rows = []
  let boundary = new Date().getFullYear()
  if (f?.available) {
    const partial = f.annual.find((a) => a.partial)
    boundary = partial ? partial.year : Math.max(...Object.keys(actual).map(Number))
    const lastFull = Math.max(...Object.keys(actual).map(Number))
    const years = [...new Set([...Object.keys(actual).map(Number), ...f.annual.map((a) => a.year)])].sort().filter((y) => y >= 2021)
    rows = years.map((y) => {
      const a = f.annual.find((x) => x.year === y)
      return { year: y, actual: actual[y] ?? null, forecast: a ? a.predicted : (y === lastFull ? actual[y] : null), band: a ? [a.lower, a.upper] : null }
    })
  }
  const monthly = (data.history.monthly_ins || []).slice(-36)
  const key = ind === 'ins_imports' ? 'imports' : 'exports'
  const mrows = monthly.map((m) => ({ label: m.period, value: m[key] }))
  const bal = monthly.map((m) => ({ label: m.period, value: m.balance }))
  return (
    <div>
      <PageHead eyebrow="Espace Finance" title="Analyse économique" sub="Contexte officiel du commerce extérieur de la Tunisie : historique, tendances et prévisions.">
        <Seg value={ind} onChange={setInd} options={Object.entries(IND)} />
      </PageHead>
      <PageGuide purpose="Cette page replace les dossiers dans le contexte économique national, à partir des publications officielles."
        steps={['Choisissez importations ou exportations.', 'Comparez l’historique et la projection.', 'Demandez à l’IA d’expliquer la projection.']}
        why="La projection est calculée sur l'historique officiel mensuel ; plusieurs méthodes sont comparées sur le passé et la plus précise est retenue. Une projection n'est jamais une certitude : la zone grisée indique l'incertitude." />
      <Card title={`${IND[ind]} de la Tunisie (millions de dinars)`} sub={f?.available ? `Historique puis projection · précision mesurée sur le passé : ${f.accuracy_pct != null ? fmt.num(f.accuracy_pct) + ' %' : 'non mesurée'}` : ''}>
        {rows.length ? <OutlookChart rows={rows} lastActual={boundary} label={IND[ind]} /> : <Empty>Projection non disponible.</Empty>}
        <div className="tiny muted" style={{ marginTop: 8 }}>Source : INS — Commerce extérieur (publication officielle)</div>
      </Card>
      <div className="grid g2 section">
        <ChartCard title={`${IND[ind]} mensuelles`} question="Comment évolue le commerce extérieur mois par mois ?" rows={mrows} unit="M DT" kind="time" source="INS — publication mensuelle"
          help={{ why: 'Pour situer les dossiers dans la conjoncture.', shows: 'La valeur mensuelle officielle, en millions de dinars.', read: 'Des variations saisonnières sont normales ; observez la tendance sur plusieurs mois.' }}>
          <TimeChart rows={mrows} unit="M DT" line />
        </ChartCard>
        <ChartCard title="Solde commercial mensuel" question="La balance commerciale se dégrade-t-elle ?" rows={bal} unit="M DT" kind="time" source="INS — publication mensuelle"
          help={{ why: 'Pour suivre l’équilibre entre exportations et importations.', shows: 'Exportations moins importations, chaque mois.', read: 'Une valeur négative correspond à un déficit commercial.' }}>
          <TimeChart rows={bal} unit="M DT" line />
        </ChartCard>
      </div>
      <Card title="Explication IA de la projection" className="section" right={<AIBadge />}>
        {ai.status === 'idle' ? <AIButton onClick={() => ai.run('/finance/economic/explain/stream')}>EXPLIQUER LA PROJECTION</AIButton> : (
          <>{!ai.text && <AIProgress steps={ai.steps} status={ai.status} />}{ai.text && <StreamText text={ai.text} active={ai.status === 'running'} />}</>
        )}
      </Card>
    </div>
  )
}
