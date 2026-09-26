import { NavLink, Route, Routes, useLocation, Link } from 'react-router-dom'
import { Database, FileText, LayoutDashboard, LineChart, Radar, Search, ShieldAlert } from 'lucide-react'
import { DemoBanner, ModeProvider, ModeSwitch } from './mode.jsx'
import Home from './pages/Home.jsx'
import Overview from './pages/Overview.jsx'
import Investigate from './pages/Investigate.jsx'
import IntelligenceNav from './pages/IntelligenceNav.jsx'
import Products from './pages/Products.jsx'
import Product360 from './pages/Product360.jsx'
import Commerce from './pages/Commerce.jsx'
import SellersReview from './pages/SellersReview.jsx'
import SellerSheet from './pages/SellerSheet.jsx'
import Countries from './pages/Countries.jsx'
import MapPage from './pages/MapPage.jsx'
import Journey from './pages/Journey.jsx'
import Risk from './pages/Risk.jsx'
import Economic from './pages/Economic.jsx'
import Sources from './pages/Sources.jsx'
import Reports from './pages/Reports.jsx'

const I = { size: 17, strokeWidth: 1.8 }

export default function App() {
  const loc = useLocation()
  const intel = loc.pathname.startsWith('/intelligence')
  return (
    <ModeProvider>
      <div className="layout">
        <aside className="sidebar">
          <Link to="/" className="brand"><div className="brand-dot" />DIWANA TRACE AI</Link>
          <nav className="nav stack" style={{ gap: 2 }}>
            <NavLink to="/vue-ensemble"><LayoutDashboard {...I} />Vue d'ensemble</NavLink>
            <NavLink to="/investigation"><Search {...I} />Investigation IA</NavLink>
            <NavLink to="/intelligence/produits" className={intel ? 'active' : ''}><Radar {...I} />Intelligence commerciale</NavLink>
            <NavLink to="/risques"><ShieldAlert {...I} />Risques et alertes</NavLink>
            <NavLink to="/perspectives"><LineChart {...I} />Perspectives économiques</NavLink>
            <NavLink to="/sources"><Database {...I} />Sources</NavLink>
            <NavLink to="/rapports"><FileText {...I} />Rapports</NavLink>
          </nav>
          <div className="sidebar-foot">
            <ModeSwitch compact />
            <p style={{ marginTop: 12 }}>L'intelligence artificielle assiste l'agent ; la décision reste humaine.</p>
          </div>
        </aside>
        <main className="main">
          <DemoBanner />
          {intel && <IntelligenceNav />}
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/vue-ensemble" element={<Overview />} />
            <Route path="/investigation" element={<Investigate />} />
            <Route path="/intelligence/produits" element={<Products />} />
            <Route path="/intelligence/produits/:id" element={<Product360 />} />
            <Route path="/intelligence/commerce" element={<Commerce />} />
            <Route path="/intelligence/vendeurs" element={<SellersReview />} />
            <Route path="/intelligence/vendeurs/:id" element={<SellerSheet />} />
            <Route path="/intelligence/pays" element={<Countries />} />
            <Route path="/intelligence/carte" element={<MapPage />} />
            <Route path="/intelligence/parcours" element={<Journey />} />
            <Route path="/risques" element={<Risk />} />
            <Route path="/perspectives" element={<Economic />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/rapports" element={<Reports />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </main>
      </div>
    </ModeProvider>
  )
}
