import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Download, Eye, MapPin } from 'lucide-react'
import { WINDOWS, api, fmt } from '../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, StreamText, useAIRun } from '../components/ai.jsx'
import { TunisiaMap } from '../components/maps.jsx'
import { Card, Empty, EvidenceButton, ExportMenu, Level, PageHead, PriorityCard, Seg } from '../components/ui.jsx'
import { ModeSwitch, useMode } from '../mode.jsx'
import { SellerCards } from './SellersReview.jsx'

export default function Risk() {
  const [win, setWin] = useState('30d')
  const { mode } = useMode()
  const ai = useAIRun()
  const ov = ai.extra.overview
  const launch = () => ai.run(`/risk/analyze/stream?window=${win}`)
  return (
    <div>
      <PageHead title="Risques et alertes" sub="L'intelligence artificielle analyse les données disponibles afin d'identifier les situations nécessitant une attention particulière.">
        <Seg value={win} onChange={(w) => { setWin(w); ai.reset() }} options={WINDOWS} />
        <ModeSwitch compact />
      </PageHead>

      {ai.status === 'idle' && (
        <div className="launch">
          <div className="launch-orb" />
          <h2>Analyse des risques — {WINDOWS.find(([k]) => k === win)[1].toLowerCase()}</h2>
          <p className="muted">{mode === 'DEMO' ? 'Données simulées de démonstration.' : 'Données réelles disponibles.'} Aucun résultat n'est affiché avant l'analyse.</p>
          <AIButton big onClick={launch}>GÉNÉRER L'ANALYSE IA</AIButton>
        </div>
      )}

      {ai.status !== 'idle' && <AIProgress steps={ai.steps} status={ai.status} />}
      {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}

      {ov && (
        <div className="stack section" style={{ gap: 26 }}>
          <Reveal>
            <div className="synthesis">
              <AIBadge label="Synthèse IA" />
              <div className="synthesis-num">{ov.situations}</div>
              <div>situation{ov.situations > 1 ? 's' : ''} nécessite{ov.situations > 1 ? 'nt' : ''} une analyse complémentaire
                <div className="small muted">{ov.priorities.length} priorité(s) · {ov.alerts.length} alerte(s) · {ov.sellers.filter((s) => ['Prioritaire', 'Élevé'].includes(s.level)).length} vendeur(s) à vérifier</div></div>
            </div>
          </Reveal>

          <Reveal delay={150}>
            <h2 className="section-title">Les 3 priorités principales</h2>
            {ov.priorities.length ? <div className="grid g3">{ov.priorities.map((p) => <PriorityCard key={p.rank} p={p} />)}</div> : <Empty />}
          </Reveal>

          <Reveal delay={300}>
            <Card title="Alertes" sub="Chaque alerte est un signal à vérifier par un agent." right={<ExportMenu dataset="anomalies" />}>
              {ov.alerts.length ? <Alerts items={ov.alerts} /> : <Empty title="Aucune alerte">Aucune situation inhabituelle sur la période.</Empty>}
            </Card>
          </Reveal>

          <Reveal delay={450}>
            <div className="row between" style={{ marginBottom: 12 }}>
              <h2 className="section-title" style={{ margin: 0 }}>Vendeurs à vérifier</h2>
              <Link className="btn small" to="/intelligence/vendeurs">Voir tous les vendeurs</Link>
            </div>
            {ov.sellers.length ? <SellerCards items={ov.sellers} limit={4} />
              : <Empty>Aucune activité commerciale nominative vérifiable dans les données connectées — aucun vendeur n'est signalé sans élément vérifiable.</Empty>}
          </Reveal>

          <Reveal delay={600}>
            <div className="grid g2">
              <Card title="Produits à surveiller">
                {ov.products.map((p) => (
                  <div key={p.product_id} className="row between list-row">
                    <div><Link to={`/intelligence/produits/${p.product_id}`}><b>{p.product}</b></Link><div className="tiny muted">{p.why[0] || p.category}</div></div>
                    <div className="row" style={{ gap: 8 }}><b>{fmt.num(p.score)}</b><Level value={p.level} /></div>
                  </div>))}
              </Card>
              <Card title="Points d'entrée à analyser">
                {ov.entry_points.length ? ov.entry_points.map((e) => (
                  <div key={e.name} className="list-row"><b>{e.name}</b>{e.type && <span className="tiny muted"> · {e.type}</span>}<div className="tiny muted">{[...new Set(e.products)].join(', ')}{e.records ? ` · ${e.records} opération(s)` : ''}</div></div>
                )) : <Empty>Les points d'entrée ne peuvent pas être déterminés avec les données connectées.</Empty>}
              </Card>
            </div>
          </Reveal>

          <Reveal delay={750}>
            <Card title="Carte des points d'attention" sub="Points commerciaux, ports, aéroports, frontières terrestres et zones présentant des alertes. Cliquez sur une zone.">
              <TunisiaMap data={ov.map} layers={{ shops: true, entries: true, attention: true }} tall />
            </Card>
          </Reveal>

          <Reveal delay={900}>
            <Recommendation ai={ai} ov={ov} win={win} />
          </Reveal>
        </div>
      )}
    </div>
  )
}

const TYPE_ORDER = ['Fragmentation possible', 'Écart commerce / douane', 'Multiplication des petits flux', 'Formalisation à vérifier',
  'Activité commerciale inhabituelle', 'Hausse récente', 'Valeur à vérifier', 'Nouveau point d\'entrée', "Changement de mode d'entrée", 'Concentration géographique']

function Alerts({ items }) {
  const [open, setOpen] = useState(null)
  const groups = {}
  items.forEach((a) => { (groups[a.type] = groups[a.type] || []).push(a) })
  const keys = Object.keys(groups).sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b))
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row" style={{ gap: 8 }}>{keys.map((k) => (
        <button key={k} className={`chip ${open === k ? 'on' : ''}`} onClick={() => setOpen(open === k ? null : k)}>{k} · {groups[k].length}</button>))}</div>
      {(open ? groups[open] : items.slice(0, 6)).map((a) => (
        <div key={a.id} className="alert-row">
          <div className="row between"><span><span className="eyebrow">{a.type}</span> <b className="small">{a.title}</b></span><Level value={a.level === 'Élevé' ? 'Élevé' : a.level === 'Modéré' ? 'Modéré' : 'Faible'}>{a.level}</Level></div>
          <div className="small muted">{a.reasons.slice(0, 2).join(' ; ')}</div>
        </div>))}
    </div>
  )
}

function Recommendation({ ai, ov, win }) {
  const rep = useAIRun()
  const first = ov.priorities[0]
  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="card reco">
        <div className="row between" style={{ marginBottom: 10 }}><h2>Recommandation IA</h2><AIBadge /></div>
        {ai.text ? <StreamText text={ai.text} active={ai.status === 'running'} /> : <p className="muted small">Rédaction en cours…</p>}
        {ai.status === 'done' && (
          <div className="row" style={{ gap: 6, marginTop: 14 }}>
            {first?.id && <EvidenceButton id={`recommendation:${first.id}`} label="Voir pourquoi" />}
            <ExportMenu dataset="recommendations" label="Voir les données" />
            <Link className="btn small" to={`/intelligence/carte${first?.product_id ? `?produit=${first.product_id}` : ''}`}><MapPin size={13} />Voir sur la carte</Link>
            <AIButton onClick={() => rep.run(`/reports/stream?window=${win}`)} disabled={rep.status === 'running'}>GÉNÉRER LE RAPPORT IA</AIButton>
          </div>
        )}
      </div>
      {rep.status !== 'idle' && (
        <div className="card">
          <AIProgress steps={rep.steps} status={rep.status} title="Génération du rapport IA" />
          {rep.result && (
            <Reveal>
              <div className="row" style={{ gap: 8, marginTop: 14 }}>
                <b>✓ Rapport terminé</b>
                <button className="btn primary small" onClick={() => api.download(`/api/reports/${rep.result.id}/download`, 'rapport.pdf')}><Download size={13} />Télécharger le rapport</button>
                <button className="btn small" onClick={() => api.open(`/api/reports/${rep.result.id}/download?inline=true`)}><Eye size={13} />Consulter le rapport</button>
              </div>
            </Reveal>
          )}
        </div>
      )}
    </div>
  )
}
