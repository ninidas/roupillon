import { useEffect, useState } from 'react'
import { api } from '../api'
import Sheet from '../components/Sheet'
import { Check, Chevron } from '../components/Icons'

const INI = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const DAY_NAMES = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
const MODES = [{ id: 'none', label: 'Aucun' }, { id: 'alternate', label: 'Alterné' }, { id: 'weekdays', label: 'Jours attitrés' }]

const p2 = (n) => String(n).padStart(2, '0')
const fromIso = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
const toIso = (x) => `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}`
const addDays = (iso, n) => { const d = fromIso(iso); return toIso(new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)) }
const dayGap = (a, b) => Math.round((fromIso(a) - fromIso(b)) / 86400000)

// Pastille d'un parent : son initiale sur sa couleur (la place du parent dans la liste choisit la couleur)
export function Who({ users, id, small }) {
  const i = users.findIndex(u => u.id === id)
  if (i < 0) return <span className={`who none${small ? ' sm' : ''}`} aria-hidden="true" />
  return <span className={`who p${i % 2}${small ? ' sm' : ''}`} aria-hidden="true">{users[i].name.slice(0, 1).toUpperCase()}</span>
}

const nameOf = (users, id) => users.find(u => u.id === id)?.name

export default function Nights({ open, close, notify, status, refresh }) {
  const [w, setW] = useState(null)
  const [start, setStart] = useState(null)       // null = la semaine de ce soir
  const [busy, setBusy] = useState(false)

  const load = (s = start) => api(`/nights${s ? `?start=${s}` : ''}`).then(setW).catch(e => notify(e.message))
  useEffect(() => { load() }, [start])  // eslint-disable-line react-hooks/exhaustive-deps

  if (!w) return <div className="wrap"><header className="top"><h1 className="rd">Nuits</h1></header><div className="empty">Chargement...</div></div>

  const next = addDays(w.this_week, 7)
  const done = (v, msg) => { setW(v); refresh(); if (msg) notify(msg) }

  async function copyLast() {
    setBusy(true)
    try { done(await api('/nights/copy', { method: 'POST', body: { start: w.start } }), 'Semaine reprise : changez les nuits qui diffèrent') }
    catch (e) { notify(e.message) } finally { setBusy(false) }
  }

  const pickNight = (n) => open(<NightSheet date={n.date} label={n.label} week={w} onClose={close}
    onDone={(v, msg) => { close(); done(v, msg) }} notify={notify} />)
  const pickRhythm = () => open(<RhythmSheet week={w} onClose={close}
    onDone={(v, msg) => { close(); done(v, msg) }} notify={notify} />)
  const rhythmLabel = MODES.find(m => m.id === w.rhythm.mode)?.label

  return (
    <div className="wrap">
      <header className="top"><h1 className="rd">Nuits</h1><div className="top-sub">Qui se lève</div>{status}</header>

      <div className="seg full" role="group" aria-label="Semaine">
        <button type="button" aria-pressed={w.start === w.this_week} onClick={() => setStart(null)}>Cette semaine</button>
        <button type="button" aria-pressed={w.start === next} onClick={() => setStart(next)}>Semaine prochaine</button>
      </div>

      <div className="group">
        <button type="button" className="cell" onClick={pickRhythm}>
          <span className="grow ttl">Rythme par défaut</span><span className="val">{rhythmLabel}</span><Chevron />
        </button>
      </div>

      <section>
        <div className="nights-h">
          <h2 className="rd">{w.label}</h2>
          {w.empty > 0 && <span className="pill warn">{w.empty} nuit{w.empty > 1 ? 's' : ''} à attribuer</span>}
        </div>
        <div className="group">
          {w.nights.map(n => (
            <button key={n.date} type="button" className={`cell night-row${n.past ? ' past' : ''}`} onClick={() => pickNight(n)}
              aria-label={`Nuit de ${n.label}, ${n.user_id ? nameOf(w.users, n.user_id) : 'personne'}`}>
              <span className="grow night-d">{n.label}{n.tonight && <span className="badge">ce soir</span>}</span>
              {n.changed && <span className="tag">modifiée</span>}
              {n.user_id
                ? <span className="night-who"><Who users={w.users} id={n.user_id} small />{nameOf(w.users, n.user_id)}</span>
                : n.past ? <span className="val">personne</span> : <span className="night-todo">À attribuer</span>}
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="secondary blue" disabled={busy} onClick={copyLast}>Reprendre la semaine dernière</button>
      <p className="foot">Une nuit va du soir au lendemain matin. Touchez une nuit pour choisir qui se lève ; l'autre parent est prévenu.</p>
    </div>
  )
}

// Qui se lève une nuit : un parent, ou personne pour l'instant. L'autre parent reçoit une notification.
export function NightSheet({ date, label, week, onClose, onDone, notify }) {
  const [w, setW] = useState(week)
  useEffect(() => { if (!week) api(`/nights?start=${date}`).then(setW).catch(e => notify(e.message)) }, [week, date, notify])
  const n = w?.nights.find(x => x.date === date)
  const d = fromIso(date), dn = DAY_NAMES[(d.getDay() + 6) % 7], after = DAY_NAMES[d.getDay() % 7]

  async function set(uid) {
    try {
      const v = await api(`/nights/${date}`, { method: 'PUT', body: { user_id: uid } })
      onDone(v, uid ? `Nuit de ${dn} : ${uid === v.me ? 'vous' : nameOf(v.users, uid)}` : `Nuit de ${dn} : personne pour l'instant`)
    } catch (e) { notify(e.message) }
  }

  const others = w ? w.users.filter(u => u.id !== w.me) : []
  return (
    <Sheet title={`Nuit de ${dn} ${d.getDate()}`} onClose={onClose}>
      <p className="sheet-sub">Du {dn} soir au {after} matin</p>
      {!w ? <div className="empty">Chargement...</div> : (
        <>
          <div className="group" role="radiogroup" aria-label="Qui se lève">
            {w.users.map(u => (
              <button key={u.id} type="button" role="radio" aria-checked={n?.user_id === u.id} className="cell pick" onClick={() => set(u.id)}>
                <Who users={w.users} id={u.id} />
                <span className="grow ttl">{u.id === w.me ? `${u.name} (vous)` : u.name}</span>
                {n?.user_id === u.id ? <span className="pick-ok"><Check /></span>
                  : <span className="val">{w.counts[u.id] ? `${w.counts[u.id]} nuit${w.counts[u.id] > 1 ? 's' : ''} cette semaine` : 'aucune nuit cette semaine'}</span>}
              </button>
            ))}
            <button type="button" role="radio" aria-checked={n?.user_id == null} className="cell pick" onClick={() => set(null)}>
              <Who users={w.users} id={null} />
              <span className="grow ttl muted">Personne pour l'instant</span>
              {n?.user_id == null && <span className="pick-ok"><Check /></span>}
            </button>
          </div>
          {others.length > 0 && <p className="foot">{others.map(u => u.name).join(' et ')} {others.length > 1 ? 'reçoivent' : 'reçoit'} une notification si sa nuit change.</p>}
        </>
      )}
    </Sheet>
  )
}

// Rythme par défaut : il préremplit les semaines à venir ; une nuit choisie à la main reste comme elle est
function RhythmSheet({ week, onClose, onDone, notify }) {
  const r = week.rhythm, users = week.users, ids = users.map(u => u.id)
  const [mode, setMode] = useState(r.mode)
  // Jours attitrés : ceux déjà choisis, sinon la semaine affichée (« garder cette semaine comme rythme »)
  const shown = week.nights.map(n => n.user_id)
  const [days, setDays] = useState(r.mode === 'weekdays' ? r.weekdays
    : shown.some(Boolean) ? shown : shown.map((_, i) => ids[i % ids.length]))
  const [alt, setAlt] = useState(r.mode === 'alternate' ? { anchor: r.anchor, first: r.first, second: r.second }
    : { anchor: week.start, first: week.nights[0].user_id ?? ids[0], second: ids.find(i => i !== (week.nights[0].user_id ?? ids[0])) })
  const [busy, setBusy] = useState(false)

  const altOn = (iso) => (dayGap(iso, alt.anchor) % 2 === 0 ? alt.first : alt.second)
  const preview = week.nights.map((n, i) => mode === 'weekdays' ? days[i] : mode === 'alternate' ? altOn(n.date) : null)
  // Jours attitrés : chaque toucher passe au parent suivant, puis à personne ; alterné : un toucher inverse les deux
  const tap = (i) => {
    if (mode === 'weekdays') {
      const k = ids.indexOf(days[i])
      setDays(days.map((v, j) => (j === i ? (k + 1 < ids.length ? ids[k + 1] : null) : v)))
    } else if (mode === 'alternate') {
      setAlt({ ...alt, first: alt.second, second: alt.first })
    }
  }

  async function save() {
    setBusy(true)
    const body = mode === 'weekdays' ? { mode, weekdays: days } : mode === 'alternate' ? { mode, ...alt } : { mode }
    try {
      const v = await api(`/nights/rhythm?start=${week.start}`, { method: 'PUT', body })
      onDone(v, mode === 'none' ? 'Plus de rythme : vous prévoyez semaine par semaine' : 'Rythme gardé : les semaines se remplissent seules')
    } catch (e) { notify(e.message) } finally { setBusy(false) }
  }

  return (
    <Sheet title="Rythme par défaut" onClose={onClose}>
      <p className="sheet-sub">Il préremplit les semaines à venir, à partir de ce soir</p>
      <div className="seg full" role="group" aria-label="Rythme">
        {MODES.map(m => <button key={m.id} type="button" aria-pressed={mode === m.id}
          disabled={m.id === 'alternate' && users.length < 2} onClick={() => setMode(m.id)}>{m.label}</button>)}
      </div>
      {mode === 'none' ? (
        <p className="foot">Pas de rythme : les nuits restent vides tant que vous ne les attribuez pas, et un rappel arrive le dimanche soir.</p>
      ) : (
        <>
          <div className="rhythm-days">
            {preview.map((uid, i) => (
              <button key={i} type="button" onClick={() => tap(i)}
                aria-label={`${DAY_NAMES[i]} : ${nameOf(users, uid) || 'personne'}`}>
                <span className="wd-i">{INI[i]}</span>
                <Who users={users} id={uid} />
              </button>
            ))}
          </div>
          <p className="foot">{mode === 'weekdays'
            ? 'Touchez un jour pour changer de parent. Une nuit modifiée à la main reste comme vous l’avez choisie.'
            : 'Un soir sur deux. Touchez un jour pour inverser.'}</p>
        </>
      )}
      <button type="button" className="primary" disabled={busy} onClick={save}>Garder ce rythme</button>
    </Sheet>
  )
}
