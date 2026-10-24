import { useEffect, useState } from 'react'
import { api, setToken } from '../api'
import Sheet, { Confirm } from '../components/Sheet'
import { Check, Chevron, Key, User } from '../components/Icons'
import widgetTemplate from '../scriptable/roupillon-widget.js?raw'

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return true } catch { return false }
}

export default function Settings({ me, setMe, open, close, notify, onLogout, status, refresh, theme, setTheme }) {
  const [s, setS] = useState(null)
  const [name, setName] = useState('')
  const [birth, setBirth] = useState('')
  const [key, setKey] = useState(null)

  useEffect(() => {
    api('/settings').then(v => { setS(v); setName(v.child_name); setBirth(v.birth_date || '') }).catch(e => notify(e.message))
  }, [notify])

  async function put(body, msg) {
    try { const v = await api('/settings', { method: 'PUT', body }); setS(v); refresh(); if (msg) notify(msg) } catch (e) { notify(e.message) }
  }

  async function makeKey() {
    try {
      const r = await api('/me/widget-key', { method: 'POST' })
      setKey(r.key); setMe({ ...me, has_widget_key: true })
    } catch (e) { notify(e.message) }
  }
  async function dropKey() {
    try { await api('/me/widget-key', { method: 'DELETE' }); setKey(null); setMe({ ...me, has_widget_key: false }); notify('Clé supprimée : le widget et les Raccourcis ne marchent plus') } catch (e) { notify(e.message) }
  }
  const script = key ? widgetTemplate.replace('__URL__', location.origin).replace('__KEY__', key) : ''

  return (
    <div className="wrap">
      <header className="top"><h1 className="rd">Réglages</h1><div className="top-sub">Pour vous deux</div>{status}</header>

      <section>
        <h2 className="section-h">Apparence</h2>
        <div className="themes">
          <button type="button" className="theme" aria-pressed={theme !== 'bleu'} onClick={() => setTheme('auto')}>
            <span className="theme-p" style={{ background: 'linear-gradient(90deg,#f5f4f8 50%,#000 50%)' }}>
              <span style={{ width: 34, height: 34, borderRadius: 17, border: '6px solid #dedbea', borderTopColor: '#5b57d6' }} />
              <span style={{ width: 34, height: 34, borderRadius: 17, border: '6px solid #2c2c2e', borderTopColor: '#5e5ce6' }} />
            </span>
            <span className="theme-n">Comme l'iPhone{theme !== 'bleu' && <span className="tick"><Check /></span>}</span>
            <span className="theme-d">Clair ou sombre, selon le réglage du téléphone</span>
          </button>
          <button type="button" className="theme" aria-pressed={theme === 'bleu'} onClick={() => setTheme('bleu')}>
            <span className="theme-p" style={{ background: '#191733' }}>
              <span style={{ width: 46, height: 46, borderRadius: 23, border: '8px solid #2a2754', borderTopColor: '#8b85ff', boxShadow: '0 0 12px rgba(139,133,255,.5)' }} />
            </span>
            <span className="theme-n">Bleu nuit{theme === 'bleu' && <span className="tick"><Check /></span>}</span>
            <span className="theme-d">Toujours sombre et doux, jour et nuit</span>
          </button>
        </div>
        <p className="foot">Choix propre à ce téléphone. Après le coucher, l'écran passe de toute façon en mode tamisé aux couleurs chaudes.</p>
      </section>

      {s && <>
        <section>
          <h2 className="section-h">Enfant</h2>
          <div className="group">
            <label className="cell" htmlFor="child">
              <span className="grow ttl">Prénom</span>
              <input id="child" className="input txt" style={{ maxWidth: 170, minHeight: 40, boxShadow: 'none', background: 'var(--fill)', textAlign: 'right' }}
                value={name} onChange={e => setName(e.target.value)} onBlur={() => name.trim() && name !== s.child_name && put({ child_name: name.trim() }, 'Prénom enregistré')} />
            </label>
            <label className="cell" htmlFor="birth">
              <span className="grow ttl">Naissance</span>
              <input id="birth" type="date" className="input txt" style={{ maxWidth: 170, minHeight: 40, boxShadow: 'none', background: 'var(--fill)' }}
                value={birth} onChange={e => { setBirth(e.target.value); if (e.target.value) put({ birth_date: e.target.value }, 'Date enregistrée') }} />
            </label>
            <div className="cell">
              <span className="grow ttl">Courbes OMS</span>
              <div className="seg" role="group" aria-label="Fille ou garçon">
                <button type="button" aria-pressed={s.sex === 'f'} onClick={() => put({ sex: 'f' }, 'Courbes des filles')}>Fille</button>
                <button type="button" aria-pressed={s.sex === 'm'} onClick={() => put({ sex: 'm' }, 'Courbes des garçons')}>Garçon</button>
              </div>
            </div>
          </div>
        </section>

        <section>
          <h2 className="section-h">Repères d'âge</h2>
          <div className="group">
            <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
              <div className="sub2" style={{ marginTop: 0 }}>{s.child.age_text ? `${s.child.name} a ${s.child.age_text.split(' · ')[0]}` : ''}</div>
              <div className="seg-wrap"><div className="seg" role="group" aria-label="Âge">
                {s.ages.map(a => (
                  <button key={a.id} type="button" aria-pressed={a.id === s.child.age_id}
                    onClick={() => put({ manual_age: a.id === s.auto_age ? null : a.id })}>{a.name}</button>
                ))}
              </div></div>
              <div className="sub2">
                {s.child.age_manual
                  ? <>Choix manuel · <button type="button" className="link" onClick={() => put({ manual_age: null })}>revenir à l'automatique</button></>
                  : "Réglé automatiquement d'après la date de naissance"}
              </div>
            </div>
          </div>
        </section>
      </>}


      <section>
        <h2 className="section-h">Widget et Raccourcis</h2>
        <div className="group">
          {key ? (
            <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
              <div className="ttl">Votre clé, montrée une seule fois</div>
              <div className="keybox">{key}</div>
              <button type="button" className="primary" onClick={async () => notify(await copy(script) ? 'Script copié : collez-le dans Scriptable' : 'Copie impossible : touchez longuement la clé')}>Copier le script du widget</button>
              <button type="button" className="secondary blue" onClick={async () => notify(await copy(key) ? 'Clé copiée' : 'Copie impossible')}>Copier la clé seule</button>
            </div>
          ) : (
            <button type="button" className="cell ic" onClick={makeKey}>
              <span className="icon i-key"><Key /></span>
              <span className="grow"><span className="ttl">{me.has_widget_key ? 'Remplacer ma clé' : 'Créer ma clé'}</span>
                <span className="sub2" style={{ display: 'block' }}>{me.has_widget_key ? "L'ancienne cessera de marcher" : "Pour le widget de l'écran verrouillé et Siri"}</span></span>
              <Chevron />
            </button>
          )}
          <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', paddingBottom: 0 }}>
            <div className="ttl">Widget de l'écran verrouillé</div>
          </div>
          <ol className="steps">
            <li>Installez <b>Scriptable</b> (App Store, gratuit), touchez <b>+</b>, collez le script, nommez-le « Siestes ».</li>
            <li>Écran verrouillé : appui long, <b>Personnaliser</b>, ajoutez un widget Scriptable, choisissez « Siestes ».</li>
            <li>Le compteur avance tout seul. Toucher le widget ouvre un menu : <b>Elle dort / réveillée</b>, <b>Biberon</b>.</li>
          </ol>
          <div className="cell" style={{ flexDirection: 'column', alignItems: 'stretch', paddingBottom: 0 }}>
            <div className="ttl">Siri, bouton Action ou tag NFC</div>
          </div>
          <ol className="steps">
            <li>App Raccourcis, nouveau raccourci, action <b>Obtenir le contenu de l'URL</b>.</li>
            <li>Adresse <b>{location.origin}/api/quick/toggle?text=1</b>, méthode <b>POST</b>, en-tête <b>X-Roupillon-Key</b> = votre clé.</li>
            <li>Ajoutez <b>Afficher la notification</b> avec le contenu obtenu. Nommez-le « Dodo » : la sieste commence ou s'arrête, la nuit c'est un réveil nocturne.</li>
            <li>Pour un biberon : même chose avec <b>/api/quick/feed?text=1</b>.</li>
          </ol>
          {me.has_widget_key && !key && (
            <div className="cell"><Confirm className="link danger" label="Supprimer ma clé" confirm="Toucher encore pour supprimer" onConfirm={dropKey} /></div>
          )}
        </div>
      </section>

      <section>
        <h2 className="section-h">Compte</h2>
        <div className="group">
          <div className="cell ic">
            <span className="icon i-user"><User /></span>
            <span className="grow"><span className="ttl">{me.display_name}</span><span className="sub2" style={{ display: 'block' }}>Identifiant : {me.username}</span></span>
          </div>
          <button type="button" className="cell" onClick={() => open(<PasswordSheet onClose={close} notify={notify} />)}>
            <span className="grow ttl">Changer le mot de passe</span><Chevron />
          </button>
          <button type="button" className="cell" onClick={onLogout}><span className="grow ttl danger">Se déconnecter</span></button>
        </div>
        <p className="foot">Tout ce qui est noté ici est partagé entre {s ? s.users.map(u => u.display_name).join(' et ') : 'vous deux'}.</p>
      </section>
    </div>
  )
}

function PasswordSheet({ onClose, notify }) {
  const [cur, setCur] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState('')
  async function save() {
    setErr('')
    try {
      const r = await api('/me/password', { method: 'POST', body: { current: cur, new: pw } })
      setToken(r.token); onClose(); notify('Mot de passe changé : vos autres appareils sont déconnectés')
    } catch (e) { setErr(e.message) }
  }
  return (
    <Sheet title="Mot de passe" onClose={onClose}>
      <label className="field">Mot de passe actuel<input id="pw-cur" type="password" className="input txt" autoComplete="current-password" value={cur} onChange={e => setCur(e.target.value)} /></label>
      <label className="field">Nouveau (12 caractères au moins)<input id="pw-new" type="password" className="input txt" autoComplete="new-password" value={pw} onChange={e => setPw(e.target.value)} /></label>
      {err && <p className="err">{err}</p>}
      <button type="button" className="primary" disabled={!cur || pw.length < 12} onClick={save}>Changer</button>
    </Sheet>
  )
}
