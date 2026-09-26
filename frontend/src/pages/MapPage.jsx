import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmt } from '../api.js'
import { TunisiaMap } from '../components/maps.jsx'
import { Card, Empty, ErrorBox, Loading, PageHead, useApi } from '../components/ui.jsx'

export default function MapPage() {
  const [params, setParams] = useSearchParams()
  const pid = params.get('produit') || ''
  const [layers, setLayers] = useState({ shops: true, entries: true, attention: true, governorates: true })
  const prods = useApi('/products')
  const { data, error, loading } = useApi(`/map${pid ? `?product_id=${pid}` : ''}`)
  const toggle = (k) => setLayers((l) => ({ ...l, [k]: !l[k] }))
  return (
    <div>
      <PageHead title="Carte" sub="Points commerciaux publics et points d'entrée douaniers, sur des couches séparées.">
        <select className="input" style={{ width: 280 }} value={pid} onChange={(e) => setParams(e.target.value ? { produit: e.target.value } : {})}>
          <option value="">Afficher le flux d'un produit…</option>
          {prods.data?.monitored?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </PageHead>
      <div className="row" style={{ marginBottom: 12 }}>
        {[['shops', '● Points commerciaux'], ['entries', "✈ ⚓ ◆ Points d'entrée"], ['attention', 'Attention IA'], ['governorates', 'Gouvernorats']].map(([k, l]) => (
          <button key={k} className={`btn small ${layers[k] ? 'primary' : ''}`} onClick={() => toggle(k)}>{l}</button>))}
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <div className="grid g-main">
          <Card>
            <TunisiaMap data={data} layers={layers} tall />
            <div className="legend">
              <span><i className="pt-shop" style={{ display: 'inline-block' }} />Point commercial public ({fmt.num(data.sellers.length)})</span>
              <span>✈ Aéroport</span><span>⚓ Port</span><span>◆ Frontière terrestre</span>
              <span><i style={{ width: 12, height: 12, borderRadius: 6, border: '1.5px dashed #d03b3b' }} />Zone d'attention IA</span>
            </div>
          </Card>
          <div className="stack" style={{ gap: 18 }}>
            {pid && data.product_flow && (
              <Card title={`Flux — ${data.product_flow.product}`} sub="Pays de provenance → point d'entrée → zones commerciales">
                <div className="eyebrow">Provenance</div>
                {data.product_flow.origins.length ? <ul className="why">{data.product_flow.origins.slice(0, 5).map((o) => <li key={o.country}>{o.country} : {fmt.money(o.value, o.unit)}</li>)}</ul> : <p className="small muted">—</p>}
                <div className="eyebrow" style={{ marginTop: 12 }}>Entrée en Tunisie</div>
                {data.product_flow.entry.available ? <ul className="why">{data.product_flow.entry.modes.map((m) => <li key={m.key}>{m.mode} : {fmt.pct(m.share)}</li>)}</ul>
                  : <p className="small muted">{data.product_flow.entry.message}</p>}
                <div className="eyebrow" style={{ marginTop: 12 }}>Zones commerciales (association statistique)</div>
                <ul className="why">{data.product_flow.zones.map((z) => <li key={z.zone}>{z.zone} : {z.count} commerces</li>)}</ul>
              </Card>
            )}
            <Card title="Points d'attention IA" sub="Une zone d'attention n'indique pas une fraude.">
              {data.attention.length ? data.attention.map((a, i) => (
                <div key={i} className="small" style={{ marginBottom: 12 }}><b>{a.zone}</b> — {a.product}<div className="muted tiny">{a.reason} · indice {fmt.num(a.priority)} / 100</div></div>
              )) : <Empty>Lancez une analyse dans « Risques et alertes ».</Empty>}
            </Card>
            <Card title="Points d'entrée officiels" sub={`${data.entry_points.length} points`}>
              <div className="table-wrap" style={{ maxHeight: 360, overflowY: 'auto' }}><table className="t">
                <tbody>{data.entry_points.map((e) => <tr key={e.id}><td className="small">{e.name}{e.lat == null && <div className="tiny muted">coordonnées non publiées</div>}</td><td className="tiny">{e.type_fr}</td><td className="small">{e.governorate || '—'}</td></tr>)}</tbody>
              </table></div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
