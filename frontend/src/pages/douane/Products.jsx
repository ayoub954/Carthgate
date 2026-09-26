import { Link } from 'react-router-dom'
import { fmt } from '../../api.js'
import { Country } from '../../components/Country.jsx'
import { Card, Empty, ErrorBox, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

const NA = <span className="muted">Information non disponible</span>

function ProductCard({ p, observed }) {
  const growth = p.growth
  return (
    <Link to={`/douane/produits/${p.product_id}`} className="card pcard">
      <div className="pcard-img">{p.image_url ? <img src={p.image_url} alt={p.product} loading="lazy" /> : <span>Image non disponible</span>}</div>
      <div className="pcard-body">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div><b>{p.product}</b><div className="tiny muted">{p.category}{p.top_brand ? ` · marque : ${p.top_brand}` : ''}</div></div>
          {p.priority_score != null && <span className="prio-pill">{fmt.num(p.priority_score)}</span>}
        </div>
        <dl className="pcard-facts">
          {observed && <><dt>Observations</dt><dd>{fmt.num(p.observations)} · {p.sources} source(s)</dd>
            <dt>Évolution</dt><dd>{growth == null ? NA : fmt.signed(growth * 100)}</dd>
            <dt>Prix observés</dt><dd>{p.price_min != null ? `${fmt.num(p.price_min)} – ${fmt.num(p.price_max)} ${p.currency || ''}` : NA}</dd>
            <dt>Zone commerciale</dt><dd>{p.zone || NA}</dd>
            <dt>Fabrication (déclarée)</dt><dd>{p.origin || NA}</dd></>}
          <dt>Pays d'origine</dt><dd>{p.provenance ? <><Country name={p.provenance.country} /> ({fmt.pct(p.provenance.share)})</> : NA}</dd>
          <dt>Continent</dt><dd>{p.provenance?.continent || NA}</dd>
          <dt>Point d'entrée</dt><dd>{p.entry_point || NA}</dd>
        </dl>
      </div>
    </Link>
  )
}

export default function Products() {
  const { data, error, loading } = useApi('/douane/products')
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Produits les plus observés" sub="Classement par nombre d'observations publiques — pas par ventes." />
      <PageGuide purpose="Cette page présente les produits suivis, leur visibilité commerciale, leur origine et leur indice de priorité."
        steps={['Repérez les produits les plus observés et leur indice.', 'Cliquez sur un produit pour ouvrir sa vue 360°.', 'Lancez l’analyse du produit pour générer son parcours.']}
        why="Le nombre d'observations compte les fiches et publications publiques rattachées au produit. Le pays d'origine provient des statistiques d'importation ; le lieu de fabrication, lorsqu'il est affiché, est celui déclaré par la source de l'observation." />
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          <Note>{data.note}</Note>
          <h2 className="section-title">Produits observés</h2>
          {data.observed.length ? <div className="pgrid">{data.observed.map((p) => <ProductCard key={p.product_id} p={p} observed />)}</div> : <Empty>Aucun produit observé.</Empty>}
          <h2 className="section-title section">Autres produits suivis</h2>
          <p className="small muted" style={{ marginBottom: 12 }}>Aucune observation publique n'est actuellement rattachée à ces produits ; leurs flux d'importation restent analysés.</p>
          <div className="pgrid">{data.others.map((p) => <ProductCard key={p.product_id} p={p} />)}</div>
        </>
      )}
    </div>
  )
}
