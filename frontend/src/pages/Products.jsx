import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../api.js'
import { Card, Empty, ErrorBox, ExportMenu, Level, Loading, OpenLink, PageHead, Seg, useApi } from '../components/ui.jsx'

export default function Products() {
  const [win, setWin] = useState('all')
  const { data, error, loading } = useApi(`/products?window=${win}`)
  if (error) return <ErrorBox error={error} />
  const top = data?.top_observed
  const m = top?.most_observed
  return (
    <div>
      <PageHead title="Produits" sub="Produits observés sur le marché et positions tarifaires suivies.">
        <Seg value={win} onChange={setWin} options={[['7d', '7 jours'], ['30d', '30 jours'], ['90d', '90 jours'], ['2026', '2026'], ['all', 'Tout']]} />
      </PageHead>
      {loading ? <Loading /> : (
        <>
          <Card title="Produit le plus observé" sub="« Observé » ne signifie pas « vendu ».">
            {m ? (
              <div className="grid" style={{ gridTemplateColumns: '200px 1fr', gap: 26 }}>
                {m.image_url ? <img className="product-img" src={m.image_url} alt={m.product} /> : <div className="product-img placeholder">Image non disponible</div>}
                <div className="stack" style={{ gap: 8 }}>
                  <h2 style={{ fontSize: 24 }}>{m.product}</h2>
                  <div className="grid g4 mini-stats">
                    <div><div className="eyebrow">Observations</div><b className="big-num">{fmt.num(m.observations)}</b></div>
                    <div><div className="eyebrow">Vendeurs / pages</div><b className="big-num">{fmt.num(m.unique_sellers)}</b></div>
                    <div><div className="eyebrow">Marques</div><b className="big-num">{fmt.num(m.brands)}</b></div>
                    <div><div className="eyebrow">Tendance (3 mois)</div><b className="big-num">{m.growth == null ? '—' : fmt.signed(m.growth * 100)}</b></div>
                  </div>
                  <table className="t"><tbody>
                    <tr><td className="muted">Marque principale</td><td>{m.top_brand || '—'}</td></tr>
                    <tr><td className="muted">Catégorie</td><td>{m.category}</td></tr>
                    <tr><td className="muted">Plateformes</td><td>{m.platforms.join(', ')}</td></tr>
                    <tr><td className="muted">Prix observés</td><td>{m.price_min != null ? `${fmt.num(m.price_min)} – ${fmt.num(m.price_max)} ${m.currency || ''}` : 'Non observés'}</td></tr>
                    <tr><td className="muted">Zone commerciale</td><td>{m.zone || '—'}</td></tr>
                    <tr><td className="muted">Origine déclarée</td><td>{m.origin || '—'}</td></tr>
                  </tbody></table>
                  <div className="row"><Link className="btn primary small" to={`/intelligence/produits/${m.product_id}`}>Explorer le produit</Link><OpenLink href={m.links?.[0]} /></div>
                </div>
              </div>
            ) : <Empty>{top?.message}</Empty>}
          </Card>

          <Card title="Produits les plus observés" className="section" right={<ExportMenu dataset="observations" />}>
            {top?.items?.length ? (
              <div className="table-wrap"><table className="t">
                <thead><tr><th></th><th>Produit</th><th>Catégorie</th><th>Observations</th><th>Vendeurs</th><th>Plateformes</th><th>Prix observés</th><th></th></tr></thead>
                <tbody>{top.items.map((i) => (
                  <tr key={i.product_id}>
                    <td>{i.image_url ? <img src={i.image_url} alt="" className="thumb" /> : <span className="thumb placeholder" />}</td>
                    <td><b>{i.product}</b></td><td>{i.category}</td><td>{i.observations}</td><td>{i.unique_sellers}</td>
                    <td className="small">{i.platforms.join(', ')}</td>
                    <td className="small">{i.price_min != null ? `${fmt.num(i.price_min)} – ${fmt.num(i.price_max)} ${i.currency || ''}` : '—'}</td>
                    <td><Link className="btn small" to={`/intelligence/produits/${i.product_id}`}>Voir</Link></td>
                  </tr>))}</tbody>
              </table></div>
            ) : <Empty>{top?.message}</Empty>}
          </Card>

          <Card title="Positions tarifaires suivies" sub="Indice de priorité = priorité de vérification" className="section" right={<ExportMenu dataset="risk_scores" label="Exporter le tableau" />}>
            <div className="table-wrap"><table className="t">
              <thead><tr><th>Produit</th><th>Catégorie</th><th>Importations (dernière année)</th><th>Observations</th><th>Indice de priorité</th><th>Couverture</th><th></th></tr></thead>
              <tbody>{data.monitored.map((p) => (
                <tr key={p.id}>
                  <td><b>{p.name}</b></td><td>{p.category}</td>
                  <td>{p.import_value_usd ? `${fmt.money(p.import_value_usd, 'USD')} (${p.import_year})` : '—'}</td>
                  <td>{p.observations}</td><td>{p.score != null ? <span className="row" style={{ gap: 8 }}><b>{fmt.num(p.score)}</b><Level value={p.level} /></span> : '—'}</td>
                  <td>{fmt.pct(p.data_coverage)}</td>
                  <td><Link className="btn small" to={`/intelligence/produits/${p.id}`}>Voir</Link></td>
                </tr>))}</tbody>
            </table></div>
          </Card>
        </>
      )}
    </div>
  )
}
