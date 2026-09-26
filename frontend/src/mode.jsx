import { createContext, useContext, useState } from 'react'
import { getMode, setMode as persist } from './api.js'

const ModeCtx = createContext({ mode: 'REAL', setMode: () => {} })

export function ModeProvider({ children }) {
  const [mode, set] = useState(getMode())
  const setMode = (m) => { persist(m); set(m) }
  return <ModeCtx.Provider value={{ mode, setMode }}>{children}</ModeCtx.Provider>
}

export const useMode = () => useContext(ModeCtx)

export function ModeSwitch({ compact }) {
  const { mode, setMode } = useMode()
  return (
    <div className={`seg ${compact ? 'small' : ''}`} title="Mode de données">
      <button className={mode === 'REAL' ? 'on' : ''} onClick={() => setMode('REAL')}>Mode réel</button>
      <button className={mode === 'DEMO' ? 'on' : ''} onClick={() => setMode('DEMO')}>Mode démonstration</button>
    </div>
  )
}

export function DemoBanner() {
  const { mode } = useMode()
  if (mode !== 'DEMO') return null
  return (
    <div className="demo-banner">
      <b>Mode démonstration</b> · Données simulées à des fins de démonstration — identités fictives, aucune situation réelle.
    </div>
  )
}
