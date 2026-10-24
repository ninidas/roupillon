// Cadran de la journée, du lever (en bas à gauche) au coucher (en bas à droite).
// Tout est dessiné dans le même repère que l'anneau : le soleil, la lune et chaque sieste ont
// exactement la largeur de l'anneau. Une sieste est une gélule posée dans l'anneau, de son début à sa fin.
const R = 112, W = 30
const CAP = (W / 2) / R * 180 / Math.PI   // ce que dépasse un bout arrondi, en degrés
const pol = (r, deg) => { const a = deg * Math.PI / 180; return [150 + r * Math.sin(a), 150 - r * Math.cos(a)] }
function arc(r, a0, a1) {
  if (a1 - a0 < 0.01) a1 = a0 + 0.01
  const [x0, y0] = pol(r, a0), [x1, y1] = pol(r, a1)
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}
const fmt = (m) => { m = Math.round(m); return String(Math.floor(m / 60) % 24).padStart(2, '0') + ':' + String(((m % 60) + 60) % 60).padStart(2, '0') }

const MOON = 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z'
// Une icône 24×24 posée au centre d'un rond de l'anneau
const Glyph = ({ x, y, size = 14, children }) => (
  <g transform={`translate(${(x - size / 2).toFixed(2)} ${(y - size / 2).toFixed(2)}) scale(${size / 24})`}>{children}</g>
)
const SunGlyph = () => (
  <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
    <circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.4M12 19.6V22M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M2 12h2.4M19.6 12H22M4.9 19.1l1.7-1.7M17.4 6.6l1.7-1.7" />
  </g>
)

// Une gélule de a0 à a1 (degrés) : bords arrondis compris, elle ne déborde pas de la durée réelle
function Pill({ a0, a1, cls }) {
  const mid = (a0 + a1) / 2
  const long = a1 - a0 > 2 * CAP
  const d = arc(R, long ? a0 + CAP : mid, long ? a1 - CAP : mid)
  return (
    <g className={`pill ${cls}`}>
      <path d={d} className="pill-edge" strokeWidth={W} />
      <path d={d} className="pill-fill" strokeWidth={W - 4} />
    </g>
  )
}

export default function Dial({ dial }) {
  const { wake, bed, now, night } = dial
  const span = Math.max(60, bed - wake)
  const A = (t) => -135 + 270 * Math.min(1, Math.max(0, (t - wake) / span))
  const showNow = !night && now >= wake && now <= bed
  const [wx, wy] = pol(R, -135), [bx, by] = pol(R, 135)

  // Heures des siestes autour de l'anneau, sauf si deux siestes sont trop proches pour deux étiquettes
  let lastLabel = -999
  const naps = dial.naps.map((x) => {
    const a0 = A(x.start), a1 = A(x.end), mid = (a0 + a1) / 2
    const label = mid - lastLabel > 16
    if (label) lastLabel = mid
    return { ...x, a0, a1, mid, label }
  })

  return (
    <svg viewBox="-30 0 360 276" className="dial" aria-hidden="true">
      <defs>
        <filter id="halo" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
      </defs>
      <path d={arc(R, -135, 135)} className="ring" strokeWidth={W} />
      {showNow && now > wake && <path d={arc(R, -135, A(now))} className="ring-past" strokeWidth={W} />}

      {dial.feeds.filter(t => t >= wake && t <= bed).map((t, i) => {
        const [fx, fy] = pol(R, A(t))
        return <circle key={`f${i}`} cx={fx.toFixed(2)} cy={fy.toFixed(2)} r="3.5" className="feed-dot" />
      })}

      {naps.map((x, i) => {
        const real = x.start_real
        const running = real && !x.end_real
        const a1 = running ? Math.max(x.a0, A(Math.min(Math.max(now, x.start), x.end))) : x.a1
        const [mx, my] = pol(R, running ? (x.a0 + a1) / 2 : x.mid)
        const [lx, ly] = pol(R + W / 2 + 21, x.mid)
        return (
          <g key={i} className="mk-in" style={{ animationDelay: `${150 + i * 110}ms` }}>
            {running && <Pill a0={x.a0} a1={x.a1} cls="plan" />}
            <Pill a0={x.a0} a1={a1} cls={real ? 'real' : 'plan'} />
            <Glyph x={mx} y={my} size={13}><path d={MOON} className={real ? 'glyph' : 'glyph-plan'} /></Glyph>
            {x.label && <text x={lx.toFixed(1)} y={(ly + 4).toFixed(1)} textAnchor="middle" className="dial-t">{fmt(x.start)}</text>}
          </g>
        )
      })}

      {showNow && (() => {
        const [nx, ny] = pol(R, A(now))
        return (
          <g className="now-dot">
            <circle cx={nx.toFixed(2)} cy={ny.toFixed(2)} r={W / 2 - 5} filter="url(#halo)" className="now-halo" />
            <circle cx={nx.toFixed(2)} cy={ny.toFixed(2)} r={W / 2 - 8} className="now-core" />
          </g>
        )
      })()}

      <g className={`end wake${dial.wake_real === false ? ' plan' : ''}`}>
        <circle cx={wx.toFixed(2)} cy={wy.toFixed(2)} r={W / 2} filter="url(#halo)" className="end-halo" />
        <circle cx={wx.toFixed(2)} cy={wy.toFixed(2)} r={W / 2 - 1} className="end-c" />
        <Glyph x={wx} y={wy} size={16}><SunGlyph /></Glyph>
      </g>
      <g className={`end bed${dial.bed_real ? '' : ' plan'}`}>
        <circle cx={bx.toFixed(2)} cy={by.toFixed(2)} r={W / 2} filter="url(#halo)" className="end-halo" />
        <circle cx={bx.toFixed(2)} cy={by.toFixed(2)} r={W / 2 - 1} className="end-c" />
        <Glyph x={bx} y={by} size={15}><path d={MOON} fill="currentColor" /></Glyph>
      </g>
      <text x={wx.toFixed(1)} y={(wy + 34).toFixed(1)} textAnchor="middle" className="dial-end wake-t">{dial.wake_label}</text>
      <text x={bx.toFixed(1)} y={(by + 34).toFixed(1)} textAnchor="middle" className="dial-end bed-t">{dial.bed_real ? '' : 'vers '}{dial.bed_label}</text>
    </svg>
  )
}
