import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { api, session } from './api.js'

const AuthCtx = createContext(null)
export const HOME = { ROLE_DOUANE: '/douane', ROLE_FINANCE: '/finance', ROLE_ADMIN: '/administration' }

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const logout = () => { session.set(null); setUser(null) }
  useEffect(() => {
    session.onUnauthorized(logout)
    if (!session.get()) { setReady(true); return }
    api.get('/auth/me').then(setUser).catch(() => session.set(null)).finally(() => setReady(true))
  }, [])
  const login = async (email, password) => {
    const r = await api.post('/auth/login', { email, password })
    session.set(r.token)
    setUser(r.user)
    return r.user
  }
  return <AuthCtx.Provider value={{ user, ready, login, logout }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)

/** Interface guard only — the server enforces the same rule on every request (403 otherwise). */
export function RequireRole({ role, children }) {
  const { user, ready } = useAuth()
  if (!ready) return null
  if (!user) return <Navigate to="/connexion" replace />
  if (user.role !== role) return <Navigate to={HOME[user.role] || '/connexion'} replace />
  return children
}
