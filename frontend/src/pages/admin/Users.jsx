import { useState } from 'react'
import { api, fmt } from '../../api.js'
import { Card, Empty, ErrorBox, Level, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

const ROLE_FR = { ROLE_DOUANE: 'Douane', ROLE_FINANCE: 'Finance', ROLE_ADMIN: 'Administration' }

export default function Users() {
  const { data, error, loading, reload } = useApi('/admin/users')
  const [form, setForm] = useState({ email: '', full_name: '', role: 'ROLE_DOUANE', password: '' })
  const [msg, setMsg] = useState(null)
  const create = async (e) => {
    e.preventDefault()
    try { await api.post('/admin/users', form); setForm({ ...form, email: '', full_name: '', password: '' }); setMsg({ ok: 'Compte créé.' }); reload() } catch (err) { setMsg({ error: err.message }) }
  }
  const toggle = async (u) => { try { await api.patch(`/admin/users/${u.id}`, { active: !u.active }); reload() } catch (err) { setMsg({ error: err.message }) } }
  return (
    <div>
      <PageHead eyebrow="Administration" title="Comptes" sub="Chaque compte possède un rôle enregistré sur le serveur : Douane, Finance ou Administration." />
      <PageGuide purpose="Cette page permet de créer et de désactiver les comptes des utilisateurs."
        steps={['Saisissez l’adresse professionnelle et le rôle.', 'Choisissez un mot de passe provisoire (10 caractères minimum).', 'Désactivez un compte pour retirer immédiatement ses accès.']}
        why="Le rôle est vérifié par le serveur à chaque requête. La convention prenom.nom@douane.com / prenom.nom@finance.com est contrôlée à la création, mais ne donne jamais d'accès à elle seule." />
      <div className="grid g-main" style={{ alignItems: 'start' }}>
        <Card title="Comptes existants">
          {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
            <div className="table-wrap"><table className="t"><thead><tr><th>Adresse</th><th>Nom</th><th>Rôle</th><th>Dernière connexion</th><th>État</th><th /></tr></thead>
              <tbody>{data.items.map((u) => <tr key={u.id}><td>{u.email}</td><td>{u.full_name || '—'}</td><td>{ROLE_FR[u.role]}</td>
                <td className="nowrap">{u.last_login ? fmt.datetime(u.last_login) : '—'}</td><td><Level value={u.active ? 'Traité' : 'Classé'}>{u.active ? 'Actif' : 'Désactivé'}</Level></td>
                <td><button className="btn small" onClick={() => toggle(u)}>{u.active ? 'Désactiver' : 'Réactiver'}</button></td></tr>)}</tbody></table></div>
          )}
        </Card>
        <Card title="Nouveau compte">
          <form className="stack" onSubmit={create}>
            <label className="field"><span>Adresse professionnelle</span><input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="prenom.nom@douane.com" /></label>
            <label className="field"><span>Nom complet</span><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
            <label className="field"><span>Rôle</span><select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {Object.entries(ROLE_FR).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="field"><span>Mot de passe provisoire</span><input className="input" type="password" required minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
            <button className="btn primary" type="submit">Créer le compte</button>
            {msg?.ok && <Note>{msg.ok}</Note>}
            {msg?.error && <Empty title="Création impossible">{msg.error}</Empty>}
          </form>
        </Card>
      </div>
    </div>
  )
}
