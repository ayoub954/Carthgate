import { Link } from 'react-router-dom'
import { ArrowRight, Sparkles } from 'lucide-react'

const STEPS = ['Observer', 'Croiser', 'Détecter', 'Comprendre', 'Prioriser', 'Vérifier']

export default function Home() {
  return (
    <div>
      <section className="hero">
        <div className="eyebrow">Plateforme d'intelligence douanière assistée par IA</div>
        <h1 style={{ marginTop: 16 }}>DIWANA TRACE AI</h1>
        <p className="tag">De données fragmentées à une intelligence douanière exploitable.</p>
        <p className="sub">Croiser commerce observé, flux douaniers et géographie pour identifier ce qui mérite une vérification — et expliquer pourquoi.</p>
        <div className="row" style={{ marginTop: 34 }}>
          <Link to="/investigation" className="btn ai big"><Sparkles size={18} />LANCER UNE INVESTIGATION <ArrowRight size={16} /></Link>
          <Link to="/risques" className="btn big-ghost">Risques et alertes</Link>
        </div>
        <div className="flow">
          {STEPS.map((s, i) => (
            <span key={s} className="row" style={{ gap: 8 }}>
              {i > 0 && <span className="arrow">→</span>}<span className="step">{s}</span>
            </span>
          ))}
        </div>
      </section>
      <div className="grid g3" style={{ maxWidth: 1000 }}>
        {[
          ['Des sources vérifiables', 'Chaque résultat indique ses sources, sa période et son niveau de confiance.'],
          ['Une IA qui explique', "L'intelligence artificielle croise les données, détecte les situations inhabituelles et explique ses conclusions."],
          ["L'agent décide", 'Trois priorités maximum. Une priorité est une priorité de vérification — jamais une accusation.'],
        ].map(([t, d]) => <div key={t} className="card"><h3>{t}</h3><p className="small muted" style={{ marginTop: 8 }}>{d}</p></div>)}
      </div>
    </div>
  )
}
