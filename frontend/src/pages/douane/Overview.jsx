import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, Flag, Send, Upload } from 'lucide-react'

const KPI_ICON = { operations: Activity, anomalies: AlertTriangle, priority: Flag, transferred: Send }
import { api, fmt } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { AIButton, AIProgress, Reveal, useAIRun } from '../../components/ai.jsx'
import { HBars, STATUS_COLORS, ShareBar, TimeChart } from '../../components/charts.jsx'
import { Card, ChartCard, Empty, ErrorBox, Kpi, Level, Loading, Note, PageGuide, useApi } from '../../components/ui.jsx'
import { CaseTable } from './Anomalies.jsx'
import { SpaceBanner } from '../../components/Brand.jsx'

export default function Overview() {
  const { user } = useAuth()
  const ov = useApi('/douane/overview')
  const ch = useApi('/douane/charts')
  const ai = useAIRun()
  const run = async () => {
    const r = await ai.run('/douane/analyze/stream')
    if (r) { ov.setData(r.overview); ch.reload() }
  }
  return (
    <div>
      <SpaceBanner role={user?.role} />
      <div className="hello">
        <h1>Bonjour,</h1>
        <p>voici les principaux points nécessitant votre attention.</p>
      </div>
      <PageGuide purpose="Cette page vous permet d'identifier rapidement les situations qui méritent une vérification."
        steps={["Lancez l'analyse pour recalculer les anomalies à partir des dernières données.", 'Consultez les dossiers prioritaires.', 'Ouvrez un dossier pour comprendre pourquoi il a été signalé.']}
        why="Les indicateurs sont calculés à chaque analyse à partir des statistiques officielles, des observations commerciales publiques et, lorsqu'elles sont importées, des déclarations détaillées. Chaque situation analysée reçoit un classement ; seules les « anomalies à vérifier » et les situations « prioritaires » deviennent des dossiers." />
      {ov.loading ? <Loading /> : ov.error ? <ErrorBox error={ov.error} /> : (
        <>
          <div className="grid g4">
            {ov.data.kpis.map((k, i) => <Kpi key={k.key} icon={KPI_ICON[k.key]} label={k.label} value={fmt.num(k.value)} detail={k.detail} accent={i === 2} />)}
          </div>

          <div className="launch-bar section">
            <div>
              <h2>Analyse des données</h2>
              <p className="small muted">{ov.data.last_analysis ? `Dernière analyse : ${ov.data.last_analysis}` : "Aucune analyse n'a encore été lancée depuis cet espace."} L'IA croise toutes les données disponibles et recalcule les priorités.</p>
            </div>
            <AIButton big onClick={run} disabled={ai.status === 'running'}>ANALYSER LES DONNÉES</AIButton>
          </div>
          {ai.status !== 'idle' && (
            <div className="grid g-main section" style={{ alignItems: 'start' }}>
              <AIProgress steps={ai.steps} status={ai.status} title="Analyse IA en cours" />
              {ai.result && (
                <Reveal>
                  <Card title="Résultat de l'analyse" sub={`${fmt.num(ai.result.summary?.subjects)} situations analysées en ${fmt.num(ai.result.duration, 1)} s`}>
                    <p className="small">{ai.result.summary?.created ? `${ai.result.summary.created} nouveau(x) dossier(s) créé(s).` : 'Aucun nouveau dossier : les situations détectées sont déjà suivies.'}</p>
                    {ai.result.incomplete_steps?.length > 0 && <Note>Certaines étapes n'ont pas pu être réalisées entièrement : {ai.result.incomplete_steps.join(', ')}.</Note>}
                    <Link className="btn small primary" to="/douane/anomalies" style={{ marginTop: 10 }}>Voir les anomalies détectées <ArrowRight size={13} /></Link>
                  </Card>
                </Reveal>
              )}
              {ai.error && <Empty title="L'analyse n'a pas pu aboutir">{ai.error}</Empty>}
            </div>
          )}

          <div className="grid g2 section">
            <Card title="Comment se répartissent les situations analysées ?" sub="Toutes les situations sont analysées ; seules les deux dernières catégories sont proposées pour vérification.">
              <ShareBar rows={Object.entries(ov.data.classification).map(([label, value]) => ({ label, value }))} colors={STATUS_COLORS} />
              <div className="grid g2 mini-stats" style={{ marginTop: 14 }}>
                {Object.entries(ov.data.classification).map(([k, v]) => <div key={k}><Level value={k} /><div className="big-num" style={{ fontSize: 22, marginTop: 6 }}>{fmt.num(v)}</div></div>)}
              </div>
            </Card>
            <Card title="Dossiers à examiner en premier" right={<Link className="btn small" to="/douane/anomalies">Tous les dossiers</Link>}>
              {ov.data.top_cases.length ? <CaseTable rows={ov.data.top_cases} compact /> : <Empty>Aucun dossier ouvert.</Empty>}
            </Card>
          </div>

          {!ov.data.declarations_connected && <DeclarationsImport note={ov.data.declarations_note} onDone={() => ov.reload()} />}

          {ch.data && (
            <div className="grid g2 section">
              <ChartCard title="Anomalies dans le temps" question="Les situations inhabituelles sont-elles plus fréquentes récemment ?"
                rows={ch.data.anomalies_time.rows} unit="anomalies" kind="time" source={ch.data.anomalies_time.source}
                help={{ why: "Pour repérer une accélération des comportements inhabituels sur les produits suivis.", shows: "Le nombre de mois-chapitres jugés inhabituels, mois par mois.", read: "Une hausse sur plusieurs mois consécutifs justifie une analyse complémentaire des produits concernés." }}>
                <TimeChart rows={ch.data.anomalies_time.rows} unit="anomalies" line={false} />
              </ChartCard>
              <ChartCard title="Petits flux dans le temps" question="Les petites opérations se multiplient-elles ?"
                rows={ch.data.small_flows_time.rows} unit="petites opérations" kind="time" emptyText={ch.data.small_flows_time.message}
                help={{ why: "La multiplication des petites opérations est le premier signe d'une activité fragmentée.", shows: "Le nombre d'opérations de faible valeur par semaine.", read: "Une hausse inhabituelle peut justifier une analyse complémentaire." }}>
                <TimeChart rows={ch.data.small_flows_time.rows} unit="opérations" />
              </ChartCard>
              <ChartCard title="Catégories les plus concernées" question="Quelles catégories de produits regroupent le plus de dossiers ?"
                rows={ch.data.categories.rows} unit="dossiers" source={ch.data.categories.source}
                help={{ why: "Pour orienter l'attention vers les familles de produits les plus exposées.", shows: "Le nombre de dossiers par catégorie.", read: "Une catégorie dominante mérite une vérification ciblée ; ce n'est pas une preuve d'irrégularité." }}>
                <HBars rows={ch.data.categories.rows} unit="dossiers" />
              </ChartCard>
              <ChartCard title="Produits les plus concernés" question="Quels produits reviennent le plus souvent dans les dossiers ?"
                rows={ch.data.products.rows} unit="dossiers" source={ch.data.products.source}
                help={{ why: "Pour identifier les produits à suivre en priorité.", shows: "Le nombre de dossiers par produit.", read: "Plusieurs dossiers sur un même produit renforcent le besoin de vérification." }}>
                <HBars rows={ch.data.products.rows} unit="dossiers" />
              </ChartCard>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function DeclarationsImport({ note, onDone }) {
  const input = useRef(null)
  const [state, setState] = useState(null)
  const send = async (f) => {
    const fd = new FormData()
    fd.append('file', f)
    setState({ busy: true })
    try { const r = await api.post('/douane/customs/import', fd); setState({ ok: r.message }); onDone?.() } catch (e) { setState({ error: e.message }) }
  }
  return (
    <Card className="section" title="Déclarations détaillées" sub="Source non connectée">
      <p className="small">{note}</p>
      <div className="row" style={{ marginTop: 12 }}>
        <input ref={input} type="file" accept=".csv,.xlsx,.xls" hidden onChange={(e) => e.target.files[0] && send(e.target.files[0])} />
        <button className="btn small" onClick={() => input.current.click()} disabled={state?.busy}><Upload size={13} />{state?.busy ? 'Import en cours…' : 'Importer un extrait autorisé'}</button>
        <span className="tiny muted">Fichier CSV ou Excel · colonnes obligatoires : date, code produit, valeur déclarée</span>
      </div>
      {state?.ok && <Note>{state.ok}</Note>}
      {state?.error && <Empty title="Import impossible">{state.error}</Empty>}
    </Card>
  )
}
