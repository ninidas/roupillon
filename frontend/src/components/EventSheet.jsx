import { useState } from 'react'
import { api } from '../api'
import Sheet, { Confirm } from './Sheet'
import TimeWheel from './TimeWheel'

const LABELS = {
  nap: { title: 'Sieste', start: 'Endormie à', end: 'Réveillée à' },
  night: { title: 'Réveil nocturne', start: 'Réveillée à', end: 'Rendormie à' },
  wake: { title: 'Lever', start: 'Levée à' },
  bed: { title: 'Coucher', start: 'Couchée à' },
  feed: { title: 'Biberon', start: 'Heure' },
}
export const ML = [60, 90, 120, 150, 180, 210]

function nowHM() {
  const d = new Date()
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

// Saisie ou correction d'un fait de la journée. event : {id, start, end, ml} existant, ou null pour un ajout.
export default function EventSheet({ kind, day, event, title, defaults = {}, onClose, onDone }) {
  const L = LABELS[kind]
  const [start, setStart] = useState(event?.start || defaults.start || nowHM())
  const [end, setEnd] = useState(event?.end || defaults.end || '')
  const [ml, setMl] = useState(event?.ml ?? '')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const span = kind === 'nap' || kind === 'night'
  const [field, setField] = useState('start')   // l'heure que la roue modifie
  const pickEnd = () => { if (!end) setEnd(nowHM()); setField('end') }

  async function save() {
    if (!start) { setErr("Indiquez l'heure"); return }
    setBusy(true); setErr('')
    const mlv = ml === '' ? null : Number(ml)
    try {
      if (event?.id) {
        const body = { start, day }
        if (span) body.end = end || null
        if (kind === 'feed') body.ml = mlv
        await api(`/events/${event.id}`, { method: 'PATCH', body })
      } else {
        await api('/events', { method: 'POST', body: { kind, day, start, end: span && end ? end : null, ml: kind === 'feed' ? mlv : null } })
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
      {span ? (
        // Deux heures : on choisit laquelle la roue règle
        <div className="when2" role="tablist">
          <button type="button" role="tab" aria-selected={field === 'start'} onClick={() => setField('start')}>
            <span>{L.start}</span><b className="rd">{start}</b>
          </button>
          <button type="button" role="tab" aria-selected={field === 'end'} onClick={pickEnd}>
            <span>{L.end}</span><b className="rd">{end || 'en cours'}</b>
          </button>
        </div>
      ) : <div className="when1">{L.start}</div>}
      <TimeWheel value={field === 'end' && end ? end : start} onChange={field === 'end' ? setEnd : setStart} />
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
          <label className="field">Autre quantité (ml)
            <input type="number" id="ev-ml" inputMode="numeric" min="0" max="400" step="5" value={ml} onChange={e => setMl(e.target.value)} placeholder="Non noté" />
          </label>
        </>
      )}
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" disabled={busy} onClick={save}>Enregistrer</button>
      {event?.id && <Confirm label="Supprimer" confirm="Toucher encore pour supprimer" onConfirm={remove} />}
    </Sheet>
  )
}

// Après « Biberon » : la quantité en un geste
export function FeedAmountSheet({ feed, onClose, onDone }) {
  async function pick(v) {
    try { await api(`/events/${feed.id}`, { method: 'PATCH', body: { ml: v } }); onDone(`Biberon de ${feed.time} : ${v} ml`) } catch { onClose() }
  }
  return (
    <Sheet title={`Biberon de ${feed.time}`} onClose={onClose}>
      <p className="sub2" style={{ margin: 0 }}>Quelle quantité ? Vous pourrez aussi la noter plus tard.</p>
      <div className="quick" style={{ gap: 10 }}>
        {ML.map(v => <button key={v} type="button" style={{ fontSize: 17, padding: '12px 18px' }} onClick={() => pick(v)}>{v} ml</button>)}
      </div>
      <button type="button" className="secondary blue" onClick={onClose}>Plus tard</button>
    </Sheet>
  )
}
