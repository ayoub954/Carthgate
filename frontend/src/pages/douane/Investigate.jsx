import { useState } from 'react'
import { Link } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, StreamText, useAIRun } from '../../components/ai.jsx'
import { HBars } from '../../components/charts.jsx'
import { Country } from '../../components/Country.jsx'
import { TunisiaMap } from '../../components/maps.jsx'
import { Card, ChartCard, Empty, EvidenceButton, Level, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

const EXAMPLES = [
  'Quels produits présentent le plus d’anomalies cette semaine ?',
  'Quels petits flux sont anormalement répétitifs ?',
  'Quels produits nécessitent davantage de contrôle ?',
  'Par quels points d’entrée passent les produits concernés ?',
  'Quelles zones nécessitent davantage d’attention ?',
]
const TABS = [['summary', 'Résumé'], ['why', 'Pourquoi ?'], ['data', 'Données utilisées'], ['charts', 'Graphiques'], ['map', 'Carte'], ['sources', 'Sources'], ['reco', 'Recommandation']]

export default function Investigate() {
  const [q, setQ] = useState('')
  const [tab, setTab] = useState('summary')
  const ai = useAIRun()
  const ask = (text) => {
    const question = (text ?? q).trim()
    if (!question) return
    setQ(question); setTab('summary')
    ai.run('/douane/investigate/stream', { question })
  }
  const res = ai.result
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Investigation IA" sub="Posez une question : l'IA recherche les données disponibles, les croise, puis explique sa réponse." />
      <PageGuide purpose="Cette page permet d'interroger l'ensemble des données disponibles en langage courant."
        steps={['Saisissez une question ou choisissez un exemple.', 'Suivez les étapes de l’analyse.', 'Parcourez le résumé, les preuves, les graphiques et la recommandation.']}
        why="L'IA n'invente aucun chiffre : elle sélectionne les analyses utiles à la question, les exécute sur les données disponibles, puis rédige une synthèse à partir de leurs résultats. Si une donnée manque, la réponse l'indique." />
      <div className="ask">
        <textarea rows={2} value={q} placeholder="Ex. : quels produits présentent le plus d'anomalies cette semaine ?"
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask() } }} />
        <AIButton onClick={() => ask()} disabled={ai.status === 'running'}>ANALYSER</AIButton>
      </div>
      {ai.status === 'idle' && <div className="row" style={{ marginTop: 14, gap: 8 }}>{EXAMPLES.map((e) => <button key={e} className="chip" onClick={() => ask(e)}>{e}</button>)}</div>}

      {ai.status !== 'idle' && (
        <div className="grid g-main section" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ gap: 18 }}>
            {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
            {(ai.text || res) && (
              <Reveal>
                <Card>
                  <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)} disabled={!res && k !== 'summary'}>{l}</button>)}</div>
                  {tab === 'summary' && <><div className="row between" style={{ marginBottom: 8 }}><h2>Résumé</h2><AIBadge /></div><StreamText text={ai.text} active={ai.status === 'running'} /></>}
                  {res && tab === 'why' && <Why cards={res.cards} />}
                  {res && tab === 'data' && <DataUsed ev={res.evidence} steps={res.steps} />}
                  {res && tab === 'charts' && <Charts res={res} />}
                  {res && tab === 'map' && <ZoneMap zones={res.map_zones} />}
                  {res && tab === 'sources' && <Sources ev={res.evidence} />}
                  {res && tab === 'reco' && <Reco res={res} />}
                </Card>
              </Reveal>
            )}
            {res && (
              <div className="row">
                <button className="btn small" onClick={() => ask(res.question)}><RotateCcw size={13} />Relancer l'analyse</button>
                <button className="linklike small" onClick={() => { ai.reset(); setQ('') }}>Nouvelle question</button>
              </div>
            )}
          </div>
          <AIProgress steps={ai.steps} status={ai.status} />
        </div>
      )}
    </div>
  )
}

function Why({ cards }) {
  if (!cards.length) return <Empty>Aucune situation particulière ne ressort pour cette question.</Empty>
  return (
    <div className="stack" style={{ gap: 14 }}>{cards.map((c) => (
      <div key={c.rank} className="result-card">
        <div className="result-img">{c.image_url ? <img src={c.image_url} alt={c.product} /> : <span className="muted tiny">Image non disponible</span>}</div>
        <div className="stack" style={{ gap: 8, minWidth: 0 }}>
          <div className="row between"><div><h3 style={{ fontSize: 17 }}>{c.product}</h3><div className="small muted">{c.category}</div></div>
            <div className="prio"><b>{fmt.num(c.priority_score)}/100</b></div></div>
          <div className="grid g4 mini-stats">
            <div><div className="eyebrow">Pays</div>{c.country ? <Country name={c.country} /> : 'Information non disponible'}</div>
            <div><div className="eyebrow">Mode d'entrée</div>{c.entry_mode || 'Information non disponible'}</div>
            <div><div className="eyebrow">Point d'entrée</div>{c.entry_point || 'Information non disponible'}</div>
            <div><div className="eyebrow">Zone</div>{c.zone || 'Information non disponible'}</div>
          </div>
          <ul className="why">{c.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
          {c.product_id && <Link className="btn small" to={`/douane/produits/${c.product_id}`} style={{ alignSelf: 'flex-start' }}>Vue 360° du produit</Link>}
        </div>
      </div>))}</div>
  )
}

function DataUsed({ ev, steps }) {
  return (
    <div>
      <h3>Analyses réalisées</h3>
      <ul className="rel-list">{steps.map((s, i) => <li key={i}><Level value={s.state === 'OK' ? 'Traité' : s.state === 'PARTIAL' ? 'En analyse' : 'Classé'}>{s.state === 'OK' ? 'Réalisée' : s.state === 'PARTIAL' ? 'Partielle' : 'Données insuffisantes'}</Level><div>{s.label}<div className="tiny muted">{s.summary}</div></div></li>)}</ul>
      <div className="grid g3 mini-stats" style={{ marginTop: 12 }}>
        <div><div className="eyebrow">Enregistrements analysés</div><b>{fmt.num(ev.records)}</b></div>
        <div><div className="eyebrow">Observations commerciales</div><b>{fmt.num(ev.observations)}</b></div>
        <div><div className="eyebrow">Période</div><b>{ev.period || '—'}</b></div>
      </div>
      {ev.insufficient?.length > 0 && <p className="small muted" style={{ marginTop: 10 }}>Données insuffisantes pour : {ev.insufficient.join(', ')}.</p>}
    </div>
  )
}

function Charts({ res }) {
  return (
    <div className="stack" style={{ gap: 16 }}>
      <ChartCard title="Indice de priorité des produits identifiés" question="Quels produits ressortent le plus nettement ?" rows={res.charts.priorities} unit="/100"
        help={{ why: 'Pour comparer rapidement les produits proposés par l’analyse.', shows: "L'indice de priorité (0 à 100) de chaque produit.", read: 'Plus l’indice est élevé, plus la vérification est prioritaire. Ce n’est jamais une accusation.' }}>
        <HBars rows={res.charts.priorities} unit="/100" />
      </ChartCard>
      <ChartCard title={`Origine des importations — ${res.charts.origins_scope}`} question="De quels pays proviennent ces produits ?" rows={res.charts.origins} unit="USD" countries
        source={`Nations unies — statistiques du commerce (${res.charts.origins_period || '—'})`}
        help={{ why: 'Pour connaître les principaux pays d’origine des flux.', shows: 'La valeur importée par pays d’origine.', read: 'Une forte concentration sur un pays n’est pas anormale en soi ; elle aide à cibler les vérifications.' }}>
        <HBars rows={res.charts.origins} unit="USD" countries />
      </ChartCard>
    </div>
  )
}

function ZoneMap({ zones }) {
  const m = useApi('/douane/map')
  if (!zones.length) return <Empty>Aucune zone n'est associée aux résultats de cette question.</Empty>
  const data = m.data ? { ...m.data, zones: m.data.zones.filter((z) => zones.includes(z.governorate)) } : null
  return (
    <div>
      <p className="small" style={{ marginBottom: 10 }}>Zones associées aux résultats : <b>{zones.join(', ')}</b> (localisation publique des commerces de la catégorie).</p>
      {data && <TunisiaMap data={data} layers={{ shops: false }} height={400} />}
    </div>
  )
}

function Sources({ ev }) {
  return (
    <div>
      <ul className="rules">{(ev.sources || []).map((s) => <li key={s}>{s}</li>)}</ul>
      <p className="small muted" style={{ marginTop: 8 }}>Mise à jour : {ev.updated}</p>
      {ev.links?.length > 0 && <div style={{ marginTop: 10 }}><div className="eyebrow">Liens originaux</div>{ev.links.map((l) => <div key={l} className="small"><a href={l} target="_blank" rel="noreferrer">{l}</a></div>)}</div>}
      <div style={{ marginTop: 12 }}><EvidenceButton evidence={{ sources: (ev.sources || []).map((name) => ({ name, updated: ev.updated, period: ev.period })), information_used: ev.data_used, links: ev.links }} /></div>
    </div>
  )
}

function Reco({ res }) {
  return (
    <div className="reco-box">
      <div className="eyebrow">Recommandation IA</div>
      <p style={{ fontSize: 16, marginTop: 6 }}>{res.recommendation}</p>
      <div className="row" style={{ marginTop: 12 }}>
        <Link className="btn small" to="/douane/conseiller">Voir les priorités de contrôle</Link>
        <Link className="btn small" to="/douane/anomalies">Ouvrir les dossiers</Link>
      </div>
      <p className="tiny muted" style={{ marginTop: 10 }}>Une recommandation désigne une priorité de vérification, jamais une conclusion.</p>
    </div>
  )
}
