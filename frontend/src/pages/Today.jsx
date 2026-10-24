import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import Dial from '../components/Dial'
import EventSheet, { ML } from '../components/EventSheet'
import { Bed, Bottle, Check, Chevron, Eye, Moon, Pencil, Plus, Sun } from '../components/Icons'
import { DaySheet } from './Journal'
import { api } from '../api'

const ACT_ICON = { nap_start: Moon, nap_end: Sun, wake: Sun, bed: Bed, night_start: Eye, night_end: Moon }
const HEAD_ICON = { moon: Moon, eye: Eye }
const INI = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const DAY_NAMES = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']

const p2 = (n) => String(n).padStart(2, '0')
const toIso = (x) => `${x.getFullYear()}-${p2(x.getMonth() + 1)}-${p2(x.getDate())}`
const fromIso = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
// Les 7 jours (lundi à dimanche) de la semaine qui contient iso, décalée de n semaines
function weekOf(iso, n) {
  const d = fromIso(iso), monday = new Date(d.getFullYear(), d.getMonth(), d.getDate() - ((d.getDay() + 6) % 7) + 7 * n)
  return Array.from({ length: 7 }, (_, i) => toIso(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i)))
}

export default function Today({ today, onAct, open, close, refresh, notify, busy, status, doneAt, version }) {
  const t = today
  const [sel, setSel] = useState(null)        // jour passé affiché, null = la journée en cours
  const [past, setPast] = useState(null)
  const [showDay, setShowDay] = useState(false)
  const night = t.mode === 'night'
  const viewing = sel && sel !== t.date

  const loadPast = () => sel && api(`/days/${sel}/view`).then(setPast).catch(e => notify(e.message))
  useEffect(() => { setPast(null); if (viewing) loadPast() }, [sel, version])  // eslint-disable-line react-hooks/exhaustive-deps

  const done = (msg) => { close(); refresh(); if (viewing) loadPast(); notify(msg) }
  const edit = (day) => (props) => open(<EventSheet day={day} {...props} onClose={close} onDone={done} />)
  const ageShort = (t.child.age_text || '').split(' · ')[0].split(' ').slice(0, 2).join(' ')

  return (
    <div className="wrap">
      <header className="top">
        <h1 className="rd">{viewing ? (past?.label || '') : night ? 'Cette nuit' : "Aujourd'hui"}</h1>
        <div className="top-sub">{t.child.name}{ageShort && ` · ${ageShort}`}</div>
        {status}
      </header>

      {!night && <WeekStrip current={t.date} sel={sel || t.date} pick={(iso) => setSel(iso === t.date ? null : iso)} />}

      {viewing
        ? <PastDay past={past} edit={edit(sel)} openDay={() => open(<DaySheet date={sel} title={past?.label || ''} onClose={() => { close(); loadPast(); refresh() }} open={open} notify={notify} />)} />
        : <CurrentDay t={t} night={night} onAct={onAct} busy={busy} doneAt={doneAt} edit={edit(t.date)}
            showDay={showDay} setShowDay={setShowDay} refresh={refresh} notify={notify} />}
    </div>
  )
}

// Bande de la semaine : elle suit le doigt et se cale sur la semaine voisine, comme une page iOS.
// Les 26 dernières semaines sont là, côte à côte ; on arrive sur la semaine en cours, la plus à droite.
const WEEKS = 26
function WeekStrip({ current, sel, pick }) {
  const ref = useRef(null)
  const weeks = useMemo(() => Array.from({ length: WEEKS }, (_, i) => weekOf(current, i - WEEKS + 1)), [current])
  const [shown, setShown] = useState(WEEKS - 1)
  useLayoutEffect(() => { const el = ref.current; el.scrollLeft = el.scrollWidth }, [current])
  // Retour à aujourd'hui (ou jour choisi ailleurs) : la bande glisse jusqu'à sa semaine
  useEffect(() => {
    const el = ref.current, i = weeks.findIndex(w => w.includes(sel))
    if (i >= 0 && Math.round(el.scrollLeft / el.clientWidth) !== i) el.scrollTo({ left: i * el.clientWidth, behavior: 'smooth' })
  }, [sel, weeks])
  const onScroll = () => { const el = ref.current; setShown(Math.round(el.scrollLeft / el.clientWidth)) }
  const first = fromIso(weeks[shown][0])
  const month = first.toLocaleDateString('fr-FR', { month: 'long', year: shown < WEEKS - 5 ? 'numeric' : undefined })
  return (
    <div className="weeks">
      <div className={`weeks-m${shown === WEEKS - 1 ? ' here' : ''}`} aria-live="polite">{month}</div>
      <div className="weeks-scroll" ref={ref} onScroll={onScroll} aria-label="Semaines, faites glisser pour remonter le temps">
        {weeks.map((days, w) => (
          <div className="week" key={days[0]}>
            {days.map((iso, i) => {
              const future = iso > current
              return (
                <button key={iso} type="button" disabled={future} aria-pressed={iso === sel}
                  aria-label={`${DAY_NAMES[i]} ${Number(iso.slice(8))}`} tabIndex={w === shown ? 0 : -1}
                  className={`wd${iso === current ? ' today' : ''}`} onClick={() => pick(iso)}>
                  <span className="wd-i">{INI[i]}</span>
                  <span className="wd-n rd">{Number(iso.slice(8))}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}

function CurrentDay({ t, night, onAct, busy, doneAt, edit, showDay, setShowDay, refresh, notify }) {
  const H = t.headline
  const HeadIcon = HEAD_ICON[H.icon]
  // Rien de noté aujourd'hui : un mot d'accueil plutôt qu'un cadran rempli de prévisions par défaut
  const started = night || t.feeds.length > 0 || t.timeline.some(x => (x.type === 'wake' && x.real) || (x.type === 'nap' && x.start_real))
  const wakes = t.timeline.find(x => x.type === 'bed')?.night || []
  const fresh = doneAt && Date.now() - doneAt < 1500

  async function setMl(v) {
    try { await api(`/events/${t.feed.ask_id}`, { method: 'PATCH', body: { ml: v } }); refresh() } catch (e) { notify(e.message) }
  }

  return (
    <>
      {night ? (
        // La nuit, l'essentiel seulement : depuis quand elle dort, ses réveils
        <section className="night-hero" aria-live="polite">
          <div className="cap">{HeadIcon && <HeadIcon />}{H.cap}</div>
          <div className="big rd">{H.big}</div>
          <div className="sub">{H.sub}</div>
        </section>
      ) : !started ? (
        <section className="hello">
          <span className="hello-i"><Sun /></span>
          <h2 className="rd">Sa journée n'a pas commencé</h2>
          <p>{t.actions.some(a => a.act === 'wake')
            ? 'Notez son lever avec le bouton ci-dessous : ses siestes et son coucher seront prévus à partir de là.'
            : "Rien n'est encore noté aujourd'hui. Utilisez les boutons ci-dessous, ou corrigez après coup."}</p>
          <p className="hello-s">Au début, les prévisions suivent les repères de son âge. Elles s'adaptent ensuite à elle, au fil des journées notées.</p>
        </section>
      ) : (
        <section className="dial-wrap" aria-live="polite">
          <Dial dial={t.dial} />
          <div className="center">
            <div className="cap">{HeadIcon && <HeadIcon />}{H.cap}</div>
            <div className={`big rd${H.big.length > 7 ? ' long' : ''}`}>{H.big}</div>
            <div className="sub">{H.sub}</div>
          </div>
        </section>
      )}

      {/* La clé change avec les boutons proposés : le nouvel état arrive en fondu */}
      <div className="actions" key={t.actions.map(a => a.act).join()}>
        {t.actions.map((a, i) => {
          const I = ACT_ICON[a.act]
          return (
            <button key={a.act} type="button" className={`action ${a.style}`} disabled={busy} onClick={() => onAct(a.act)}>
              {i === 0 && fresh ? <span className="tick"><Check /></span> : I && <I />}
              <span className="action-t rd">{a.label}{a.time && <small>à {a.time}</small>}</span>
            </button>
          )
        })}
      </div>

      <div className="feedline">
        <span className="feedline-i"><Bottle /></span>
        <div className="grow">
          {t.feed.last
            ? <><b>Biberon à {t.feed.last.time}{t.feed.last.ml ? ` · ${t.feed.last.ml} ml` : ''}</b><span>prochain vers {t.feed.last.next}</span></>
            : <><b>Aucun biberon noté</b><span>aujourd'hui</span></>}
        </div>
        <button type="button" className="feedbtn" disabled={busy} onClick={() => onAct('feed')}><Plus />Biberon</button>
      </div>
      {t.feed.ask_id && (
        <div className="quick fit" aria-label="Quantité du dernier biberon">
          {ML.slice(0, 5).map(v => <button key={v} type="button" onClick={() => setMl(v)}>{v} ml</button>)}
        </div>
      )}

      {night && wakes.length > 0 && (
        <section>
          <h2 className="section-h">Réveils de la nuit</h2>
          <div className="tl">
            {wakes.map((w, j) => (
              <Row key={w.id} time={w.start} dot="eye" small title={`Réveil ${j + 1}`}
                right={w.end ? w.dur : 'en cours'}
                onClick={() => edit({ kind: 'night', title: `Réveil nocturne ${j + 1}`, event: { id: w.id, start: w.start, end: w.end || '' } })} />
            ))}
          </div>
        </section>
      )}

      {night && !showDay ? (
        <button type="button" className="addrow show-day" onClick={() => setShowDay(true)}>Voir la journée<Chevron /></button>
      ) : started && (
        <section>
          <h2 className="section-h">{night ? 'Journée et nuit' : 'Journée'}</h2>
          <Timeline items={t.timeline} edit={edit} live />
          <p className="foot">Touchez une ligne pour corriger une heure. Les signes de fatigue priment toujours sur l'horloge.</p>
        </section>
      )}
    </>
  )
}

function PastDay({ past, edit, openDay }) {
  if (!past) return <div className="dial-wrap"><div className="empty">Chargement...</div></div>
  const s = past.summary
  return (
    <>
      <section className="dial-wrap past">
        <Dial dial={past.dial} />
        <div className="center">
          <div className="cap"><Moon />Siestes</div>
          <div className="big rd">{s ? s.day_sleep : '0 min'}</div>
          <div className="sub">{s?.night ? `puis nuit de ${s.night.sleep}` : 'nuit non notée'}</div>
        </div>
      </section>
      <div className="actions">
        <button type="button" className="action ghost wide" onClick={openDay}><Pencil /><span className="action-t rd">Corriger cette journée</span></button>
      </div>
      {s && <p className="past-line">{[s.naps === 1 ? '1 sieste' : `${s.naps} siestes`, s.wake && `lever ${s.wake}`, s.bed && `couchée ${s.bed}`, s.feeds && `${s.feeds} biberon${s.feeds > 1 ? 's' : ''}${s.ml ? `, ${s.ml}\u00a0ml` : ''}`].filter(Boolean).join(' · ')}</p>}
      <section>
        <h2 className="section-h">Journée</h2>
        <Timeline items={past.timeline} edit={edit} />
      </section>
    </>
  )
}

// Frise : une ligne par fait, l'heure à gauche, la durée à droite, l'éveil entre deux lignes
function Timeline({ items, edit, live }) {
  const bed = items.find(x => x.type === 'bed')
  return (
    <div className="tl">
      {items.map((x, i) => {
        if (x.type === 'gap') return <div key={i} className="tl-gap">{x.text}</div>
        if (x.type === 'wake') return (
          <Row key={i} time={x.time} dot="sun" plan={!x.real} title={<>Lever{!x.real && <span className="badge todo">à noter</span>}</>}
            onClick={() => edit({ kind: 'wake', event: x.real ? { id: x.id, start: x.time } : null, defaults: { start: x.time } })} />
        )
        if (x.type === 'nap') {
          const real = x.start_real
          return (
            <Row key={i} time={x.start} dot="moon" plan={!real} now={x.now}
              title={<>{x.label}{real && !x.end_real && <span className="badge">en cours</span>}{!real && x.now && <span className="badge">maintenant</span>}</>}
              right={real && !x.end_real ? `réveil ~${x.end}` : x.dur}
              onClick={() => edit({ kind: 'nap', title: x.label, event: real ? { id: x.id, start: x.start, end: x.end_real ? x.end : '' } : null, defaults: { start: x.start } })} />
          )
        }
        if (x.type === 'bed') return (
          <div key={i}>
            <Row time={x.time} dot="bed" plan={!x.real} now={x.now}
              title={<>Coucher{!x.real && x.now && <span className="badge">ensuite</span>}</>}
              onClick={() => edit({ kind: 'bed', event: x.real ? { id: x.id, start: x.time } : null, defaults: { start: x.time } })} />
            {(x.night || []).map((w, j) => (
              <Row key={w.id} time={w.start} dot="eye" small title={`Réveil ${j + 1}`} right={w.end ? w.dur : 'en cours'}
                onClick={() => edit({ kind: 'night', title: `Réveil nocturne ${j + 1}`, event: { id: w.id, start: w.start, end: w.end || '' } })} />
            ))}
            {x.real && <button type="button" className="addrow tl-add" onClick={() => edit({ kind: 'night', event: null, defaults: {} })}><Plus />Réveil nocturne oublié</button>}
            {x.late && <div className="warn">Coucher tardif : avancez-le si elle montre de la fatigue.</div>}
          </div>
        )
        return null
      })}
      {(!live || !bed?.real) && (
        <button type="button" className="addrow tl-add" onClick={() => edit({ kind: 'nap', title: 'Sieste oubliée', event: null, defaults: { start: '' } })}>
          <Plus />Sieste oubliée
        </button>
      )}
    </div>
  )
}

function Row({ time, dot, title, right, plan, now, small, onClick }) {
  return (
    <button type="button" className={`tl-row${plan ? ' plan' : ''}${now ? ' now' : ''}${small ? ' small' : ''}`} onClick={onClick}>
      <span className="tl-time rd">{plan && time ? <small>vers</small> : null}{time}</span>
      <span className={`tl-dot ${dot}`} />
      <span className="grow ttl">{title}</span>
      {right && <span className="tl-right">{right}</span>}
    </button>
  )
}
