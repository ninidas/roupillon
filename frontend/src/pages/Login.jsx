import { useState } from 'react'
import { api, setToken } from '../api'
import { Moon } from '../components/Icons'

export function Login({ onDone }) {
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try { const r = await api('/login', { method: 'POST', body: { username: u, password: p }, auth: false }); setToken(r.token); onDone(r.user) }
    catch (e2) { setErr(e2.status === 429 ? "Trop d'essais, attendez une minute" : e2.message); setBusy(false) }
  }
  return (
    <form className="login" onSubmit={submit}>
      <div className="moon"><Moon /></div>
      <div><h1>Siestes</h1><p>Connectez-vous une fois : l'app s'en souviendra.</p></div>
      <label>Identifiant<input id="login-user" className="input txt" autoCapitalize="none" autoCorrect="off" autoComplete="username" value={u} onChange={e => setU(e.target.value)} /></label>
      <label>Mot de passe<input id="login-pw" type="password" className="input txt" autoComplete="current-password" value={p} onChange={e => setP(e.target.value)} /></label>
      {err && <p className="err">{err}</p>}
      <button className="primary" disabled={busy || !u || !p}>Se connecter</button>
    </form>
  )
}

const emptyAccount = { display_name: '', username: '', password: '' }

export function Setup({ onDone }) {
  const [child, setChild] = useState('')
  const [birth, setBirth] = useState('')
  const [acc, setAcc] = useState([{ ...emptyAccount }, { ...emptyAccount }])
  const [err, setErr] = useState('')
  const set = (i, k, v) => setAcc(acc.map((a, j) => (j === i ? { ...a, [k]: v } : a)))
  async function submit(e) {
    e.preventDefault(); setErr('')
    const accounts = acc.filter(a => a.display_name || a.username || a.password)
    try {
      const r = await api('/setup', { method: 'POST', auth: false, body: { child_name: child, birth_date: birth, accounts } })
      setToken(r.token); onDone(r.user)
    } catch (e2) { setErr(e2.message) }
  }
  return (
    <form className="login" onSubmit={submit}>
      <div className="moon"><Moon /></div>
      <div><h1>Bienvenue</h1><p>Première ouverture : l'enfant, puis vos deux comptes.</p></div>
      <label>Prénom de l'enfant<input id="setup-child" className="input txt" value={child} onChange={e => setChild(e.target.value)} /></label>
      <label>Date de naissance<input id="setup-birth" type="date" className="input txt" value={birth} onChange={e => setBirth(e.target.value)} /></label>
      {acc.map((a, i) => (
        <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <h2 className="section-h" style={{ margin: '8px 0 0' }}>{i === 0 ? 'Votre compte' : 'Second parent (facultatif)'}</h2>
          <label>Prénom<input id={`setup-name-${i}`} className="input txt" value={a.display_name} onChange={e => set(i, 'display_name', e.target.value)} /></label>
          <label>Identifiant<input id={`setup-user-${i}`} className="input txt" autoCapitalize="none" autoCorrect="off" value={a.username} onChange={e => set(i, 'username', e.target.value)} /></label>
          <label>Mot de passe (12 caractères au moins)<input id={`setup-pw-${i}`} type="password" className="input txt" autoComplete="new-password" value={a.password} onChange={e => set(i, 'password', e.target.value)} /></label>
        </div>
      ))}
      {err && <p className="err">{err}</p>}
      <button className="primary" disabled={!child || !birth}>Commencer</button>
    </form>
  )
}
