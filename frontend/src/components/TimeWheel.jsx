import { useEffect, useLayoutEffect, useRef } from 'react'

// Sélecteur d'heure en roues, posé directement dans la feuille (comme le réveil de l'iPhone),
// au lieu de la bulle du champ « heure » de Safari. Chaque roue se cale sur une valeur.
const ITEM = 40
const HOURS = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0'))
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

// Les roues tournent en boucle : les valeurs sont répétées, et quand la roue s'arrête on la
// replace sans animation sur la copie du milieu (avant 00 vient 59, avant 00 h vient 23).
const REPS = 7
const MID = Math.floor(REPS / 2)

function Column({ values, value, onChange, label }) {
  const ref = useRef(null)
  const timer = useRef()
  const n = values.length
  const idx = Math.max(0, values.indexOf(value))
  useLayoutEffect(() => { ref.current.scrollTop = (MID * n + idx) * ITEM }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  // Valeur changée ailleurs (bouton « maintenant », autre champ) : la roue glisse vers la copie la plus proche
  useEffect(() => {
    const el = ref.current, at = Math.round(el.scrollTop / ITEM)
    if (((at % n) + n) % n === idx) return
    let to = at - (((at % n) + n) % n) + idx
    if (to - at > n / 2) to -= n
    if (at - to > n / 2) to += n
    el.scrollTo({ top: to * ITEM, behavior: 'smooth' })
  }, [idx])  // eslint-disable-line react-hooks/exhaustive-deps
  // La valeur est prise quand la roue s'arrête, élan compris
  const onScroll = () => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const el = ref.current
      const at = Math.max(0, Math.min(n * REPS - 1, Math.round(el.scrollTop / ITEM)))
      const i = at % n
      if (Math.floor(at / n) !== MID) el.scrollTop = (MID * n + i) * ITEM
      if (values[i] !== value) onChange(values[i])
    }, 90)
  }
  return (
    <div className="wheel-col" ref={ref} onScroll={onScroll} role="listbox" aria-label={label}>
      <div style={{ height: ITEM * 2 }} />
      {Array.from({ length: n * REPS }, (_, j) => {
        const i = j % n, copy = Math.floor(j / n) === MID
        return (
          <div key={j} role={copy ? 'option' : undefined} aria-hidden={copy ? undefined : true} aria-selected={copy ? i === idx : undefined}
            className={`wheel-i rd${i === idx ? ' on' : ''}`}
            onClick={() => ref.current.scrollTo({ top: j * ITEM, behavior: 'smooth' })}>{values[i]}</div>
        )
      })}
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
