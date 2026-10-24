// Appels au serveur. Hors connexion, les gestes (dort, réveillée, biberon...) sont gardés sur le
// téléphone avec leur heure réelle, puis envoyés dès que le réseau revient.
const TOKEN = 'rp_token'
const QUEUE = 'rp_queue'
const CACHE = 'rp_today'

const ls = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v) } catch { return d } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)) } catch { /* stockage indisponible */ } },
}
export { ls }

export const getToken = () => ls.get(TOKEN)
export const setToken = (t) => ls.set(TOKEN, t)

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}
export class Offline extends Error {}

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

export async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (auth && token) headers.Authorization = `Bearer ${token}`
  let res
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  } catch {
    throw new Offline('Pas de réseau')
  }
  if (res.status === 401 && auth) onUnauthorized()
  let data = null
  try { data = await res.json() } catch { /* réponse vide */ }
  if (!res.ok) {
    const d = data?.detail
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? 'Valeur refusée, vérifiez la saisie' : 'Le serveur ne répond pas comme prévu'
    throw new ApiError(res.status, msg)
  }
  return data
}

// Heure locale du téléphone au format du serveur
export function stampNow(offsetMin = 0) {
  const d = new Date(Date.now() - offsetMin * 60000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}

export const cachedToday = () => ls.get(CACHE)

export async function loadToday() {
  const t = await api('/today')
  ls.set(CACHE, t)
  return t
}

export const pending = () => ls.get(QUEUE, []).length

export async function act(act, extra = {}) {
  const body = { act, at: stampNow(), ...extra }
  try {
    const r = await api('/actions', { method: 'POST', body })
    ls.set(CACHE, r.today)
    return r
  } catch (e) {
    if (!(e instanceof Offline)) throw e
    ls.set(QUEUE, [...ls.get(QUEUE, []), body])
    return { offline: true, message: 'Pas de réseau : noté sur le téléphone, envoi dès le retour du réseau' }
  }
}

let flushing = false
export async function flushQueue() {
  if (flushing) return 0
  flushing = true
  let sent = 0
  try {
    let q = ls.get(QUEUE, [])
    while (q.length) {
      try {
        await api('/actions', { method: 'POST', body: q[0] })
      } catch (e) {
        if (e instanceof Offline) break
        // Refusé (sieste déjà notée par l'autre parent...) : on n'insiste pas
      }
      q = q.slice(1)
      ls.set(QUEUE, q)
      sent++
    }
  } finally {
    flushing = false
  }
  return sent
}
