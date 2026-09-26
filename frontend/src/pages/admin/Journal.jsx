import { fmt } from '../../api.js'
import { Card, ErrorBox, Level, Loading, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

const EV = { Connexion: 'Traité', 'Échec de connexion': 'À surveiller', 'Accès refusé': 'Prioritaire' }

export default function Journal() {
  const { data, error, loading } = useApi('/admin/access-logs')
  return (
    <div>
      <PageHead eyebrow="Administration" title="Journal des accès" sub="Connexions, échecs de connexion et tentatives d'accès à l'espace d'une autre institution." />
      <PageGuide purpose="Ce journal permet de contrôler les accès à la plateforme."
        steps={['Repérez les échecs de connexion répétés.', 'Repérez les accès refusés : un compte a tenté d’ouvrir l’espace d’une autre institution.']} />
      <Card>
        {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
          <div className="table-wrap"><table className="t"><thead><tr><th>Date</th><th>Compte</th><th>Événement</th><th>Page demandée</th><th>Détail</th></tr></thead>
            <tbody>{data.map((a, i) => <tr key={i}><td className="nowrap">{fmt.datetime(a.at)}</td><td>{a.email || '—'}</td><td><Level value={EV[a.event]}>{a.event}</Level></td>
              <td className="small mono">{a.path || '—'}</td><td className="small">{a.detail || '—'}</td></tr>)}</tbody></table></div>
        )}
      </Card>
    </div>
  )
}
