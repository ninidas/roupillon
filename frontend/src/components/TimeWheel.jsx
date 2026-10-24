import { useEffect, useLayoutEffect, useRef } from 'react'

// Sélecteur d'heure en roues, posé directement dans la feuille (comme le réveil de l'iPhone),
// au lieu de la bulle du champ « heure » de Safari. Chaque roue se cale sur une valeur.
const ITEM = 40
const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

function Column({ values, value, onChange, label }) {
  const ref = useRef(null)
  const timer = useRef()
  const idx = Math.max(0, values.indexOf(value))
  useLayoutEffect(() => { ref.current.scrollTop = idx * ITEM }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  // Valeur changée ailleurs (bouton « maintenant », autre champ) : la roue y glisse
  useEffect(() => {
    const el = ref.current
    if (Math.round(el.scrollTop / ITEM) !== idx) el.scrollTo({ top: idx * ITEM, behavior: 'smooth' })
  }, [idx])
  // La valeur est prise quand la roue s'arrête, élan compris
  const onScroll = () => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const i = Math.max(0, Math.min(values.length - 1, Math.round(ref.current.scrollTop / ITEM)))
      if (values[i] !== value) onChange(values[i])
    }, 90)
  }
  return (
    <div className="wheel-col" ref={ref} onScroll={onScroll} role="listbox" aria-label={label}>
      <div style={{ height: ITEM * 2 }} />
      {values.map((v, i) => (
        <div key={v} role="option" aria-selected={i === idx} className={`wheel-i rd${i === idx ? ' on' : ''}`}
          onClick={() => ref.current.scrollTo({ top: i * ITEM, behavior: 'smooth' })}>{v}</div>
      ))}
      <div style={{ height: ITEM * 2 }} />
    </div>
  )
}

export default function TimeWheel({ value, onChange }) {
  const [h, m] = (value || '00:00').split(':')
  return (
    <div className="wheel">
      <div className="wheel-band" />
      <Column values={HOURS} value={h} label="Heures" onChange={(v) => onChange(`${v}:${m}`)} />
      <span className="wheel-sep rd">:</span>
      <Column values={MINUTES} value={m} label="Minutes" onChange={(v) => onChange(`${h}:${v}`)} />
    </div>
  )
}
