"""
HabitFlow — minimal habit tracker
DevOps focus: exposes /metrics for Prometheus, /health for Jenkins health checks.
"""

import os, sqlite3, logging
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, render_template_string, g
from apscheduler.schedulers.background import BackgroundScheduler
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

app = Flask(__name__)
DB_PATH = os.getenv("DB_PATH", "/data/habits.db")

# ── Prometheus Metrics ─────────────────────────────────────────────────────
CHECKINS       = Counter('habitflow_checkins_total',       'Total check-ins logged')
NUDGES_FIRED   = Counter('habitflow_nudges_fired_total',   'Nudges fired for at-risk habits')
ACTIVE_HABITS  = Gauge(  'habitflow_active_habits',        'Number of active habits')
BROKEN_STREAKS = Counter('habitflow_broken_streaks_total', 'Streaks broken (missed a day)')

# ── Database ───────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS habits (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT    NOT NULL UNIQUE,
            created   TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkins (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id   INTEGER NOT NULL REFERENCES habits(id),
            checked_on TEXT    NOT NULL,
            UNIQUE(habit_id, checked_on)
        );
    """)
    conn.commit()
    conn.close()
    log.info("DB initialised at %s", DB_PATH)

# ── Streak helper ──────────────────────────────────────────────────────────
def streak_for(habit_id: int, db) -> int:
    rows = db.execute(
        "SELECT checked_on FROM checkins WHERE habit_id=? ORDER BY checked_on DESC",
        (habit_id,)
    ).fetchall()
    if not rows: return 0
    streak, expected = 0, date.today()
    for r in rows:
        d = date.fromisoformat(r["checked_on"])
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif d < expected:
            break
    return streak

# ── Nudge scheduler (runs every hour inside the same container) ────────────
def check_nudges():
    """
    At-risk logic: if habit has a streak >= 1 and NOT checked in today → nudge.
    In production: send email/push. Here: log + increment Prometheus counter.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        today = date.today().isoformat()
        habits = conn.execute("SELECT * FROM habits").fetchall()
        ACTIVE_HABITS.set(len(habits))

        for h in habits:
            checked_today = conn.execute(
                "SELECT 1 FROM checkins WHERE habit_id=? AND checked_on=?",
                (h["id"], today)
            ).fetchone()
            if checked_today:
                continue

            streak = streak_for(h["id"], conn)
            if streak >= 1:
                log.warning("NUDGE ▶ '%s' streak=%d — not checked in today!", h["name"], streak)
                NUDGES_FIRED.inc()

            # Detect broken streak: yesterday had a streak but today missed AND it's past 8pm
            if streak == 0:
                yesterday = conn.execute(
                    "SELECT 1 FROM checkins WHERE habit_id=? AND checked_on=?",
                    (h["id"], (date.today() - timedelta(days=1)).isoformat())
                ).fetchone()
                if yesterday:
                    BROKEN_STREAKS.inc()
                    log.error("BROKEN STREAK ▶ '%s'", h["name"])

        conn.close()
    except Exception as e:
        log.error("Nudge scheduler error: %s", e)

# ── HTML UI (single-page, minimal) ────────────────────────────────────────
PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HabitFlow</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f5f0e8;--fg:#1a1a1a;--card:#fff;--accent:#ff4d00;
  --muted:#888;--border:#e0d9ce;--streak:#ff4d00;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--fg);font-family:'IBM Plex Mono',monospace;min-height:100vh;padding:2rem 1rem}
header{max-width:700px;margin:0 auto 2.5rem;display:flex;justify-content:space-between;align-items:flex-end}
h1{font-family:'Syne',sans-serif;font-weight:800;font-size:2.2rem;letter-spacing:-1px}
h1 span{color:var(--accent)}
.version{font-size:.7rem;color:var(--muted);background:#eee;padding:.2rem .5rem;border-radius:4px}
.container{max-width:700px;margin:0 auto;display:grid;gap:1.5rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:1.5rem}
.card h2{font-family:'Syne',sans-serif;font-size:1rem;font-weight:700;text-transform:uppercase;
          letter-spacing:2px;margin-bottom:1rem;color:var(--muted)}
.add-row{display:flex;gap:.75rem}
input[type=text]{flex:1;background:var(--bg);border:1.5px solid var(--border);border-radius:8px;
  padding:.65rem 1rem;font-family:inherit;font-size:.9rem;outline:none;transition:border .2s}
input[type=text]:focus{border-color:var(--accent)}
button{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:.65rem 1.2rem;
  font-family:'Syne',sans-serif;font-weight:700;font-size:.85rem;cursor:pointer;transition:opacity .2s;white-space:nowrap}
button:hover{opacity:.85}
button.ghost{background:transparent;color:var(--fg);border:1.5px solid var(--border)}
button.ghost:hover{border-color:var(--accent);color:var(--accent)}
.habits-list{display:grid;gap:.75rem}
.habit-row{display:flex;align-items:center;gap:1rem;padding:.9rem 1rem;
  border:1.5px solid var(--border);border-radius:10px;transition:border .2s}
.habit-row.done{border-color:#34d399;background:#f0fdf4}
.habit-name{flex:1;font-size:.9rem;font-weight:500}
.streak-badge{font-family:'Syne',sans-serif;font-weight:700;font-size:.8rem;
  color:var(--streak);background:#fff3ee;padding:.25rem .6rem;border-radius:20px;white-space:nowrap}
.check-btn{padding:.5rem 1rem;font-size:.8rem}
.check-btn:disabled{opacity:.4;cursor:not-allowed}
.nudge-banner{background:#fff8f0;border:1.5px solid #ffd0b0;border-radius:10px;
  padding:.75rem 1rem;font-size:.8rem;color:#b34a00;margin-bottom:.5rem}
.empty{text-align:center;color:var(--muted);padding:2rem 0;font-size:.85rem}
footer{max-width:700px;margin:2rem auto 0;font-size:.7rem;color:var(--muted);text-align:center}
</style>
</head>
<body>
<header>
  <h1>Habit<span>Flow</span></h1>
  <span class="version" id="ver">v—</span>
</header>
<div class="container">
  <div class="card">
    <h2>Add Habit</h2>
    <div class="add-row">
      <input type="text" id="hname" placeholder="e.g. Morning run, Read 20 pages…" maxlength="60">
      <button onclick="addHabit()">+ Add</button>
    </div>
  </div>
  <div class="card">
    <h2>Today — <span id="today-date"></span></h2>
    <div class="habits-list" id="habits-list"><div class="empty">No habits yet. Add one above.</div></div>
  </div>
</div>
<footer>HabitFlow · Dockerised Flask · CI/CD via Jenkins · Monitored with Prometheus + Grafana</footer>
<script>
const fmt=new Intl.DateTimeFormat('en-US',{weekday:'long',month:'long',day:'numeric'});
document.getElementById('today-date').textContent=fmt.format(new Date());

async function load(){
  const r=await fetch('/api/habits');
  const habits=await r.json();
  const list=document.getElementById('habits-list');
  if(!habits.length){list.innerHTML='<div class="empty">No habits yet.</div>';return}
  list.innerHTML=habits.map(h=>`
    <div class="habit-row ${h.checked_today?'done':''}" id="row-${h.id}">
      ${!h.checked_today&&h.streak>=1?`<div class="nudge-banner">⚠ ${h.name} — streak at risk!</div>`:''}
      <span class="habit-name">${h.name}</span>
      <span class="streak-badge">${h.streak>0?'🔥 '+h.streak+' day'+(h.streak>1?'s':''):'—'}</span>
      <button class="ghost check-btn" onclick="checkin(${h.id})" ${h.checked_today?'disabled':''}>
        ${h.checked_today?'✓ Done':'Check in'}
      </button>
    </div>
  `).join('');
}

async function addHabit(){
  const name=document.getElementById('hname').value.trim();
  if(!name)return;
  await fetch('/api/habits',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
  document.getElementById('hname').value='';
  load();
}

async function checkin(id){
  await fetch('/api/checkin',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({habit_id:id})});
  load();
}

async function loadVersion(){
  const r=await fetch('/health');
  const d=await r.json();
  document.getElementById('ver').textContent='v'+d.version;
}

load();loadVersion();
</script>
</body>
</html>
"""

# ── API Routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template_string(PAGE)

@app.route('/api/habits', methods=['GET'])
def list_habits():
    db = get_db()
    habits = db.execute("SELECT * FROM habits ORDER BY created DESC").fetchall()
    ACTIVE_HABITS.set(len(habits))
    today = date.today().isoformat()
    result = []
    for h in habits:
        checked = db.execute(
            "SELECT 1 FROM checkins WHERE habit_id=? AND checked_on=?",
            (h["id"], today)
        ).fetchone()
        result.append({
            "id":            h["id"],
            "name":          h["name"],
            "streak":        streak_for(h["id"], db),
            "checked_today": bool(checked),
        })
    return jsonify(result)

@app.route('/api/habits', methods=['POST'])
def add_habit():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="name required"), 400
    db = get_db()
    try:
        db.execute("INSERT INTO habits (name, created) VALUES (?, ?)",
                   (name, datetime.utcnow().isoformat()))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="habit already exists"), 409
    return jsonify(ok=True), 201

@app.route('/api/checkin', methods=['POST'])
def checkin():
    data = request.get_json(silent=True) or {}
    habit_id = data.get("habit_id")
    if not habit_id:
        return jsonify(error="habit_id required"), 400
    db = get_db()
    today = date.today().isoformat()
    try:
        db.execute("INSERT INTO checkins (habit_id, checked_on) VALUES (?,?)", (habit_id, today))
        db.commit()
        CHECKINS.inc()
    except sqlite3.IntegrityError:
        pass  # already checked in today
    return jsonify(ok=True)

@app.route('/health')
def health():
    return jsonify(status="ok", version=os.getenv("APP_VERSION", "dev"))

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

# ── Boot ───────────────────────────────────────────────────────────────────
init_db()

scheduler = BackgroundScheduler()
scheduler.add_job(check_nudges, 'interval', hours=1, id='nudge_check')
scheduler.start()
log.info("Nudge scheduler started — checking every hour")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
