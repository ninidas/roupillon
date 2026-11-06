import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

createRoot(document.getElementById('root')).render(<App />)

if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  navigator.serviceWorker.register('/sw.js').catch(() => {})
}

// Une app d'écran d'accueil peut rester des jours en pause et reprendre avec son ancien code :
// au retour au premier plan, si le serveur sert une autre version, on la charge
const loaded = document.querySelector('script[type="module"][src^="/assets/"]')?.getAttribute('src')
async function checkVersion() {
  if (!loaded || document.visibilityState !== 'visible') return
  try {
    const html = await (await fetch('/', { cache: 'no-store' })).text()
    const served = html.match(/<script[^>]*\ssrc="(\/assets\/[^"]+\.js)"/)?.[1]
    // Garde-fou : un seul rechargement par minute, même si quelque chose cloche
    const last = Number(sessionStorage.getItem('rp_reload') || 0)
    if (served && served !== loaded && Date.now() - last > 60000) {
      sessionStorage.setItem('rp_reload', String(Date.now()))
      location.reload()
    }
  } catch { /* hors connexion : on garde la version en cours */ }
}
document.addEventListener('visibilitychange', checkVersion)
window.addEventListener('online', checkVersion)
