import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { fmt } from '../../api.js'
import { HBars, TimeChart } from '../../components/charts.jsx'
import { Card, ChartCard, Empty, ErrorBox, Level, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

const bars = (o) => Object.entries(o || {}).map(([label, value]) => ({ label, value }))

export default function Commerce() {
  const { data, error, loading } = useApi('/douane/commerce')
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const m = data.top.most_observed
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Commerce en ligne" sub="Identifier les activités commerciales en ligne qui méritent d'être comparées aux informations disponibles." />
      <PageGuide purpose="Cette page rassemble les produits et commerces publiquement visibles afin de les comparer aux flux douaniers."
        steps={['Repérez les produits et catégories les plus observés.', 'Ouvrez la source originale d’une observation.', 'Comparez avec les importations de la même catégorie.']}
        why="Seules des informations publiques et légalement accessibles sont utilisées. Une observation (une fiche ou une publication) n'est jamais transformée en nombre de ventes." />
      <Note>Observation ≠ vente : le nombre de publications ou de fiches n'indique pas un volume vendu.</Note>
      <div className="grid g4">
        <div className="card kpi"><div className="label">Produits observés</div><div className="value">{fmt.num(data.total)}</div><div className="detail">rattachés aux produits suivis</div></div>
        <div className="card kpi"><div className="label">Commerces référencés</div><div className="value">{fmt.num(data.sellers_total)}</div><div className="detail">localisation commerciale publique</div></div>
        <div className="card kpi"><div className="label">Avec page ou site public</div><div className="value">{fmt.num(data.sellers_with_links)}</div><div className="detail">lien source disponible</div></div>
        <div className="card kpi"><div className="label">Sources</div><div className="stack" style={{ gap: 4, marginTop: 8 }}>{data.sources_status.map((s) => <div key={s.name} className="row between tiny"><span>{s.name}</span><Level value={s.status === 'Connectée' ? 'Connectée' : null}>{s.status}</Level></div>)}</div></div>
      </div>

      {m && (
        <Card title="Produit le plus observé" className="section" sub="« Observé » ne signifie pas « vendu ».">
          <div className="row" style={{ gap: 22, alignItems: 'flex-start' }}>
            {m.image_url ? <img className="product-img" style={{ width: 150 }} src={m.image_url} alt="" /> : <div className="product-img placeholder" style={{ width: 150 }}>Image non disponible</div>}
            <div className="stack" style={{ gap: 6 }}>
              <h2 style={{ fontSize: 21 }}>{m.product}</h2>
              <div className="small">{m.category} · {fmt.num(m.observations)} observation(s) · {m.brands} marque(s)</div>
              <div className="small">Prix observés : {m.price_min != null ? `${fmt.num(m.price_min)} – ${fmt.num(m.price_max)} ${m.currency || ''}` : 'Information non disponible'}</div>
              <div className="small">Localisation commerciale publique : {m.zone || 'Information non disponible'}</div>
              <Link className="btn small primary" to={`/douane/produits/${m.product_id}`} style={{ alignSelf: 'flex-start', marginTop: 6 }}>Vue 360° du produit</Link>
            </div>
          </div>
        </Card>
      )}

      <div className="grid g2 section">
        <ChartCard title="Catégories observées" question="Quelles familles de produits sont les plus visibles dans le commerce public ?" rows={bars(data.categories)} unit="observations"
          help={{ why: "Pour savoir où se concentre l'offre visible.", shows: "Le nombre d'observations par catégorie.", read: 'Une catégorie très visible mérite d’être comparée à ses importations déclarées.' }}>
          <HBars rows={bars(data.categories)} unit="observations" />
        </ChartCard>
        <ChartCard title="Évolution des observations" question="L'activité observée augmente-t-elle ?" rows={(data.trend || []).map((t) => ({ label: t.period, value: t.observations }))} unit="observations" kind="time"
          help={{ why: 'Pour repérer une montée de l’activité commerciale visible.', shows: 'Le nombre de fiches ou publications datées par mois.', read: 'Une hausse de visibilité n’est pas une hausse des ventes, mais elle peut justifier une comparaison avec les flux.' }}>
          <TimeChart rows={(data.trend || []).map((t) => ({ label: t.period, value: t.observations }))} unit="observations" />
        </ChartCard>
      </div>

      <Card title="Commerce observé et importations, par catégorie" className="section" sub={data.comparison.note}>
        <div className="table-wrap"><table className="t"><thead><tr><th>Catégorie</th><th>Importations {data.comparison.year}</th><th>Produits observés</th><th>Commerces référencés</th></tr></thead>
          <tbody>{data.comparison.rows.map((r) => <tr key={r.category}><td>{r.category}</td><td>{r.imports_usd != null ? fmt.money(r.imports_usd, 'USD') : <span className="muted">Information non disponible</span>}</td><td>{fmt.num(r.observations)}</td><td>{fmt.num(r.shops)}</td></tr>)}</tbody></table></div>
      </Card>

      <Card title="Dernières observations" className="section" sub="Chaque observation reste liée à sa source originale.">
        {data.feed.length ? <div className="gallery">{data.feed.map((o, i) => (
          <figure key={i}>
            {o.image_url ? <img src={o.image_url} alt={o.product || ''} loading="lazy" /> : <div className="obs-noimg">Image non disponible</div>}
            <figcaption className="tiny"><b>{o.product || '—'}</b><br /><span className="muted">{[o.brand, o.platform].filter(Boolean).join(' · ')}</span>
              <br /><span className="muted">{o.price != null ? `${fmt.num(o.price)} ${o.currency || ''} · ` : ''}{o.date ? fmt.date(o.date) : 'date non publiée'}</span>
              {o.link && <a href={o.link} target="_blank" rel="noreferrer"><ExternalLink size={11} /> Ouvrir la source</a>}</figcaption>
          </figure>))}</div> : <Empty>Aucune observation disponible.</Empty>}
      </Card>
    </div>
  )
}
