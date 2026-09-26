import { useEffect, useRef, useState } from 'react'
import { Check, Sparkles } from 'lucide-react'
import { api } from '../api.js'

/** Étapes de l'analyse, alimentées par les événements réels du serveur. */
export function useAIRun() {
  const [steps, setSteps] = useState([])
  const [text, setText] = useState('')
  const [status, setStatus] = useState('idle') // idle | running | done | error
  const [result, setResult] = useState(null)
  const [extra, setExtra] = useState({})
  const [error, setError] = useState(null)

  const run = async (path, body) => {
    setSteps([]); setText(''); setResult(null); setExtra({}); setError(null); setStatus('running')
    try {
      const res = await api.stream(path, body, (ev) => {
        if (ev.type === 'step') {
          setSteps((prev) => {
            const key = ev.key || ev.label
            const i = prev.findIndex((s) => s.key === key)
            const item = { key, label: ev.label, status: ev.status, summary: ev.summary }
            if (i === -1) return [...prev, item]
            const next = [...prev]; next[i] = { ...next[i], ...item }; return next
          })
        } else if (ev.type === 'text') {
          setText((t) => t + ev.delta)
        } else if (ev.type !== 'result') {
          setExtra((x) => ({ ...x, [ev.type]: ev.data }))
        }
      })
      setResult(res)
      setSteps((prev) => prev.map((s) => ({ ...s, status: 'done' })))
      setStatus('done')
      return res
    } catch (e) {
      setError(e.message); setStatus('error')
      return null
    }
  }
  const reset = () => { setSteps([]); setText(''); setResult(null); setExtra({}); setStatus('idle'); setError(null) }
  return { steps, text, status, result, extra, error, run, reset }
}

export function AIProgress({ steps, status, title = 'Analyse par intelligence artificielle' }) {
  if (!steps.length && status !== 'running') return null
  return (
    <div className="ai-progress">
      <div className="ai-progress-head">
        {status === 'running' ? <span className="ai-orb" /> : <span className="ai-done"><Check size={14} /></span>}
        <span>{status === 'running' ? title : 'Analyse terminée'}</span>
      </div>
      <ol>
        {steps.map((s) => (
          <li key={s.key} className={`ai-step ${s.status}`}>
            <span className="ai-step-icon">{s.status === 'done' ? <Check size={13} /> : <span className="ai-pulse" />}</span>
            <span className="ai-step-label">{s.label}{s.status === 'running' ? '…' : ''}</span>
            {s.status === 'done' && s.summary && <span className="ai-step-summary">{s.summary}</span>}
          </li>
        ))}
      </ol>
    </div>
  )
}

/** Texte généré, affiché progressivement (effet de rédaction). */
export function StreamText({ text, active }) {
  const [shown, setShown] = useState('')
  const target = useRef(text)
  target.current = text
  useEffect(() => {
    const t = setInterval(() => {
      setShown((s) => (s.length < target.current.length ? target.current.slice(0, s.length + Math.max(2, Math.ceil((target.current.length - s.length) / 30))) : s))
    }, 18)
    return () => clearInterval(t)
  }, [])
  useEffect(() => { if (!text) setShown('') }, [text])
  const typing = active || shown.length < text.length
  return (
    <div className="ai-text">
      {renderRich(shown)}
      {typing && <span className="caret" />}
    </div>
  )
}

function renderRich(s) {
  return s.split('\n').map((line, i) => (
    <p key={i} className={line.trim().startsWith('•') ? 'bullet' : ''}>
      {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) => (part.startsWith('**') && part.endsWith('**') ? <b key={j}>{part.slice(2, -2)}</b> : part))}
    </p>
  ))
}

export function AIBadge({ label = 'Généré par l’IA' }) {
  return <span className="ai-badge"><Sparkles size={12} />{label}</span>
}

export function AIButton({ children, onClick, disabled, big }) {
  return (
    <button className={`btn ai ${big ? 'big' : ''}`} onClick={onClick} disabled={disabled}>
      <Sparkles size={big ? 18 : 15} />{children}
    </button>
  )
}

/** Apparition progressive des blocs de résultats. */
export function Reveal({ children, delay = 0 }) {
  return <div className="reveal" style={{ animationDelay: `${delay}ms` }}>{children}</div>
}
