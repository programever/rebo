// Made from haba/shared/haba-read.ts (repo programever/haba). Do not edit here: change the master, build, copy. Marks "read" in Haba after 3 minutes on this page.

// shared/haba-mark.ts
var BASE = "https://firestore.googleapis.com/v1/projects/habits-433f8/databases/(default)/documents";
var KEY = "AIzaSyDtkJvnZLPIkIAJzj9w3F486bX2E8T5kuU";
var DAY_START_HOUR = 4;
var pad = (n) => String(n).padStart(2, "0");
var ymd = (d) => d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
function habaDay(t) {
  const d = new Date(t instanceof Date ? t.getTime() : t);
  d.setHours(d.getHours() - DAY_START_HOUR);
  return ymd(d);
}
function isoLocal(d) {
  const off = -d.getTimezoneOffset();
  const a = Math.abs(off);
  return ymd(d) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds()) + (off >= 0 ? "+" : "-") + pad(Math.floor(a / 60)) + ":" + pad(a % 60);
}
async function recordsOf(item, day2) {
  const res = await fetch(`${BASE}:runQuery?key=${KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ structuredQuery: {
      from: [{ collectionId: "records" }],
      where: { fieldFilter: { field: { fieldPath: "item" }, op: "EQUAL", value: { stringValue: item } } }
    } })
  });
  if (!res.ok) throw new Error(`Haba answered ${res.status}`);
  const rows = await res.json();
  return rows.filter((r) => r.document && habaDay(r.document.fields?.t?.stringValue ?? "") === day2).map((r) => r.document.name);
}
async function markHaba(item, day2) {
  const when = day2 ? /* @__PURE__ */ new Date(`${day2}T12:00:00`) : /* @__PURE__ */ new Date();
  const key = habaDay(when);
  if ((await recordsOf(item, key)).length) return "already";
  const res = await fetch(`${BASE}/records?key=${KEY}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields: { t: { stringValue: isoLocal(when) }, item: { stringValue: item } } })
  });
  if (!res.ok) throw new Error(`Haba answered ${res.status}`);
  return "added";
}

// shared/haba-read.ts
var NEED_SECONDS = 180;
var FLAG = "haba-read";
var onScreen = 0;
var day = habaDay(/* @__PURE__ */ new Date());
var busy = false;
var retryAt = 0;
function listened() {
  let s = 0;
  for (const a of Array.from(document.querySelectorAll("audio"))) {
    for (let i = 0; i < a.played.length; i++) s += a.played.end(i) - a.played.start(i);
  }
  return s;
}
function markedToday() {
  try {
    return localStorage.getItem(FLAG) === habaDay(/* @__PURE__ */ new Date());
  } catch {
    return false;
  }
}
async function check() {
  if (busy || Date.now() < retryAt || markedToday()) return;
  if (onScreen + listened() < NEED_SECONDS) return;
  busy = true;
  try {
    await markHaba("read");
    try {
      localStorage.setItem(FLAG, habaDay(/* @__PURE__ */ new Date()));
    } catch {
    }
  } catch (e) {
    console.warn('Could not mark "read" in Haba:', e);
    retryAt = Date.now() + 6e4;
  } finally {
    busy = false;
  }
}
setInterval(() => {
  const now = habaDay(/* @__PURE__ */ new Date());
  if (now !== day) {
    day = now;
    onScreen = 0;
  }
  if (document.visibilityState === "visible") onScreen += 1;
  void check();
}, 1e3);
document.addEventListener("pause", () => void check(), true);
document.addEventListener("ended", () => void check(), true);
document.addEventListener("visibilitychange", () => void check());
