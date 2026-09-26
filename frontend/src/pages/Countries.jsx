import { useState } from 'react'
import { fmt } from '../api.js'
import { HBar, TradeSankey } from '../components/charts.jsx'
import { WorldFlowMap } from '../components/maps.jsx'
import { Bar, Card, Empty, ErrorBox, ExportMenu, Loading, Note, PageHead, Seg, SourceLine, useApi } from '../components/ui.jsx'
import { useMode } from '../mode.jsx'

export default function Countries() {
  const { data, error, loading } = useApi('/countries')
  const { mode } = useMode()
  const [metric, setMetric] = useState('value')
  const sk = useApi(`/sankey?metric=${metric}`)
  if (loading) return <Loading />
  if (error) return <ErrorBox error={error} />
  const flows = data.countries.slice(0, 25).map((c) => ({ ...c, value: c.imports_mtnd, label: `${fmt.mdt(c.imports_mtnd)} importés`, period: data.period }))
  return (
    <div>
      <PageHead title="Pays et provenance" sub={`Importations de la Tunisie par pays — ${data.period} (données officielles)`}>
        <ExportMenu dataset="customs_records" />
      </PageHead>
      {mode === 'DEMO' && <Note>Cette page présente toujours des données officielles réelles.</Note>}
      <div className="grid g-main">
        <Card title="Flux commerciaux vers la Tunisie" sub="Épaisseur proportionnelle à la valeur importée"><WorldFlowMap flows={flows} /><SourceLine sources={data.sources[0]} /></Card>
        <Card title={`Continent principal : ${data.top_continent || '—'}`} sub="Selon la valeur importée depuis le début de l'année">
          <div className="stack">{data.continents.map((c) => <div key={c.continent}><div className="row between small"><span>{c.continent}</span><span>{fmt.mdt(c.imports_mtnd)} · {fmt.pct(c.share, 1)}</span></div><Bar value={c.share} /></div>)}</div>
        </Card>
      </div>
      <Card title="Principaux pays de provenance" className="section">
        <div className="grid g2">
          <HBar data={data.countries.slice(0, 12)} dataKey="imports_mtnd" nameKey="country" format={(v) => fmt.mdt(v)} />
          <div className="table-wrap"><table className="t">
            <thead><tr><th>Pays</th><th>Continent</th><th>Importations</th><th>Part</th><th>Évolution</th><th>Catégories suivies</th></tr></thead>
            <tbody>{data.countries.slice(0, 18).map((c) => <tr key={c.iso3}><td>{c.country}</td><td>{c.continent}</td><td>{fmt.mdt(c.imports_mtnd)}</td><td>{fmt.pct(c.share, 1)}</td><td>{c.trend == null ? '—' : fmt.signed(c.trend * 100)}</td><td className="tiny">{c.categories.join(', ') || '—'}</td></tr>)}</tbody>
          </table></div>
        </div>
      </Card>
      <Card title="Flux commerciaux détaillés" className="section" sub="Continent → pays → produit → mode d'entrée → point d'entrée → zone"
        right={<Seg value={metric} onChange={setMetric} options={[['value', 'Valeur'], ['weight', 'Quantité'], ['records', 'Opérations']]} />}>
        {sk.loading ? <Loading /> : sk.data?.links?.length ? <TradeSankey data={sk.data} /> : <Empty />}
        {sk.data?.missing_reason && <p className="tiny muted" style={{ marginTop: 10 }}>{sk.data.missing_reason}</p>}
      </Card>
    </div>
  )
}
