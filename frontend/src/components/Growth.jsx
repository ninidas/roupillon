import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import Sheet from './Sheet'
import { Plus } from './Icons'

// Croissance : les pesées et les tailles sur les courbes de l'OMS, et ce qu'elle a pris d'une mesure à l'autre.
// Aucun verdict : la bande montre où se situent la plupart des bébés, c'est la régularité qui compte.
export default function Growth({ open, close, notify, version }) {
  const [g, setG] = useState(null)
  const [tab, setTab] = useState('w')       // w : poids, h : taille
  const load = () => api('/growth').then(setG).catch(e => notify(e.message))
  useEffect(() => { load() }, [version])  // eslint-disable-line react-hooks/exhaustive-deps
  const done = (msg) => { close(); load(); notify(msg) }
  if (!g) return null
  const K = KINDS[tab]
  const list = g[K.list]
  return (
    <section>
      <div className="section-row">
        <h2 className="section-h">Croissance</h2>
        <button type="button" className="feedbtn accent" onClick={() => open(<MeasureSheet onClose={close} onDone={done} />)}><Plus />Mesure</button>
      </div>
      <div className="group chart-card">
        <div className="seg" role="tablist" aria-label="Courbe">
          <button type="button" role="tab" id="g-tab-w" aria-selected={tab === 'w'} onClick={() => setTab('w')}>Poids</button>
          <button type="button" role="tab" id="g-tab-h" aria-selected={tab === 'h'} onClick={() => setTab('h')}>Taille</button>
        </div>
        <GrowthChart key={tab} g={g} K={K} />
        {g[K.curves]
          ? <div className="legend"><span><i className="lg-band" />Courbes 3 à 97 de l'OMS</span><span><i className="lg-mid" />Médiane</span><span><i className="lg-dot" />{K.dots}</span></div>
          : <p className="foot" style={{ margin: '4px 6px 0' }}>Indiquez fille ou garçon dans Réglages pour voir les courbes de l'OMS.</p>}
      </div>
      {list.length > 0 && <div className="group" style={{ marginTop: 10 }}>
        {list.slice(0, 6).map(m => (
          <button key={m.id} type="button" className="cell" onClick={() => open(<MeasureDetail m={m} K={K} onClose={close} onDone={done} />)}>
            <span className="grow"><span className="ttl rd" style={{ fontWeight: 600 }}>{m[K.text]} {K.unit}</span><span className="sub2" style={{ display: 'block' }}>{m.label}</span></span>
            {m.gain && <span className="val">{m.gain}</span>}
          </button>
        ))}
      </div>}
      <p className="foot">
        La plupart des bébés se situent entre les courbes 3 et 97 ; le pédiatre regarde surtout si elle suit régulièrement la sienne.
        {tab === 'w' && g.milk ? ` D'après sa dernière pesée, les bébés de son âge boivent ${g.milk.label}, un simple ordre de grandeur : chaque bébé règle son appétit.` : ''}
      </p>
    </section>
  )
}

// Ce qui change entre la courbe de poids et celle de taille
const KINDS = {
  w: { list: 'weights', curves: 'curves', unit: 'kg', text: 'kg', value: (m) => m.grams / 1000, dots: 'Ses pesées',
       empty: 'Ajoutez une première pesée pour voir sa courbe.', aria: 'Courbe de poids sur les courbes de l\'OMS',
       step: (r) => r > 8 ? 2 : r > 2.5 ? 1 : 0.5, pad: [0.5, 0.3], zpad: 0.15, path: 'weights', gone: 'Pesée supprimée', del: 'Supprimer cette pesée' },
  h: { list: 'heights', curves: 'height_curves', unit: 'cm', text: 'cm', value: (m) => m.mm / 10, dots: 'Ses mesures',
       empty: 'Ajoutez une première mesure de taille pour voir sa courbe.', aria: 'Courbe de taille sur les courbes de l\'OMS',
       step: (r) => r > 30 ? 10 : r > 12 ? 5 : 2, pad: [2, 2], zpad: 0.5, path: 'heights', gone: 'Mesure supprimée', del: 'Supprimer cette mesure' },
}

const CW = 340, CH = 210, X0 = 30, X1 = CW - 22, Y0 = 8, Y1 = CH - 24
const MIN_SPAN = 14     // zoom maximal : deux semaines à l'écran
const fmtV = (k) => String(Math.round(k * 10) / 10).replace('.', ',')

// Courbe de poids ou de taille. Sur téléphone : deux doigts pour zoomer, un doigt pour se déplacer une fois zoomé,
// double tape pour tout revoir. Seul l'axe du temps se zoome ; l'axe des valeurs suit ce qui est à l'écran.
function GrowthChart({ g, K }) {
  const span = g.span_days || 183
  const [view, setView] = useState(null)        // [premier jour, dernier jour] affichés, null = tout
  const box = useRef(null)
  const st = useRef({})
  const [d0, d1] = view || [0, span]

  const c = g[K.curves]
  const has = g[K.list].length > 0 || !!c
  useEffect(() => { st.current.view = null; setView(null) }, [span])

  useEffect(() => {
    const el = box.current
    if (!el) return
    const toX = (clientX) => { const r = el.getBoundingClientRect(); return (clientX - r.left) * CW / r.width }
    const dayAt = (px, v) => v[0] + ((px - X0) / (X1 - X0)) * (v[1] - v[0])
    const clamp = (a, w) => { w = Math.min(span, Math.max(MIN_SPAN, w)); a = Math.min(span - w, Math.max(0, a)); return [a, a + w] }
    const cur = () => st.current.view || [0, span]

    function start(e) {
      const t = e.touches
      if (t.length === 2) {
        const mid = toX((t[0].clientX + t[1].clientX) / 2)
        st.current.pinch = { dist: Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY), day: dayAt(mid, cur()), w: cur()[1] - cur()[0] }
        st.current.pan = null
      } else if (t.length === 1) {
        const now = Date.now()
        if (now - (st.current.tap || 0) < 300 && st.current.view) { st.current.view = null; setView(null); st.current.tap = 0; return }
        st.current.tap = now
        st.current.pan = st.current.view ? { x: t[0].clientX, y: t[0].clientY, v: cur(), dir: null } : null
      }
    }
    function move(e) {
      const t = e.touches
      const p = st.current.pinch
      if (t.length === 2 && p) {
        e.preventDefault()
        const dist = Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY)
        const w = p.w * p.dist / Math.max(dist, 1)
        const mid = toX((t[0].clientX + t[1].clientX) / 2)
        const ww = Math.min(span, Math.max(MIN_SPAN, w))
        const v = clamp(p.day - ((mid - X0) / (X1 - X0)) * ww, ww)
        st.current.view = v[1] - v[0] >= span - 0.5 ? null : v
        setView(st.current.view)
      } else if (t.length === 1 && st.current.pan) {
        const q = st.current.pan
        const dx = t[0].clientX - q.x, dy = t[0].clientY - q.y
        if (!q.dir && Math.hypot(dx, dy) > 6) q.dir = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
        if (q.dir !== 'x') return
        e.preventDefault()
        const r = el.getBoundingClientRect()
        const days = -dx * (CW / r.width) / (X1 - X0) * (q.v[1] - q.v[0])
        st.current.view = clamp(q.v[0] + days, q.v[1] - q.v[0])
        setView(st.current.view)
      }
    }
    function end(e) {
      if (e.touches.length < 2) st.current.pinch = null
      if (e.touches.length === 0) st.current.pan = null
    }
    const stop = (e) => e.preventDefault()    // pas de zoom de toute la page sur iPhone
    el.addEventListener('touchstart', start, { passive: true })
    el.addEventListener('touchmove', move, { passive: false })
    el.addEventListener('touchend', end)
    el.addEventListener('touchcancel', end)
    el.addEventListener('gesturestart', stop)
    return () => {
      el.removeEventListener('touchstart', start); el.removeEventListener('touchmove', move)
      el.removeEventListener('touchend', end); el.removeEventListener('touchcancel', end); el.removeEventListener('gesturestart', stop)
    }
  }, [span, has])

  const pts = g[K.list].filter(w => w.age_days != null).map(w => ({ d: w.age_days, kg: K.value(w) })).reverse()
  if (!has) return <div className="empty">{K.empty}</div>
  // Valeurs : ce qui est visible entre d0 et d1 (mesures et courbes 3 et 97)
  const inView = (d) => d >= d0 - 1 && d <= d1 + 1
  const vis = pts.filter(p => inView(p.d)).map(p => p.kg)
  if (c) c.days.forEach((d, i) => { if (inView(d)) vis.push(c.p3[i], c.p97[i]) })
  const kgs = vis.length ? vis : pts.map(p => p.kg)
  const zoomed = !!view
  const lo = Math.min(...kgs), hi = Math.max(...kgs)
  const kgStep = K.step(hi - lo)
  const ymin = Math.max(0, Math.floor((lo - (zoomed ? K.zpad : K.pad[0])) / kgStep) * kgStep)
  const ymax = Math.ceil((hi + (zoomed ? K.zpad : K.pad[1])) / kgStep) * kgStep
  const x = (d) => X0 + ((d - d0) / (d1 - d0)) * (X1 - X0)
  const y = (kg) => Y1 - ((kg - ymin) / (ymax - ymin)) * (Y1 - Y0)
  const line = (ks) => c.days.map((d, i) => `${x(d).toFixed(1)},${y(ks[i]).toFixed(1)}`).join(' ')
  const band = (a, b) => `${line(b)} ${c.days.map((d, i) => `${x(d).toFixed(1)},${y(a[i]).toFixed(1)}`).reverse().join(' ')}`
  // Repères du temps : mois quand on voit large, semaines de vie quand on a zoomé
  const width = d1 - d0
  let ticks
  if (width > 100) {
    const every = width / 30.4375 > 8 ? 2 : 1
    ticks = []
    for (let m = Math.ceil(d0 / 30.4375); m * 30.4375 <= d1; m++) if (m % every === 0) ticks.push({ d: m * 30.4375, t: m === 0 ? '0' : `${m} m` })
  } else {
    const every = width > 50 ? 2 : 1
    ticks = []
    for (let w = Math.ceil(d0 / 7); w * 7 <= d1; w++) if (w % every === 0) ticks.push({ d: w * 7, t: w === 0 ? '0' : `${w} sem.` })
  }
  const lastIn = (k) => { let j = -1; c.days.forEach((d, i) => { if (d <= d1) j = i }); return c[k][Math.max(0, j)] }
  return (
    <>
      <div ref={box} className="chart-zoom">
        <svg className="chart" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label={K.aria}>
          <defs><clipPath id="w-plot"><rect x={X0} y={0} width={X1 - X0} height={Y1 + 1} /></clipPath></defs>
          {Array.from({ length: Math.round((ymax - ymin) / kgStep) + 1 }, (_, i) => ymin + i * kgStep).map(k => (
            <g key={`k${k}`}>
              <line x1={X0} x2={X1} y1={y(k)} y2={y(k)} stroke="var(--sep)" strokeDasharray="2 3" />
              {y(k) > Y0 + 9 && <text x={X0 - 6} y={y(k) + 3.5} textAnchor="end" className="chart-t">{fmtV(k)}</text>}
            </g>
          ))}
          {ticks.map(tk => <text key={`t${tk.d}`} x={x(tk.d)} y={CH - 8} textAnchor="middle" className="chart-t">{tk.t}</text>)}
          <text x={X0 - 6} y={Y0 + 2} textAnchor="end" className="chart-t">{K.unit}</text>
          <g clipPath="url(#w-plot)">
            {c && <>
              <polygon points={band(c.p3, c.p97)} className="who-band" />
              <polygon points={band(c.p15, c.p85)} className="who-band inner" />
              <polyline points={line(c.p50)} className="who-mid" />
            </>}
            {pts.length > 1 && <polyline points={pts.map(p => `${x(p.d).toFixed(1)},${y(p.kg).toFixed(1)}`).join(' ')} className="w-line" />}
            {pts.map((p, i) => <circle key={i} cx={x(p.d).toFixed(1)} cy={y(p.kg).toFixed(1)} r={i === pts.length - 1 ? 5 : 3.8} className="w-dot" />)}
          </g>
          {c && [['p97', '97'], ['p50', '50'], ['p3', '3']].map(([k, t]) => {
            const v = lastIn(k)
            return v >= ymin && v <= ymax ? <text key={k} x={X1 + 4} y={y(v) + 3.5} className="chart-t">{t}</text> : null
          })}
          {g.age_days != null && g.age_days >= d0 && g.age_days <= d1 && <path d={`M${x(g.age_days) - 4} ${Y1 + 7}L${x(g.age_days) + 4} ${Y1 + 7}L${x(g.age_days)} ${Y1 + 1}z`} className="age-mark" />}
        </svg>
      </div>
      <div className="zoom-hint">
        {zoomed
          ? <button type="button" className="link" onClick={() => { st.current.view = null; setView(null) }}>Tout voir</button>
          : <span>Deux doigts pour zoomer sur la courbe</span>}
      </div>
    </>
  )
}

// Une mesure : le poids, la taille, ou les deux (chez le pédiatre, on prend souvent les deux)
function MeasureSheet({ onClose, onDone }) {
  const d = new Date()
  const [day, setDay] = useState(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  const [kg, setKg] = useState('')
  const [cm, setCm] = useState('')
  const [err, setErr] = useState('')
  const num = (v) => Number(String(v).replace(',', '.'))
  const okKg = kg === '' || (num(kg) >= 1.5 && num(kg) <= 25)
  const okCm = cm === '' || (num(cm) >= 30 && num(cm) <= 130)
  const ready = (kg !== '' || cm !== '') && okKg && okCm
  const show = (v) => String(num(v)).replace('.', ',')
  async function save() {
    setErr('')
    try {
      if (kg !== '') await api('/weights', { method: 'POST', body: { day, kg: num(kg) } })
      if (cm !== '') await api('/heights', { method: 'POST', body: { day, cm: num(cm) } })
      onDone([kg !== '' && `${show(kg)} kg`, cm !== '' && `${show(cm)} cm`].filter(Boolean).join(' et ') + ' enregistrés')
    } catch (e) { setErr(e.message) }
  }
  return (
    <Sheet title="Mesure" onClose={onClose}>
      <div className="fields">
        <label className="field">Poids (kg)<input id="m-kg" className="input" inputMode="decimal" placeholder="5,5" value={kg} onChange={e => setKg(e.target.value)} /></label>
        <label className="field">Taille (cm)<input id="m-cm" className="input" inputMode="decimal" placeholder="60" value={cm} onChange={e => setCm(e.target.value)} /></label>
      </div>
      <label className="field">Date de la mesure<input id="m-day" type="date" className="input txt" value={day} onChange={e => setDay(e.target.value)} /></label>
      <p className="foot" style={{ margin: 0 }}>Remplissez l'un ou l'autre, ou les deux.</p>
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" disabled={!ready} onClick={save}>Enregistrer</button>
    </Sheet>
  )
}

function MeasureDetail({ m, K, onClose, onDone }) {
  async function remove() {
    try { await api(`/${K.path}/${m.id}`, { method: 'DELETE' }); onDone(K.gone) } catch { onClose() }
  }
  return (
    <Sheet title={`${m[K.text]} ${K.unit}`} onClose={onClose}>
      <p className="sub2" style={{ margin: 0 }}>{m.label}{m.gain ? ` · ${m.gain} depuis la mesure précédente` : ''}</p>
      <button type="button" className="secondary" onClick={remove}>{K.del}</button>
    </Sheet>
  )
}
