import { useEffect, useState } from 'react'

// Feuille qui monte du bas, comme sur iOS. Fermeture : bouton, fond grisé ou glissement vers le bas.
export default function Sheet({ title, onClose, action, children }) {
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const esc = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => { document.body.style.overflow = prev; window.removeEventListener('keydown', esc) }
  }, [onClose])

  let y0 = null
  const start = (e) => { y0 = e.touches[0].clientY }
  const move = (e) => { if (y0 != null && e.touches[0].clientY - y0 > 70 && e.currentTarget.scrollTop <= 0) { y0 = null; onClose() } }

  return (
    <>
      <div className="backdrop" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} onTouchStart={start} onTouchMove={move}>
        <div className="grab" />
        <div className="sheet-h">
          <button type="button" className="link" onClick={onClose}>Fermer</button>
          <h2>{title}</h2>
          <span style={{ minWidth: 52, textAlign: 'right' }}>{action}</span>
        </div>
        {children}
      </div>
    </>
  )
}

// Bouton en deux temps : le premier appui demande confirmation
export function Confirm({ label, confirm, onConfirm, className = 'secondary' }) {
  const [armed, setArmed] = useState(false)
  useEffect(() => { if (!armed) return; const t = setTimeout(() => setArmed(false), 4000); return () => clearTimeout(t) }, [armed])
  return (
    <button type="button" className={className} onClick={() => (armed ? onConfirm() : setArmed(true))}>
      {armed ? confirm : label}
    </button>
  )
}
