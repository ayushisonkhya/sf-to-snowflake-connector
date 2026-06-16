"""
dashboard.py
============
FastAPI web dashboard for the Salesforce → Snowflake connector.

Features:
  - Sync status per object (last run, rows loaded, success/fail)
  - Trigger sync from UI (Run Now button)
  - Full sync history from _SYNC_LOG table

How to run:
  pip install fastapi uvicorn
  python dashboard.py

Then open: http://localhost:8000
"""

import logging
import threading
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from snowflake_client import SnowflakeClient
from connector import run
from config import SALESFORCE_OBJECTS, SYNC_MODE

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="SF → Snowflake Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track running syncs so UI can show "Syncing..." state
_running_syncs: set = set()


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    """
    Returns the latest sync status for every configured object.
    Reads from _SYNC_LOG in Snowflake.
    """
    try:
        snow = SnowflakeClient()
        snow.cursor.execute("""
            SELECT
                "OBJECT_NAME",
                "SYNC_MODE",
                "STATUS",
                "ROWS_LOADED",
                "STARTED_AT",
                "FINISHED_AT",
                "DURATION_SEC",
                "ERROR_MESSAGE"
            FROM _SYNC_LOG
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY "OBJECT_NAME"
                ORDER BY "FINISHED_AT" DESC
            ) = 1
            ORDER BY "OBJECT_NAME"
        """)
        rows = snow.cursor.fetchall()
        cols = [
            "object_name", "sync_mode", "status", "rows_loaded",
            "started_at", "finished_at", "duration_sec", "error_message"
        ]
        results = []
        for row in rows:
            record = dict(zip(cols, row))
            # Convert datetimes to strings for JSON
            for key in ("started_at", "finished_at"):
                if record[key]:
                    record[key] = record[key].strftime("%Y-%m-%d %H:%M:%S")
                    # Convert Decimal to float for JSON
            for key in ("rows_loaded", "duration_sec"):
                if record[key] is not None:
                    record[key] = float(record[key])
            record["is_running"] = record["object_name"] in _running_syncs
            results.append(record)

        # Add objects that have never been synced
        synced_objects = {r["object_name"] for r in results}
        for obj in SALESFORCE_OBJECTS:
            if obj.upper() not in synced_objects and obj not in synced_objects:
                results.append({
                    "object_name": obj,
                    "sync_mode": None,
                    "status": "NEVER RUN",
                    "rows_loaded": 0,
                    "started_at": None,
                    "finished_at": None,
                    "duration_sec": None,
                    "error_message": None,
                    "is_running": obj in _running_syncs,
                })

        snow.close()
        return JSONResponse(content={"objects": results})
    except Exception as e:
        log.error(f"Status fetch error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.get("/api/history")
def get_history(limit: int = 50):
    """
    Returns full sync history from _SYNC_LOG.
    """
    try:
        snow = SnowflakeClient()
        snow.cursor.execute(f"""
            SELECT
                "OBJECT_NAME",
                "SYNC_MODE",
                "STATUS",
                "ROWS_LOADED",
                "STARTED_AT",
                "FINISHED_AT",
                "DURATION_SEC",
                "ERROR_MESSAGE"
            FROM _SYNC_LOG
            ORDER BY "STARTED_AT" DESC
            LIMIT {limit}
        """)
        rows = snow.cursor.fetchall()
        cols = [
            "object_name", "sync_mode", "status", "rows_loaded",
            "started_at", "finished_at", "duration_sec", "error_message"
        ]
        results = []
        for row in rows:
            record = dict(zip(cols, row))
            for key in ("started_at", "finished_at"):
                if record[key]:
                    record[key] = record[key].strftime("%Y-%m-%d %H:%M:%S")
                    # Convert Decimal to float for JSON
            for key in ("rows_loaded", "duration_sec"):
                if record[key] is not None:
                    record[key] = float(record[key])
            results.append(record)

        snow.close()
        return JSONResponse(content={"history": results})
    except Exception as e:
        log.error(f"History fetch error: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)


@app.post("/api/sync")
def trigger_sync(object_name: Optional[str] = None, mode: Optional[str] = None):
    """
    Triggers a sync in a background thread so the UI doesn't hang.
    Pass object_name to sync one object, or leave blank to sync all.
    """
    objects = [object_name] if object_name else SALESFORCE_OBJECTS
    sync_mode = mode or SYNC_MODE

    # Mark as running
    for obj in objects:
        _running_syncs.add(obj)

    def do_sync():
        try:
            run(objects=objects, mode=sync_mode)
        finally:
            for obj in objects:
                _running_syncs.discard(obj)

    thread = threading.Thread(target=do_sync, daemon=True)
    thread.start()

    return JSONResponse(content={
        "message": f"Sync started for: {', '.join(objects)} [{sync_mode}]",
        "objects": objects,
        "mode": sync_mode,
    })


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Serves the dashboard UI."""
    return HTMLResponse(content=DASHBOARD_HTML)


# ── Dashboard HTML ─────────────────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SF → Snowflake Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:        #0a0e1a;
    --surface:   #111827;
    --border:    #1e2d40;
    --accent:    #00d4ff;
    --accent2:   #7c3aed;
    --success:   #10b981;
    --error:     #ef4444;
    --warning:   #f59e0b;
    --text:      #e2e8f0;
    --muted:     #64748b;
    --font-mono: 'IBM Plex Mono', monospace;
    --font-sans: 'IBM Plex Sans', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-sans);
    min-height: 100vh;
    padding: 0;
  }

  /* ── Header ── */
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 20px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 100;
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .logo {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: -0.5px;
  }

  .logo span { color: var(--muted); }

  .live-badge {
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--success);
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.2);
    padding: 4px 10px;
    border-radius: 20px;
  }

  .live-dot {
    width: 6px;
    height: 6px;
    background: var(--success);
    border-radius: 50%;
    animation: pulse 2s infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .btn-sync-all {
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 600;
    background: var(--accent);
    color: #000;
    border: none;
    padding: 10px 20px;
    border-radius: 6px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all 0.2s;
  }

  .btn-sync-all:hover { background: #00b8d9; transform: translateY(-1px); }
  .btn-sync-all:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

  /* ── Main layout ── */
  .main { padding: 32px 40px; max-width: 1400px; margin: 0 auto; }

  /* ── Section title ── */
  .section-title {
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  /* ── Object cards grid ── */
  .cards-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }

  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }

  .card:hover { border-color: var(--accent); }

  .card-accent {
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
  }

  .card-accent.success { background: var(--success); }
  .card-accent.error   { background: var(--error); }
  .card-accent.warning { background: var(--warning); }
  .card-accent.never   { background: var(--border); }
  .card-accent.running { background: linear-gradient(90deg, var(--accent), var(--accent2)); background-size: 200%; animation: shimmer 1.5s infinite; }

  @keyframes shimmer {
    0% { background-position: 200% center; }
    100% { background-position: -200% center; }
  }

  .card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  .object-name {
    font-family: var(--font-mono);
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .status-badge {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 4px;
    letter-spacing: 1px;
  }

  .status-badge.SUCCESS  { background: rgba(16,185,129,0.15); color: var(--success); }
  .status-badge.FAILED   { background: rgba(239,68,68,0.15);  color: var(--error); }
  .status-badge.RUNNING  { background: rgba(0,212,255,0.15);  color: var(--accent); }
  .status-badge.NEVER { background: rgba(100,116,139,0.15); color: var(--muted); }

  .card-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
  }

  .stat label {
    font-family: var(--font-mono);
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 1px;
    text-transform: uppercase;
    display: block;
    margin-bottom: 4px;
  }

  .stat value {
    font-family: var(--font-mono);
    font-size: 14px;
    color: var(--text);
    font-weight: 500;
  }

  .card-actions {
    display: flex;
    gap: 8px;
  }

  .btn-run {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    color: var(--accent);
    border: 1px solid var(--accent);
    padding: 8px;
    border-radius: 6px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all 0.2s;
  }

  .btn-run:hover { background: rgba(0,212,255,0.1); }
  .btn-run:disabled { opacity: 0.4; cursor: not-allowed; }

  .btn-full {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
    padding: 8px;
    border-radius: 6px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: all 0.2s;
  }

  .btn-full:hover { color: var(--text); border-color: var(--muted); }
  .btn-full:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ── History table ── */
  .history-table-wrap {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-family: var(--font-mono);
    font-size: 12px;
  }

  thead tr {
    background: rgba(30, 45, 64, 0.8);
    border-bottom: 1px solid var(--border);
  }

  th {
    padding: 12px 16px;
    text-align: left;
    font-size: 10px;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 1.5px;
    text-transform: uppercase;
  }

  tbody tr {
    border-bottom: 1px solid rgba(30,45,64,0.5);
    transition: background 0.15s;
  }

  tbody tr:hover { background: rgba(255,255,255,0.02); }
  tbody tr:last-child { border-bottom: none; }

  td {
    padding: 12px 16px;
    color: var(--text);
  }

  .pill {
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    letter-spacing: 1px;
  }

  .pill.SUCCESS { background: rgba(16,185,129,0.15); color: var(--success); }
  .pill.FAILED  { background: rgba(239,68,68,0.15);  color: var(--error); }

  .error-msg {
    max-width: 300px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--error);
    font-size: 11px;
  }

  /* ── Toast ── */
  .toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 14px 20px;
    border-radius: 8px;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text);
    opacity: 0;
    transform: translateY(10px);
    transition: all 0.3s;
    z-index: 999;
    max-width: 400px;
  }

  .toast.show { opacity: 1; transform: translateY(0); }

  /* ── Empty state ── */
  .empty {
    text-align: center;
    padding: 40px;
    color: var(--muted);
    font-family: var(--font-mono);
    font-size: 13px;
  }

  /* ── Spinner ── */
  .spinner {
    display: inline-block;
    width: 10px;
    height: 10px;
    border: 2px solid rgba(0,212,255,0.3);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin-right: 6px;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="logo">SF <span>→</span> Snowflake</div>
    <div class="live-badge">
      <div class="live-dot"></div>
      LIVE
    </div>
  </div>
  <button class="btn-sync-all" onclick="syncAll()">⚡ Sync All</button>
</div>

<div class="main">

  <!-- Object Status Cards -->
  <div class="section-title">Object Status</div>
  <div class="cards-grid" id="cards">
    <div class="empty">Loading...</div>
  </div>

  <!-- Sync History -->
  <div class="section-title">Sync History</div>
  <div class="history-table-wrap">
    <table>
      <thead>
        <tr>
          <th>Object</th>
          <th>Mode</th>
          <th>Status</th>
          <th>Rows</th>
          <th>Started</th>
          <th>Duration</th>
          <th>Error</th>
        </tr>
      </thead>
      <tbody id="history-body">
        <tr><td colspan="7" class="empty">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
  // ── Fetch and render status cards ────────────────────────────────────────

  async function loadStatus() {
    try {
      const res  = await fetch('/api/status');
      const data = await res.json();
      renderCards(data.objects || []);
    } catch (e) {
      document.getElementById('cards').innerHTML =
        '<div class="empty">Failed to load status.</div>';
    }
  }

  function renderCards(objects) {
    const grid = document.getElementById('cards');
    if (!objects.length) {
      grid.innerHTML = '<div class="empty">No objects configured.</div>';
      return;
    }

    grid.innerHTML = objects.map(obj => {
      const isRunning = obj.is_running;
      const status    = isRunning ? 'RUNNING' : obj.status;
      const accentCls = isRunning ? 'running'
                      : status === 'SUCCESS'  ? 'success'
                      : status === 'FAILED'   ? 'error'
                      : status === 'NEVER RUN'? 'never'
                      : 'warning';

      const rows     = obj.rows_loaded ? obj.rows_loaded.toLocaleString() : '—';
      const lastRun  = obj.finished_at || '—';
      const duration = obj.duration_sec ? obj.duration_sec + 's' : '—';
      const mode     = obj.sync_mode   || '—';

      return `
        <div class="card">
          <div class="card-accent ${accentCls}"></div>
          <div class="card-header">
            <div class="object-name">${obj.object_name}</div>
            <div class="status-badge ${status.replace(' ','_')}">
              ${isRunning ? '<span class="spinner"></span>' : ''}${status}
            </div>
          </div>
          <div class="card-stats">
            <div class="stat">
              <label>Rows Loaded</label>
              <value>${rows}</value>
            </div>
            <div class="stat">
              <label>Duration</label>
              <value>${duration}</value>
            </div>
            <div class="stat">
              <label>Last Run</label>
              <value style="font-size:11px">${lastRun}</value>
            </div>
            <div class="stat">
              <label>Mode</label>
              <value>${mode}</value>
            </div>
          </div>
          <div class="card-actions">
            <button class="btn-run"  onclick="syncOne('${obj.object_name}','incremental')"
              ${isRunning ? 'disabled' : ''}>▶ Incremental</button>
            <button class="btn-full" onclick="syncOne('${obj.object_name}','full')"
              ${isRunning ? 'disabled' : ''}>↺ Full Refresh</button>
          </div>
        </div>`;
    }).join('');
  }

  // ── Fetch and render history table ───────────────────────────────────────

  async function loadHistory() {
    try {
      const res  = await fetch('/api/history?limit=50');
      const data = await res.json();
      renderHistory(data.history || []);
    } catch (e) {
      document.getElementById('history-body').innerHTML =
        '<tr><td colspan="7" class="empty">Failed to load history.</td></tr>';
    }
  }

  function renderHistory(rows) {
    const tbody = document.getElementById('history-body');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">No sync runs yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${r.object_name}</td>
        <td>${r.sync_mode || '—'}</td>
        <td><span class="pill ${r.status}">${r.status}</span></td>
        <td>${r.rows_loaded != null ? r.rows_loaded.toLocaleString() : '—'}</td>
        <td>${r.started_at || '—'}</td>
        <td>${r.duration_sec != null ? r.duration_sec + 's' : '—'}</td>
        <td><div class="error-msg" title="${r.error_message || ''}">${r.error_message || '—'}</div></td>
      </tr>`).join('');
  }

  // ── Sync triggers ─────────────────────────────────────────────────────────

  async function syncOne(objectName, mode) {
    showToast(`Starting ${mode} sync for ${objectName}...`);
    await fetch(`/api/sync?object_name=${objectName}&mode=${mode}`, { method: 'POST' });
    setTimeout(loadStatus, 1000);
  }

  async function syncAll() {
    showToast('Starting sync for all objects...');
    await fetch('/api/sync', { method: 'POST' });
    setTimeout(loadStatus, 1000);
  }

  // ── Toast ─────────────────────────────────────────────────────────────────

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3000);
  }

  // ── Auto-refresh every 10s ────────────────────────────────────────────────

  function refresh() {
    loadStatus();
    loadHistory();
  }

  refresh();
  setInterval(refresh, 10000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("dashboard:app", host="0.0.0.0", port=8000, reload=False)