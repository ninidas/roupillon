import { useState } from 'react'
import { api } from '../api'
import Sheet from './Sheet'
import TimeWheel from './TimeWheel'

const LABELS = {
  nap: { title: 'Sieste', laid: 'Au lit à', start: 'Endormie à', end: 'Réveillée à' },
  night: { title: 'Réveil nocturne', start: 'Réveillée à', end: 'Rendormie à' },
  wake: { title: 'Lever', start: 'Levée à' },
  bed: { title: 'Coucher', start: 'Couchée à', asleep: 'Endormie à' },
  feed: { title: 'Biberon', start: 'Heure' },
}
export const ML = [60, 90, 120, 150, 180, 210]

const p2 = (n) => String(n).padStart(2, '0')
function nowHM() {
  const d = new Date()
  return p2(d.getHours()) + ':' + p2(d.getMinutes())
}
// « 14:50 » décalé de n minutes
function addHM(hm, n) {
  const [h, m] = hm.split(':').map(Number), t = ((h * 60 + m + n) % 1440 + 1440) % 1440
  return p2(Math.floor(t / 60)) + ':' + p2(t % 60)
}
// « 2026-10-24T11:06:00 » reculé de n minutes, au format attendu par le serveur
export function shiftStamp(s, n) {
  const [d, t] = s.split('T'), [y, m, j] = d.split('-').map(Number), [h, mi] = t.split(':').map(Number)
  const x = new Date(y, m - 1, j, h, mi - n)
  return `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}T${p2(x.getHours())}:${p2(x.getMinutes())}`
}

// Saisie ou correction d'un fait de la journée. event : {id, start, end, ml} existant, ou null pour un ajout.
export default function EventSheet({ kind, day, event, title, defaults = {}, onClose, onDone }) {
  const L = LABELS[kind]
  const [start, setStart] = useState(event?.start || defaults.start || nowHM())
  const [end, setEnd] = useState(event?.end || defaults.end || '')
  // Sieste : mise au lit avant l'endormissement. Coucher : endormissement après la mise au lit. Vides si non notés.
  const [laid, setLaid] = useState(event?.laid || '')
  const [asleep, setAsleep] = useState(event?.asleep || '')
  const [ml, setMl] = useState(event?.ml ?? '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const span = kind === 'nap' || kind === 'night'
  const [field, setField] = useState('start')   // l'heure que la roue modifie
  const pickEnd = () => { if (!end) setEnd(nowHM()); setField('end') }
  const pickLaid = () => { if (!laid) setLaid(start); setField('laid') }
  const pickAsleep = () => { if (!asleep) setAsleep(start); setField('asleep') }
  const wheel = { start: [start, setStart], end: [end || start, setEnd], laid: [laid || start, setLaid], asleep: [asleep || start, setAsleep] }[field]
  const stepMl = (d) => setMl(v => Math.max(0, Math.min(400, (Number(v) || 0) + d)))

  async function save() {
    if (!start) { setErr("Indiquez l'heure"); return }
    setBusy(true); setErr('')
    const mlv = ml === '' ? null : Number(ml)
    try {
      // Le serveur garde l'endormissement dans start et la mise au lit à part
      const times = kind === 'nap' ? { start, laid: laid || null }
        : kind === 'bed' ? (asleep ? { start: asleep, laid: start } : { start, laid: null })
        : { start }
      if (event?.id) {
        const body = { ...times, day }
        if (span) body.end = end || null
        if (kind === 'feed') body.ml = mlv
        await api(`/events/${event.id}`, { method: 'PATCH', body })
      } else {
        await api('/events', { method: 'POST', body: { kind, day, ...times, end: span && end ? end : null, ml: kind === 'feed' ? mlv : null } })
      }
      onDone('Enregistré')
    } catch (e) {
      setErr(e.message); setBusy(false)
    }
  }

  async function remove() {
    try { await api(`/events/${event.id}`, { method: 'DELETE' }); onDone('Supprimé') } catch (e) { setErr(e.message) }
  }

  return (
    <Sheet title={title || L.title} onClose={onClose}
      action={<button type="button" className="link" style={{ fontWeight: 600 }} disabled={busy} onClick={save}>OK</button>}>
      {span || kind === 'bed' ? (
        // Plusieurs heures : on choisit laquelle la roue règle
        <div className={`when2${kind === 'nap' ? ' three' : ''}`} role="tablist">
          {kind === 'nap' && (
            <button type="button" role="tab" aria-selected={field === 'laid'} onClick={pickLaid}>
              <span>{L.laid}</span><b className="rd">{laid || '–'}</b>
            </button>
          )}
          <button type="button" role="tab" aria-selected={field === 'start'} onClick={() => setField('start')}>
            <span>{L.start}</span><b className="rd">{start}</b>
          </button>
          {span ? (
            <button type="button" role="tab" aria-selected={field === 'end'} onClick={pickEnd}>
              <span>{L.end}</span><b className="rd">{end || 'en cours'}</b>
            </button>
          ) : (
            <button type="button" role="tab" aria-selected={field === 'asleep'} onClick={pickAsleep}>
              <span>{L.asleep}</span><b className="rd">{asleep || '–'}</b>
            </button>
          )}
        </div>
      ) : <div className="when1">{L.start}</div>}
      <TimeWheel value={wheel[0]} onChange={wheel[1]} />
      {(field === 'laid' && laid) || (field === 'asleep' && asleep) ? (
        <div className="quick indigo">
          <button type="button" onClick={() => { field === 'laid' ? setLaid('') : setAsleep(''); setField('start') }}>Pas notée</button>
        </div>
      ) : null}
      {span && field === 'end' && end && (
        <div className="quick indigo">
          <button type="button" onClick={() => setEnd(nowHM())}>Maintenant</button>
          <button type="button" onClick={() => { setEnd(''); setField('start') }}>{kind === 'nap' ? 'Laisser en cours' : 'Pas encore'}</button>
        </div>
      )}
      {kind === 'feed' && (
        <>
          <div className="quick">
            {ML.map(v => <button key={v} type="button" aria-pressed={Number(ml) === v} onClick={() => setMl(v)}>{v} ml</button>)}
          </div>
          {/* Elle n'a pas tout bu : on part du biberon préparé et on retire 10 ml par touche */}
          <div className="field">Quantité prise
            <div className="ml-step">
              <button type="button" aria-label="10 ml de moins" onClick={() => stepMl(-10)}>−10</button>
              <label className="ml-val">
                <input type="number" id="ev-ml" inputMode="numeric" min="0" max="400" step="1" value={ml} onChange={e => setMl(e.target.value)} placeholder="Non noté" aria-label="Quantité prise en ml" />
                <span>ml</span>
              </label>
              <button type="button" aria-label="10 ml de plus" onClick={() => stepMl(10)}>+10</button>
            </div>
          </div>
        </>
      )}
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" disabled={busy} onClick={save}>Enregistrer</button>
      {event?.id && <button type="button" className="secondary" disabled={busy} onClick={remove}>Supprimer</button>}
    </Sheet>
  )
}

// Réveillée alors que l'endormissement n'avait pas été noté : vers quand s'est-elle endormie ?
export function AsleepSheet({ ask, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  const [h, m] = ask.laid.split(':').map(Number), [eh, em] = ask.end.split(':').map(Number)
  const max = ((eh * 60 + em) - (h * 60 + m) + 1440) % 1440
  const offs = [0, 5, 10, 15, 20, 30, 45].filter(n => n < max)
  async function run(body, msg) {
    setBusy(true)
    try {
      await (body ? api(`/events/${ask.id}`, { method: 'PATCH', body }) : api(`/events/${ask.id}`, { method: 'DELETE' }))
      onDone(msg)
    } catch { onClose() }
  }
  return (
    <Sheet title="Endormie vers quand ?" onClose={onClose}>
      <p className="sub2" style={{ margin: 0 }}>Au lit à {ask.laid}, réveillée à {ask.end}.</p>
      <div className="quick" style={{ gap: 10 }}>
        {offs.map(n => (
          <button key={n} type="button" disabled={busy} style={{ fontSize: 17, padding: '12px 18px' }}
            onClick={() => run({ start: addHM(ask.laid, n) }, `Endormie à ${addHM(ask.laid, n)}`)}>
            {n ? `${addHM(ask.laid, n)} · ${n} min` : 'Tout de suite'}
          </button>
        ))}
      </div>
      <button type="button" className="secondary blue" disabled={busy} onClick={() => run({ laid: null }, 'Endormissement non noté')}>Je ne sais pas</button>
      <button type="button" className="secondary" disabled={busy} onClick={() => run(null, 'Sieste retirée')}>Elle n'a pas dormi</button>
    </Sheet>
  )
}

// Après « Biberon » : quand il a commencé et la quantité (un choix ou la quantité exacte), enregistrés d'un seul bouton
const BACK = [0, 10, 15, 20]
export function FeedAmountSheet({ feed, onClose, onDone }) {
  const [ml, setMl] = useState('')
  const [busy, setBusy] = useState(false)
  const [back, setBack] = useState(0)
  const [custom, setCustom] = useState(false)
  const at = feed.at ? shiftStamp(feed.at, back) : null
  const time = at ? at.slice(11, 16) : feed.time
  const yesterday = at && at.slice(0, 10) !== feed.at.slice(0, 10)
  // Noté à la fin du biberon : on recule son heure au début, pour que le prochain soit bien annoncé
  async function moveBack(n) {
    const prev = back
    setBack(n)
    try { await api(`/events/${feed.id}`, { method: 'PATCH', body: { start: shiftStamp(feed.at, n) } }) } catch { setBack(prev) }
  }
  // Heure choisie sur les roues : toujours dans le passé, donc la veille si elle dépasse l'heure de la saisie
  function pickTime(hm) {
    const [h, m] = hm.split(':').map(Number), [bh, bm] = feed.at.slice(11, 16).split(':').map(Number)
    moveBack(((bh * 60 + bm - h * 60 - m) % 1440 + 1440) % 1440)
  }
  const v = ml === '' ? null : Number(ml)
  const ok = v !== null && Number.isInteger(v) && v > 0 && v <= 400
  async function pick(x) {
    setBusy(true)
    try { await api(`/events/${feed.id}`, { method: 'PATCH', body: { ml: x } }); onDone(`Biberon de ${time} : ${x} ml`) } catch { onClose() }
  }
  return (
    <Sheet title={`Biberon de ${time}${yesterday ? ' (hier)' : ''}`} onClose={onClose}>
      {feed.at && <>
        <p className="sub2" style={{ margin: 0 }}>Commencé</p>
        <div className="quick fit">
          {BACK.map(n => <button key={n} type="button" aria-pressed={!custom && back === n} onClick={() => { setCustom(false); moveBack(n) }}>{n ? `il y a ${n} min` : "à l'instant"}</button>)}
        </div>
        <div className="quick fit">
          <button type="button" aria-pressed={custom || !BACK.includes(back)} onClick={() => setCustom(c => !c)}>{custom || !BACK.includes(back) ? `Commencé à ${time}` : 'Autre heure'}</button>
        </div>
        {custom && <TimeWheel value={time} onChange={pickTime} />}
      </>}
      <p className="sub2" style={{ margin: 0 }}>Quelle quantité ? Vous pourrez aussi la noter plus tard.</p>
      <div className="quick" style={{ gap: 10 }}>
        {ML.map(x => <button key={x} type="button" disabled={busy} aria-pressed={v === x} style={{ fontSize: 17, padding: '12px 18px' }} onClick={() => setMl(String(x))}>{x} ml</button>)}
      </div>
      <div className="field">Quantité exacte
        <label className="ml-val">
          <input type="number" id="feed-ml" inputMode="numeric" min="1" max="400" step="1" value={ml} onChange={e => setMl(e.target.value)} placeholder="ex. 170" aria-label="Quantité prise en ml" />
          <span>ml</span>
        </label>
      </div>
      {ok && <button type="button" className="primary" disabled={busy} onClick={() => pick(v)}>Enregistrer {v} ml</button>}
      <button type="button" className="secondary blue" onClick={() => back ? onDone(`Biberon de ${time}`) : onClose()}>Plus tard</button>
    </Sheet>
  )
}

// Après « Levée » : noté en retard, on recule l'heure du lever (raccourcis ou roues), enregistrée à chaque choix
const WAKE_BACK = [0, 15, 30, 60]
export function WakeTimeSheet({ wake, onClose, onDone }) {
  const [back, setBack] = useState(0)
  const [custom, setCustom] = useState(false)
  const [err, setErr] = useState('')
  const time = shiftStamp(wake.at, back).slice(11, 16)
  const [bh, bm] = wake.at.slice(11, 16).split(':').map(Number)
  async function moveBack(n) {
    const prev = back
    setBack(n); setErr('')
    try { await api(`/events/${wake.id}`, { method: 'PATCH', body: { start: shiftStamp(wake.at, n) } }) } catch (e) { setBack(prev); setErr(e.message) }
  }
  // Le lever est du jour même : une heure plus tard que la saisie n'est pas encore passée
  function pickTime(hm) {
    const [h, m] = hm.split(':').map(Number), n = bh * 60 + bm - h * 60 - m
    if (n < 0) { setErr(`Choisissez une heure avant ${wake.at.slice(11, 16)}`); return }
    moveBack(n)
  }
  const other = custom || !WAKE_BACK.includes(back)
  return (
    <Sheet title={`Levée à ${time}`} onClose={() => onDone(`Levée à ${time}`)}>
      <p className="sub2" style={{ margin: 0 }}>Notée en retard ? Indiquez quand elle s'est réveillée.</p>
      <div className="quick fit">
        {WAKE_BACK.map(n => <button key={n} type="button" aria-pressed={!custom && back === n} onClick={() => { setCustom(false); moveBack(n) }}>{n ? `il y a ${n < 60 ? `${n} min` : '1 h'}` : "à l'instant"}</button>)}
      </div>
      <div className="quick fit">
        <button type="button" aria-pressed={other} onClick={() => setCustom(c => !c)}>{other ? `Réveillée à ${time}` : 'Autre heure'}</button>
      </div>
      {custom && <TimeWheel value={time} onChange={pickTime} />}
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" onClick={() => onDone(`Levée à ${time}`)}>C'est noté</button>
    </Sheet>
  )
}
