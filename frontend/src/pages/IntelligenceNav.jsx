import { NavLink } from 'react-router-dom'

const LINKS = [
  ['/intelligence/produits', 'Produits'],
  ['/intelligence/commerce', 'Commerce numérique'],
  ['/intelligence/vendeurs', 'Vendeurs à vérifier'],
  ['/intelligence/pays', 'Pays et provenance'],
  ['/intelligence/carte', 'Carte'],
  ['/intelligence/parcours', 'Parcours commercial'],
]

export default function IntelligenceNav() {
  return (
    <div className="subnav">
      <span className="eyebrow">Intelligence commerciale</span>
      <div className="subnav-links">{LINKS.map(([to, l]) => <NavLink key={to} to={to}>{l}</NavLink>)}</div>
    </div>
  )
}
