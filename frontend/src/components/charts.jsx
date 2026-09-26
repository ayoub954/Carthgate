import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Sankey, Tooltip, XAxis, YAxis } from 'recharts'
import { fmt } from '../api.js'

const compact = (v) => (Math.abs(v) >= 1e9 ? `${+(v / 1e9).toFixed(1)}B` : Math.abs(v) >= 1e6 ? `${+(v / 1e6).toFixed(1)}M` : Math.abs(v) >= 1e3 ? `${+(v / 1e3).toFixed(1)}k` : `${+Number(v).toFixed(1)}`)
const axis = { stroke: 'var(--axis)', tick: { fill: 'var(--muted)', fontSize: 11 }, tickLine: false }
const tip = { contentStyle: { background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontSize: 12, color: 'var(--ink)' }, labelStyle: { color: 'var(--ink-2)' } }

// Monthly imports vs exports (MTND). Two series → legend + series colors 1/2.
export function TradeChart({ series, height = 280 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="period" {...axis} minTickGap={28} />
        <YAxis {...axis} width={58} tickFormatter={(v) => fmt.num(v)} />
        <Tooltip {...tip} formatter={(v) => fmt.mdt(v)} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
        <Line type="monotone" dataKey="imports" name="Importations" stroke="var(--series-1)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
        <Line type="monotone" dataKey="exports" name="Exportations" stroke="var(--series-2)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

// Actual (solid) vs forecast (dashed) with 80% uncertainty band. Clear separation at the last actual year.
export function OutlookChart({ rows, lastActual, height = 360, label }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={rows} margin={{ top: 12, right: 16, bottom: 0, left: 4 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey="year" {...axis} />
        <YAxis {...axis} width={70} tickFormatter={(v) => fmt.num(v)} />
        <Tooltip {...tip} formatter={(v, n) => (Array.isArray(v) ? `${fmt.num(v[0])} – ${fmt.num(v[1])} M DT` : fmt.mdt(v))} />
        <ReferenceArea x1={lastActual + 0.5} x2={rows[rows.length - 1]?.year} fill="var(--surface-2)" fillOpacity={0.6} />
        <ReferenceLine x={lastActual + 0.5} stroke="var(--axis)" strokeDasharray="3 3" label={{ value: 'PROJECTION →', position: 'insideTopRight', fill: 'var(--muted)', fontSize: 11 }} />
        <Area dataKey="band" name="Incertitude" stroke="none" fill="var(--series-1)" fillOpacity={0.14} isAnimationActive={false} />
        <Line dataKey="actual" name={`${label} — historique`} stroke="var(--series-1)" strokeWidth={2.2} dot={{ r: 3 }} connectNulls={false} isAnimationActive={false} />
        <Line dataKey="forecast" name={`${label} — projection`} stroke="var(--series-1)" strokeWidth={2} strokeDasharray="6 4" dot={false} isAnimationActive={false} />
        <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, color: 'var(--ink-2)' }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

export function HBar({ data, dataKey, nameKey, height, format = (v) => fmt.num(v) }) {
  return (
    <ResponsiveContainer width="100%" height={height || Math.max(160, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" {...axis} tickFormatter={compact} />
        <YAxis type="category" dataKey={nameKey} {...axis} width={150} />
        <Tooltip {...tip} formatter={format} cursor={{ fill: 'var(--surface-2)' }} />
        <Bar dataKey={dataKey} fill="var(--series-1)" radius={[0, 4, 4, 0]} barSize={14} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Spark({ data, dataKey, height = 140, xKey = 'period', format = (v) => fmt.num(v) }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" vertical={false} />
        <XAxis dataKey={xKey} {...axis} minTickGap={24} />
        <YAxis {...axis} width={48} tickFormatter={compact} />
        <Tooltip {...tip} formatter={format} />
        <Line dataKey={dataKey} stroke="var(--series-1)" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function SankeyNode({ x, y, width, height, payload }) {
  return (
    <g>
      <rect x={x} y={y} width={width} height={Math.max(height, 1)} fill="var(--ink)" rx={2} />
      <text x={x + width + 6} y={y + height / 2} dy={4} fontSize={11} fill="var(--ink-2)">{payload.name}</text>
    </g>
  )
}

export function TradeSankey({ data, height = 520 }) {
  if (!data?.links?.length) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <Sankey data={{ nodes: data.nodes, links: data.links }} node={<SankeyNode />} nodePadding={14} nodeWidth={8}
        margin={{ top: 8, right: 170, bottom: 8, left: 8 }} link={{ stroke: 'var(--series-1)', strokeOpacity: 0.22 }}>
        <Tooltip {...tip} formatter={(v) => fmt.num(v)} />
      </Sankey>
    </ResponsiveContainer>
  )
}
