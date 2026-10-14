"""Local Web Trust Dashboard and User Governance Surface.

Zero external CDN dependencies (100% self-contained HTML/CSS/Vanilla JS).
Serves http://127.0.0.1:8000/ui for inspecting context, submitting corrections,
managing consent grants, and executing cascade deletions.
"""

from __future__ import annotations

from fastapi.responses import HTMLResponse

DASHBOARD_HTML: str = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Entorhinal Trust & Privacy Dashboard</title>
  <style>
    :root {
      --bg-primary: #0f172a;
      --bg-secondary: #1e293b;
      --bg-tertiary: #334155;
      --text-primary: #f8fafc;
      --text-muted: #94a3b8;
      --accent-cyan: #06b6d4;
      --accent-blue: #3b82f6;
      --accent-green: #10b981;
      --accent-red: #ef4444;
      --accent-yellow: #f59e0b;
      --accent-purple: #8b5cf6;
      --border-color: #334155;
      --radius: 8px;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
    body { background-color: var(--bg-primary); color: var(--text-primary); min-height: 100vh; display: flex; flex-direction: column; }
    header { background-color: var(--bg-secondary); border-bottom: 1px solid var(--border-color); padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
    .logo-group { display: flex; align-items: center; gap: 0.75rem; }
    .logo-badge { background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue)); color: #fff; font-weight: 800; font-size: 1.1rem; padding: 0.35rem 0.7rem; border-radius: 6px; }
    .header-title { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.025em; }
    .header-badges { display: flex; gap: 0.5rem; }
    .badge { padding: 0.25rem 0.6rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
    .badge-green { background-color: rgba(16, 185, 129, 0.2); color: var(--accent-green); border: 1px solid var(--accent-green); }
    .badge-cyan { background-color: rgba(6, 182, 212, 0.2); color: var(--accent-cyan); border: 1px solid var(--accent-cyan); }
    .badge-yellow { background-color: rgba(245, 158, 11, 0.2); color: var(--accent-yellow); border: 1px solid var(--accent-yellow); }
    
    .nav-tabs { display: flex; background-color: var(--bg-secondary); border-bottom: 1px solid var(--border-color); padding: 0 2rem; gap: 0.5rem; }
    .nav-tab { background: none; border: none; color: var(--text-muted); padding: 0.85rem 1.25rem; font-size: 0.9rem; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
    .nav-tab:hover { color: var(--text-primary); }
    .nav-tab.active { color: var(--accent-cyan); border-bottom-color: var(--accent-cyan); }

    main { flex: 1; padding: 2rem; max-width: 1400px; width: 100%; margin: 0 auto; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }

    .card { background-color: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius); padding: 1.5rem; margin-bottom: 1.5rem; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem; }
    .card-title { font-size: 1.1rem; font-weight: 600; color: var(--text-primary); }

    .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }

    .stat-box { background-color: var(--bg-tertiary); padding: 1rem; border-radius: 6px; }
    .stat-label { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.25rem; text-transform: uppercase; }
    .stat-value { font-size: 1.5rem; font-weight: 700; color: var(--text-primary); }

    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.875rem; }
    th { background-color: var(--bg-tertiary); padding: 0.75rem 1rem; font-weight: 600; color: var(--text-muted); }
    td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
    tr:hover td { background-color: rgba(255, 255, 255, 0.02); }

    .btn { background-color: var(--accent-blue); color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; font-weight: 600; cursor: pointer; transition: background 0.2s; font-size: 0.85rem; }
    .btn:hover { opacity: 0.9; }
    .btn-danger { background-color: var(--accent-red); }
    .btn-success { background-color: var(--accent-green); }
    .btn-secondary { background-color: var(--bg-tertiary); color: var(--text-primary); }

    .form-group { margin-bottom: 1rem; }
    label { display: block; font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.4rem; }
    input[type="text"], input[type="datetime-local"], select, textarea { width: 100%; padding: 0.6rem 0.8rem; background-color: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 6px; color: var(--text-primary); font-size: 0.9rem; }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--accent-cyan); }

    .node-pill { display: inline-block; background-color: var(--bg-tertiary); border: 1px solid var(--border-color); padding: 0.35rem 0.75rem; border-radius: 6px; margin: 0.25rem; font-size: 0.85rem; }
    .node-pill strong { color: var(--accent-cyan); }

    #focusCard { border-left: 4px solid var(--accent-cyan); }
    .banner-danger { background-color: rgba(239, 68, 68, 0.15); border: 1px solid var(--accent-red); padding: 1rem; border-radius: 6px; margin-bottom: 1rem; color: #fca5a5; font-size: 0.9rem; }
    .json-pre { background-color: var(--bg-primary); padding: 1rem; border-radius: 6px; overflow-x: auto; font-family: monospace; font-size: 0.8rem; color: var(--accent-cyan); max-height: 350px; }
  </style>
</head>
<body>

  <header>
    <div class="logo-group">
      <div class="logo-badge">EN</div>
      <div>
        <div class="header-title">Entorhinal Trust & Privacy Control</div>
        <div style="font-size: 0.75rem; color: var(--text-muted);">Human Sovereignty Tier & Provenance Explorer</div>
      </div>
    </div>
    <div class="header-badges">
      <span class="badge badge-green">Loopback (127.0.0.1)</span>
      <span class="badge badge-yellow">Zero Action Authority</span>
      <span class="badge badge-cyan">Epistemic Tier 6</span>
    </div>
  </header>

  <div style="padding: 0.75rem 2rem; background-color: var(--bg-secondary); border-bottom: 1px solid var(--border-color); display: flex; gap: 0.5rem; align-items: center;">
    <label for="authToken" style="font-size: 0.8rem; color: var(--text-muted);">API credential (Bearer token, admin role for governance):</label>
    <input id="authToken" type="password" placeholder="ent_..." autocomplete="off"
      style="flex: 1; max-width: 28rem; background-color: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-color); border-radius: 6px; padding: 0.4rem 0.6rem;" />
  </div>

  <div class="nav-tabs">
    <button class="nav-tab active" onclick="switchTab('tab-timeline')">Timeline & Focus</button>
    <button class="nav-tab" onclick="switchTab('tab-graph')">Semantic Graph</button>
    <button class="nav-tab" onclick="switchTab('tab-corrections')">User Corrections</button>
    <button class="nav-tab" onclick="switchTab('tab-grants')">Consent & Grants</button>
    <button class="nav-tab" onclick="switchTab('tab-forget')">Forget This (Deletion)</button>
    <button class="nav-tab" onclick="switchTab('tab-audit')">Audit Logs</button>
  </div>

  <main>
    <!-- TAB 1: TIMELINE & FOCUS -->
    <div id="tab-timeline" class="tab-content active">
      <div class="card" id="focusCard">
        <div class="card-header">
          <span class="card-title">Real-Time Foreground Immediate Focus</span>
          <span class="badge badge-cyan" id="focusDwell">0.0s Dwell</span>
        </div>
        <div class="grid-3">
          <div class="stat-box">
            <div class="stat-label">Active App</div>
            <div class="stat-value" id="focusApp">--</div>
          </div>
          <div class="stat-box" style="grid-column: span 2;">
            <div class="stat-label">Window Title / URI</div>
            <div style="font-size: 1rem; font-weight: 600; margin-top: 0.25rem;" id="focusTitle">--</div>
            <div style="font-size: 0.8rem; color: var(--accent-cyan); word-break: break-all;" id="focusUri">--</div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Durable Evidence Timeline (Append-Only Journal)</span>
          <button class="btn btn-secondary" onclick="loadTimeline()">Refresh</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>Timestamp (UTC)</th>
              <th>Source</th>
              <th>Application</th>
              <th>Window / URI</th>
              <th>Classification</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="timelineTableBody">
            <tr><td colspan="6" style="text-align: center; color: var(--text-muted);">Loading evidence records...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB 2: SEMANTIC GRAPH -->
    <div id="tab-graph" class="tab-content">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Active Entity-Relationship Graph & Derived Facts</span>
          <button class="btn btn-secondary" onclick="loadGraph()">Recompile Projections</button>
        </div>
        <div id="graphSummary" style="margin-bottom: 1rem;"></div>
        <div class="grid-2">
          <div>
            <h4 style="margin-bottom: 0.5rem; color: var(--accent-cyan);">Entity Nodes</h4>
            <div id="nodesList" style="max-height: 400px; overflow-y: auto;"></div>
          </div>
          <div>
            <h4 style="margin-bottom: 0.5rem; color: var(--accent-purple);">Active Derived Facts</h4>
            <div id="factsList" style="max-height: 400px; overflow-y: auto;"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 3: USER CORRECTIONS -->
    <div id="tab-corrections" class="tab-content">
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Submit Permanent User Correction</span>
          </div>
          <form id="correctionForm" onsubmit="submitCorrection(event)">
            <div class="form-group">
              <label>Target Fact ID or Entity URI</label>
              <input type="text" id="corrTarget" placeholder="e.g. project:org/repo or session:cluster-001" required>
            </div>
            <div class="form-group">
              <label>Override Action</label>
              <select id="corrAction">
                <option value="overwrite">OVERWRITE (Lock Value)</option>
                <option value="exclude">EXCLUDE (Suppress Fact)</option>
                <option value="delete">DELETE (Prune from Projections)</option>
              </select>
            </div>
            <div class="form-group">
              <label>Corrected Value (JSON or String)</label>
              <textarea id="corrValue" rows="3" placeholder='e.g. {"name": "Refactored Core Engine", "project": "entorhinal-v1"}'></textarea>
            </div>
            <div class="form-group">
              <label>User Note / Rationale</label>
              <input type="text" id="corrNote" placeholder="e.g. Human verified task intent">
            </div>
            <button type="submit" class="btn btn-success">Apply Override Lock (&lt;50ms)</button>
          </form>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">Active Human Override Locks</span>
            <button class="btn btn-secondary" onclick="loadCorrections()">Refresh</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Target</th>
                <th>Action</th>
                <th>Locked Value</th>
                <th>User Note</th>
              </tr>
            </thead>
            <tbody id="correctionsTableBody">
              <tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No corrections registered.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 4: CONSENT & GRANTS -->
    <div id="tab-grants" class="tab-content">
      <div class="grid-2">
        <div class="card">
          <div class="card-header">
            <span class="card-title">Add Capture Permission Rule</span>
          </div>
          <form id="grantForm" onsubmit="submitGrant(event)">
            <div class="form-group">
              <label>Source Type</label>
              <select id="grantSource">
                <option value="browser">Browser Signals</option>
                <option value="os_window">OS Window Signals</option>
                <option value="terminal_pty">Terminal PTY</option>
                <option value="user_input">User Direct Input</option>
              </select>
            </div>
            <div class="form-group">
              <label>Application Match Pattern</label>
              <input type="text" id="grantApp" value="*" placeholder="e.g. Google Chrome, Code, or *">
            </div>
            <div class="form-group">
              <label>Domain / URI Match Pattern</label>
              <input type="text" id="grantDomain" value="*" placeholder="e.g. *.internal.net or *">
            </div>
            <button type="submit" class="btn btn-success">Grant Consent Rule</button>
          </form>
        </div>

        <div class="card">
          <div class="card-header">
            <span class="card-title">Active Consent Grants</span>
            <button class="btn btn-secondary" onclick="loadGrants()">Refresh</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Permission</th>
                <th>Source</th>
                <th>App Pattern</th>
                <th>Domain Pattern</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody id="grantsTableBody">
              <tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Loading grants...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 5: FORGET THIS (DELETION) -->
    <div id="tab-forget" class="tab-content">
      <div class="card" style="border-left: 4px solid var(--accent-red);">
        <div class="card-header">
          <span class="card-title" style="color: var(--accent-red);">Cryptographic Cascade Deletion ("Forget This")</span>
        </div>
        <div class="banner-danger">
          <strong>Cryptographic Deletion Guarantee:</strong> Tombstoning securely zeroes payload bytes in the append-only journal, rewrites disk blocks, prunes all dependent semantic graph nodes, and invalidates outgoing query caches. Hash chain continuity is preserved with PROHIBITED status.
        </div>
        <form id="forgetForm" onsubmit="submitForget(event)" style="max-width: 600px;">
          <div class="form-group">
            <label>Start Timestamp</label>
            <input type="datetime-local" id="forgetStart" required>
          </div>
          <div class="form-group">
            <label>End Timestamp</label>
            <input type="datetime-local" id="forgetEnd" required>
          </div>
          <div class="form-group">
            <label>Deletion Reason</label>
            <input type="text" id="forgetReason" value="User requested cryptographic deletion via Trust Dashboard">
          </div>
          <button type="submit" class="btn btn-danger">Execute Cryptographic Deletion</button>
        </form>

        <div id="deletionResult" style="margin-top: 1.5rem; display: none;">
          <h4 style="color: var(--accent-green); margin-bottom: 0.5rem;">Proof of Deletion Report:</h4>
          <pre class="json-pre" id="deletionReportJson"></pre>
        </div>
      </div>
    </div>

    <!-- TAB 6: AUDIT LOGS -->
    <div id="tab-audit" class="tab-content">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Consumer Query & Disclosure Audit Trail</span>
          <div>
            <button class="btn btn-secondary" onclick="loadAudit()">Refresh</button>
            <button class="btn btn-success" onclick="exportData('json')">Export JSON</button>
            <button class="btn btn-secondary" onclick="exportData('zip')">Export ZIP</button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>Timestamp (UTC)</th>
              <th>Action</th>
              <th>Consumer</th>
              <th>Permitted</th>
              <th>Disclosed Facts</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="auditTableBody">
            <tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Loading audit logs...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <script>
    function authHeaders(extra) {
      const headers = Object.assign({}, extra || {});
      const box = document.getElementById('authToken');
      const token = box ? box.value.trim() : '';
      if (token) headers['Authorization'] = 'Bearer ' + token;
      return headers;
    }
    function authFetch(url, options) {
      const opts = Object.assign({}, options || {});
      opts.headers = authHeaders(opts.headers);
      return fetch(url, opts);
    }
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
      event.target.classList.add('active');

      if (tabId === 'tab-timeline') loadTimeline();
      if (tabId === 'tab-graph') loadGraph();
      if (tabId === 'tab-corrections') loadCorrections();
      if (tabId === 'tab-grants') loadGrants();
      if (tabId === 'tab-audit') loadAudit();
    }

    async function loadFocus() {
      try {
        const res = await authFetch('/api/v1/context/focus');
        if (res.ok) {
          const data = await res.json();
          document.getElementById('focusApp').textContent = data.app_identifier || 'Idle';
          document.getElementById('focusTitle').textContent = data.window_title || 'N/A';
          document.getElementById('focusUri').textContent = data.target_uri || '';
          document.getElementById('focusDwell').textContent = (data.duration_seconds || 0).toFixed(1) + 's Dwell';
        }
      } catch (e) {
        console.error('Failed to load focus:', e);
      }
    }

    async function loadTimeline() {
      try {
        const res = await authFetch('/api/v1/context/timeline');
        if (res.ok) {
          const records = await res.json();
          const tbody = document.getElementById('timelineTableBody');
          tbody.innerHTML = '';
          if (records.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No evidence records found.</td></tr>';
            return;
          }
          records.forEach(r => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td>${r.persisted_at.substring(0, 19).replace('T', ' ')}</td>
              <td><span class="badge badge-cyan">${r.source_type}</span></td>
              <td><strong>${r.app_identifier}</strong></td>
              <td style="color:var(--text-muted);">${(r.window_title || r.target_uri || '').substring(0, 60)}</td>
              <td><span class="badge ${r.classification === 'prohibited' ? 'badge-yellow' : 'badge-green'}">${r.classification}</span></td>
              <td>${r.is_tombstone ? '<span style="color:var(--accent-red); font-weight:700;">TOMBSTONED</span>' : '<span style="color:var(--accent-green);">ACTIVE</span>'}</td>
            `;
            tbody.appendChild(tr);
          });
        }
      } catch (e) {
        console.error('Failed to load timeline:', e);
      }
    }

    async function loadGraph() {
      try {
        const res = await authFetch('/api/v1/context/graph');
        if (res.ok) {
          const data = await res.json();
          document.getElementById('graphSummary').innerHTML = `
            <span class="node-pill">Nodes: <strong>${data.nodes.length}</strong></span>
            <span class="node-pill">Edges: <strong>${data.edges.length}</strong></span>
            <span class="node-pill">Active Facts: <strong>${data.facts.length}</strong></span>
          `;
          const nodesList = document.getElementById('nodesList');
          nodesList.innerHTML = data.nodes.map(n => `
            <div class="node-pill" style="display:block; margin-bottom:0.5rem;">
              <strong>[${n.entity_type}]</strong> ${n.name} <span style="font-size:0.75rem; color:var(--text-muted);">${n.entity_uri}</span>
            </div>
          `).join('') || '<div style="color:var(--text-muted);">No nodes found.</div>';

          const factsList = document.getElementById('factsList');
          factsList.innerHTML = data.facts.map(f => `
            <div class="node-pill" style="display:block; margin-bottom:0.5rem;">
              <strong>${f.attribute}:</strong> ${typeof f.value === 'object' ? JSON.stringify(f.value) : f.value}
              <div style="font-size:0.75rem; color:var(--text-muted);">${f.entity_uri} (conf: ${f.confidence})</div>
            </div>
          `).join('') || '<div style="color:var(--text-muted);">No facts found.</div>';
        }
      } catch (e) {
        console.error('Failed to load graph:', e);
      }
    }

    async function loadCorrections() {
      try {
        const res = await authFetch('/api/v1/user/corrections');
        if (res.ok) {
          const list = await res.json();
          const tbody = document.getElementById('correctionsTableBody');
          tbody.innerHTML = '';
          if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No corrections registered.</td></tr>';
            return;
          }
          list.forEach(c => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td><strong>${c.target_entity_or_fact_id}</strong></td>
              <td><span class="badge badge-yellow">${c.override_action}</span></td>
              <td><code>${JSON.stringify(c.corrected_value)}</code></td>
              <td>${c.user_comment || 'None'}</td>
            `;
            tbody.appendChild(tr);
          });
        }
      } catch (e) {
        console.error('Failed to load corrections:', e);
      }
    }

    async function submitCorrection(e) {
      e.preventDefault();
      const target = document.getElementById('corrTarget').value;
      const action = document.getElementById('corrAction').value;
      const valRaw = document.getElementById('corrValue').value;
      const note = document.getElementById('corrNote').value;

      let val = valRaw;
      try { val = JSON.parse(valRaw); } catch(_) {}

      const res = await authFetch('/api/v1/user/corrections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_entity_or_fact_id: target,
          override_action: action,
          corrected_value: val,
          user_comment: note,
        })
      });
      if (res.ok) {
        alert('Permanent User Correction Lock Applied (<50ms)!');
        document.getElementById('correctionForm').reset();
        loadCorrections();
      }
    }

    async function loadGrants() {
      try {
        const res = await authFetch('/api/v1/user/grants');
        if (res.ok) {
          const list = await res.json();
          const tbody = document.getElementById('grantsTableBody');
          tbody.innerHTML = '';
          if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Default allow policy with blacklists active.</td></tr>';
            return;
          }
          list.forEach(g => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td><span class="badge ${g.allow ? 'badge-green' : 'badge-yellow'}">${g.allow ? 'ALLOW' : 'DENY'}</span></td>
              <td>${g.source_type || '*'}</td>
              <td>${g.app_pattern || '*'}</td>
              <td>${g.domain_pattern || '*'}</td>
              <td><button class="btn btn-danger" onclick="revokeGrant('${g.rule_id}')">Revoke</button></td>
            `;
            tbody.appendChild(tr);
          });
        }
      } catch (e) {
        console.error('Failed to load grants:', e);
      }
    }

    async function submitGrant(e) {
      e.preventDefault();
      const source = document.getElementById('grantSource').value;
      const app = document.getElementById('grantApp').value;
      const domain = document.getElementById('grantDomain').value;

      const res = await authFetch('/api/v1/user/grants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: source, app_pattern: app, domain_pattern: domain })
      });
      if (res.ok) {
        alert('Grant Rule Added!');
        loadGrants();
      }
    }

    async function revokeGrant(ruleId) {
      const res = await authFetch('/api/v1/user/grants/' + ruleId, { method: 'DELETE' });
      if (res.ok) {
        loadGrants();
      }
    }

    async function submitForget(e) {
      e.preventDefault();
      const start = document.getElementById('forgetStart').value;
      const end = document.getElementById('forgetEnd').value;
      const reason = document.getElementById('forgetReason').value;

      const res = await authFetch('/api/v1/user/forget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          start_time: new Date(start).toISOString(),
          end_time: new Date(end).toISOString(),
          reason: reason,
        })
      });
      if (res.ok) {
        const report = await res.json();
        document.getElementById('deletionResult').style.display = 'block';
        document.getElementById('deletionReportJson').textContent = JSON.stringify(report, null, 2);
      }
    }

    async function loadAudit() {
      try {
        const res = await authFetch('/api/v1/user/audit');
        if (res.ok) {
          const list = await res.json();
          const tbody = document.getElementById('auditTableBody');
          tbody.innerHTML = '';
          if (list.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">No audit records found.</td></tr>';
            return;
          }
          list.forEach(ev => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
              <td>${ev.timestamp.substring(0, 19).replace('T', ' ')}</td>
              <td><strong>${ev.action}</strong></td>
              <td><span class="badge badge-cyan">${ev.consumer_id}</span></td>
              <td><span class="badge ${ev.permitted ? 'badge-green' : 'badge-yellow'}">${ev.permitted ? 'YES' : 'NO'}</span></td>
              <td>${ev.disclosed_fact_count || 0}</td>
              <td style="font-size:0.75rem; color:var(--text-muted);">${JSON.stringify(ev.details || {})}</td>
            `;
            tbody.appendChild(tr);
          });
        }
      } catch (e) {
        console.error('Failed to load audit:', e);
      }
    }

    function exportData(format) {
      window.open('/api/v1/user/export?format=' + format, '_blank');
    }

    // Auto-refresh focus every 2s
    setInterval(loadFocus, 2000);
    loadFocus();
    loadTimeline();
  </script>
</body>
</html>
"""


def get_trust_ui_html() -> HTMLResponse:
    """Return local self-contained HTML dashboard response."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)
