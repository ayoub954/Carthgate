import { useEffect, useMemo, useState } from 'react'
import { flagUrl } from './Country.jsx'

export const REL_STYLE = {
  'OBSERVÉ': { stroke: 'var(--series-1)', dash: null, label: 'Observé (source directe)' },
  'VÉRIFIÉ': { stroke: 'var(--ink)', dash: null, label: 'Vérifié (référentiel ou décision humaine)' },
  'CORRÉLATION STATISTIQUE': { stroke: 'var(--series-2)', dash: '6 5', label: 'Corrélation statistique' },
  'HYPOTHÈSE À VÉRIFIER': { stroke: 'var(--ai)', dash: '2 5', label: 'Hypothèse à vérifier' },
  'DONNÉE NON CONNECTÉE': { stroke: 'var(--axis)', dash: '2 6', label: 'Donnée non connectée' },
}

const safe = (id) => id.replace(/[^a-zA-Z0-9]/g, '_')
const W = 1000
const LEFT = 170
const ROW = 82

/**
 * Parcours intelligent des flux : réseau en couches (continent → … → finance).
 * Les couches apparaissent progressivement, les connexions « s'allument », des impulsions circulent sur les liens.
 */
export default function NeuralPath({ graph, onSelect, selectedId, animateKey }) {
  const [revealed, setRevealed] = useState(-1)
  const layers = graph?.layers || []

  useEffect(() => {
    setRevealed(-1)
    let i = -1
    const t = setInterval(() => {
      i += 1
      setRevealed(i)
      if (i >= layers.length) clearInterval(t)
    }, 330)
    return () => clearInterval(t)
  }, [graph, animateKey, layers.length])

  const pos = useMemo(() => {
    const by = {}
    ;(graph?.nodes || []).forEach((n) => { (by[n.layer] = by[n.layer] || []).push(n) })
    const p = {}
    Object.entries(by).forEach(([layer, list]) => {
      const n = list.length
      list.forEach((node, j) => {
        p[node.id] = { x: LEFT + ((j + 1) * (W - LEFT)) / (n + 1), y: 46 + Number(layer) * ROW, node, room: Math.max(6, Math.floor((W - LEFT) / (n + 1) / 6.2)) }
      })
    })
    return p
  }, [graph])

  const linked = useMemo(() => {
    if (!selectedId) return null
    const s = new Set([selectedId])
    ;(graph?.edges || []).forEach((e) => { if (e.source === selectedId) s.add(e.target); if (e.target === selectedId) s.add(e.source) })
    return s
  }, [selectedId, graph])

  if (!graph?.nodes?.length) return null
  const H = 46 + layers.length * ROW
  const edges = graph.edges.filter((e) => pos[e.source] && pos[e.target])

  const pathOf = (e) => {
    const a = pos[e.source], b = pos[e.target]
    const my = (a.y + b.y) / 2
    return `M ${a.x} ${a.y} C ${a.x} ${my}, ${b.x} ${my}, ${b.x} ${b.y}`
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="neural" role="img" aria-label="Parcours intelligent des flux">
      <defs>
        <radialGradient id="nodeGlow"><stop offset="0%" stopColor="var(--ai)" stopOpacity="0.45" /><stop offset="100%" stopColor="var(--ai)" stopOpacity="0" /></radialGradient>
      </defs>
      {layers.map((l, i) => (
        <g key={l} className={`layer-label ${i <= revealed ? 'on' : ''}`}>
          <line x1={LEFT - 10} x2={W} y1={46 + i * ROW} y2={46 + i * ROW} stroke="var(--grid)" strokeDasharray="2 6" />
          <text x={8} y={46 + i * ROW + 4} fontSize="11.5" fontWeight="650" fill="var(--muted)" letterSpacing="0.06em">{l.toUpperCase()}</text>
        </g>
      ))}
      {edges.map((e, i) => {
        const vis = pos[e.source].node.layer <= revealed && pos[e.target].node.layer <= revealed
        const st = REL_STYLE[e.relation] || REL_STYLE['OBSERVÉ']
        const dim = linked && !(linked.has(e.source) && linked.has(e.target) && (e.source === selectedId || e.target === selectedId))
        const d = pathOf(e)
        return (
          <g key={i} className={`edge ${vis ? 'on' : ''}`} opacity={dim ? 0.08 : 1}>
            <path d={d} fill="none" stroke={st.stroke} strokeWidth={1.2 + 2.5 * Math.min(1, e.weight || 0)} strokeDasharray={st.dash || undefined}
              strokeLinecap="round" opacity={0.75} />
            {vis && !dim && (e.relation === 'OBSERVÉ' || e.relation === 'VÉRIFIÉ') && (
              <circle r="2.6" fill={st.stroke}>
                <animateMotion dur={`${2.2 + (i % 5) * 0.35}s`} repeatCount="indefinite" path={d} />
              </circle>
            )}
          </g>
        )
      })}
      {Object.values(pos).map(({ x, y, node, room }) => {
        const vis = node.layer <= revealed
        const sel = node.id === selectedId
        const dim = linked && !linked.has(node.id)
        const r = node.layer === 2 ? 13 : node.layer === 1 ? 12 : node.layer >= 9 ? 11 : 9
        const fill = node.unavailable ? 'var(--surface)' : node.layer === 9 ? 'var(--serious)' : node.layer >= 11 ? 'var(--ink)' : node.layer === 2 ? 'var(--series-1)' : 'var(--ai)'
        return (
          <g key={node.id} className={`nnode ${vis ? 'on' : ''}`} transform={`translate(${x},${y})`} opacity={dim ? 0.2 : 1}
            onClick={() => onSelect?.(node, graph.edges.filter((e) => e.source === node.id || e.target === node.id))} style={{ cursor: 'pointer' }}>
            <circle r={r * 2.2} fill="url(#nodeGlow)" className="glow" />
            <circle r={r} fill={fill} stroke={node.unavailable ? 'var(--muted)' : 'var(--surface)'} strokeWidth={node.unavailable ? 1.5 : 2.5}
              strokeDasharray={node.unavailable ? '3 3' : undefined} />
            {node.layer === 1 && flagUrl(node.label, node.iso3) && (
              <g><clipPath id={`fc-${safe(node.id)}`}><circle r={r - 1} /></clipPath>
                <image href={flagUrl(node.label, node.iso3)} x={-r} y={-r} width={r * 2} height={r * 2} preserveAspectRatio="xMidYMid slice" clipPath={`url(#fc-${safe(node.id)})`} /></g>
            )}
            {sel && <circle r={r + 5} fill="none" stroke="var(--gold)" strokeWidth="2" />}
            <text y={r + 14} textAnchor="middle" fontSize="11.5" fontWeight="600" fill={node.unavailable ? 'var(--muted)' : 'var(--ink)'}>
              {node.label.length > Math.min(26, room) ? node.label.slice(0, Math.min(26, room) - 1) + '…' : node.label}
            </text>
            {node.sub && <text y={r + 27} textAnchor="middle" fontSize="10" fill="var(--muted)">{node.sub.length > Math.min(30, room + 2) ? node.sub.slice(0, Math.min(30, room + 2) - 1) + '…' : node.sub}</text>}
          </g>
        )
      })}
    </svg>
  )
}

export function RelationLegend() {
  return (
    <div className="legend">
      {Object.entries(REL_STYLE).map(([k, v]) => (
        <span key={k}><svg width="26" height="8"><line x1="1" x2="25" y1="4" y2="4" stroke={v.stroke} strokeWidth="2" strokeDasharray={v.dash || undefined} /></svg>{v.label}</span>
      ))}
    </div>
  )
}
