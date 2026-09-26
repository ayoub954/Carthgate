import { Link } from 'react-router-dom'
import { MapPin, Waypoints } from 'lucide-react'
import { fmt } from '../../api.js'
import { AIBadge, AIButton, AIProgress, Reveal, StreamText, useAIRun } from '../../components/ai.jsx'
import { Card, Empty, EvidenceButton, Gauge, Level, Note, PageGuide, PageHead } from '../../components/ui.jsx'

export default function Advisor() {
  const ai = useAIRun()
  const res = ai.result
  return (
    <div>
      <PageHead eyebrow="Conseiller IA" title="Où concentrer les contrôles ?" sub="L'IA analyse les données disponibles et propose des priorités de vérification." />
      <PageGuide purpose="Cette page propose au maximum trois priorités de contrôle : zone, point d'entrée, catégorie, raisons et action recommandée."
        steps={['Cliquez sur « Générer les priorités ».', 'Lisez pour chaque priorité les raisons et la recommandation.', 'Vérifiez les preuves, la carte ou les dossiers avant d’agir.']}
        why="Les priorités regroupent les dossiers ouverts par catégorie, zone et point d'entrée, puis les classent selon leur indice le plus élevé et le nombre de dossiers similaires. Aucune recommandation n'est produite sans dossier qui la justifie." />
      <div className="launch-bar">
        <div><h2>Priorités de vérification</h2><p className="small muted">Géographie, produits, points d'entrée, anomalies et évolution récente sont analysés ensemble.</p></div>
        <AIButton big onClick={() => ai.run('/douane/advisor/stream')} disabled={ai.status === 'running'}>GÉNÉRER LES PRIORITÉS</AIButton>
      </div>
      {ai.status !== 'idle' && (
        <div className="grid g-main section" style={{ alignItems: 'start' }}>
          <div className="stack" style={{ gap: 16 }}>
            {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
            {ai.text && <Card right={<AIBadge />} title="Synthèse"><StreamText text={ai.text} active={ai.status === 'running'} /></Card>}
            {res && !res.entry_points_connected && <Note>Les points d'entrée ne peuvent pas être désignés tant que les déclarations détaillées ne sont pas connectées : les priorités portent sur les zones et catégories.</Note>}
            {res?.recommendations?.map((r, i) => (
              <Reveal key={r.rank} delay={i * 180}>
                <div className="card priority">
                  <div className="row between"><span className="rank">PRIORITÉ {r.rank}</span><Level value={r.level} /></div>
                  <div className="grid g-prio">
                    <div>
                      <div className="kv"><span>Zone</span><b>{r.zone}</b></div>
                      <div className="kv"><span>Point d'entrée</span><div>{r.entry_point}{r.entry_note && <div className="tiny muted">{r.entry_note}</div>}</div></div>
                      <div className="kv"><span>Catégorie</span><div><b>{r.category}</b><div className="tiny muted">{r.products.join(', ')}</div></div></div>
                      <div className="kv"><span>Évolution</span><div>{r.evolution}</div></div>
                    </div>
                    <div><div className="eyebrow">Indice de priorité</div><Gauge value={r.priority_score} /></div>
                  </div>
                  <div className="kv"><span>Pourquoi ?</span><ul className="why">{r.why.map((w, k) => <li key={k}>{w}</li>)}</ul></div>
                  <div className="reco-box" style={{ marginTop: 12 }}><div className="eyebrow">Recommandation</div><p>« {r.action} »</p></div>
                  <div className="row" style={{ gap: 6, marginTop: 12 }}>
                    <EvidenceButton evidence={r.evidence} />
                    {r.zone !== 'Information non disponible' && <Link className="btn small" to={`/douane/carte?zone=${encodeURIComponent(r.zone)}`}><MapPin size={13} />Voir sur la carte</Link>}
                    <Link className="btn small" to="/douane/parcours"><Waypoints size={13} />Voir le parcours</Link>
                    <Link className="btn small primary" to={`/douane/anomalies?category=${encodeURIComponent(r.category)}`}>Ouvrir les dossiers ({r.case_ids.length})</Link>
                  </div>
                  <div className="tiny muted" style={{ marginTop: 8 }}>Dossier principal : {r.top_case.ref} — {r.top_case.product} ({fmt.num(r.top_case.priority_score)}/100)</div>
                </div>
              </Reveal>
            ))}
            {res && !res.recommendations.length && <Empty title="Aucune priorité">{res.text}</Empty>}
          </div>
          <AIProgress steps={ai.steps} status={ai.status} title="Analyse IA en cours" doneTitle="Recommandations générées" />
        </div>
      )}
    </div>
  )
}
