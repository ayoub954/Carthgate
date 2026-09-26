import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { MapPin } from 'lucide-react'
import { fmt } from '../api.js'
import { HBar, Spark } from '../components/charts.jsx'
import Constellation from '../components/Constellation.jsx'
import { Bar, Card, Empty, ErrorBox, EvidenceButton, ExportMenu, Level, Loading, PageHead, SourceLine, useApi } from '../components/ui.jsx'

const TABS = [['overview', "Vue d'ensemble"], ['entry', 'Entrée en Tunisie'], ['origin', 'Provenance'], ['online', 'Commerce observé'],
  ['customs', 'Données douanières'], ['sellers', 'Vendeurs'], ['anomalies', 'Comportements'], ['network', 'Parcours'], ['sources', 'Sources']]

export default function Product360() {
  const { id } = useParams()
  const [tab, setTab] = useState('overview')
  const head = useApi(`/products/${id}?section=overview`)
  const o = head.data?.sections?.overview
  return (
    <div>
      <PageHead eyebrow={`Fiche produit · position ${id}`} title={o?.name || '…'} sub={o?.category}>
        {o?.score != null && <span className="row" style={{ gap: 8 }}><span className="muted small">Indice de priorité</span><b>{fmt.num(o.score)} / 100</b><Level value={o.level} /></span>}
        <ExportMenu dataset="customs_records" params={{ hs: id }} label="Exporter les données" />
      </PageHead>
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
      <Section id={id} tab={tab} overview={o} />
    </div>
  )
}

function Section({ id, tab, overview }) {
  const sec = tab === 'overview' ? 'risk' : tab
  const { data, error, loading } = useApi(`/products/${id}?section=${sec}`)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const s = data.sections[sec]
  switch (tab) {
    case 'overview': return <OverviewTab id={id} r={s} o={overview} />
    case 'entry': return <Entry s={s} id={id} />
    case 'origin': return <Origin s={s} />
    case 'online': return <Online s={s} />
    case 'customs': return <Customs s={s} />
    case 'sellers': return <Sellers s={s} />
    case 'anomalies': return <Anomalies s={s} />
    case 'network': return <Card title="Parcours commercial" sub="Cliquez sur un élément pour mettre en évidence son parcours."><Constellation graph={s} /></Card>
    case 'sources': return <Card title="Sources"><table className="t"><tbody>{s.map((x) => <tr key={x.source_key}><td>{x.source_url ? <a href={x.source_url} target="_blank" rel="noreferrer">{x.source_name}</a> : x.source_name}</td><td>{x.status}</td><td>{x.period || '—'}</td></tr>)}</tbody></table></Card>
    default: return null
  }
}

function OverviewTab({ id, r, o }) {
  const entry = useApi(`/products/${id}?section=entry`)
  return (
    <div className="grid g2">
      <Score id={id} r={r} />
      <div className="stack" style={{ gap: 18 }}>
        {o?.image_url && <Card><img className="product-img" style={{ maxHeight: 220 }} src={o.image_url} alt="" /></Card>}
        {entry.data && <Entry s={entry.data.sections.entry} id={id} compact />}
      </div>
    </div>
  )
}

function Score({ id, r }) {
  if (r.score == null) return <Card title="Indice de priorité"><Empty>{r.message}</Empty></Card>
  return (
    <Card title="Indice de priorité" sub={r.period} right={<EvidenceButton id={`risk:${id}`} />}>
      <div className="row" style={{ gap: 32 }}>
        <div><div className="big-num" style={{ fontSize: 44 }}>{fmt.num(r.score)}<span className="muted small"> / 100</span></div><Level value={r.level} /></div>
        <div><div className="eyebrow">Couverture des données</div><div className="big-num">{fmt.pct(r.data_coverage)}</div></div>
        <div><div className="eyebrow">Niveau de confiance</div><div className="big-num">{r.confidence}</div></div>
      </div>
      <div className="divider" />
      <h3>Pourquoi cette priorité ?</h3>
      <ul className="why">{r.why.map((w, i) => <li key={i}><b>{w.sign === '+' ? '▲' : '▽'}</b> {w.factor} — {w.detail}</li>)}</ul>
      <details style={{ marginTop: 12 }}><summary className="small muted">Détail des indicateurs</summary>
        <table className="t" style={{ marginTop: 8 }}><tbody>{r.factors.map((f) => (
          <tr key={f.label}><td>{f.label}</td><td>{f.available ? `${fmt.num(f.value)} / 100` : <span className="muted">Non disponible</span>}</td><td className="small">{f.detail}</td></tr>))}</tbody></table>
      </details>
      <p className="tiny muted" style={{ marginTop: 10 }}>Priorité de vérification — jamais une accusation. Les indicateurs sans données ne sont pas comptés.</p>
    </Card>
  )
}

function Entry({ s, id, compact }) {
  return (
    <Card title="Comment ce produit entre-t-il en Tunisie ?" right={s.available && <span className="muted small">Confiance : {s.confidence}</span>}>
      {!s.available ? <Empty title="Données insuffisantes">{s.message}</Empty> : (
        <>
          {s.modes.map((m) => (
            <div key={m.key} style={{ marginBottom: 12 }}>
              <div className="row between"><b>{{ SEA: '⚓', AIR: '✈', LAND: '◆' }[m.key]} {m.mode.toUpperCase()}</b><span className="big-num" style={{ fontSize: 20 }}>{fmt.pct(m.share)}</span></div>
              <Bar value={m.share} />
            </div>))}
          {!compact && (
            <>
              <h3 style={{ marginTop: 16 }}>Principaux points d'entrée</h3>
              <table className="t"><thead><tr><th>Point d'entrée</th><th>Type</th><th>Opérations</th><th>Part</th></tr></thead>
                <tbody>{s.entry_points.map((t) => <tr key={t.entry_point_id}><td>{t.name}</td><td>{t.type}</td><td>{t.records}</td><td>{fmt.pct(t.share)}</td></tr>)}</tbody></table>
            </>
          )}
          <div className="tiny muted" style={{ marginTop: 10 }}>{fmt.num(s.records)} opérations analysées · {s.period} · couverture {fmt.pct(s.coverage)}</div>
          <div className="row" style={{ marginTop: 12 }}>
            <Link className="btn small" to={`/intelligence/carte?produit=${id}`}><MapPin size={13} />Voir sur la carte</Link>
            <ExportMenu dataset="customs_records" params={{ hs: id }} label="Voir les données" />
          </div>
        </>
      )}
    </Card>
  )
}

function Origin({ s }) {
  if (!s.countries.length) return <Card title="Provenance"><Empty /></Card>
  return (
    <div className="grid g2">
      <Card title="Pays de provenance" sub={s.note}><HBar data={s.countries.slice(0, 10)} dataKey="value" nameKey="country" format={(v) => fmt.money(v, s.countries[0].unit)} /></Card>
      <Card title="Continents" sub={`Continent principal : ${s.top_continent}`}>
        <div className="stack">{s.continents.map((c) => <div key={c.continent}><div className="row between small"><span>{c.continent}</span><span>{fmt.pct(c.share, 1)}</span></div><Bar value={c.share} /></div>)}</div>
      </Card>
    </div>
  )
}

function Online({ s }) {
  return (
    <Card title={`Commerce observé — ${fmt.num(s.observations)} observations`} sub="« Observé » ne signifie pas « vendu ».">
      <div className="row small muted" style={{ gap: 18, marginBottom: 14 }}>
        <span>Plateformes : {Object.entries(s.platforms).map(([k, v]) => `${k} (${v})`).join(', ') || '—'}</span>
        <span>Prix observés : {s.price_min != null ? `${fmt.num(s.price_min)} – ${fmt.num(s.price_max)}` : '—'}</span>
      </div>
      {s.items.length ? <div className="grid g4">{s.items.map((i, k) => (
        <div key={k} className="obs">
          {i.image_url ? <img src={i.image_url} alt="" /> : <div className="obs-noimg">Image non disponible</div>}
          <div className="small"><b>{i.product || '—'}</b></div>
          <div className="tiny muted">{[i.brand, i.platform, i.seller].filter(Boolean).join(' · ')} · {i.observations} obs.</div>
          {i.link && <a className="tiny" href={i.link} target="_blank" rel="noreferrer">Consulter la source ↗</a>}
        </div>))}</div> : <Empty />}
    </Card>
  )
}

function Customs({ s }) {
  return (
    <div className="grid g2">
      <Card title="Importations annuelles" sub="Statistiques douanières officielles">{s.by_year.length ? <Spark data={s.by_year} dataKey="value" format={(v) => fmt.money(v, 'USD')} /> : <Empty />}<SourceLine sources={s.sources[0]} /></Card>
      <Card title={s.declarations ? 'Déclarations par mois' : `Chapitre ${s.chapter} — importations mensuelles`}>
        {s.declarations ? <Spark data={s.declarations_monthly} dataKey="value" format={(v) => fmt.money(v)} />
          : s.chapter_monthly.length ? <Spark data={s.chapter_monthly} dataKey="value" format={(v) => fmt.money(v)} /> : <Empty />}
      </Card>
    </div>
  )
}

function Sellers({ s }) {
  return (
    <Card title={`Vendeurs et commerces — ${s.total}`} sub="Commerces de la même catégorie" right={<ExportMenu dataset="sellers" />}>
      {s.items.length ? <table className="t"><thead><tr><th>Nom</th><th>Plateforme</th><th>Zone</th><th></th></tr></thead>
        <tbody>{s.items.map((x) => <tr key={x.id}><td>{x.name || <span className="muted">(nom non publié)</span>}</td><td>{x.platform || 'Commerce physique'}</td><td>{x.governorate}</td><td><Link className="btn small" to={`/intelligence/vendeurs/${x.id}`}>Fiche</Link></td></tr>)}</tbody></table> : <Empty />}
    </Card>
  )
}

function Anomalies({ s }) {
  return (
    <div className="stack" style={{ gap: 18 }}>
      <Card title="Comportements détectés" sub="Comportement habituel · À surveiller · Comportement inhabituel">
        {s.items.length ? <table className="t"><thead><tr><th>Analyse</th><th>Période</th><th>État</th><th>Pourquoi ?</th><th></th></tr></thead>
          <tbody>{s.items.map((a) => <tr key={a.id}><td className="small">{a.kind}</td><td>{a.period}</td><td><Level value={a.state} /></td><td className="small">{(a.why || []).join(' ; ')}</td><td><EvidenceButton id={`anomaly:${a.id}`} label="Preuves" /></td></tr>)}</tbody></table>
          : <Empty title="Comportement habituel">Aucun comportement inhabituel détecté.</Empty>}
      </Card>
      {s.fragmentation.length > 0 && (
        <Card title="Petits flux et fragmentation">
          <table className="t"><tbody>{s.fragmentation.map((f) => <tr key={f.window_days}><td>{f.window_days} jours</td><td><Level value={f.state} /></td><td className="small">{f.reasons.join(' ; ')}</td></tr>)}</tbody></table>
        </Card>
      )}
    </div>
  )
}
