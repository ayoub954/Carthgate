import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Download, ExternalLink, Send } from 'lucide-react'
import { api, fmt } from '../../api.js'
import { AIBadge } from '../../components/ai.jsx'
import { Country } from '../../components/Country.jsx'
import { TimeChart } from '../../components/charts.jsx'
import { Card, ChartCard, Empty, ErrorBox, EvidenceButton, Gauge, Level, Loading, Modal, Note, PageGuide, useApi } from '../../components/ui.jsx'

export const REL_BADGE = { 'OBSERVÉ': 'obs', 'VÉRIFIÉ': 'ver', 'CORRÉLATION STATISTIQUE': 'stat', 'HYPOTHÈSE À VÉRIFIER': 'hyp' }
const MOTIFS = ['Écart de valeur à analyser', 'Fragmentation possible des importations', 'Hausse inhabituelle des flux', 'Concentration inhabituelle', 'Autre motif']

export function Facts({ c }) {
  const na = <span className="muted">Information non disponible</span>
  const items = [
    ['Produit', c.product], ['Catégorie', c.category], ['Période', c.period], ['Pays d\'origine', c.country ? <><Country name={c.country} iso3={c.country_iso3} />{c.continent ? <span className="muted"> · {c.continent}</span> : null}</> : null],
    ['Mode d\'entrée', c.entry_mode], ['Point d\'entrée', c.entry_point || (c.entry_points || [])[0]], ['Zone', c.zone], ['Niveau de confiance', c.confidence],
    ['Valeur des opérations concernées', c.value_concerned != null ? fmt.money(c.value_concerned, c.amount_unit) : null],
    ['Écart potentiel à vérifier', c.gap_to_verify != null ? fmt.money(c.gap_to_verify, c.amount_unit) : null],
  ]
  return <div className="facts">{items.map(([k, v]) => <div key={k}><span>{k}</span><b>{v ?? na}</b></div>)}</div>
}

export function Operations({ ops, unit }) {
  if (!ops?.length) return <Empty>Aucune opération détaillée disponible.</Empty>
  const rows = ops.map((o) => ({ label: o.date, value: o.value || 0 }))
  return (
    <>
      <ChartCard title="Chronologie des opérations" question="Comment les opérations concernées se répartissent-elles dans le temps ?"
        rows={rows} unit={ops[0]?.unit || unit} kind="time"
        help={{ why: 'Pour voir si les opérations se concentrent sur une courte période ou progressent brutalement.', shows: 'La valeur de chaque opération (ou de chaque période publiée) liée au dossier.', read: 'Un pic isolé ou une succession rapprochée de petites opérations justifie une vérification.' }}>
        <TimeChart rows={rows} unit={ops[0]?.unit || unit} height={220} />
      </ChartCard>
      <details className="section-sm"><summary className="small">Voir le détail des {ops.length} opération(s)</summary>
        <div className="table-wrap" style={{ maxHeight: 300, marginTop: 8 }}>
          <table className="t"><thead><tr><th>Date</th><th>Libellé</th><th>Valeur</th><th>Quantité</th></tr></thead>
            <tbody>{ops.map((o, i) => <tr key={i}><td className="nowrap">{o.date}</td><td className="small">{o.label || <>{o.country && <Country name={o.country} />}{[o.entry_point, o.mode].filter(Boolean).length ? ` · ${[o.entry_point, o.mode].filter(Boolean).join(' · ')}` : ''}</>}</td>
              <td className="nowrap">{fmt.money(o.value, o.unit)}</td><td className="nowrap">{o.quantity != null ? `${fmt.num(o.quantity)} ${o.quantity_unit || ''}` : '—'}</td></tr>)}</tbody></table>
        </div>
      </details>
    </>
  )
}

export function History({ items }) {
  return (
    <ol className="timeline">{items.map((h, i) => (
      <li key={i}><span className="tl-dot" /><div><b>{h.action}</b>{h.detail && <div className="small">{h.detail}</div>}
        <div className="tiny muted">{fmt.datetime(h.at)} · {h.actor}{h.institution ? ` (${h.institution === 'DOUANE' ? 'Douane' : 'Finance'})` : ''}</div></div></li>))}</ol>
  )
}

export default function CaseSheet() {
  const { id } = useParams()
  const { data: c, error, loading, setData } = useApi(`/douane/cases/${id}`)
  const [transfer, setTransfer] = useState(false)
  const [classify, setClassify] = useState(false)
  const [msg, setMsg] = useState(null)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const move = async (status, comment) => {
    try { setData(await api.post(`/douane/cases/${id}/status`, { status, comment })); setMsg(null) } catch (e) { setMsg(e.message) }
  }
  const pdf = async () => {
    const r = await api.post(`/douane/cases/${id}/report`)
    api.download(`/douane/reports/${r.id}/download`, `dossier_${c.ref}.pdf`)
  }
  return (
    <div>
      <Link to="/douane/anomalies" className="back"><ArrowLeft size={14} />Anomalies détectées</Link>
      <div className="case-head">
        <div>
          <div className="eyebrow">Dossier {c.ref} · {c.kind}</div>
          <h1>{c.product}</h1>
          <div className="row" style={{ marginTop: 8 }}><Level value={c.classification} /><Level value={c.status_label} />{c.transfer && <span className="small muted">Statut Finance : <b>{c.transfer.status}</b></span>}</div>
        </div>
        <div className="case-actions">
          <Gauge value={c.priority_score} />
          <div className="row" style={{ gap: 6, justifyContent: 'flex-end' }}>
            {c.next_status.filter((s) => s.value !== 'CLASSE').map((s) => <button key={s.value} className="btn small" onClick={() => move(s.value)}>{s.value === 'EN_COURS' ? 'Prendre en charge' : s.value === 'A_VERIFIER' ? 'Marquer « À vérifier »' : s.label}</button>)}
            {c.next_status.some((s) => s.value === 'CLASSE') && <button className="btn small" onClick={() => setClassify(true)}>Classer</button>}
            {c.status !== 'TRANSMIS' && (
              <button className="btn primary" disabled={!c.transferable} onClick={() => setTransfer(true)}
                title={c.transferable ? '' : 'Prenez d\'abord le dossier en charge et vérifiez-le'}><Send size={14} />TRANSMETTRE À FINANCE</button>
            )}
          </div>
          {!c.transferable && c.status === 'A_ANALYSER' && <div className="tiny muted" style={{ textAlign: 'right' }}>Prenez le dossier en charge pour pouvoir le vérifier puis le transmettre.</div>}
        </div>
      </div>
      {msg && <Note>{msg}</Note>}
      <PageGuide purpose="Cette fiche explique pourquoi la situation a été signalée et rassemble les éléments nécessaires à sa vérification."
        steps={['Lisez l’explication et les indicateurs.', 'Contrôlez la chronologie, les valeurs et les sources.', 'Après vérification, transmettez à Finance ou classez le dossier.']}
        why={c.evidence?.method} />

      <section className="card why-card">
        <div className="row between"><h2>Pourquoi ce dossier a été signalé ?</h2><AIBadge label="Analyse IA" /></div>
        <p className="why-motif">{c.motif}</p>
        <p className="why-text">{c.explanation}</p>
        <div className="row" style={{ marginTop: 12, gap: 6 }}>
          <EvidenceButton evidence={c.evidence} />
          <button className="btn small" onClick={pdf}><Download size={13} />Rapport du dossier</button>
        </div>
      </section>

      <div className="grid g-main section" style={{ alignItems: 'start' }}>
        <div className="stack" style={{ gap: 18 }}>
          <Card title="Éléments du dossier"><Facts c={c} /></Card>
          <Operations ops={c.operations} unit={c.amount_unit} />
          {c.online?.available && (
            <Card title="Activité commerciale associée" sub={`${c.online.count} observation(s) publique(s) — une observation n'est pas une vente.`}>
              <div className="gallery">{c.online.items.filter((i) => i.image_url).slice(0, 6).map((i, k) => (
                <figure key={k}><img src={i.image_url} alt={i.product || ''} loading="lazy" /><figcaption className="tiny">{i.product}<br /><span className="muted">{i.platform} · {i.date || 'date non publiée'}</span>
                  {i.link && <a href={i.link} target="_blank" rel="noreferrer" className="tiny"><ExternalLink size={11} /> Ouvrir la source</a>}</figcaption></figure>))}</div>
            </Card>
          )}
        </div>
        <div className="stack" style={{ gap: 18 }}>
          <Card title="Relations observées" sub="Nature de chaque lien : une corrélation n'est jamais une preuve.">
            <ul className="rel-list">{c.indicators.map((i, k) => (
              <li key={k}><span className={`rel ${REL_BADGE[i.relation] || ''}`}>{i.relation}</span><div>{i.label}{i.detail && <div className="tiny muted">{i.detail}</div>}<div className="tiny muted">{i.source}</div></div></li>))}</ul>
          </Card>
          {c.entry_points?.length > 0 && (
            <Card title="Points d'entrée">{c.entry_points.map((e) => <div key={e.id} className="row between small list-row"><span>{e.name}</span><b>{e.operations} op. · {fmt.pct(e.share)}</b></div>)}</Card>
          )}
          <Card title="Historique du dossier"><History items={c.history} /></Card>
        </div>
      </div>

      {transfer && <TransferModal c={c} onClose={() => setTransfer(false)} onDone={(d) => { setData(d); setTransfer(false) }} />}
      {classify && <ClassifyModal onClose={() => setClassify(false)} onConfirm={(comment) => { move('CLASSE', comment); setClassify(false) }} />}
    </div>
  )
}

function TransferModal({ c, onClose, onDone }) {
  const [motif, setMotif] = useState(MOTIFS[0])
  const [other, setOther] = useState('')
  const [comment, setComment] = useState('')
  const [verified, setVerified] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const confirm = async () => {
    setBusy(true); setErr(null)
    try {
      onDone(await api.post(`/douane/cases/${c.id}/transfer`, { motif: motif === 'Autre motif' ? other : motif, comment, verified }))
    } catch (e) { setErr(e.message); setBusy(false) }
  }
  return (
    <Modal title="Transmission du dossier" onClose={onClose}>
      <p className="small muted" style={{ marginTop: -6 }}>Dossier {c.ref} — {c.product}. La transmission est une décision humaine : l'IA ne transmet jamais un dossier.</p>
      <label className="field"><span>Motif</span>
        <select className="input" value={motif} onChange={(e) => setMotif(e.target.value)}>{MOTIFS.map((m) => <option key={m}>{m}</option>)}</select>
        {motif === 'Autre motif' && <input className="input" style={{ marginTop: 6 }} placeholder="Précisez le motif" value={other} onChange={(e) => setOther(e.target.value)} />}
      </label>
      <label className="field"><span>Commentaire de la Douane</span>
        <textarea className="input" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Éléments vérifiés, points d'attention pour Finance…" /></label>
      <div className="field"><span>Éléments transmis</span>
        <div className="checks">{c.transfer_items.map((i) => <span key={i}><CheckCircle2 size={14} />{i}</span>)}</div>
        <div className="tiny muted" style={{ marginTop: 6 }}>Les observations commerciales détaillées et les outils internes de la Douane ne sont pas transmis.</div>
      </div>
      <label className="row small" style={{ gap: 8, marginTop: 8 }}><input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
        J'ai vérifié ce dossier et je confirme qu'il nécessite une analyse financière.</label>
      {err && <Note>{err}</Note>}
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 16 }}>
        <button className="btn" onClick={onClose}>Annuler</button>
        <button className="btn primary" disabled={!verified || busy || (motif === 'Autre motif' && !other.trim())} onClick={confirm}><Send size={14} />{busy ? 'Transmission…' : 'CONFIRMER LA TRANSMISSION'}</button>
      </div>
    </Modal>
  )
}

function ClassifyModal({ onClose, onConfirm }) {
  const [comment, setComment] = useState('')
  return (
    <Modal title="Classer le dossier" onClose={onClose}>
      <p className="small">Indiquez pourquoi le dossier ne nécessite pas de suite (par exemple : explication légitime identifiée).</p>
      <textarea className="input" rows={3} value={comment} onChange={(e) => setComment(e.target.value)} />
      <div className="row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="btn" onClick={onClose}>Annuler</button>
        <button className="btn primary" disabled={!comment.trim()} onClick={() => onConfirm(comment)}>Classer le dossier</button>
      </div>
    </Modal>
  )
}
