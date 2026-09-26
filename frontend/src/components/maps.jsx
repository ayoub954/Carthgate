import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet.markercluster'

const TILE = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTR = '&copy; OpenStreetMap contributors'
const EP = { AIRPORT: ['✈', ''], SEAPORT: ['⚓', ''], LAND_BORDER: ['◆', 'land'] }
const EP_FR = { AIRPORT: 'Aéroport', SEAPORT: 'Port', LAND_BORDER: 'Frontière terrestre' }

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

/**
 * Tunisia map: commercial points = small black dots (clustered at low zoom),
 * customs entry points = distinct symbols (separate layer), optional AI attention + product flow.
 */
export function TunisiaMap({ data, layers = { shops: true, entries: true, attention: false, governorates: false }, tall, onSeller, onZone }) {
  const el = useRef(null)
  const map = useRef(null)
  const groups = useRef({})

  useEffect(() => {
    map.current = L.map(el.current, { zoomControl: true, scrollWheelZoom: true }).setView([34.0, 9.6], 6)
    L.tileLayer(TILE, { attribution: ATTR, maxZoom: 19 }).addTo(map.current)
    return () => map.current.remove()
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m || !data) return
    Object.values(groups.current).forEach((g) => m.removeLayer(g))
    groups.current = {}
    if (layers.governorates && data.governorates) {
      const g = L.layerGroup()
      data.governorates.forEach((z) => L.geoJSON(z.geometry, { style: { color: '#52514e', weight: 1.2, opacity: 0.7, fill: false } }).bindTooltip(z.name, { sticky: true }).addTo(g))
      groups.current.gov = g.addTo(m)
    }
    if (layers.attention && data.attention) {
      const g = L.layerGroup()
      data.attention.forEach((a) => {
        if (a.lat == null) return
        L.circle([a.lat, a.lon], { radius: 12000 + 40000 * a.intensity, color: '#d03b3b', weight: 1.5, fillColor: '#d03b3b', fillOpacity: 0.08 + 0.25 * a.intensity, dashArray: '4 4' })
          .bindPopup(`<b>Point d'attention — ${esc(a.zone)}</b><br/><b>Pourquoi ?</b> ${esc(a.reason)}<br/>Produit concerné : ${esc(a.product)}<br/>Observations : ${esc(a.observations)}<br/>Indice de priorité : ${Math.round(a.priority)} / 100<br/><small>${esc(a.period || '')}</small><br/><a href="/intelligence/produits/${esc(a.product_id)}">ANALYSER →</a>`).addTo(g)
      })
      groups.current.att = g.addTo(m)
    }
    if (layers.shops && data.sellers) {
      const cl = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45, disableClusteringAtZoom: 15 })
      const icon = L.divIcon({ className: '', html: '<div class="pt-shop"></div>', iconSize: [6, 6] })
      data.sellers.forEach((s) => {
        const mk = L.marker([s.lat, s.lon], { icon })
        mk.bindPopup(`<b>${esc(s.name || '(nom non publié)')}</b><br/>${esc(s.category || '')} · ${esc(s.governorate || '')}<br/><a href="/intelligence/vendeurs/${s.id}">Voir la fiche →</a>`)
        if (onSeller) mk.on('click', () => onSeller(s))
        cl.addLayer(mk)
      })
      groups.current.shops = cl.addTo(m)
    }
    if (layers.entries && data.entry_points) {
      const g = L.layerGroup()
      data.entry_points.filter((e) => e.lat != null).forEach((e) => {
        const [sym, cls] = EP[e.type] || ['•', '']
        const icon = L.divIcon({ className: '', html: `<div class="ep-icon ${cls}"><span>${sym}</span></div>`, iconSize: [26, 26], iconAnchor: [13, 13] })
        L.marker([e.lat, e.lon], { icon, zIndexOffset: 1000 }).bindPopup(`<b>${esc(e.name)}</b><br/>${EP_FR[e.type] || ''}${e.governorate ? ' · ' + esc(e.governorate) : ''}<br/><a href="${esc(e.source_url)}" target="_blank">Consulter la source</a>`).addTo(g)
      })
      groups.current.eps = g.addTo(m)
    }
    if (data.product_flow?.zones?.length && data.governorates) {
      const g = L.layerGroup()
      const cent = {}
      data.governorates.forEach((z) => { const c = L.geoJSON(z.geometry).getBounds().getCenter(); cent[z.name] = c })
      data.product_flow.zones.forEach((z) => {
        const c = cent[z.zone]
        if (c) L.circleMarker(c, { radius: 6 + Math.sqrt(z.count), color: '#2a78d6', weight: 2, fillOpacity: 0.15, dashArray: '3 3' })
          .bindTooltip(`${z.zone} : ${z.count} commerces de cette catégorie`).addTo(g)
      })
      groups.current.flow = g.addTo(m)
    }
  }, [data, layers.shops, layers.entries, layers.attention, layers.governorates])

  return <div ref={el} className={`map ${tall ? 'tall' : ''}`} />
}

/** World map: COUNTRY → TUNISIA flows (only officially reported flows). */
export function WorldFlowMap({ flows, height = 420 }) {
  const el = useRef(null)
  const map = useRef(null)
  const layer = useRef(null)
  useEffect(() => {
    map.current = L.map(el.current, { worldCopyJump: true, scrollWheelZoom: false }).setView([28, 15], 2)
    L.tileLayer(TILE, { attribution: ATTR, maxZoom: 8 }).addTo(map.current)
    return () => map.current.remove()
  }, [])
  useEffect(() => {
    const m = map.current
    if (!m || !flows) return
    if (layer.current) m.removeLayer(layer.current)
    const g = L.layerGroup()
    const tn = [36.8, 10.18]
    const max = Math.max(...flows.map((f) => f.value || 0), 1)
    flows.forEach((f) => {
      if (f.lat == null) return
      const w = 1 + 7 * Math.sqrt((f.value || 0) / max)
      L.polyline([[f.lat, f.lon], tn], { color: '#2a78d6', weight: w, opacity: 0.55 })
        .bindTooltip(`<b>${esc(f.country)} → Tunisie</b><br/>${esc(f.label)}<br/>${esc(f.period || '')}`, { sticky: true }).addTo(g)
      L.circleMarker([f.lat, f.lon], { radius: 3, color: '#0b0b0b', weight: 1, fillOpacity: 1 }).addTo(g)
    })
    L.circleMarker(tn, { radius: 6, color: '#0b0b0b', fillColor: '#fff', fillOpacity: 1, weight: 2 }).bindTooltip('Tunisie').addTo(g)
    layer.current = g.addTo(m)
  }, [flows])
  return <div ref={el} className="map" style={{ height }} />
}
