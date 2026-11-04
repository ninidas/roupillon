import { useCallback, useEffect, useRef, useState } from 'react'
import { act, api, ApiError, cachedToday, flushQueue, getToken, loadToday, ls, Offline, pending, setToken, setUnauthorizedHandler } from './api'
import { AsleepSheet, FeedAmountSheet, shiftStamp } from './components/EventSheet'
import { TabJournal, TabSettings, TabToday } from './components/Icons'
import Journal from './pages/Journal'
import { Login, Setup } from './pages/Login'
import Settings from './pages/Settings'
import Today from './pages/Today'

const TABS = [
  { id: 'today', label: "Aujourd'hui", Icon: TabToday },
  { id: 'journal', label: 'Journal', Icon: TabJournal },
  { id: 'settings', label: 'Réglages', Icon: TabSettings },
]

export default function App() {
  const [phase, setPhase] = useState('boot')
  const [me, setMeState] = useState(ls.get('rp_me'))
  const [today, setToday] = useState(cachedToday())
  const [tab, setTabState] = useState(ls.get('rp_tab', 'today'))
  const [sheet, setSheet] = useState(null)
  const [toast, setToast] = useState(null)
  const [online, setOnline] = useState(true)
  const [queued, setQueued] = useState(pending())
  const [busy, setBusy] = useState(false)
  const [version, setVersion] = useState(0)
  const [doneAt, setDoneAt] = useState(0)
  const [theme, setThemeState] = useState(ls.get('rp_theme', 'bleu'))
  const toastTimer = useRef()

  const setMe = (u) => { setMeState(u); ls.set('rp_me', u) }
  const setTheme = (v) => { setThemeState(v); ls.set('rp_theme', v) }
  const setTab = (t) => { setTabState(t); ls.set('rp_tab', t); window.scrollTo(0, 0) }
  const close = useCallback(() => setSheet(null), [])
  const notify = useCallback((msg, actions = []) => {
    clearTimeout(toastTimer.current)
    setToast({ id: Date.now(), msg, actions })
    toastTimer.current = setTimeout(() => setToast(null), actions.length ? 8000 : 4000)
  }, [])

  const refresh = useCallback(async () => {
    try {
      if (pending()) { await flushQueue(); setQueued(pending()) }
      setToday(await loadToday())
      setOnline(true)
    } catch (e) {
      if (e instanceof Offline) setOnline(false)
    }
  }, [])

  // Démarrage : installation, connexion, ou directement l'app
  useEffect(() => {
    setUnauthorizedHandler(() => { setToken(null); setPhase('login') })
    if (!getToken()) {
      api('/setup', { auth: false }).then(r => setPhase(r.needs_setup ? 'setup' : 'login')).catch(() => setPhase('login'))
      return
    }
    api('/me').then(u => { setMe(u); setPhase('app') }).catch(e => {
      if (e instanceof Offline && ls.get('rp_me')) { setOnline(false); setPhase('app') }
    })
  }, [])

  // Mise à jour chaque demi-minute, et dès que l'app revient au premier plan
  useEffect(() => {
    if (phase !== 'app') return
    refresh()
    const tick = () => document.visibilityState === 'visible' && refresh()
    const id = setInterval(tick, 30000)
    document.addEventListener('visibilitychange', tick)
    window.addEventListener('online', tick)
    return () => { clearInterval(id); document.removeEventListener('visibilitychange', tick); window.removeEventListener('online', tick) }
  }, [phase, refresh])

  // Ambiance choisie sur ce téléphone, et la nuit le mode tamisé ; la barre d'état suit la couleur du fond
  useEffect(() => {
    const root = document.documentElement
    if (theme === 'bleu') root.dataset.theme = 'bleu'
    else delete root.dataset.theme
    if (today?.mode === 'night') root.dataset.night = '1'
    else delete root.dataset.night
    const bg = getComputedStyle(root).getPropertyValue('--bg').trim()
    document.querySelectorAll('meta[name="theme-color"]').forEach(m => m.setAttribute('content', bg))
  }, [today?.mode, theme])

  async function undo(u) {
    setToast(null)
    try {
      if (u.op === 'delete') await api(`/events/${u.id}`, { method: 'DELETE' })
      else await api(`/events/${u.id}`, { method: 'PATCH', body: u.body })
      await refresh(); setVersion(v => v + 1); notify('Annulé')
    } catch (e) { notify(e.message) }
  }

  async function shift(r, n) {
    setToast(null)
    const at = shiftStamp(r.at, n)
    try {
      await api(`/events/${r.event_id}`, { method: 'PATCH', body: { [r.field]: at } })
      await refresh(); notify(`Corrigé : ${at.slice(11)}`)
    } catch (e) { notify(e.message) }
  }

  async function onAct(a) {
    setBusy(true)
    try {
      const r = await act(a)
      if (r.offline) { setOnline(false); setQueued(pending()); notify(r.message); return }
      setToday(r.today); setOnline(true); setVersion(v => v + 1); setDoneAt(Date.now())
      const acts = [{ label: 'Annuler', cls: 'undo', run: () => undo(r.undo) }]
      if (a !== 'feed') [5, 10, 15].forEach(n => acts.push({ label: `${n} min`, early: true, run: () => shift(r, n) }))
      notify(r.message, acts)
      if (a === 'feed') {
        setSheet(<FeedAmountSheet feed={{ id: r.event_id, time: r.at.slice(11, 16), at: r.at }} onClose={close}
          onDone={(msg) => { close(); refresh(); notify(msg) }} />)
      }
      if (r.ask_asleep) {
        setSheet(<AsleepSheet ask={r.ask_asleep} onClose={close} onDone={(msg) => { close(); refresh(); notify(msg) }} />)
      }
    } catch (e) {
      notify(e instanceof ApiError ? e.message : "Rien n'a été noté, réessayez")
      refresh()
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    setToken(null); ls.set('rp_me', null); ls.set('rp_today', null); setToday(null); setPhase('login')
  }

  const onIn = (u) => { setMe(u); setTab('today'); setPhase('app') }
  if (phase === 'boot') return null
  if (phase === 'setup') return <Setup onDone={onIn} />
  if (phase === 'login') return <Login onDone={onIn} />

  const status = !online
    ? <span className="pill warn">Hors ligne{queued ? ` · ${queued} en attente` : ''}</span>
    : queued ? <span className="pill">{queued} en attente</span> : null
  const common = { open: setSheet, close, notify, status, refresh }

  return (
    <>
      {tab === 'today' && (today
        ? <Today today={today} onAct={onAct} busy={busy} doneAt={doneAt} version={version} {...common} />
        : <div className="wrap"><div className="empty">Chargement...</div></div>)}
      {tab === 'journal' && <Journal version={version} {...common} />}
      {tab === 'settings' && me && <Settings me={me} setMe={setMe} onLogout={logout} theme={theme} setTheme={setTheme} {...common} />}

      <nav className="tabbar" aria-label="Onglets">
        {TABS.map(({ id, label, Icon }) => (
          <button key={id} type="button" aria-current={tab === id ? 'page' : undefined} onClick={() => setTab(id)}>
            <Icon />{label}
          </button>
        ))}
      </nav>

      {sheet}
      {toast && <Toast toast={toast} top={!!sheet} key={toast.id} onClose={() => { clearTimeout(toastTimer.current); setToast(null) }} />}
    </>
  )
}

// Bandeau de confirmation : il part seul, ou tout de suite d'un toucher sur le texte ou d'un glissement
function Toast({ toast, top, onClose }) {
  const from = useRef(null)
  const [dy, setDy] = useState(0)
  const down = (e) => { from.current = e.clientY }
  const move = (e) => { if (from.current !== null) setDy(e.clientY - from.current) }
  const up = () => {
    if (from.current === null) return
    from.current = null
    if (Math.abs(dy) > 30) onClose(); else setDy(0)
  }
  return (
    <div className={`toast${top ? ' top' : ''}`} role="status"
      style={dy ? { transform: `translate(-50%, ${dy}px)`, opacity: Math.max(0.2, 1 - Math.abs(dy) / 120), animation: 'none' } : undefined}
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={up}>
      <div className="toast-row">
        <div className="toast-msg" onClick={onClose}>{toast.msg}</div>
        {toast.actions.filter(x => !x.early).map(x => <button key={x.label} type="button" className={x.cls} onClick={x.run}>{x.label}</button>)}
      </div>
      {toast.actions.some(x => x.early) && (
        <div className="toast-acts">
          <span>C'était il y a</span>
          {toast.actions.filter(x => x.early).map(x => <button key={x.label} type="button" onClick={x.run}>{x.label}</button>)}
        </div>
      )}
    </div>
  )
}
