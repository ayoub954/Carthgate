import { useState } from 'react'
import { Download, Eye } from 'lucide-react'
import { WINDOWS, api, fmt } from '../api.js'
import { AIButton, AIProgress, Reveal, useAIRun } from '../components/ai.jsx'
import { Card, Empty, ExportMenu, PageHead, Seg, useApi } from '../components/ui.jsx'

const EXPORTS = [['customs_records', 'Statistiques douanières'], ['observations', 'Observations commerciales'], ['sellers', 'Vendeurs et commerces'],
  ['anomalies', 'Comportements inhabituels'], ['risk_scores', 'Indices de priorité'], ['recommendations', 'Recommandations'],
  ['economic_indicators', 'Indicateurs économiques'], ['forecasts', 'Projections'], ['entry_points', "Points d'entrée"]]

export default function Reports() {
  const [win, setWin] = useState('30d')
  const ai = useAIRun()
  const list = useApi('/reports', [ai.result?.id])
  return (
    <div>
      <PageHead title="Rapports" sub="Rapports IA et exports de données, avec sources et périodes.">
        <Seg value={win} onChange={setWin} options={WINDOWS} />
        <AIButton onClick={() => ai.run(`/reports/stream?window=${win}`)} disabled={ai.status === 'running'}>GÉNÉRER UN RAPPORT IA</AIButton>
      </PageHead>
      {ai.status !== 'idle' && (
        <Card>
          <AIProgress steps={ai.steps} status={ai.status} title="Génération du rapport IA" />
          {ai.result && (
            <Reveal>
              <div className="row" style={{ gap: 8, marginTop: 14 }}>
                <b>✓ Rapport prêt</b>
                <button className="btn primary small" onClick={() => api.download(`/api/reports/${ai.result.id}/download`, 'rapport.pdf')}><Download size={13} />Télécharger le rapport</button>
                <button className="btn small" onClick={() => api.open(`/api/reports/${ai.result.id}/download?inline=true`)}><Eye size={13} />Consulter</button>
              </div>
            </Reveal>
          )}
          {ai.error && <Empty title="Génération impossible">{ai.error}</Empty>}
        </Card>
      )}
      <div className="grid g2 section">
        <Card title="Rapports générés">
          {list.data?.length ? list.data.map((r) => (
            <div key={r.id} className="row between list-row">
              <div><b className="small">{r.title}</b><div className="tiny muted">{fmt.date(r.created_at)}</div></div>
              <div className="row" style={{ gap: 6 }}>
                <button className="btn small" onClick={() => api.open(`/api/reports/${r.id}/download?inline=true`)}>Consulter</button>
                <button className="btn small" onClick={() => api.download(`/api/reports/${r.id}/download`, 'rapport.pdf')}><Download size={13} />Télécharger</button>
              </div>
            </div>)) : <Empty title="Aucun rapport">Générez votre premier rapport IA.</Empty>}
        </Card>
        <Card title="Exporter les données" sub="Chaque ligne indique sa source, sa période et sa date de récupération.">
          {EXPORTS.map(([k, l]) => <div key={k} className="row between list-row"><span className="small">{l}</span><ExportMenu dataset={k} /></div>)}
        </Card>
      </div>
    </div>
  )
}
