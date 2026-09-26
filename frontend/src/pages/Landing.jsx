import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Compass, GitMerge, Radar, Send } from 'lucide-react'
import { HOME, useAuth } from '../auth.jsx'
import { Logo, Wordmark } from '../components/Brand.jsx'

const FEATURES = [
  { icon: GitMerge, title: 'Croiser les informations', text: 'Statistiques officielles, points d’entrée, commerce observé et zones commerciales réunis dans une même lecture.' },
  { icon: Radar, title: 'Détecter les anomalies', text: 'Les petits flux répétés et les écarts de valeur sont repérés, expliqués et classés par priorité.' },
  { icon: Compass, title: 'Orienter la décision', text: 'Où concentrer les contrôles, quels produits, par quels points d’entrée — avec les preuves associées.' },
  { icon: Send, title: 'Transmettre à Finance', text: 'Après vérification humaine, les dossiers pertinents sont transmis pour analyse financière.' },
]

/** Animated flows over the hero: thin luminous arcs converging on Tunisia + drifting particles. */
function FlowLayer() {
  const arcs = [
    'M 1500 120 C 1200 80, 980 220, 860 360', 'M 1500 520 C 1250 560, 1040 470, 860 380',
    'M 1180 -20 C 1100 120, 960 260, 860 370', 'M 1500 330 C 1300 300, 1060 360, 862 372',
  ]
  return (
    <svg className="hero-flows" viewBox="0 0 1500 700" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs>
        <linearGradient id="arcG" x1="1" x2="0"><stop offset="0%" stopColor="#4fa3e0" stopOpacity="0" /><stop offset="60%" stopColor="#4fa3e0" stopOpacity=".75" /><stop offset="100%" stopColor="#c8a24a" stopOpacity=".9" /></linearGradient>
      </defs>
      {arcs.map((d, i) => (
        <g key={i}>
          <path d={d} className="arc" stroke="url(#arcG)" style={{ animationDelay: `${0.4 + i * 0.35}s` }} />
          <circle r="3.2" className="arc-dot"><animateMotion dur={`${5 + i}s`} begin={`${1 + i * 0.6}s`} repeatCount="indefinite" path={d} /></circle>
        </g>
      ))}
      <circle cx="860" cy="372" r="6" className="hub" />
      <circle cx="860" cy="372" r="16" className="hub-ring" />
      {Array.from({ length: 26 }).map((_, i) => (
        <circle key={`p${i}`} className="particle" cx={600 + ((i * 137) % 900)} cy={40 + ((i * 89) % 620)} r={1 + (i % 3) * 0.6}
          style={{ animationDelay: `${(i % 9) * 0.7}s`, animationDuration: `${7 + (i % 5)}s` }} />
      ))}
    </svg>
  )
}

export default function Landing() {
  const { user } = useAuth()
  const nav = useNavigate()
  const bg = useRef(null)
  useEffect(() => {
    const onScroll = () => { if (bg.current) bg.current.style.transform = `translateY(${window.scrollY * 0.22}px) scale(1.06)` }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  const enter = () => nav(user ? HOME[user.role] : '/connexion')
  return (
    <div className="landing">
      <header className="pub-header">
        <div className="pub-left">
          <Logo name="tun" alt="République Tunisienne" className="pub-rt" />
          <i className="inst-sep" /><Wordmark size="md" />
        </div>
        <div className="pub-right">
          <div className="pub-logos">
            <Logo name="diw" alt="Douane Tunisienne" /><i className="inst-sep" />
            <Logo name="min" alt="Ministère des Finances" /><i className="inst-sep" />
            <Logo name="dcf" alt="DFC" />
          </div>
          <button className="btn primary small" onClick={enter}>Accéder</button>
        </div>
      </header>

      <section className="hero">
        <div className="hero-bg" ref={bg} style={{ backgroundImage: 'url(/back.png)' }} />
        <div className="hero-veil" />
        <FlowLayer />
        <div className="hero-content">
          <div className="hero-eyebrow reveal-1">Intelligence financière &amp; douanière</div>
          <h1 className="hero-title reveal-2"><Wordmark size="xl" /></h1>
          <div className="gold-rule reveal-3" />
          <p className="hero-slogan reveal-3">« Là où les flux deviennent intelligence. »</p>
          <p className="hero-lines reveal-4">Croiser les informations. Détecter les anomalies. Orienter la décision.</p>
          <p className="hero-text reveal-5">CarthaGate transforme les flux commerciaux, douaniers et financiers en une vision claire pour mieux comprendre, anticiper et décider.</p>
          <div className="hero-actions reveal-6">
            <button className="btn hero-cta" onClick={enter}>ACCÉDER À CARTHAGATE <ArrowRight size={16} /></button>
            <a className="btn hero-ghost" href="#decouvrir">DÉCOUVRIR LA PLATEFORME</a>
          </div>
        </div>
      </section>

      <section className="discover" id="decouvrir">
        <div className="discover-head">
          <div className="eyebrow gold">La plateforme</div>
          <h2>Des informations dispersées, une vision exploitable</h2>
          <p>De grandes activités commerciales peuvent se cacher derrière de nombreuses petites opérations. CarthaGate les rassemble, les explique et oriente la vérification.</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f, i) => (
            <div key={f.title} className="feature" style={{ animationDelay: `${i * 120}ms` }}>
              <div className="feature-icon"><f.icon size={20} /></div>
              <h3>{f.title}</h3><p>{f.text}</p>
            </div>
          ))}
        </div>
        <div className="flow-ribbon">
          {['Flux et données', 'Analyse IA', 'Anomalies', 'Douane', 'Transmission', 'Finance'].map((s, i, a) => (
            <span key={s} className="row" style={{ gap: 10 }}><span className={`ribbon-step ${s === 'Analyse IA' ? 'ai' : ''}`}>{s}</span>{i < a.length - 1 && <i>→</i>}</span>
          ))}
        </div>
      </section>

      <footer className="pub-footer">
        <div className="row" style={{ gap: 14 }}><Logo name="tun" alt="République Tunisienne" className="foot-logo" /><Wordmark size="sm" /></div>
        <span>« Là où les flux deviennent intelligence. »</span>
        <span className="muted tiny">La décision reste toujours humaine.</span>
      </footer>
    </div>
  )
}
