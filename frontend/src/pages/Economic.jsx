import { useEffect, useState } from 'react'
import { api, fmt } from '../api.js'
import { AIBadge, AIButton, AIProgress, StreamText, useAIRun } from '../components/ai.jsx'
import { OutlookChart, Spark } from '../components/charts.jsx'
import { Card, Empty, ErrorBox, EvidenceButton, ExportMenu, Loading, Note, PageHead, Seg, SourceLine, useApi } from '../components/ui.jsx'
import { useMode } from '../mode.jsx'

const IND = { ins_imports: 'Importations', ins_exports: 'Exportations' }
const SCEN = [['BASELINE', 'Tendance actuelle'], ['CONSERVATIVE', 'Scénario prudent'], ['MODERATE', 'Scénario intermédiaire'], ['AMBITIOUS', 'Scénario renforcé']]

export default function Economic() {
  const [ind, setInd] = useState('ins_imports')
  const fc = useApi('/economic/forecast')
  const hist = useApi('/economic/history')
  const { mode } = useMode()
  const ai = useAIRun()
  if (fc.loading) return <Loading />
  if (fc.error) return <ErrorBox error={fc.error} />
  const f = fc.data.forecasts[ind]
  const actual = Object.fromEntries((fc.data.actual[ind] || []).map((a) => [a.year, a.value]))
  let rows = [], boundary = 2026
  if (f?.available) {
    const partial = f.annual.find((a) => a.partial)
    boundary = partial ? partial.year : Math.max(...Object.keys(actual).map(Number))
    const years = [...new Set([...Object.keys(actual).map(Number), ...f.annual.map((a) => a.year)])].sort().filter((y) => y >= 2023)
    const lastFull = Math.max(...Object.keys(actual).map(Number))
    rows = years.map((y) => {
      const a = f.annual.find((x) => x.year === y)
      return { year: y, actual: actual[y] ?? null, forecast: a ? a.predicted : (y === lastFull ? actual[y] : null), band: a ? [a.lower, a.upper] : null }
    })
  }
  return (
    <div>
      <PageHead title="Perspectives économiques" sub="Historique officiel, projection et scénarios — une projection n'est jamais une certitude.">
        <Seg value={ind} onChange={setInd} options={Object.entries(IND)} />
        <ExportMenu dataset="forecasts" />
      </PageHead>
      {mode === 'DEMO' && <Note>Cette page présente toujours des données officielles réelles.</Note>}
      <Card title={`${IND[ind]} de la Tunisie, 2023–2035 (millions de dinars)`}
        sub={f?.available ? `Historique jusqu'en ${boundary - 1} · ${boundary} : ${f.annual[0]?.actual_months} mois publiés + estimation · ${boundary + 1}–2035 : projection avec zone d'incertitude` : ''}
        right={<EvidenceButton id={`forecast:${ind}`} />}>
        {rows.length ? <OutlookChart rows={rows} lastActual={boundary} label={IND[ind]} /> : <Empty />}
        {f?.accuracy_pct != null && <p className="small muted" style={{ marginTop: 8 }}>Analyse prédictive — précision mesurée sur les données passées : {fmt.num(f.accuracy_pct)} %. Les projections s'éloignent en incertitude avec le temps.</p>}
        <SourceLine sources={fc.data.sources} />
      </Card>

      <div className="grid g2 section">
        <Card title="Explication IA" right={<AIBadge />} sub="Pourquoi cette évolution ? Quels facteurs historiques ?">
          {ai.status === 'idle' ? <AIButton onClick={() => ai.run('/economic/explain/stream')}>EXPLIQUER LA PROJECTION</AIButton> : (
            <>
              {!ai.text && <AIProgress steps={ai.steps} status={ai.status} />}
              {ai.text && <StreamText text={ai.text} active={ai.status === 'running'} />}
            </>
          )}
        </Card>
        <Card title="Historique de long terme" sub="Importations de biens et services (milliards de dinars)">
          {hist.data?.long_term?.imports?.length ? <Spark data={hist.data.long_term.imports} dataKey="value" format={(v) => `${fmt.num(v / 1e9, 1)} Md DT`} /> : <Empty />}
          <SourceLine sources={hist.data?.sources?.[1]} />
        </Card>
      </div>
      <Scenario />
    </div>
  )
}

function Scenario() {
  const presets = useApi('/economic/scenario/presets')
  const [preset, setPreset] = useState('MODERATE')
  const [a, setA] = useState({})
  const [res, setRes] = useState(null)
  useEffect(() => { if (presets.data) setA({ ...presets.data.presets[preset], effective_duty_rate_pct: presets.data.effective_duty_rate.rate_pct }) }, [preset, presets.data])
  useEffect(() => { if (Object.keys(a).length) api.post('/economic/scenario', { preset, assumptions: a }).then(setRes) }, [a]) // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card title="Simulation de scénarios" className="section" sub="Une simulation repose sur des hypothèses modifiables ; elle est distincte de la projection."
      right={<Seg value={preset} onChange={setPreset} options={SCEN} />}>
      <div className="grid g-main">
        <div>
          {res?.results ? (
            <table className="t"><thead><tr><th>Année</th><th>Importations (projection)</th><th>Recettes supplémentaires potentielles</th><th>Cumul</th></tr></thead>
              <tbody>{res.results.map((r) => <tr key={r.year}><td>{r.year}</td><td>{fmt.mdt(r.baseline_imports_mtnd)}</td>
                <td>{fmt.num(r.potential_additional_customs_revenue_mtnd, 1)} M DT <span className="tiny muted">[{fmt.num(r.revenue_lower_mtnd, 1)} – {fmt.num(r.revenue_upper_mtnd, 1)}]</span></td>
                <td>{fmt.num(r.cumulative_mtnd, 1)} M DT</td></tr>)}</tbody></table>
          ) : res ? <Empty>{res.message}</Empty> : <Loading />}
          {res?.statement && <p className="small" style={{ marginTop: 12 }}>{res.statement}</p>}
        </div>
        <div className="stack">
          {Object.entries(a).map(([k, v]) => (
            <label key={k} className="small"><div className="row between"><span>{res?.names?.[k] || k}</span><span className="tiny muted">HYPOTHÈSE</span></div>
              <input className="input" type="number" step="0.1" value={v ?? ''} onChange={(e) => setA({ ...a, [k]: e.target.value === '' ? null : Number(e.target.value) })} />
              <div className="tiny muted">{res?.assumption_labels?.[k]}</div></label>))}
        </div>
      </div>
    </Card>
  )
}
