// Siestes : widget Scriptable pour l'écran verrouillé et l'écran d'accueil.
// Toucher le widget ouvre un menu : « Elle dort / Elle est réveillée » et « Biberon ».
// Créé depuis l'app (Réglages > Widget) : l'adresse et la clé sont déjà remplies.
const BASE = "__URL__"
const KEY = "__KEY__"

const fm = FileManager.local()
const CACHE = fm.joinPath(fm.cacheDirectory(), "siestes-widget.json")
const INDIGO = new Color("#5856d6"), INDIGO2 = new Color("#7a78f0"), ORANGE = new Color("#ff9500"), NIGHT = new Color("#14121f")

function req(path, method) {
  const r = new Request(BASE + path)
  r.method = method || "GET"
  r.headers = { "X-Roupillon-Key": KEY }
  r.timeoutInterval = 10
  return r
}

async function status() {
  try {
    const r = req("/api/quick/status")
    const data = await r.loadJSON()
    if (r.response.statusCode !== 200) return { error: data.detail || "Erreur " + r.response.statusCode }
    fm.writeString(CACHE, JSON.stringify(data))
    return { data }
  } catch (e) {
    if (fm.fileExists(CACHE)) return { data: JSON.parse(fm.readString(CACHE)), stale: true }
    return { error: "Pas de réseau" }
  }
}

// « 2026-10-24T13:40:00 » en heure locale
function toDate(s) {
  if (!s) return null
  const [d, t] = s.split("T"), [y, m, j] = d.split("-").map(Number), [h, mi] = t.split(":").map(Number)
  return new Date(y, m - 1, j, h, mi)
}
const hm = (d) => String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0")
const asleep = (s) => s === "nap" || s === "night"

// Ce que montre le widget, selon l'état : un titre, un compteur qui avance tout seul, une précision
function content(data) {
  const target = toDate(data.target), since = toDate(data.since)
  switch (data.state) {
    case "nap": return { title: data.title, label: "dort depuis", timer: since, note: data.line, symbol: "moon.zzz.fill" }
    case "night": return { title: "Nuit en cours", label: "depuis", timer: since, note: data.line, symbol: "moon.stars.fill" }
    case "night_awake": return { title: "Réveil nocturne", label: "depuis", timer: since, note: data.line, symbol: "eye.fill" }
    case "awake": return { title: data.title, label: "dans", timer: target, note: since ? "éveillée depuis " + hm(since) : data.line, symbol: "sun.max.fill" }
    default: return { title: data.title, label: "éveillée depuis", timer: since, note: data.line, symbol: "bed.double.fill" }
  }
}

function timerRow(stack, c, size, color) {
  const row = stack.addStack()
  row.centerAlignContent()
  const l = row.addText(c.label + " ")
  l.font = Font.mediumSystemFont(size * 0.8)
  l.textColor = color
  l.textOpacity = 0.8
  if (c.timer) {
    const t = row.addDate(c.timer)
    t.applyTimerStyle()
    t.font = Font.boldMonospacedSystemFont(size)
    t.textColor = color
  }
}

function ring(progress, asleepNow) {
  const size = 100, ctx = new DrawContext()
  ctx.size = new Size(size, size)
  ctx.opaque = false
  ctx.respectScreenScale = true
  const arc = (from, to, color, width) => {
    const p = new Path(), pts = [], r = size / 2 - width / 2 - 2
    for (let a = from; a <= to; a += 2) {
      const rad = (a - 90) * Math.PI / 180
      pts.push(new Point(size / 2 + r * Math.cos(rad), size / 2 + r * Math.sin(rad)))
    }
    if (pts.length < 2) return
    p.addLines(pts)
    ctx.addPath(p)
    ctx.setStrokeColor(color)
    ctx.setLineWidth(width)
    ctx.strokePath()
  }
  arc(0, 360, new Color("#ffffff", 0.25), 9)
  if (progress != null) arc(0, Math.max(4, Math.min(1, progress) * 360), new Color("#ffffff"), 9)
  else if (asleepNow) arc(0, 360, new Color("#ffffff", 0.6), 9)
  return ctx.getImage()
}

async function buildWidget() {
  const { data, error, stale } = await status()
  const w = new ListWidget()
  const family = config.widgetFamily || "accessoryRectangular"
  // iOS reste maître du rythme, mais une demande courte le rend nettement plus fréquent (1 à 3 min observées)
  w.refreshAfterDate = new Date(Date.now() + 60 * 1000)
  if (!data) {
    const t = w.addText(error === "Pas de réseau" ? "Siestes : hors ligne" : "Siestes : " + error)
    t.font = Font.mediumSystemFont(13)
    return w
  }
  const c = content(data)

  if (family === "accessoryInline") {
    w.addText(c.title || "")
    return w
  }

  if (family === "accessoryCircular") {
    w.backgroundImage = ring(data.progress, asleep(data.state))
    w.addSpacer()
    const sym = w.addImage(SFSymbol.named(c.symbol).image)
    sym.imageSize = new Size(14, 14)
    sym.centerAlignImage()
    const time = data.target ? hm(toDate(data.target)) : c.timer ? hm(c.timer) : ""
    const t = w.addText(time)
    t.font = Font.boldRoundedSystemFont(14)
    t.centerAlignText()
    t.minimumScaleFactor = 0.6
    w.addSpacer()
    return w
  }

  if (family === "accessoryRectangular") {
    const top = w.addStack()
    top.centerAlignContent()
    const img = top.addImage(SFSymbol.named(c.symbol).image)
    img.imageSize = new Size(13, 13)
    top.addSpacer(4)
    const t = top.addText(c.title)
    t.font = Font.boldSystemFont(14)
    t.lineLimit = 1
    t.minimumScaleFactor = 0.7
    timerRow(w, c, 17, Color.white())
    const n = w.addText((stale ? "hors ligne · " : "") + (c.note || ""))
    n.font = Font.systemFont(12)
    n.textOpacity = 0.75
    n.lineLimit = 1
    return w
  }

  // Écran d'accueil : même contenu, en grand, sur le dégradé de l'app
  const night = data.state === "night" || data.state === "night_awake"
  const g = new LinearGradient()
  g.colors = night ? [NIGHT, new Color("#05050a")] : data.state === "awake" ? [INDIGO2, INDIGO] : [INDIGO, new Color("#3a3a8c")]
  g.locations = [0, 1]
  w.backgroundGradient = g
  w.setPadding(14, 14, 14, 14)
  const head = w.addStack()
  head.centerAlignContent()
  const img = head.addImage(SFSymbol.named(c.symbol).image)
  img.imageSize = new Size(15, 15)
  img.tintColor = Color.white()
  head.addSpacer(5)
  const name = head.addText(data.child)
  name.font = Font.semiboldSystemFont(14)
  name.textColor = Color.white()
  name.textOpacity = 0.85
  w.addSpacer(6)
  const t = w.addText(c.title)
  t.font = Font.boldSystemFont(family === "small" ? 17 : 20)
  t.textColor = Color.white()
  t.minimumScaleFactor = 0.7
  t.lineLimit = 2
  w.addSpacer(4)
  timerRow(w, c, family === "small" ? 22 : 28, Color.white())
  w.addSpacer()
  const n = w.addText((stale ? "hors ligne · " : "") + (c.note || ""))
  n.font = Font.systemFont(13)
  n.textColor = Color.white()
  n.textOpacity = 0.8
  n.lineLimit = 2
  return w
}

async function menu() {
  const { data, error } = await status()
  const a = new Alert()
  a.title = data ? data.title : "Siestes"
  a.message = data ? (data.headline && data.headline.sub) || data.line : error
  const toggle = !data ? "Elle dort / réveillée"
    : data.state === "nap" ? "Elle est réveillée"
    : data.state === "night" ? "Réveil nocturne"
    : data.state === "night_awake" ? "Rendormie"
    : "Elle dort"
  a.addAction(toggle)
  a.addAction("Biberon maintenant")
  a.addCancelAction("Fermer")
  const i = await a.presentSheet()
  if (i < 0) return
  try {
    const r = req(i === 0 ? "/api/quick/toggle?text=1" : "/api/quick/feed?text=1", "POST")
    const text = await r.loadString()
    const done = new Alert()
    done.title = text
    done.addAction("OK")
    await done.presentAlert()
  } catch (e) {
    const fail = new Alert()
    fail.title = "Pas de réseau"
    fail.message = "Rien n'a été noté. Réessayez ou passez par l'app."
    fail.addAction("OK")
    await fail.presentAlert()
  }
}

// Noter d'un seul toucher : widget réglé sur Open URL scriptable:///run/Siestes?do=toggle (ou do=feed).
// L'app Scriptable s'ouvre, ce qui fait aussi rafraîchir le widget.
async function quick(what) {
  let text
  try {
    text = await req(what === "feed" ? "/api/quick/feed?text=1" : "/api/quick/toggle?text=1", "POST").loadString()
  } catch (e) {
    text = "Pas de réseau : rien n'a été noté"
  }
  const done = new Alert()
  done.title = text
  done.addAction("OK")
  await done.presentAlert()
}

const q = args.queryParameters || {}
if (config.runsInWidget) {
  Script.setWidget(await buildWidget())
} else if (q.do) {
  await quick(q.do)
} else if (q.preview) {
  const w = await buildWidget()
  await w.presentMedium()
} else {
  await menu()
}
Script.complete()
