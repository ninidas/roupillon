import { Fragment, useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import EventSheet from '../components/EventSheet'
import Sheet, { Confirm } from '../components/Sheet'
import { Bed, Bottle, Chevron, Moon, Plus, Sun } from '../components/Icons'

export default function Journal({ open, close, notify, status, version }) {
  const [h, setH] = useState(null)
  const [err, setErr] = useState('')
  const load = useCallback(() => api('/history?days=30').then(setH).catch(e => setErr(e.message)), [])
  useEffect(() => { load() }, [load, version])

  const openDay = (d) => open(<DaySheet date={d.date} title={d.label} onClose={() => { close(); load() }} open={open} notify={notify} />)

  return (
    <div className="wrap">
      <header className="top"><h1 className="rd">Journal</h1><div className="top-sub">30 derniers jours</div>{status}</header>
      {err && <p className="err">{err}</p>}
      {h && <>
        <Tiles days={h.days} refRange={h.ref_24h} />
        {h.days.length > 1 && (
          <section>
            <h2 className="section-h">Sommeil sur 14 jours</h2>
            <div className="group chart-card">
              <Chart days={h.days} refRange={h.ref_24h} />
              <div className="legend">
                <span><i className="lg-day" />Siestes</span><span><i className="lg-night" />Nuit</span>
                <span><i className="lg-ref" />Repère sur 24 h : {h.ref_24h.label}</span>
              </div>
            </div>
          </section>
        )}

        <section>
          <h2 className="section-h">Journées</h2>
          <div className="group">
            {h.days.length ? h.days.map(d => (
              <button key={d.date} type="button" className="cell day" onClick={() => openDay(d)}>
                <div className="grow">
                  <div className="day-h"><span className="ttl">{d.label}</span><span className="val strong">{d.day_sleep}</span></div>
                  <Strip s={d.strip} />
                  <div className="sub2">{summary(d)}</div>
                </div>
                <Chevron />
              </button>
            )) : <div className="empty">Les journées apparaîtront ici dès que vous aurez noté des siestes.</div>}
          </div>
          <p className="foot">Touchez une journée pour la corriger, même plusieurs jours après.</p>
        </section>

        <section>
          <h2 className="section-h">Son rythme</h2>
          <div className="group">
            <div className="rhythm">
              <span /><span className="rh-h">Éveil avant</span><span className="rh-h">Durée</span>
              {h.rhythm.map(r => (
                <Fragment key={r.label}>
                  <span className="rh-l">{r.label}</span>
                  <span><b>{r.win}</b><small>repère {r.win_ref}</small></span>
                  <span><b>{r.nap}</b><small>repère {r.nap_ref}</small></span>
                </Fragment>
              ))}
            </div>
          </div>
          <p className="foot">
            {h.learned_days
              ? `Les prévisions mêlent les repères de son âge et ses ${h.learned_days > 1 ? `${h.learned_days} dernières journées` : 'dernière journée'}. Plus il y a de journées notées, plus elles lui ressemblent ; une journée inhabituelle ne les fausse pas.`
              : "Pour l'instant, les prévisions suivent les repères de son âge. Elles s'adapteront d'elles-mêmes à mesure que vous noterez ses journées."}
          </p>
        </section>
      </>}
    </div>
  )
}

// Nuit dernière et sommeil sur 24 h (siestes d'hier et nuit qui a suivi), comparé au repère de son âge
function Tiles({ days, refRange }) {
  const y = days.find(d => d.label === 'Hier')
  if (!y?.night) return null
  const total = y.day_sleep_min + y.night.min
  const h = (m) => { m = Math.round(m); const hh = Math.floor(m / 60), mm = m % 60; return mm ? `${hh} h ${String(mm).padStart(2, '0')}` : `${hh} h` }
  const where = total < refRange.lo ? 'sous le repère' : total > refRange.hi ? 'au-dessus du repère' : 'dans le repère'
  return (
    <div className="tiles">
      <div className="tile"><span>Nuit dernière</span><b>{y.night.sleep}</b><span>{y.night.count ? `${y.night.count} réveil${y.night.count > 1 ? 's' : ''}` : 'aucun réveil'}{y.bed ? ` · couchée ${y.bed}` : ''}</span></div>
      <div className="tile"><span>Sur 24 h</span><b>{h(total)}</b><span className={where === 'dans le repère' ? 'ok' : ''}>{where}</span></div>
    </div>
  )
}

// Barres empilées : siestes en bas, nuit au-dessus (la nuit qui suit la journée), bande du repère sur 24 h
const CW = 340, CH = 168, X0 = 30, Y0 = 8, Y1 = 140, MAXH = 18 * 60
const cy = (m) => Y1 - (Math.min(m, MAXH) / MAXH) * (Y1 - Y0)
function isoMinus(iso, k) {
  const [y, m, d] = iso.split('-').map(Number), x = new Date(y, m - 1, d - k)
  return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`
}
function Chart({ days, refRange }) {
  const byDate = Object.fromEntries(days.map(d => [d.date, d]))
  const last = days[0].date
  const slots = Array.from({ length: 14 }, (_, k) => isoMinus(last, 13 - k))
  const step = (CW - X0 - 4) / 14, bw = step * 0.62
  return (
    <svg className="chart" viewBox={`0 0 ${CW} ${CH}`} role="img" aria-label="Sommeil de jour et de nuit sur 14 jours">
      <rect x={X0} width={CW - X0 - 4} y={cy(refRange.hi)} height={cy(refRange.lo) - cy(refRange.hi)} fill="var(--green)" opacity=".13" />
      {[6, 12, 18].map(hh => (
        <g key={hh}>
          <line x1={X0} x2={CW - 4} y1={cy(hh * 60)} y2={cy(hh * 60)} stroke="var(--sep)" strokeDasharray="2 3" />
          <text x={X0 - 6} y={cy(hh * 60) + 4} textAnchor="end" className="chart-t">{hh} h</text>
        </g>
      ))}
      <line x1={X0} x2={CW - 4} y1={Y1} y2={Y1} stroke="var(--sep)" />
      {slots.map((iso, k) => {
        const d = byDate[iso], x = X0 + k * step + (step - bw) / 2
        const day = d ? d.day_sleep_min : 0, nightM = d?.night?.min || 0
        const partial = k === 13 && !d?.night
        return (
          <g key={iso} opacity={partial ? 0.55 : 1} className="bar-g" style={{ animationDelay: `${k * 35}ms` }}>
            {day > 0 && <rect x={x} width={bw} y={cy(day)} height={Y1 - cy(day)} rx="2" fill="var(--action)" />}
            {nightM > 0 && <rect x={x} width={bw} y={cy(day + nightM)} height={cy(day) - cy(day + nightM)} rx="2" fill="var(--bedc)" />}
            <text x={x + bw / 2} y={CH - 12} textAnchor="middle" className={`chart-t${k === 13 ? ' strong' : ''}`}>{Number(iso.slice(8))}</text>
          </g>
        )
      })}
    </svg>
  )
}

// Frise d'une journée, de 6 h à 21 h : siestes en violet, nuit à partir du coucher
const S0 = 6 * 60, S1 = 21 * 60
const pos = (m) => `${Math.max(0, Math.min(100, (m - S0) / (S1 - S0) * 100))}%`
function Strip({ s }) {
  if (!s) return null
  return (
    <div className="strip" aria-hidden="true">
      {[9, 12, 15, 18].map(hh => <i key={hh} className="tk" style={{ left: pos(hh * 60) }} />)}
      {s.wake != null && <i className="wake" style={{ left: pos(s.wake) }} />}
      {s.naps.map(([a, b], k) => <i key={k} className="nap" style={{ left: pos(a), width: `calc(${pos(b)} - ${pos(a)})` }} />)}
      {s.bed != null && <i className="night" style={{ left: pos(s.bed), right: 0 }} />}
      {s.now != null && s.bed == null && <i className="now" style={{ left: pos(s.now) }} />}
    </div>
  )
}

function summary(d) {
  const parts = []
  if (d.wake) parts.push(`Lever ${d.wake}`)
  parts.push(d.naps === 1 ? '1 sieste' : `${d.naps} siestes`)
  if (d.bed) parts.push(`couchée ${d.bed}`)
  if (d.night) parts.push(`nuit ${d.night.sleep}${d.night.count ? `, ${d.night.count} réveil${d.night.count > 1 ? 's' : ''}` : ''}`)
  if (d.feeds) parts.push(`${d.feeds} biberon${d.feeds > 1 ? 's' : ''}`)
  // Espaces insécables : « 1 h 35 » ne se coupe pas en fin de ligne
  return parts.join(' · ').replace(/(\d) h (\d)/g, '$1\u00a0h\u00a0$2').replace(/(\d) (h|min|ml)\b/g, '$1\u00a0$2')
}

// Une journée passée, ligne par ligne, chaque ligne corrigeable
export function DaySheet({ date, title, onClose, notify }) {
  const [d, setD] = useState(null)
  const [edit, setEdit] = useState(null)
  const load = useCallback(() => api(`/days/${date}`).then(setD).catch(e => notify(e.message)), [date, notify])
  useEffect(() => { load() }, [load])
  const done = (msg) => { setEdit(null); load(); notify(msg) }

  async function clearDay() {
    try { await api(`/days/${date}`, { method: 'DELETE' }); load(); notify('Journée effacée') } catch (e) { notify(e.message) }
  }

  if (edit) return <EventSheet day={date} {...edit} onClose={() => setEdit(null)} onDone={done} />

  return (
    <Sheet title={title} onClose={onClose}>
      {!d ? <div className="empty">Chargement...</div> : <>
        <div className="group">
          <button type="button" className="cell ic" onClick={() => setEdit({ kind: 'wake', event: d.wake.real ? { id: d.wake.id, start: d.wake.time } : null, defaults: { start: d.wake.time } })}>
            <span className="icon i-sun"><Sun /></span><span className="grow ttl">Lever{!d.wake.real && <span className="badge todo">non noté</span>}</span>
            <span className="val">{d.wake.real ? d.wake.time : ''}</span><Chevron />
          </button>
          {d.naps.map(n => (
            <button key={n.id} type="button" className="cell ic" onClick={() => setEdit({ kind: 'nap', title: n.label, event: { id: n.id, start: n.start, end: n.end || '' } })}>
              <span className="icon i-moon"><Moon /></span>
              <span className="grow"><span className="ttl">{n.label}</span><span className="sub2" style={{ display: 'block' }}>{n.start} à {n.end || '...'}{n.dur ? ` · ${n.dur}` : ''}</span></span><Chevron />
            </button>
          ))}
          <button type="button" className="addrow" onClick={() => setEdit({ kind: 'nap', title: 'Sieste oubliée', event: null })}><Plus />Ajouter une sieste</button>
        </div>

        <div className="group">
          <button type="button" className="cell ic" onClick={() => setEdit({ kind: 'bed', event: d.bed ? { id: d.bed.id, start: d.bed.time } : null })}>
            <span className="icon i-bed"><Bed /></span><span className="grow ttl">Coucher</span>
            <span className="val">{d.bed ? d.bed.time : 'non noté'}</span><Chevron />
          </button>
          {d.night.map((w, j) => (
            <button key={w.id} type="button" className="cell" style={{ paddingLeft: 58 }} onClick={() => setEdit({ kind: 'night', title: `Réveil nocturne ${j + 1}`, event: { id: w.id, start: w.start, end: w.end || '' } })}>
              <span className="grow"><span className="ttl" style={{ fontSize: 16 }}>Réveil {j + 1}</span><span className="sub2" style={{ display: 'block' }}>{w.start} à {w.end || '...'}{w.dur ? ` · ${w.dur}` : ''}</span></span><Chevron />
            </button>
          ))}
          {d.bed && <button type="button" className="addrow" style={{ paddingLeft: 58 }} onClick={() => setEdit({ kind: 'night', event: null })}><Plus />Ajouter un réveil nocturne</button>}
        </div>

        <div className="group">
          {d.feeds.map(f => (
            <button key={f.id} type="button" className="cell ic" onClick={() => setEdit({ kind: 'feed', event: { id: f.id, start: f.time, ml: f.ml } })}>
              <span className="icon i-feed"><Bottle /></span><span className="grow ttl">Biberon {f.time}</span>
              <span className="val">{f.ml ? `${f.ml} ml` : 'quantité ?'}</span><Chevron />
            </button>
          ))}
          <button type="button" className="addrow" onClick={() => setEdit({ kind: 'feed', event: null })}><Plus />Ajouter un biberon</button>
        </div>

        <Confirm label="Effacer la journée" confirm="Toucher encore : siestes, coucher, nuit et biberons seront effacés" onConfirm={clearDay} />
      </>}
    </Sheet>
  )
}
