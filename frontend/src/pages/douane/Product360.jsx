import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, useAIRun } from '../../components/ai.jsx'
import { TimeChart } from '../../components/charts.jsx'
import { Country } from '../../components/Country.jsx'
import NeuralPath, { RelationLegend } from '../../components/NeuralPath.jsx'
import { Card, ChartCard, Empty, ErrorBox, Gauge, Level, Loading, PageGuide, useApi } from '../../components/ui.jsx'
import { LinkPanel } from './Pathway.jsx'

const NA = 'Information non disponible'

function Step({ label, children, last }) {
  return (
    <div className="v360-step">
      <div className="v360-label">{label}</div>
      <div className="v360-body">{children}</div>
      {!last && <div className="v360-arrow">↓</div>}
    </div>
  )
}

export default function Product360() {
  const { id } = useParams()
  const { data: p, error, loading } = useApi(`/douane/products/${id}`)
  const ai = useAIRun()
  const [sel, setSel] = useState(null)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const ev = p.entry
  return (
    <div>
      <Link to="/douane/produits" className="back"><ArrowLeft size={14} />Produits observés</Link>
      <PageGuide purpose="Cette vue 360° répond simplement à : quoi, d'où, comment, par où, où, qu'est-ce qui est inhabituel, pourquoi et que faire."
        steps={['Lisez la chaîne de haut en bas.', 'Lancez « Analyser ce produit » pour générer son parcours.', 'Ouvrez les dossiers ou la source d’une observation.']}
        why="Chaque étape affiche uniquement des informations disponibles ; une étape sans donnée l'indique clairement au lieu de la deviner." />
      <div className="grid g-main" style={{ alignItems: 'start' }}>
        <div className="v360">
          <div className="v360-head">
            <div className="v360-img">{p.image ? <img src={p.image.image_url} alt={p.name} /> : <span>Image non disponible</span>}</div>
            <div><div className="eyebrow">Position {p.hs} · {p.category}</div><h1>{p.name}</h1>
              {p.image && <div className="tiny muted">Image : {p.image.product} — {p.image.platform}</div>}</div>
          </div>
          <Step label="Origine">{p.origin.country ? <><b><Country name={p.origin.country} /></b> · {p.origin.continent} <span className="muted small">({fmt.pct(p.origin.share)} de la valeur importée en {p.origin.year})</span></> : NA}</Step>
          <Step label="Importation">
            {p.imports.by_year.length ? <><b>{fmt.money(p.imports.by_year.at(-1).value, 'USD')}</b> en {p.imports.by_year.at(-1).period}
              {p.imports.evolution != null && <span className={p.imports.evolution > 0 ? 'up' : 'down'}> · {fmt.signed(p.imports.evolution * 100)} sur un an</span>}</> : NA}
            <div className="tiny muted">{p.imports.frequency}</div>
          </Step>
          <Step label="Entrée en Tunisie">{ev.available ? ev.modes.map((m) => `${m.mode} ${fmt.pct(m.share)}`).join(' · ') : <span className="muted">{NA} — mer, air ou terre non publiés par les sources connectées</span>}</Step>
          <Step label="Point d'entrée">{ev.available && ev.entry_points.length ? ev.entry_points.map((e) => e.name).join(', ') : <span className="muted">{NA}</span>}</Step>
          <Step label="Activité commerciale observée">{p.online.observations ? <>{fmt.num(p.online.observations)} observation(s) · {Object.keys(p.online.platforms).join(', ')}</> : <span className="muted">Aucune observation publique rattachée</span>}</Step>
          <Step label="Localisation">{p.zones.length ? p.zones.slice(0, 3).map((z) => `${z.governorate} (${z.count})`).join(' · ') : NA}<div className="tiny muted">Commerces publics de la catégorie — association statistique</div></Step>
          <Step label="Anomalies">{p.cases.length ? p.cases.map((c) => <div key={c.id}><Link to={`/douane/dossiers/${c.id}`}>{c.ref}</Link> — {c.kind} <Level value={c.classification} /></div>) : <span className="muted">Aucune anomalie détectée</span>}</Step>
          <Step label="Indice de priorité">{p.priority_score != null ? <Gauge value={p.priority_score} /> : NA}</Step>
          <Step label="Conseil IA" last>
            <div className="row between"><b>{p.advice.action}</b><AIBadge label="Recommandation IA" /></div>
            <ul className="why">{p.advice.why.map((w, i) => <li key={i}>{w}</li>)}</ul>
          </Step>
        </div>
        <div className="stack" style={{ gap: 18 }}>
          <Card title="Analyse IA du produit" sub="Recherche des observations, de l'origine, des flux, des points d'entrée et des anomalies, puis génération du parcours.">
            <AIButton onClick={() => ai.run(`/douane/products/${id}/analyze/stream`)} disabled={ai.status === 'running'}>ANALYSER CE PRODUIT</AIButton>
            {ai.status !== 'idle' && <div style={{ marginTop: 14 }}><AIProgress steps={ai.steps} status={ai.status} /></div>}
          </Card>
          <ChartCard title="Importations annuelles" question="Les importations de ce produit augmentent-elles ?" rows={p.imports.by_year.map((r) => ({ label: r.period, value: r.value }))} unit="USD" kind="time"
            source="Nations unies — statistiques du commerce"
            help={{ why: 'Pour situer le produit dans le temps.', shows: 'La valeur importée chaque année.', read: 'Une forte hausse combinée à des dossiers ouverts renforce la priorité.' }}>
            <TimeChart rows={p.imports.by_year.map((r) => ({ label: r.period, value: r.value }))} unit="USD" height={200} />
          </ChartCard>
        </div>
      </div>

      {ai.result?.pathway && (
        <Reveal>
          <Card title={`Parcours intelligent — ${p.name}`} className="section" sub="Cliquez sur un élément pour comprendre le lien.">
            <div className="pathway-layout">
              <NeuralPath graph={ai.result.pathway} selectedId={sel?.node.id} onSelect={(node, links) => setSel({ node, links })} />
              <LinkPanel sel={sel} graph={ai.result.pathway} />
            </div>
            <RelationLegend />
          </Card>
        </Reveal>
      )}

      <Card title="Observations du produit" className="section" sub="Chaque capture reste liée à sa source. Une image illustre une observation, jamais une vente.">
        {p.gallery.length ? <div className="gallery">{p.gallery.map((g, i) => (
          <figure key={i}><img src={g.image_url} alt={g.product || ''} loading="lazy" />
            <figcaption className="tiny"><b>{g.product}</b><br /><span className="muted">{g.source} · {g.date ? fmt.date(g.date) : 'date non publiée'}</span><br />
              <span className="muted">Prix observé : {g.price != null ? fmt.num(g.price) : 'non publié'} · {g.seller || 'page non précisée'}</span>
              {g.link && <a href={g.link} target="_blank" rel="noreferrer"><ExternalLink size={11} /> Ouvrir la source</a>}</figcaption></figure>))}</div>
          : <Empty>Aucune capture publique disponible pour ce produit.</Empty>}
      </Card>
    </div>
  )
}
