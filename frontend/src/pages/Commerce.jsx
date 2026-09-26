import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fmt } from '../api.js'
import { HBar, Spark } from '../components/charts.jsx'
import { Card, Empty, ErrorBox, ExportMenu, Loading, Note, PageHead, Seg, useApi } from '../components/ui.jsx'

export default function Commerce() {
  const [win, setWin] = useState('all')
  const { data, error, loading } = useApi(`/commerce?window=${win}`)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const m = data.top.most_observed
  const toBars = (o) => Object.entries(o).map(([name, value]) => ({ name, value }))
  return (
    <div>
      <PageHead title="Commerce numérique" sub="Facebook · Instagram · TikTok · sites marchands · registres de produits">
        <Seg value={win} onChange={setWin} options={[['30d', '30 jours'], ['90d', '90 jours'], ['2026', '2026'], ['all', 'Tout']]} />
        <ExportMenu dataset="observations" />
      </PageHead>
      {data.social_note && <Note>{data.social_note} L'analyse se poursuit automatiquement avec les autres sources disponibles.</Note>}
      {!data.total ? <Empty>Aucune observation commerciale sur cette période.</Empty> : (
        <>
          <div className="grid g-main">
            <Card title="Produit le plus observé" sub="« Observé » ne signifie pas « vendu ».">
              {m && (
                <div className="row" style={{ gap: 20, alignItems: 'flex-start' }}>
                  {m.image_url ? <img className="product-img" style={{ width: 160 }} src={m.image_url} alt="" /> : <div className="product-img placeholder" style={{ width: 160 }}>Image non disponible</div>}
                  <div className="stack" style={{ gap: 6 }}>
                    <h2 style={{ fontSize: 22 }}>{m.product}</h2>
                    <div className="small">{m.category} · {fmt.num(m.observations)} observations · {m.unique_sellers} vendeur(s) / page(s)</div>
                    <div className="small">Plateformes : {m.platforms.join(', ')}</div>
                    <div className="small">Prix observés : {m.price_min != null ? `${fmt.num(m.price_min)} – ${fmt.num(m.price_max)} ${m.currency || ''}` : 'non observés'}</div>
                    <div className="small">Zone commerciale : {m.zone || '—'}</div>
                    <Link className="btn small primary" to={`/intelligence/produits/${m.product_id}`} style={{ alignSelf: 'flex-start', marginTop: 6 }}>Explorer le produit</Link>
                  </div>
                </div>
              )}
            </Card>
            <Card title="Plateformes" sub={`${fmt.num(data.total)} observations`}>
              <HBar data={toBars(data.platforms)} dataKey="value" nameKey="name" />
            </Card>
          </div>
          <div className="grid g3 section">
            <Card title="Catégories"><HBar data={toBars(data.categories)} dataKey="value" nameKey="name" /></Card>
            <Card title="Vendeurs / pages les plus actifs"><HBar data={toBars(data.sellers)} dataKey="value" nameKey="name" /></Card>
            <Card title="Tendance des observations">{data.trend.length > 1 ? <Spark data={data.trend} dataKey="observations" /> : <Empty />}</Card>
          </div>
          {Object.keys(data.brands).length > 0 && <Card title="Marques" className="section"><div className="row" style={{ gap: 8 }}>{Object.entries(data.brands).map(([b, n]) => <span key={b} className="chip static">{b} · {n}</span>)}</div></Card>}
          <Card title="Dernières observations" className="section" sub="Publications et fiches produits, avec lien vers la source originale lorsqu'il existe.">
            <div className="grid g4">{data.feed.map((o, i) => (
              <div key={i} className="obs">
                {o.image_url ? <img src={o.image_url} alt="" /> : <div className="obs-noimg">Image non disponible</div>}
                <div className="small"><b>{o.product || '—'}</b></div>
                <div className="tiny muted">{[o.brand, o.platform, o.seller].filter(Boolean).join(' · ')}</div>
                <div className="tiny muted">{o.price != null ? `${fmt.num(o.price)} ${o.currency || ''} · ` : ''}{o.zone || ''} {o.date ? `· ${fmt.date(o.date)}` : ''}</div>
                {o.link && <a className="tiny" href={o.link} target="_blank" rel="noreferrer">Consulter la source ↗</a>}
              </div>))}</div>
          </Card>
        </>
      )}
    </div>
  )
}
