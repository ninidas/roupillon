// Cadran de la journée, du lever (en bas à gauche) au coucher (en bas à droite).
// Tout est dessiné dans le même repère que l'anneau : le soleil, la lune et chaque sieste ont
// exactement la largeur de l'anneau. Une sieste est une gélule posée dans l'anneau, de son début à sa fin,
// éclairée d'un halo doux ; seules les heures du lever et du coucher sont écrites, le détail est dans la frise.
const R = 112, W = 30
const CAP = (W / 2) / R * 180 / Math.PI   // ce que dépasse un bout arrondi, en degrés
const pol = (r, deg) => { const a = deg * Math.PI / 180; return [150 + r * Math.sin(a), 150 - r * Math.cos(a)] }
function arc(r, a0, a1) {
  if (a1 - a0 < 0.01) a1 = a0 + 0.01
  const [x0, y0] = pol(r, a0), [x1, y1] = pol(r, a1)
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`
}

// Petites illustrations 24×24, en dégradé, posées au centre d'un rond de l'anneau
const At = ({ x, y, size, children }) => (
  <g transform={`translate(${(x - size / 2).toFixed(2)} ${(y - size / 2).toFixed(2)}) scale(${size / 24})`}>{children}</g>
)
const NapIcon = ({ dim }) => (
  <g opacity={dim ? 0.55 : 1}>
    <path d="M17.6 4.2a5 5 0 1 0 4.2 6.9 4 4 0 0 1-4.2-6.9z" fill="url(#g-moon)" />
    <path d="M6.5 19.5h11a3.6 3.6 0 0 0 .3-7.2 5 5 0 0 0-9.5-.6 3.9 3.9 0 0 0-1.8 7.8z" fill="url(#g-cloud)" />
  </g>
)
const WakeIcon = () => (
  <g>
    <path d="M5 16a7 7 0 0 1 14 0z" fill="url(#g-sun)" />
    <path d="M12 4.5v2.2M5.6 7.6l1.5 1.5M18.4 7.6l-1.5 1.5M2.8 12.6h2M19.2 12.6h2" stroke="#ffd98a" strokeWidth="1.8" strokeLinecap="round" />
    <path d="M3 18.6h18" stroke="#ffd98a" strokeWidth="1.8" strokeLinecap="round" />
  </g>
)
const BedIcon = () => (
  <g>
    <path d="M15.5 3.5a8.5 8.5 0 1 0 5 13.6A7 7 0 0 1 15.5 3.5z" fill="url(#g-dusk)" />
    <circle cx="19.5" cy="5" r="1.1" fill="#ffe2c8" /><circle cx="21.3" cy="9.2" r=".8" fill="#ffe2c8" />
  </g>
)

// Contour d'une gélule posée dans l'anneau, de l'angle s à l'angle e : un vrai tracé fermé
// (bord extérieur, bout arrondi, bord intérieur, bout arrondi), pour un liseré net, plein ou en pointillés.
function capsule(s, e, h) {
  const big = e - s > 180 ? 1 : 0
  const [x1, y1] = pol(R + h, s), [x2, y2] = pol(R + h, e), [x3, y3] = pol(R - h, e), [x4, y4] = pol(R - h, s)
  const f = (v) => v.toFixed(2)
  return `M${f(x1)} ${f(y1)}A${R + h} ${R + h} 0 ${big} 1 ${f(x2)} ${f(y2)}A${h} ${h} 0 0 1 ${f(x3)} ${f(y3)}` +
    `A${R - h} ${R - h} 0 ${big} 0 ${f(x4)} ${f(y4)}A${h} ${h} 0 0 1 ${f(x1)} ${f(y1)}Z`
}

// Une gélule de a0 à a1 (degrés) : bouts arrondis compris, elle ne déborde pas de la durée réelle ;
// une sieste très courte devient un rond. Le liseré est tracé juste à l'intérieur de l'anneau.
function Pill({ a0, a1, cls }) {
  const mid = (a0 + a1) / 2
  const long = a1 - a0 > 2 * CAP
  const s = long ? a0 + CAP : mid, e = long ? a1 - CAP : mid
  const h = W / 2 - 0.75
  const [cx, cy] = pol(R, mid)
  return (
    <g className={`pill ${cls}`}>
      {cls === 'real' && <path d={arc(R, s, e)} className="pill-halo" strokeWidth={W + 6} filter="url(#glow)" />}
      {long
        ? <path d={capsule(s, e, h)} className="pill-shape" />
        : <circle cx={cx.toFixed(2)} cy={cy.toFixed(2)} r={h} className="pill-shape" />}
    </g>
  )
}

function End({ x, y, cls, onClick, children }) {
  return (
    <g className={`end ${cls}${onClick ? ' tap' : ''}`} onClick={onClick}>
      <circle cx={x.toFixed(2)} cy={y.toFixed(2)} r={W / 2 + 3} filter="url(#glow)" className="end-halo" />
      <circle cx={x.toFixed(2)} cy={y.toFixed(2)} r={W / 2 - 0.75} className="end-c" />
      <At x={x} y={y} size={19}>{children}</At>
      {onClick && <circle cx={x.toFixed(2)} cy={y.toFixed(2)} r={W / 2 + 10} className="hit-c" />}
    </g>
  )
}

export default function Dial({ dial, onPick }) {
  const tap = (kind, idx) => onPick && { onClick: () => onPick(kind, idx), className: 'tap' }
  const { wake, bed, now, night } = dial
  const span = Math.max(60, bed - wake)
  const A = (t) => -135 + 270 * Math.min(1, Math.max(0, (t - wake) / span))
  const showNow = !night && now >= wake && now <= bed
  const [wx, wy] = pol(R, -135), [bx, by] = pol(R, 135)

  return (
    <svg viewBox="6 4 288 276" className="dial" aria-hidden="true">
      <defs>
        <filter id="glow" filterUnits="userSpaceOnUse" x="-20" y="-20" width="340" height="340"><feGaussianBlur stdDeviation="6" /></filter>
        <linearGradient id="g-cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffffff" /><stop offset="1" stopColor="#c9c4ff" /></linearGradient>
        <linearGradient id="g-moon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#d9d5ff" /><stop offset="1" stopColor="#8b85ff" /></linearGradient>
        <linearGradient id="g-sun" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ffe9a8" /><stop offset="1" stopColor="#f5a93b" /></linearGradient>
        <linearGradient id="g-dusk" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#ffd2a8" /><stop offset="1" stopColor="#ee8656" /></linearGradient>
      </defs>
      <path d={arc(R, -135, 135)} className="ring" strokeWidth={W} />

      {/* Biberons : un petit point lumineux juste à l'extérieur de l'anneau, à son heure */}
      {dial.feeds.filter(f => f.t >= wake && f.t <= bed).map((f) => {
        const [fx, fy] = pol(R + W / 2 + 9, A(f.t))
        return (
          <g key={`f${f.id}`} className="feed-mk"><g {...tap('feed', f.id)}>
            <circle cx={fx.toFixed(2)} cy={fy.toFixed(2)} r="7" filter="url(#glow)" className="feed-halo" />
            <circle cx={fx.toFixed(2)} cy={fy.toFixed(2)} r="6.5" className="feed-c" />
            <At x={fx} y={fy} size={9.5}><path d="M9 2h6M10 2v3l-2 3v12a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2V8l-2-3V2M8 12h8" className="feed-g" /></At>
            {onPick && <circle cx={fx.toFixed(2)} cy={fy.toFixed(2)} r="13" className="hit-c" />}
          </g></g>
        )
      })}

      {dial.naps.map((x, i) => {
        const a0 = A(x.start), full = A(x.end)
        const real = x.start_real
        const running = real && !x.end_real
        const a1 = running ? Math.max(a0, A(Math.min(Math.max(now, x.start), x.end))) : full
        const [mx, my] = pol(R, (a0 + (running ? full : a1)) / 2)
        return (
          <g key={i} className="mk-in" style={{ animationDelay: `${120 + i * 110}ms` }}>
            <g {...tap('nap', x.idx)}>
            {running && <Pill a0={a0} a1={full} cls="plan" />}
            <Pill a0={a0} a1={a1} cls={real ? 'real' : 'plan'} />
            <At x={mx} y={my} size={18}><NapIcon dim={!real} /></At>
            {/* Zone de toucher un peu plus large que la gélule, pour le pouce */}
            {onPick && <path d={arc(R, a0, full)} className="hit" strokeWidth={W + 14} />}
            </g>
          </g>
        )
      })}

      {showNow && (() => {
        const [nx, ny] = pol(R, A(now))
        return (
          <g className="now-dot">
            <circle cx={nx.toFixed(2)} cy={ny.toFixed(2)} r={9} filter="url(#glow)" className="now-halo" />
            <circle cx={nx.toFixed(2)} cy={ny.toFixed(2)} r={5.5} className="now-core" />
          </g>
        )
      })()}

      <End x={wx} y={wy} cls={`wake${dial.wake_real === false ? ' plan' : ''}`} onClick={onPick && (() => onPick('wake'))}><WakeIcon /></End>
      <End x={bx} y={by} cls={`bed${dial.bed_real ? '' : ' plan'}`} onClick={onPick && (() => onPick('bed'))}><BedIcon /></End>
      <text x={wx.toFixed(1)} y={(wy + 36).toFixed(1)} textAnchor="middle" className="dial-end wake-t">{dial.wake_label}</text>
      <text x={bx.toFixed(1)} y={(by + 36).toFixed(1)} textAnchor="middle" className="dial-end bed-t">{dial.bed_real ? '' : 'vers '}{dial.bed_label}</text>
    </svg>
  )
}
