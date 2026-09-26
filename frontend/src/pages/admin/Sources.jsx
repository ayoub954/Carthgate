import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api, fmt } from '../../api.js'
import { Card, ErrorBox, Level, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

export default function Sources() {
  const { data, error, loading, reload } = useApi('/admin/sources')
  const [st, setSt] = useState(null)
  useEffect(() => {
    if (!st?.running) return
    const t = setInterval(() => api.get('/admin/refresh/status').then((s) => { setSt(s); if (!s.running) reload() }), 4000)
    return () => clearInterval(t)
  }, [st?.running]) // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = async () => { const r = await api.post('/admin/refresh'); setSt({ running: r.started, step: 'Mise à jour des sources' }) }
  return (
    <div>
      <PageHead eyebrow="Administration" title="Sources de données" sub="État des sources connectées et des accès institutionnels à obtenir.">
        <button className="btn" onClick={refresh} disabled={st?.running}><RefreshCw size={14} />{st?.running ? `${st.step || 'Mise à jour'}…` : 'Mettre à jour les données'}</button>
      </PageHead>
      <PageGuide purpose="Cette page indique quelles sources alimentent la plateforme et lesquelles nécessitent une autorisation."
        steps={['Vérifiez que les sources publiques sont connectées.', 'Identifiez les accès institutionnels à demander.', 'Lancez une mise à jour si nécessaire (plusieurs minutes).']} />
      {st?.running && <Note>Mise à jour en cours : {st.step}. La plateforme reste utilisable pendant l'opération.</Note>}
      <Card>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
          <div className="table-wrap"><table className="t"><thead><tr><th>Source</th><th>Contenu</th><th>État</th><th>Période</th><th>Enregistrements</th><th>Mise à jour</th></tr></thead>
            <tbody>{data.map((s) => <tr key={s.key}><td>{s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a> : s.name}</td><td className="small">{s.description}</td>
              <td><Level value={s.connected ? 'Connectée' : null}>{s.status}</Level></td><td className="small">{s.period || '—'}</td><td>{fmt.num(s.records)}</td><td>{s.updated || '—'}</td></tr>)}</tbody></table></div>
        )}
      </Card>
    </div>
  )
}
