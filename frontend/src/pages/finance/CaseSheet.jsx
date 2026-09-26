import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Download } from 'lucide-react'
import { api, fmt } from '../../api.js'
import { AIBadge } from '../../components/ai.jsx'
import { Card, ErrorBox, EvidenceButton, Gauge, Level, Loading, Note, PageGuide, useApi } from '../../components/ui.jsx'
import { Facts, History, Operations, REL_BADGE } from '../douane/CaseSheet.jsx'

export default function CaseSheet() {
  const { id } = useParams()
  const { data, error, loading, setData } = useApi(`/finance/cases/${id}`)
  const [comment, setComment] = useState('')
  const [msg, setMsg] = useState(null)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const s = data.snapshot || {}
  const act = async (status) => {
    try { setData(await api.post(`/finance/cases/${id}/status`, { status, comment })); setComment(''); setMsg(null) } catch (e) { setMsg(e.message) }
  }
  const note = async () => {
    try { setData(await api.post(`/finance/cases/${id}/note`, { comment })); setComment('') } catch (e) { setMsg(e.message) }
  }
  const pdf = async () => {
    const r = await api.post(`/finance/cases/${id}/report`)
    api.download(`/finance/reports/${r.id}/download`, `dossier_${s.ref}.pdf`)
  }
  return (
    <div>
      <Link to="/finance/dossiers" className="back"><ArrowLeft size={14} />Dossiers reçus</Link>
      <div className="case-head">
        <div>
          <div className="eyebrow">Dossier {s.ref} · transmis le {fmt.datetime(data.transferred_at)}</div>
          <h1>{s.product}</h1>
          <div className="row" style={{ marginTop: 8 }}><Level value={s.classification} /><Level value={data.status_label} /></div>
        </div>
        <div className="case-actions"><Gauge value={s.priority_score} /></div>
      </div>
      <PageGuide purpose="Cette fiche présente le dossier tel que la Douane l'a transmis : synthèse, opérations, valeurs, sources et analyse IA."
        steps={['Lisez la synthèse et le commentaire de la Douane.', 'Examinez les opérations et les montants.', 'Faites avancer le statut et consignez vos notes.']}
        why="Les montants indiqués sont la valeur des opérations concernées et, lorsqu'il est calculable, l'écart potentiel à vérifier. Ils ne constituent ni une créance ni une estimation de recettes." />
      <div className="grid g-main" style={{ alignItems: 'start' }}>
        <div className="stack" style={{ gap: 18 }}>
          <section className="card why-card">
            <div className="row between"><h2>Synthèse du dossier</h2><AIBadge label="Analyse IA" /></div>
            <p className="why-motif">{s.motif}</p>
            <p className="why-text">{s.explanation}</p>
            <div className="transfer-note"><div className="eyebrow">Transmission Douane</div><b>{s.transfer_motif}</b>{s.agent_comment && <p className="small">« {s.agent_comment} »</p>}</div>
            <div className="row" style={{ marginTop: 12, gap: 6 }}>
              <EvidenceButton evidence={{ sources: s.sources, information_used: s.information_used, method: s.method }} />
              <button className="btn small" onClick={pdf}><Download size={13} />Rapport du dossier</button>
            </div>
          </section>
          <Card title="Valeurs et informations disponibles"><Facts c={s} /></Card>
          <Operations ops={s.operations} unit={s.amount_unit} />
        </div>
        <div className="stack" style={{ gap: 18 }}>
          <Card title="Traitement Finance">
            {data.next_status.length ? (
              <>
                <textarea className="input" rows={3} placeholder="Note d'analyse financière (facultatif)" value={comment} onChange={(e) => setComment(e.target.value)} />
                <div className="row" style={{ marginTop: 10, gap: 6 }}>
                  {data.next_status.map((n) => <button key={n.value} className="btn primary small" onClick={() => act(n.value)}>Passer à « {n.label} »</button>)}
                  <button className="btn small" disabled={!comment.trim()} onClick={note}>Ajouter la note</button>
                </div>
              </>
            ) : <p className="small">Dossier traité{data.processed_at ? ` le ${fmt.datetime(data.processed_at)}` : ''}.</p>}
            {msg && <Note>{msg}</Note>}
            <p className="tiny muted" style={{ marginTop: 10 }}>La Douane voit uniquement le statut (Reçu, En analyse, Traité), jamais vos notes.</p>
          </Card>
          <Card title="Indicateurs transmis">
            <ul className="rel-list">{(s.indicators || []).map((i, k) => <li key={k}><span className={`rel ${REL_BADGE[i.relation] || ''}`}>{i.relation}</span><div>{i.label}<div className="tiny muted">{i.source}</div></div></li>)}</ul>
          </Card>
          <Card title="Historique"><History items={data.history} /></Card>
        </div>
      </div>
    </div>
  )
}
