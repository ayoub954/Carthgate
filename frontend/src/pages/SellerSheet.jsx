import { useParams } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { fmt } from '../api.js'
import { TunisiaMap } from '../components/maps.jsx'
import { Card, Empty, ErrorBox, Level, Loading, PageHead, useApi } from '../components/ui.jsx'

const LINKS = [['facebook', 'Facebook', 'Ouvrir la page'], ['instagram', 'Instagram', 'Ouvrir la page'], ['tiktok', 'TikTok', 'Ouvrir la page'], ['website', 'Site web', 'Ouvrir le site']]

export default function SellerSheet() {
  const { id } = useParams()
  const { data: s, error, loading } = useApi(`/sellers/${id}`)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const links = LINKS.filter(([k]) => s.links[k])
  return (
    <div>
      <PageHead eyebrow="Fiche vendeur / commerce" title={s.name} sub={[s.category, s.platform, s.location.governorate].filter(Boolean).join(' · ')}>
        {s.review && <span className="row" style={{ gap: 8 }}><span className="small muted">Indice de priorité</span><b>{fmt.num(s.review.score)} / 100</b><Level value={s.review.level} /></span>}
      </PageHead>
      <div className="grid g-main">
        <div className="stack" style={{ gap: 18 }}>
          <Card title="Profil">
            <table className="t"><tbody>
              <tr><td className="muted">Produits observés</td><td>{s.products.join(', ') || '—'}</td></tr>
              <tr><td className="muted">Produit principal</td><td>{s.main_product || '—'}</td></tr>
              <tr><td className="muted">Observations</td><td>{fmt.num(s.observations)}</td></tr>
              <tr><td className="muted">Prix observés</td><td>{s.price_min != null ? `${fmt.num(s.price_min)} – ${fmt.num(s.price_max)} DT` : '—'}</td></tr>
              <tr><td className="muted">Formalisation</td><td>{s.formalization}</td></tr>
              {s.review && <tr><td className="muted">Activité douanière observable</td><td>{s.review.customs_activity}</td></tr>}
              {s.review && <tr><td className="muted">Cohérence</td><td>{s.review.consistency}</td></tr>}
            </tbody></table>
            {s.review?.reasons?.length > 0 && <><div className="eyebrow" style={{ marginTop: 14 }}>Pourquoi cette fiche apparaît ?</div><ul className="why">{s.review.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul></>}
          </Card>
          <Card title="Pages et sites publiés">
            {links.length ? links.map(([k, l, cta]) => (
              <div key={k} className="row between" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}><b>{l}</b><a className="btn small" href={s.links[k]} target="_blank" rel="noreferrer"><ExternalLink size={13} />{cta}</a></div>
            )) : <p className="small muted">Aucun lien publié par la source.</p>}
            <div className="tiny muted" style={{ marginTop: 10 }}>Source : {s.sources.map((x) => x.url ? <a key={x.name} href={x.url} target="_blank" rel="noreferrer">{x.name}</a> : x.name)} {s.sources[0]?.retrieved_at && `· consulté le ${fmt.date(s.sources[0].retrieved_at)}`}</div>
          </Card>
        </div>
        <Card title="Localisation commerciale publique" sub="Jamais d'adresse privée.">
          {s.location.lat ? <TunisiaMap data={{ sellers: [{ id: s.id, lat: s.location.lat, lon: s.location.lon, name: s.name, category: s.category, governorate: s.location.governorate }], entry_points: [] }} /> : <Empty />}
        </Card>
      </div>
    </div>
  )
}
