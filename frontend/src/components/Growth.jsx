import { useEffect, useState } from 'react'
import { api } from '../api'
import Sheet, { Confirm } from './Sheet'
import { Plus } from './Icons'

// Croissance : les pesées sur les courbes de l'OMS, et ce qu'elle a pris d'une pesée à l'autre.
// Aucun verdict : la bande montre où se situent la plupart des bébés, c'est la régularité qui compte.
export default function Growth({ open, close, notify, version }) {
  const [g, setG] = useState(null)
  const load = () => api('/growth').then(setG).catch(e => notify(e.message))
  useEffect(() => { load() }, [version])  // eslint-disable-line react-hooks/exhaustive-deps
  const done = (msg) => { close(); load(); notify(msg) }
  if (!g) return null
  return (
    <section>
      <h2 className="section-h">Croissance</h2>
      <div className="group chart-card">
        <WeightChart g={g} />
        {g.curves
          ? <div className="legend"><span><i className="lg-band" />Courbes 3 à 97 de l'OMS</span><span><i className="lg-mid" />Médiane</span><span><i className="lg-dot" />Ses pesées</span></div>
          : <p className="foot" style={{ margin: '4px 6px 0' }}>Indiquez fille ou garçon dans Réglages pour voir les courbes de l'OMS.</p>}
      </div>
      <div className="group" style={{ marginTop: 10 }}>
        {g.weights.slice(0, 6).map(w => (
          <button key={w.id} type="button" className="cell" onClick={() => open(<WeightDetail w={w} onClose={close} onDone={done} />)}>
            <span className="grow"><span className="ttl rd" style={{ fontWeight: 600 }}>{w.kg} kg</span><span className="sub2" style={{ display: 'block' }}>{w.label}</span></span>
            {w.gain && <span className="val">{w.gain}</span>}
          </button>
        ))}
        <button type="button" className="addrow" onClick={() => open(<WeightSheet onClose={close} onDone={done} />)}><Plus />Ajouter une pesée</button>
      </div>
      <p className="foot">
        La plupart des bébés se situent entre les courbes 3 et 97 ; le pédiatre regarde surtout si elle suit régulièrement la sienne.
        {g.milk ? ` D'après sa dernière pesée, les bébés de son âge boivent ${g.milk.label}, un simple ordre de grandeur : chaque bébé règle son appétit.` : ''}
      </p>
    </section>
  )
}

const CW = 340, CH = 210, X0 = 30, X1 = CW - 22, Y0 = 8, Y1 = CH - 24
function WeightChart({ g }) {
  const span = g.span_days || 183
  const pts = g.weights.filter(w => w.age_days != null).map(w => ({ d: w.age_days, kg: w.grams / 1000 })).reverse()
  const c = g.curves
  const kgs = pts.map(p => p.kg).concat(c ? [c.p3[0], c.p97[c.p97.length - 1]] : [])
  if (!kgs.length) return <div className="empty">Ajoutez une première pesée pour voir sa courbe.</div>
  const ymin = Math.max(0, Math.floor(Math.min(...kgs) - 0.5)), ymax = Math.ceil(Math.max(...kgs) + 0.3)
  const x = (d) => X0 + (d / span) * (X1 - X0)
  const y = (kg) => Y1 - ((kg - ymin) / (ymax - ymin)) * (Y1 - Y0)
  const line = (ks) => c.days.map((d, i) => `${x(d).toFixed(1)},${y(ks[i]).toFixed(1)}`).join(' ')
  const band = (lo, hi) => `${line(hi)} ${c.days.map((d, i) => `${x(d).toFixed(1)},${y(lo[i]).toFixed(1)}`).reverse().join(' ')}`
  const months = Math.floor(span / 30.4375)
  const every = months > 8 ? 2 : 1
  const kgStep = ymax - ymin > 8 ? 2 : 1
  return (
    <svg className="chart" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label="Courbe de poids sur les courbes de l'OMS">
      {Array.from({ length: Math.floor((ymax - ymin) / kgStep) + 1 }, (_, i) => ymin + i * kgStep).map(k => (
        <g key={`k${k}`}>
          <line x1={X0} x2={X1} y1={y(k)} y2={y(k)} stroke="var(--sep)" strokeDasharray="2 3" />
          <text x={X0 - 6} y={y(k) + 3.5} textAnchor="end" className="chart-t">{k}</text>
        </g>
      ))}
      {Array.from({ length: months + 1 }, (_, m) => m).filter(m => m % every === 0).map(m => (
        <text key={`m${m}`} x={x(m * 30.4375)} y={CH - 8} textAnchor="middle" className="chart-t">{m === 0 ? '0' : `${m} m`}</text>
      ))}
      <text x={X0 - 6} y={Y0 + 2} textAnchor="end" className="chart-t">kg</text>
      {c && <>
        <polygon points={band(c.p3, c.p97)} className="who-band" />
        <polygon points={band(c.p15, c.p85)} className="who-band inner" />
        <polyline points={line(c.p50)} className="who-mid" />
        {[['p97', '97'], ['p50', '50'], ['p3', '3']].map(([k, t]) => (
          <text key={k} x={X1 + 4} y={y(c[k][c[k].length - 1]) + 3.5} className="chart-t">{t}</text>
        ))}
      </>}
      {g.age_days != null && g.age_days <= span && <path d={`M${x(g.age_days) - 4} ${Y1 + 7}L${x(g.age_days) + 4} ${Y1 + 7}L${x(g.age_days)} ${Y1 + 1}z`} className="age-mark" />}
      {pts.length > 1 && <polyline points={pts.map(p => `${x(p.d).toFixed(1)},${y(p.kg).toFixed(1)}`).join(' ')} className="w-line" />}
      {pts.map((p, i) => <circle key={i} cx={x(p.d).toFixed(1)} cy={y(p.kg).toFixed(1)} r={i === pts.length - 1 ? 5 : 3.8} className="w-dot" />)}
    </svg>
  )
}

function WeightSheet({ onClose, onDone }) {
  const d = new Date()
  const [day, setDay] = useState(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`)
  const [kg, setKg] = useState('')
  const [err, setErr] = useState('')
  const value = Number(String(kg).replace(',', '.'))
  async function save() {
    setErr('')
    try { await api('/weights', { method: 'POST', body: { day, kg: value } }); onDone(`Pesée de ${String(value).replace('.', ',')} kg enregistrée`) } catch (e) { setErr(e.message) }
  }
  return (
    <Sheet title="Pesée" onClose={onClose}>
      <label className="field">Poids (kg)<input id="w-kg" className="input" inputMode="decimal" placeholder="5,5" value={kg} onChange={e => setKg(e.target.value)} /></label>
      <label className="field">Date de la pesée<input id="w-day" type="date" className="input txt" value={day} onChange={e => setDay(e.target.value)} /></label>
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" disabled={!(value >= 1.5 && value <= 25)} onClick={save}>Enregistrer</button>
    </Sheet>
  )
}

function WeightDetail({ w, onClose, onDone }) {
  async function remove() {
    try { await api(`/weights/${w.id}`, { method: 'DELETE' }); onDone('Pesée supprimée') } catch { onClose() }
  }
  return (
    <Sheet title={`${w.kg} kg`} onClose={onClose}>
      <p className="sub2" style={{ margin: 0 }}>{w.label}{w.gain ? ` · ${w.gain} depuis la pesée précédente` : ''}</p>
      <Confirm label="Supprimer cette pesée" confirm="Toucher encore pour supprimer" onConfirm={remove} />
    </Sheet>
  )
}
