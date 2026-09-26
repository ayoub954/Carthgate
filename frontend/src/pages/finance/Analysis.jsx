import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, useAIRun } from '../../components/ai.jsx'
import { Card, Empty, Level, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'
import FinanceCharts, { FinanceFilters } from './FinanceCharts.jsx'

export default function Analysis() {
  const [g, setG] = useState('month')
  const [f, setF] = useState({})
  const [unit, setUnit] = useState(null)
  const qs = new URLSearchParams({ granularity: g, ...(unit ? { unit } : {}), ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) }).toString()
  const an = useApi(`/finance/analytics?${qs}`)
  const ai = useAIRun()
  const res = ai.result
  const fc = an.data?.forecast
  return (
    <div>
      <PageHead eyebrow="Espace Finance" title="Analyse financière" sub="Montants, concentrations, évolutions et dossiers prioritaires — calculés sur les dossiers transmis." />
      <PageGuide purpose="Cette page aide à comprendre les montants associés aux dossiers transmis et à décider lesquels examiner en premier."
        steps={['Choisissez la période (jour, semaine, mois, année) et les filtres.', 'Cliquez sur « Générer l’analyse financière ».', 'Sous chaque graphique, demandez son explication à l’IA.']}
        why="Chaque phrase de l'analyse est calculée à partir des graphiques affichés, avec les mêmes filtres. Les dossiers en dollars et en dinars ne sont jamais additionnés entre eux."
        more="La projection de tendance n'est calculée qu'à partir de six périodes d'historique ; sinon, elle est explicitement refusée." />
      <FinanceFilters g={g} setG={setG} f={f} setF={setF} unit={an.data?.unit} setUnit={setUnit} options={an.data?.filters} />

      <div className="launch-bar section">
        <div><h2>Analyse IA</h2><p className="small muted">Synthèse · tendances · concentrations · évolutions · points importants · dossiers prioritaires · explication des graphiques.</p></div>
        <AIButton big onClick={() => ai.run('/finance/analysis/stream', { ...f, granularity: g, unit: an.data?.unit })} disabled={ai.status === 'running'}>GÉNÉRER L'ANALYSE FINANCIÈRE</AIButton>
      </div>
      {ai.status !== 'idle' && (
        <div className="grid g-main section" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ gap: 16 }}>
            {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
            {res && (
              <Reveal>
                <Card title="Analyse financière" right={<AIBadge />}>
                  {res.narrative && <p style={{ marginBottom: 12 }}>{res.narrative}</p>}
                  <div className="analysis-sections">{Object.entries(res.sections).map(([k, lines]) => (
                    <div key={k}><h3>{k}</h3><ul className="why">{lines.map((l, i) => <li key={i}>{l}</li>)}</ul></div>))}</div>
                </Card>
              </Reveal>
            )}
            {res?.priorities?.length > 0 && (
              <Reveal delay={200}>
                <Card title="Dossiers prioritaires à examiner">
                  {res.priorities.map((p) => (
                    <div key={p.transfer_id} className="row between list-row">
                      <div><b>{p.ref}</b> — {p.product}<div className="tiny muted">{p.motif}</div></div>
                      <div className="row"><span className="small">{fmt.money(p.value_concerned, p.amount_unit)}</span><Level value={p.classification} /><Link className="btn small" to={`/finance/dossiers/${p.case_id}`}>Ouvrir</Link></div>
                    </div>))}
                </Card>
              </Reveal>
            )}
          </div>
          <AIProgress steps={ai.steps} status={ai.status} title="Analyse IA en cours" />
        </div>
      )}

      <div className="section">
        {an.loading ? <Loading /> : an.data?.total ? (
          <>
            <p className="small muted" style={{ marginBottom: 12 }}>{an.data.total} dossier(s) · montants en {fmt.unit(an.data.unit)}</p>
            <FinanceCharts a={an.data} />
            <Card title="Tendance et prévision" className="section" sub="Projection des montants à vérifier pour les prochaines périodes.">
              {fc?.available ? (
                <div className="grid g3 mini-stats">{fc.points.map((p) => (
                  <div key={p.step}><div className="eyebrow">Période +{p.step}</div><b>{fmt.money(p.value, fc.unit)}</b><div className="tiny muted">entre {fmt.money(p.low, fc.unit)} et {fmt.money(p.high, fc.unit)}</div></div>))}</div>
              ) : null}
              <Note>{fc?.message}</Note>
            </Card>
          </>
        ) : <Empty title="Aucun dossier">Aucun dossier transmis ne correspond à la sélection. Les graphiques s'afficheront dès réception des premiers dossiers.</Empty>}
      </div>
    </div>
  )
}
