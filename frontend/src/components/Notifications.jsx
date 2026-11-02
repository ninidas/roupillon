import { useEffect, useState } from 'react'
import { api } from '../api'
import { Confirm } from './Sheet'
import { Bell, Chevron } from './Icons'

// Clé publique du serveur (base64url) au format attendu par le navigateur
function keyBytes(s) {
  const b = atob((s + '='.repeat((4 - s.length % 4) % 4)).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(b, c => c.charCodeAt(0))
}

const supported = typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
const ios = typeof navigator !== 'undefined' && /iPhone|iPad|iPod/.test(navigator.userAgent)

const KINDS = [
  { id: 'nap', label: 'Prochaine sieste' },
  { id: 'feed', label: 'Prochain biberon' },
  { id: 'bed', label: 'Coucher' },
]

export default function Notifications({ notify }) {
  const [p, setP] = useState(null)       // réglages et clé, côté serveur
  const [sub, setSub] = useState(null)   // abonnement de ce téléphone
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api('/push').then(setP).catch(e => notify(e.message))
    if (!supported) return
    navigator.serviceWorker.ready.then(r => r.pushManager.getSubscription()).then(s => {
      setSub(s)
      // Le serveur a pu l'oublier (téléphone restauré, envoi refusé) : on le lui redonne
      if (s) api('/push/subscribe', { method: 'POST', body: s.toJSON() }).then(setP).catch(() => {})
    }).catch(() => {})
  }, [notify])

  async function enable() {
    setBusy(true)
    try {
      const perm = await Notification.requestPermission()
      if (perm !== 'granted') { notify('Notifications refusées : autorisez-les dans les réglages du téléphone'); return }
      const reg = await navigator.serviceWorker.ready
      const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(p.key) })
      setP(await api('/push/subscribe', { method: 'POST', body: s.toJSON() }))
      setSub(s)
      notify('Notifications activées sur ce téléphone')
    } catch (e) {
      notify(e.message || 'Activation impossible')
    } finally {
      setBusy(false)
    }
  }

  async function disable() {
    const endpoint = sub.endpoint
    try { await sub.unsubscribe() } catch { /* déjà désabonné */ }
    setSub(null)
    try { setP(await api('/push/unsubscribe', { method: 'POST', body: { endpoint } })) } catch (e) { notify(e.message) }
    notify('Notifications coupées sur ce téléphone')
  }

  async function test() {
    try { await api('/push/test', { method: 'POST' }); notify('Essai envoyé') } catch (e) { notify(e.message) }
  }

  async function put(body) {
    try { setP(await api('/push/prefs', { method: 'PUT', body })) } catch (e) { notify(e.message) }
  }

  return (
    <section>
      <h2 className="section-h">Notifications</h2>
      <div className="group">
        {!supported ? (
          <div className="cell ic">
            <span className="icon i-bell"><Bell /></span>
            <span className="grow sub2" style={{ marginTop: 0 }}>
              {ios ? <>Ouvrez Roupillon depuis son icône sur l'écran d'accueil, puis revenez ici. Pas encore d'icône : dans Safari, <b>Partager</b> puis <b>Sur l'écran d'accueil</b>.</>
                : 'Ce navigateur ne peut pas recevoir de notifications.'}
            </span>
          </div>
        ) : sub ? (
          <>
            <div className="cell ic">
              <span className="icon i-bell"><Bell /></span>
              <span className="grow"><span className="ttl">Activées sur ce téléphone</span>
                {p && p.devices > 1 && <span className="sub2" style={{ display: 'block' }}>{p.devices} appareils pour votre compte</span>}</span>
            </div>
            <button type="button" className="cell" onClick={test}><span className="grow ttl">Envoyer un essai</span><Chevron /></button>
          </>
        ) : (
          <button type="button" className="cell ic" onClick={enable} disabled={busy || !p}>
            <span className="icon i-bell"><Bell /></span>
            <span className="grow"><span className="ttl">Activer sur ce téléphone</span>
              <span className="sub2" style={{ display: 'block' }}>Un rappel avant la sieste et le biberon</span></span>
            <Chevron />
          </button>
        )}
        {p && KINDS.map(k => (
          <div className="cell" key={k.id}>
            <span className="grow ttl">{k.label}</span>
            <div className="seg" role="group" aria-label={k.label}>
              <button type="button" aria-pressed={p.prefs[k.id]} onClick={() => put({ [k.id]: true })}>Oui</button>
              <button type="button" aria-pressed={!p.prefs[k.id]} onClick={() => put({ [k.id]: false })}>Non</button>
            </div>
          </div>
        ))}
        {p && (
          <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
            <span className="ttl">Prévenir avant</span>
            <div className="seg-wrap"><div className="seg" role="group" aria-label="Prévenir avant">
              {p.leads.map(n => (
                <button key={n} type="button" aria-pressed={p.prefs.lead === n} onClick={() => put({ lead: n })}>{n} min</button>
              ))}
            </div></div>
          </div>
        )}
        {sub && <div className="cell"><Confirm className="link danger" label="Couper sur ce téléphone" confirm="Toucher encore pour couper" onConfirm={disable} /></div>}
      </div>
      <p className="foot">Réglages de votre compte, sur tous vos appareils. Rien la nuit ni pendant une sieste ; les siestes sont annoncées une fois le lever noté. Les heures restent des estimations.</p>
    </section>
  )
}
