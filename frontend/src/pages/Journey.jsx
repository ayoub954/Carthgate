import { useState } from 'react'
import Constellation from '../components/Constellation.jsx'
import { Card, Empty, ErrorBox, Loading, PageHead, useApi } from '../components/ui.jsx'

export default function Journey() {
  const prods = useApi('/products')
  const [pid, setPid] = useState('8517')
  const g = useApi(`/network/${pid}`)
  return (
    <div>
      <PageHead title="Parcours commercial" sub="Continent → pays → produit → mode d'entrée → point d'entrée → zone commerciale → vendeur">
        <select className="input" style={{ width: 280 }} value={pid} onChange={(e) => setPid(e.target.value)}>
          {prods.data?.monitored?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </PageHead>
      <Card sub="Cliquez sur un élément pour mettre en évidence son parcours. Aucun lien entre importateur et vendeur n'est supposé.">
        {g.loading ? <Loading /> : g.error ? <ErrorBox error={g.error} /> : g.data?.nodes?.length ? <Constellation graph={g.data} height={620} /> : <Empty />}
      </Card>
    </div>
  )
}
