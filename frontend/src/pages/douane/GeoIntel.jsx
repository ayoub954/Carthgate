import { useState } from 'react'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, StreamText, useAIRun } from '../../components/ai.jsx'
import { HBars, ShareBar } from '../../components/charts.jsx'
import { Country } from '../../components/Country.jsx'
import { TunisiaMap, WorldFlowMap } from '../../components/maps.jsx'
import ZonePanel from '../../components/ZonePanel.jsx'
import { Card, ChartCard, Empty, Loading, PageGuide, PageHead, Select, useApi } from '../../components/ui.jsx'

const CONT_COLORS = { Asie: 'var(--series-1)', Europe: 'var(--series-2)', Afrique: 'var(--series-3)', 'Amérique du Nord': 'var(--series-4)', 'Amérique du Sud': 'var(--series-5)', Océanie: 'var(--series-6)', Amérique: 'var(--series-7)', 'Non précisé': 'var(--axis)' }

export default function GeoIntel() {
  const map = useApi('/douane/map')
  const cat = useApi('/douane/catalog')
  const [zone, setZone] = useState(null)
  const ai = useAIRun()
  const [f, setF] = useState({ category: null, product: null, year: null })
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const o = useApi(`/douane/origins${qs ? `?${qs}` : ''}`)
  const [fp, setFp] = useState('8517')
  const fl = useApi(`/douane/flows?product=${fp}`)
  const products = (cat.data?.products || []).filter((p) => !f.category || p.category === f.category)
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Intelligence géographique" sub="Où se concentre l'activité ? D'où viennent les produits ? Par où entrent-ils ? Où renforcer l'attention ?" />
      <PageGuide purpose="Cette page croise les informations géographiques, commerciales et douanières afin d'identifier les zones nécessitant une attention particulière."
        steps={["Lancez l'analyse de la carte par l'IA.", 'Cliquez sur une zone pour comprendre pourquoi elle attire l’attention.', 'Consultez l’origine des produits et les flux vers la Tunisie.']}
        why="Seules des localisations publiques (commerces, gouvernorats, points d'entrée officiels) et les statistiques d'importation sont utilisées. Aucune personne n'est localisée à partir d'informations privées." />

      <div className="launch-bar">
        <div><h2>Analyse de la carte</h2><p className="small muted">L'IA repère les zones où se concentrent les commerces observés et les dossiers détectés.</p></div>
        <AIButton big onClick={() => ai.run('/douane/geo/analyze/stream')} disabled={ai.status === 'running'}>ANALYSER LA CARTE AVEC L'IA</AIButton>
      </div>
      {ai.status !== 'idle' && (
        <div className="grid g-main section" style={{ alignItems: 'start' }}>
          <Card title="Résultat de l'analyse géographique" right={<AIBadge />}>
            {ai.result ? <StreamText text={ai.result.text} /> : <Loading label="Analyse en cours…" />}
            {ai.result?.zones?.length > 0 && <div className="row" style={{ gap: 6, marginTop: 10 }}>{ai.result.zones.map((z) => <button key={z.governorate} className="chip" onClick={() => setZone(z.governorate)}>{z.governorate}</button>)}</div>}
          </Card>
          <AIProgress steps={ai.steps} status={ai.status} />
        </div>
      )}

      <div className="map-layout section">
        <Card title="Carte intelligente de Tunisie">
          {map.data ? <TunisiaMap data={map.data} height={560} onZone={setZone} selected={zone} /> : <Loading />}
          <div className="legend"><span><i className="lg-shop" />Activités commerciales observées</span><span><i className="lg-dot" style={{ background: '#ec835a' }} />Activités nécessitant une vérification</span>
            <span><i className="lg-dot" style={{ background: '#d03b3b' }} />Concentration d'anomalies</span><span>⚓ Port</span><span>✈ Aéroport</span><span>⇄ Passage terrestre</span></div>
        </Card>
        {zone ? <ZonePanel gov={zone} onClose={() => setZone(null)} /> : <aside className="zone-panel"><div className="eyebrow">Zone analysée</div><p className="small muted" style={{ marginTop: 8 }}>Cliquez sur une zone de la carte pour afficher son analyse.</p></aside>}
      </div>

      <h2 className="section-title section">Origine des produits</h2>
      <div className="filters">
        <Select value={f.category} onChange={(v) => setF({ ...f, category: v, product: null })} options={cat.data?.categories || []} placeholder="Toutes les catégories" />
        <Select value={f.product} onChange={(v) => setF({ ...f, product: v })} options={products.map((p) => ({ value: p.id, label: p.name }))} placeholder="Tous les produits" />
        <Select value={f.year} onChange={(v) => setF({ ...f, year: v })} options={o.data?.years || []} placeholder="Dernière année disponible" />
      </div>
      {o.loading ? <Loading /> : o.data && (
        <>
          <div className="grid g4">{o.data.concepts.map((c) => (
            <div key={c.label} className="card concept"><div className="eyebrow">{c.label}</div><b>{c.status}</b><p className="tiny muted">{c.detail}</p></div>))}</div>
          <p className="tiny muted" style={{ margin: '8px 0 0' }}>{o.data.note}</p>
          <div className="grid g2 section">
            <ChartCard title="Origine géographique des flux" question="De quel continent proviennent principalement les produits sélectionnés ?"
              rows={o.data.continents.map((c) => ({ label: c.continent, value: +(c.share * 100).toFixed(1) }))} unit="%" source={`${o.data.source} — ${o.data.year}`}
              help={{ why: 'Pour savoir quelle région du monde fournit l’essentiel des produits suivis.', shows: 'La part de chaque continent dans la valeur importée, calculée à partir des données chargées.', read: 'Un continent dominant oriente les vérifications vers ses principaux pays.' }}>
              <ShareBar rows={o.data.continents.map((c) => ({ label: c.continent, value: c.share * 100 }))} colors={CONT_COLORS} />
            </ChartCard>
            <ChartCard title="Principaux pays d'origine" question="Quels pays fournissent le plus ?" rows={o.data.countries.map((c) => ({ label: c.country, value: c.value }))} unit="USD" countries source={`${o.data.source} — ${o.data.year}`}
              help={{ why: 'Pour identifier les pays à l’origine des principaux flux.', shows: 'La valeur importée par pays d’origine.', read: 'Comparez avec les dossiers : un pays fréquent dans les dossiers mérite une attention particulière.' }}>
              <HBars rows={o.data.countries.map((c) => ({ label: c.country, value: c.value }))} unit="USD" max={10} countries />
            </ChartCard>
          </div>
          {o.data.by_category.length > 1 && (
            <Card title="Répartition par catégorie et par continent" className="section" sub="Part de chaque continent dans la valeur importée de la catégorie.">
              <div className="table-wrap"><table className="t"><thead><tr><th>Catégorie</th>{o.data.continents.map((c) => <th key={c.continent}>{c.continent}</th>)}</tr></thead>
                <tbody>{o.data.by_category.map((r) => { const tot = o.data.continents.reduce((a, c) => a + (r[c.continent] || 0), 0) || 1; return (
                  <tr key={r.category}><td>{r.category}</td>{o.data.continents.map((c) => <td key={c.continent}>{r[c.continent] ? fmt.pct(r[c.continent] / tot) : '—'}</td>)}</tr>) })}</tbody></table></div>
            </Card>
          )}
        </>
      )}

      <h2 className="section-title section">Flux vers la Tunisie</h2>
      <Card sub="Continent → pays → (mode et point d'entrée lorsqu'ils sont connus) → Tunisie. L'épaisseur d'un flux dépend de la valeur importée réellement déclarée."
        right={<Select value={fp} onChange={(v) => setFp(v || '8517')} options={(cat.data?.products || []).map((p) => ({ value: p.id, label: p.name }))} placeholder="Choisir un produit" />}>
        {fl.loading ? <Loading /> : fl.data?.paths?.length ? (
          <div className="grid g-main" style={{ alignItems: 'start' }}>
            <WorldFlowMap paths={fl.data.paths} height={400} />
            <div className="stack" style={{ gap: 6 }}>
              {fl.data.paths.map((p) => (
                <div key={p.country} className="path-row">
                  <span className="muted small">{p.continent}</span><span>→</span><b><Country name={p.country} /></b><span>→</span>
                  {p.entry ? <><span>{p.entry}</span><span>→</span></> : null}<b>Tunisie</b><span className="small muted" style={{ marginLeft: 'auto' }}>{fmt.pct(p.share)}</span>
                </div>))}
              {fl.data.entry_note && <p className="tiny muted" style={{ marginTop: 6 }}>{fl.data.entry_note}</p>}
              <p className="tiny muted">Source : {fl.data.source} ({fl.data.year})</p>
            </div>
          </div>
        ) : <Empty>Aucun flux publié pour ce produit.</Empty>}
      </Card>
    </div>
  )
}
