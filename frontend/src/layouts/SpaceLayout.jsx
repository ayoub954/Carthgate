import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Bell, LogOut } from 'lucide-react'
import { api, fmt } from '../api.js'
import { useAuth } from '../auth.jsx'
import { SpaceCtx } from '../components/ui.jsx'
import { IDENTITY, Logo, Wordmark } from '../components/Brand.jsx'

const I = { size: 17, strokeWidth: 1.8 }

/** Sidebar + header of one institutional space. Each space has its own menu — no link to the other space. */
export default function SpaceLayout({ space, label, tagline, menu, children }) {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const id = IDENTITY[user?.role] || { logo: 'tun', title: label, subtitle: '', institution: '' }
  const name = user?.full_name || user?.email
  return (
    <SpaceCtx.Provider value={space}>
      <div className={`layout space-${space}`}>
        <aside className="sidebar">
          <Link to={`/${space === 'admin' ? 'administration' : space}`} className="side-brand">
            <Logo name={id.logo} alt={id.alt} className="side-logo" />
            <div className="side-title">{id.title}</div>
            <div className="side-sub">{id.subtitle}</div>
            <div className="side-platform"><Wordmark size="xs" /></div>
          </Link>
          <nav className="nav">
            {menu.map((m) => m.section ? <div key={m.section} className="nav-label">{m.section}</div> : (
              <NavLink key={m.to} to={m.to} end={m.end}><m.icon {...I} />{m.label}</NavLink>
            ))}
          </nav>
          <div className="sidebar-foot">
            <div className="who">
              <div className="avatar">{(name || '?').slice(0, 1).toUpperCase()}</div>
              <div style={{ minWidth: 0 }}><div className="who-name">{name}</div><div className="who-mail">{id.institution}</div></div>
            </div>
            <button className="btn small logout" onClick={() => { logout(); nav('/connexion') }}><LogOut size={14} />Se déconnecter</button>
            <p>{tagline}</p>
          </div>
        </aside>
        <main className="main">
          <div className="topbar">
            <div className="topbar-rt"><Logo name="tun" alt="République Tunisienne" /></div>
            <div className="row" style={{ gap: 10 }}>
              <span className="space-chip">{id.title}</span>
              {space !== 'admin' && <Notifications space={space} />}
            </div>
          </div>
          <div className="page-enter">{children}</div>
        </main>
      </div>
    </SpaceCtx.Provider>
  )
}

function Notifications({ space }) {
  const [data, setData] = useState({ unread: 0, items: [] })
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const nav = useNavigate()
  const load = () => api.get('/notifications').then(setData).catch(() => {})
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t) }, [])
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [])
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="icon-btn bell" onClick={() => setOpen(!open)} aria-label="Notifications">
        <Bell size={18} />{data.unread > 0 && <span className="bell-count">{data.unread}</span>}
      </button>
      {open && (
        <div className="menu notif-menu">
          <div className="row between" style={{ padding: '6px 10px' }}>
            <b className="small">Notifications</b>
            {data.unread > 0 && <button className="linklike tiny" onClick={() => api.post('/notifications/read-all').then(load)}>Tout marquer comme lu</button>}
          </div>
          {!data.items.length && <div className="small muted" style={{ padding: 10 }}>Aucune notification.</div>}
          {data.items.map((n) => (
            <button key={n.id} className={`notif ${n.read ? '' : 'unread'}`} onClick={() => { setOpen(false); if (n.case_id && space === 'finance') nav(`/finance/dossiers/${n.case_id}`) }}>
              <b>{n.title}</b>
              {n.body && <span className="tiny">Dossier {n.body.ref} · {n.body.category} · {n.body.priority}</span>}
              <span className="tiny muted">{fmt.datetime(n.created_at)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
