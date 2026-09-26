import { useEffect, useState } from 'react'
import { RefreshCw, Upload } from 'lucide-react'
import { api, fmt } from '../api.js'
import { Card, Empty, ErrorBox, ExportMenu, Loading, OpenLink, PageHead, useApi } from '../components/ui.jsx'

const DATASETS = [['customs_records', 'Statistiques douanières'], ['economic_indicators', 'Indicateurs économiques'], ['observations', 'Observations commerciales'],
  ['sellers', 'Vendeurs et commerces'], ['entry_points', "Points d'entrée"], ['anomalies', 'Comportements inhabituels'], ['risk_scores', 'Indices de priorité'],
  ['recommendations', 'Recommandations'], ['forecasts', 'Projections']]

export default function Sources() {
  const { data, error, loading } = useApi('/sources')
  const [st, setSt] = useState(null)
  useEffect(() => {
    const t = setInterval(() => api.get('/refresh/status').then(setSt).catch(() => {}), 4000)
    return () => clearInterval(t)
  }, [])
  return (
    <div>
      <PageHead title="Sources" sub="Origine, état et fraîcheur des données utilisées par la plateforme.">
        {st?.running && <span className="small muted row"><div className="spinner" />{st.step || 'Mise à jour'}…</span>}
        <button className="btn primary" disabled={st?.running} onClick={() => api.post('/refresh', {}).then(() => setSt({ running: true }))}><RefreshCw size={14} />Actualiser les données</button>
      </PageHead>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <div className="grid g3">{data.map((s) => (
          <div key={s.key} className={`card source ${s.connected ? '' : 'off'}`}>
            <div className="row between"><h3>{s.name}</h3><span className={`status ${s.connected ? 'ok' : ''}`}>{s.status}</span></div>
            <p className="small muted" style={{ marginTop: 6 }}>{s.description}</p>
            {s.connected && <div className="tiny muted" style={{ marginTop: 10 }}>{s.period && `Période : ${s.period} · `}{s.records ? `${fmt.num(s.records)} enregistrements · ` : ''}{s.updated && `mise à jour le ${s.updated}`}</div>}
            <div style={{ marginTop: 12 }}><OpenLink href={s.url} /></div>
          </div>))}</div>
      )}
      <Explorer />
      <Card title="Ajouter un extrait douanier autorisé" className="section" sub="Réservé aux données que vous êtes habilité à traiter. Les identifiants des importateurs sont anonymisés à l'import.">
        <ImportExtract />
      </Card>
    </div>
  )
}

function Explorer() {
  const [f, setF] = useState({ dataset: 'customs_records', hs: '', country: '', period_from: '', period_to: '', governorate: '', category: '' })
  const qs = new URLSearchParams(Object.fromEntries(Object.entries(f).filter(([, v]) => v))).toString()
  const { data, error, loading } = useApi(`/explorer?${qs}&limit=200`)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const cols = (data?.columns || []).filter((c) => !['source_url', 'data_mode'].includes(c))
  return (
    <Card title="Explorer les données" className="section" right={<ExportMenu dataset={f.dataset} params={{ hs: f.hs, country: f.country, governorate: f.governorate, category: f.category }} label="Exporter le tableau" />}>
      <div className="grid g4" style={{ marginBottom: 14 }}>
        <select className="input" value={f.dataset} onChange={set('dataset')}>{DATASETS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input className="input" placeholder="Produit (position tarifaire)" value={f.hs} onChange={set('hs')} />
        <input className="input" placeholder="Pays" value={f.country} onChange={set('country')} />
        <input className="input" placeholder="Gouvernorat" value={f.governorate} onChange={set('governorate')} />
        <input className="input" placeholder="Période du (AAAA-MM)" value={f.period_from} onChange={set('period_from')} />
        <input className="input" placeholder="au (AAAA-MM)" value={f.period_to} onChange={set('period_to')} />
        <input className="input" placeholder="Catégorie" value={f.category} onChange={set('category')} />
      </div>
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : data.rows.length ? (
        <>
          <div className="small muted" style={{ marginBottom: 8 }}>{fmt.num(data.total)} lignes (200 affichées)</div>
          <div className="table-wrap" style={{ maxHeight: 460, overflowY: 'auto' }}><table className="t">
            <thead><tr><th></th>{cols.map((c) => <th key={c}>{c.replaceAll('_', ' ')}</th>)}</tr></thead>
            <tbody>{data.rows.map((r, i) => <tr key={i}><td>{r.source_url && <a className="tiny" href={r.source_url} target="_blank" rel="noreferrer">Source</a>}</td>
              {cols.map((c) => <td key={c} className="small">{typeof r[c] === 'number' ? fmt.num(r[c], 2) : String(r[c] ?? '')}</td>)}</tr>)}</tbody>
          </table></div>
        </>
      ) : <Empty>Aucune ligne pour ces filtres.</Empty>}
    </Card>
  )
}

function ImportExtract() {
  const [res, setRes] = useState(null)
  const [err, setErr] = useState(null)
  const up = (e) => {
    const fd = new FormData(); fd.append('file', e.target.files[0])
    api.post('/customs/import', fd).then(setRes).catch((x) => setErr(x.message))
  }
  return (
    <div>
      <p className="small muted">Colonnes attendues : date de déclaration, position tarifaire, valeur déclarée (et si disponibles : importateur, provenance, point d'entrée, mode de transport, quantité, gouvernorat de destination).</p>
      <label className="btn" style={{ marginTop: 12 }}><Upload size={14} />Choisir un fichier<input type="file" accept=".csv,.xlsx" hidden onChange={up} /></label>
      {res && <p className="small" style={{ marginTop: 10 }}>{res.rows} lignes importées. Relancez une analyse dans « Risques et alertes ».</p>}
      {err && <p className="small" style={{ marginTop: 10 }}>{err}</p>}
    </div>
  )
}
