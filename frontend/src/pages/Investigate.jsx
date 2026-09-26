import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Download, MapPin, RotateCcw } from 'lucide-react'
import { api, fmt } from '../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, StreamText, useAIRun } from '../components/ai.jsx'
import { Bar, Empty, EvidenceButton, ExportMenu, Level, PageHead, Trend, WatchButton, levelOf } from '../components/ui.jsx'

const EXAMPLES = [
  'Quels produits électroniques nécessitent le plus d’attention actuellement ?',
  'Quels produits présentent actuellement une activité inhabituelle ?',
  'Quels produits sont fortement présents dans le commerce numérique ?',
  'Par quels points d’entrée arrivent principalement les produits électroniques ?',
  'Compare les flux maritimes, aériens et terrestres.',
  'Quels produits présentent une possible fragmentation des importations ?',
  'Quelles zones nécessitent une attention particulière cette semaine ?',
  'Quels changements importants sont apparus durant les 30 derniers jours ?',
]

export default function Investigate() {
  const [q, setQ] = useState('')
  const ai = useAIRun()
  const nav = useNavigate()
  const [report, setReport] = useState(null)
  const ask = (text) => {
    const question = (text ?? q).trim()
    if (!question) return
    setQ(question); setReport(null)
    ai.run('/investigate/stream', { question })
  }
  const loc = useLocation()
  useEffect(() => { if (loc.state?.q) ask(loc.state.q) }, [loc.state?.q]) // eslint-disable-line react-hooks/exhaustive-deps
  const res = ai.result
  const genReport = async () => {
    setReport({ busy: true })
    const r = await api.stream('/reports/stream?window=30d', {}, () => {})
    setReport(r)
  }
  return (
    <div>
      <PageHead eyebrow="Investigation IA" title="Que souhaitez-vous analyser ?" sub="Posez une question : l'IA recherche les données disponibles, les croise, puis explique ses conclusions." />
      <div className="ask">
        <textarea rows={2} value={q} placeholder="Ex. : quels produits électroniques nécessitent le plus d'attention actuellement ?"
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }} />
        <AIButton onClick={() => ask()} disabled={ai.status === 'running'}>ANALYSER AVEC L'IA</AIButton>
      </div>
      {ai.status === 'idle' && (
        <div className="row" style={{ marginTop: 16, gap: 8 }}>
          {EXAMPLES.map((e) => <button key={e} className="chip" onClick={() => ask(e)}>{e}</button>)}
        </div>
      )}

      {ai.status !== 'idle' && (
        <div className="grid g-main section" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ gap: 18 }}>
            {(ai.text || res) && (
              <Reveal>
                <div className="card">
                  <div className="row between" style={{ marginBottom: 10 }}><h2>Résultat</h2><AIBadge /></div>
                  <StreamText text={ai.text} active={ai.status === 'running'} />
                </div>
              </Reveal>
            )}
            {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
            {res && (
              <>
                {res.cards.length > 0 && (
                  <Reveal delay={150}>
                    <h2 style={{ margin: '6px 0 12px' }}>{res.cards.length} priorité{res.cards.length > 1 ? 's' : ''} identifiée{res.cards.length > 1 ? 's' : ''}</h2>
                    <div className="stack" style={{ gap: 14 }}>{res.cards.map((c) => <ResultCard key={c.rank} c={c} />)}</div>
                  </Reveal>
                )}
                <Reveal delay={300}>
                  <div className="card">
                    <div className="row" style={{ gap: 8 }}>
                      <EvidenceButton evidence={res.evidence} />
                      <Link className="btn small" to={`/intelligence/carte${res.cards[0]?.product_id ? `?produit=${res.cards[0].product_id}` : ''}`}><MapPin size={13} />Voir sur la carte</Link>
                      <ExportMenu dataset="recommendations" />
                      <button className="btn small primary" onClick={genReport} disabled={report?.busy}>{report?.busy ? 'Génération du rapport…' : 'Générer le rapport'}</button>
                      {report?.id && <button className="btn small" onClick={() => api.download(`/api/reports/${report.id}/download`, 'rapport.pdf')}><Download size={13} />Télécharger le rapport</button>}
                      <button className="btn small" onClick={() => ask(res.question)}><RotateCcw size={13} />Relancer l'analyse</button>
                      <WatchButton target={res.question} />
                    </div>
                  </div>
                </Reveal>
              </>
            )}
          </div>
          <AIProgress steps={ai.steps} status={ai.status} />
        </div>
      )}
      {res && <p className="tiny muted" style={{ marginTop: 18 }}>Les résultats sont des priorités de vérification, jamais des conclusions. <button className="linklike" onClick={() => { ai.reset(); setQ(''); nav('/investigation') }}>Nouvelle question</button></p>}
    </div>
  )
}

function ResultCard({ c }) {
  const modes = Object.entries(c.entry_modes || {})
  const level = c.level || levelOf(c.priority_score)
  return (
    <div className="card result-card">
      <div className="result-img">{c.image_url ? <img src={c.image_url} alt={c.product} /> : <span className="muted tiny">Image non disponible</span>}</div>
      <div className="stack" style={{ gap: 10, minWidth: 0 }}>
        <div className="row between">
          <div><span className="rank">PRIORITÉ {c.rank}</span><h3 style={{ fontSize: 18, marginTop: 4 }}>{c.product}</h3><div className="small muted">{c.category}</div></div>
          <div style={{ textAlign: 'right' }}><div className="eyebrow">Indice de priorité</div><div className="big-num">{fmt.num(c.priority_score)}<span className="muted small"> / 100</span></div><Level value={level} /></div>
        </div>
        <div className="grid g4 mini-stats">
          <div><div className="eyebrow">Pays</div>{c.country || '—'}</div>
          <div><div className="eyebrow">Mode d'entrée</div>{c.entry_mode ? c.entry_mode.charAt(0).toUpperCase() + c.entry_mode.slice(1) : 'Non déterminé'}</div>
          <div><div className="eyebrow">Point d'entrée</div>{c.entry_point || 'Non déterminé'}</div>
          <div><div className="eyebrow">Zone commerciale</div>{c.zone || '—'}</div>
        </div>
        {modes.length > 0 && (
          <div className="grid g3 mini-stats">{modes.map(([m, v]) => (
            <div key={m}><div className="row between small"><span>{m.charAt(0).toUpperCase() + m.slice(1)}</span><b>{fmt.pct(v)}</b></div><Bar value={v} /></div>))}</div>
        )}
        <div><div className="eyebrow">Pourquoi ?</div><ul className="why">{c.why.map((w, i) => <li key={i}>{w}</li>)}</ul></div>
        <div className="row small muted" style={{ gap: 16 }}><span>Évolution : <Trend value={c.trend} /></span><span>Couverture des données : {fmt.pct(c.data_coverage)}</span>{c.period && <span>Période : {c.period}</span>}</div>
        <div className="row" style={{ gap: 6 }}>
          {c.product_id && <Link className="btn small" to={`/intelligence/produits/${c.product_id}`}>Analyser plus en détail</Link>}
          {c.recommendation_id && <EvidenceButton id={`recommendation:${c.recommendation_id}`} />}
          {!c.recommendation_id && c.product_id && <EvidenceButton id={`risk:${c.product_id}`} />}
        </div>
      </div>
    </div>
  )
}
