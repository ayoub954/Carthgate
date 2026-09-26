import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ArrowLeft, Lock, Mail, ShieldCheck } from 'lucide-react'
import { HOME, useAuth } from '../auth.jsx'
import { InstitutionStrip, Wordmark } from '../components/Brand.jsx'

export default function Login() {
  const { user, ready, login } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  if (ready && user) return <Navigate to={HOME[user.role]} replace />
  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const u = await login(email.trim(), password)
      nav(HOME[u.role], { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="login-page">
      <div className="login-bg" style={{ backgroundImage: 'url(/back.png)' }} />
      <div className="login-veil" />
      <Link to="/" className="login-back"><ArrowLeft size={14} />Accueil</Link>
      <div className="login-wrap">
        <form className="login-card" onSubmit={submit}>
          <Wordmark size="lg" />
          <div className="gold-rule center" />
          <p className="login-sub"><ShieldCheck size={15} />Accès sécurisé à la plateforme</p>
          <label className="field">
            <span>Adresse professionnelle</span>
            <div className="field-input"><Mail size={16} /><input type="email" autoComplete="username" required value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="prenom.nom@douane.com" /></div>
          </label>
          <label className="field">
            <span>Mot de passe</span>
            <div className="field-input"><Lock size={16} /><input type="password" autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} /></div>
          </label>
          {error && <div className="login-error" role="alert">{error}</div>}
          <button className="btn primary big" type="submit" disabled={busy}>{busy ? 'Connexion…' : 'SE CONNECTER'}</button>
          <p className="tiny muted" style={{ textAlign: 'center', marginTop: 14 }}>Accès réservé aux services habilités de la Douane et des Finances.</p>
        </form>
        <InstitutionStrip compact />
      </div>
    </div>
  )
}
