import { Card, Loading, PageGuide, PageHead, useApi } from '../components/ui.jsx'

const FLOW = [
  { k: 'in', items: ['Petites importations', 'Commerce en ligne', 'Données entreprises', "Points d'entrée"] },
  { k: 'ai', items: ['Analyse IA'] },
  { k: 'step', items: ['Regroupement des flux'] },
  { k: 'step', items: ['Détection des anomalies'] },
  { k: 'step', items: ['Priorisation'] },
  { k: 'human', items: ['Vérification Douane'] },
  { k: 'step', items: ['Transmission'] },
  { k: 'fin', items: ['Finance'] },
  { k: 'fin', items: ['Analyse financière'] },
]

export default function About() {
  const { data, loading } = useApi('/about')
  return (
    <div>
      <PageHead eyebrow="À propos de la solution" title="Une grande activité peut se cacher derrière de nombreuses petites opérations"
        sub="CarthaGate aide la Douane à rassembler ces signaux, détecter les situations à vérifier, comprendre où concentrer ses contrôles, puis transmettre les dossiers pertinents à Finance." />
      <PageGuide purpose="Cette page présente le problème traité, le fonctionnement de la plateforme et les règles qu'elle respecte."
        steps={['Lisez le problème et la question métier.', 'Suivez le parcours des données jusqu’à Finance.', 'Consultez les règles de lecture des résultats.']} />
      {loading ? <Loading /> : (
        <>
          <div className="grid g2">
            <Card title="Le problème"><p>{data.problem}</p></Card>
            <Card title="La question métier"><p className="big-q">« {data.question} »</p></Card>
          </div>
          <Card title="Le parcours des données" className="section" sub="Des données séparées deviennent une information exploitable lorsqu'on les relie.">
            <div className="workflow">
              {FLOW.map((f, i) => (
                <div key={i} className="wf-row">
                  <div className="wf-items">{f.items.map((x) => <span key={x} className={`wf-node ${f.k}`}>{x}</span>)}</div>
                  {i < FLOW.length - 1 && <div className="wf-arrow">{i === 0 ? '＋ ↓' : '↓'}</div>}
                </div>
              ))}
            </div>
          </Card>
          <div className="grid g2 section">
            <Card title="Thèmes du hackathon couverts">
              <div className="stack">{data.themes.map((t) => (
                <div key={t.code} className="theme"><span className="theme-code">{t.code}</span><div><b>{t.label}</b><div className="small muted">{t.how}</div></div></div>))}</div>
            </Card>
            <Card title="Règles respectées par l'IA">
              <ul className="rules">{data.rules.map((r) => <li key={r}>{r}</li>)}</ul>
              <p className="small muted" style={{ marginTop: 10 }}>L'IA ne déclare jamais « fraude confirmée » : elle signale une anomalie, une activité à vérifier, un écart potentiel ou une priorité de contrôle.</p>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
