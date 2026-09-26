import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fmt } from '../../api.js'
import { TunisiaMap } from '../../components/maps.jsx'
import ZonePanel from '../../components/ZonePanel.jsx'
import { Card, ErrorBox, Loading, Note, PageGuide, PageHead, useApi } from '../../components/ui.jsx'

export default function ControlMap() {
  const { data, error, loading } = useApi('/douane/map')
  const [params] = useSearchParams()
  const [zone, setZone] = useState(params.get('zone'))
  const [layers, setLayers] = useState({ shops: true, entries: true, zones: true, governorates: true })
  const toggle = (k) => setLayers({ ...layers, [k]: !layers[k] })
  return (
    <div>
      <PageHead eyebrow="Espace Douane" title="Carte des contrôles" sub="Identifier les zones et points d'entrée où l'attention pourrait être renforcée." />
      <PageGuide purpose="Cette carte réunit les points d'entrée, les commerces publiquement référencés et les zones où se concentrent les dossiers."
        steps={['Activez ou masquez les couches de la carte.', 'Cliquez sur une zone colorée pour l’analyser.', 'Ouvrez les dossiers de la zone depuis le panneau.']}
        why="La taille d'un cercle correspond au nombre de dossiers rattachés à la zone ; sa couleur, au niveau de priorité de la zone. Les commerces proches sont regroupés automatiquement." />
      {loading ? <Loading /> : error ? <ErrorBox error={error} /> : (
        <>
          {data.notes.map((n) => <Note key={n}>{n}</Note>)}
          <div className="map-layout">
            <Card>
              <div className="row" style={{ gap: 6, marginBottom: 10 }}>
                {[['zones', 'Concentrations de dossiers'], ['shops', 'Activités commerciales observées'], ['entries', "Points d'entrée"], ['governorates', 'Gouvernorats']].map(([k, l]) => (
                  <button key={k} className={`chip ${layers[k] ? 'on' : ''}`} onClick={() => toggle(k)}>{l}</button>))}
              </div>
              <TunisiaMap data={data} layers={layers} height={620} onZone={setZone} selected={zone} />
              <div className="legend">
                <span><i className="lg-dot" style={{ background: '#d03b3b' }} />Prioritaire</span>
                <span><i className="lg-dot" style={{ background: '#ec835a' }} />Anomalie à vérifier</span>
                <span><i className="lg-dot" style={{ background: '#fab219' }} />À surveiller</span>
                <span><i className="lg-shop" />Activité commerciale observée</span>
                <span>⚓ Port</span><span>✈ Aéroport</span><span>⇄ Passage terrestre</span>
              </div>
            </Card>
            {zone ? <ZonePanel gov={zone} onClose={() => setZone(null)} /> : (
              <aside className="zone-panel">
                <div className="eyebrow">Zones à examiner</div>
                <p className="small muted" style={{ margin: '6px 0 10px' }}>Cliquez sur une zone de la carte, ou choisissez-la ci-dessous.</p>
                {data.zones.filter((z) => z.cases).map((z) => (
                  <button key={z.governorate} className="zone-row" onClick={() => setZone(z.governorate)}>
                    <b>{z.governorate}</b><span className="small muted">{z.cases} dossier(s) · {fmt.num(z.shops)} commerce(s)</span><span className="prio">{fmt.num(z.priority_index)}</span>
                  </button>))}
                <div className="eyebrow" style={{ marginTop: 16 }}>Points d'entrée</div>
                <div className="small muted">{data.entry_points.filter((e) => e.type === 'SEAPORT').length} ports · {data.entry_points.filter((e) => e.type === 'AIRPORT').length} aéroports · {data.entry_points.filter((e) => e.type === 'LAND_BORDER').length} passages terrestres</div>
              </aside>
            )}
          </div>
        </>
      )}
    </div>
  )
}
