"""Interactive State Space Tree (SST) DAG Visualizer with SSE Streaming and REST Endpoints."""

from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sst.core.models import SSTTree
from sst.storage.serializer import serialize_sst_tree


def render_html_visualizer(tree_data: dict[str, Any]) -> str:
    """Renders a self-contained interactive HTML/JS visualization for State Space Trees with XSS escaping."""
    # Prevent closing script tag injection
    data_json = json.dumps(tree_data).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AuDHD State Space Tree Visualizer</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dagre@0.8.5/dist/dagre.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/cytoscape-dagre@2.5.0/cytoscape-dagre.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }}
        body {{ background-color: #0d1117; color: #c9d1d9; display: flex; height: 100vh; overflow: hidden; }}
        #sidebar {{ width: 390px; background: #161b22; border-right: 1px solid #30363d; display: flex; flex-direction: column; }}
        #header {{ padding: 16px; border-bottom: 1px solid #30363d; background: #21262d; }}
        #header-top {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }}
        #header h1 {{ font-size: 1.1rem; color: #58a6ff; display: flex; align-items: center; gap: 8px; }}
        #header p {{ font-size: 0.8rem; color: #8b949e; }}
        #live-indicator {{ font-size: 0.75rem; font-weight: bold; color: #3fb950; display: inline-flex; align-items: center; gap: 4px; }}
        .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; text-transform: uppercase; }}
        .badge-adhd {{ background: #ff7b7233; color: #ff7b72; border: 1px solid #ff7b72; }}
        .badge-asd {{ background: #79c0ff33; color: #79c0ff; border: 1px solid #79c0ff; }}
        .badge-cortex {{ background: #d2a8ff33; color: #d2a8ff; border: 1px solid #d2a8ff; }}
        .badge-pass {{ background: #3fb95033; color: #3fb950; border: 1px solid #3fb950; }}
        .badge-pruned {{ background: #f8514933; color: #f85149; border: 1px solid #f85149; }}
        .badge-epoch {{ background: #e3b34122; color: #e3b341; border: 1px solid #e3b341; }}
        .badge-superseded {{ background: #8b949e22; color: #8b949e; border: 1px dashed #8b949e; }}
        .badge-concept {{ background: #8957e533; color: #d2a8ff; border: 1px solid #d2a8ff; }}
        .badge-hypothesis {{ background: #d2992233; color: #d29922; border: 1px solid #d29922; }}
        #stats {{ padding: 12px 16px; border-bottom: 1px solid #30363d; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; font-size: 0.75rem; text-align: center; }}
        .stat-box {{ background: #0d1117; padding: 8px; border-radius: 6px; border: 1px solid #30363d; }}
        .stat-val {{ font-size: 1.1rem; font-weight: bold; color: #f0f6fc; }}
        #details {{ flex: 1; padding: 16px; overflow-y: auto; font-size: 0.85rem; }}
        .detail-row {{ margin-bottom: 12px; }}
        .detail-label {{ color: #8b949e; font-size: 0.75rem; text-transform: uppercase; margin-bottom: 4px; }}
        .code-box {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px; font-size: 0.75rem; overflow-x: auto; white-space: pre-wrap; word-break: break-word; color: #7ee787; max-height: 250px; }}
        .markdown-rendered {{ color: #c9d1d9; line-height: 1.5; font-size: 0.85rem; }}
        .markdown-rendered h1, .markdown-rendered h2, .markdown-rendered h3 {{ color: #58a6ff; margin: 12px 0 6px 0; font-size: 0.95rem; }}
        .markdown-rendered p {{ margin-bottom: 8px; }}
        .markdown-rendered ul, .markdown-rendered ol {{ margin-left: 20px; margin-bottom: 8px; }}
        .markdown-rendered code {{ background: #0d1117; padding: 2px 4px; border-radius: 3px; color: #7ee787; font-size: 0.8rem; }}
        .markdown-rendered pre {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px; margin: 8px 0; overflow-x: auto; }}
        .markdown-rendered blockquote {{ border-left: 3px solid #58a6ff; padding-left: 8px; color: #8b949e; margin: 8px 0; }}
        #main-area {{ flex: 1; display: flex; flex-direction: column; height: 100vh; position: relative; overflow: hidden; }}
        #cy {{ flex: 1; width: 100%; height: calc(100% - 58px); }}
        .controls {{ position: absolute; top: 16px; right: 16px; display: flex; gap: 8px; z-index: 10; align-items: center; }}
        .btn {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.8rem; transition: background 0.15s; }}
        .btn:hover {{ background: #30363d; color: #58a6ff; }}
        .btn-primary {{ background: #238636; border-color: #2ea043; color: #ffffff; font-weight: bold; }}
        .btn-primary:hover {{ background: #2ea043; color: #ffffff; }}
        .select-btn {{ background: #21262d; border: 1px solid #30363d; color: #c9d1d9; padding: 6px 10px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; outline: none; }}
        .select-btn:hover {{ border-color: #58a6ff; }}
        .toggle-label {{ display: inline-flex; align-items: center; gap: 6px; font-size: 0.75rem; color: #8b949e; background: #21262d; border: 1px solid #30363d; padding: 5px 8px; border-radius: 6px; cursor: pointer; }}
        #timeline-bar {{ height: 58px; background: #161b22; border-top: 1px solid #30363d; display: flex; align-items: center; padding: 0 16px; gap: 12px; z-index: 20; }}
        #timeline-controls {{ display: flex; align-items: center; gap: 6px; }}
        #timeline-slider {{ flex: 1; cursor: pointer; accent-color: #58a6ff; }}
        #timeline-label {{ font-size: 0.75rem; color: #8b949e; white-space: nowrap; min-width: 170px; font-variant-numeric: tabular-nums; }}
    </style>
</head>
<body>
    <div id="sidebar">
        <div id="header">
            <div id="header-top">
                <h1>🌲 AuDHD State Space Tree</h1>
                <span id="live-indicator">● LIVE SSE</span>
            </div>
            <p id="tree-goal">Loading goal...</p>
        </div>
        <div id="stats">
            <div class="stat-box"><div class="stat-val" id="stat-nodes">0</div><div>Total Nodes</div></div>
            <div class="stat-box"><div class="stat-val" id="stat-active" style="color:#58a6ff">0</div><div>Active</div></div>
            <div class="stat-box"><div class="stat-val" id="stat-pruned" style="color:#f85149">0</div><div>Pruned</div></div>
        </div>
        <div id="details">
            <p style="color:#8b949e; text-align:center; margin-top:40px;">Select a node in the graph to inspect rollout details, concept lineages, and markdown notes.</p>
        </div>
    </div>
    <div id="main-area">
        <div id="cy"></div>
        <div class="controls">
            <select id="layout-select" class="select-btn" onchange="switchLayout(this.value)">
                <option value="TB">Layout: Hierarchical (TB)</option>
                <option value="LR">Layout: Chronological (LR)</option>
                <option value="concentric">Layout: Concentric (Epochs)</option>
                <option value="breadthfirst">Layout: Breadthfirst</option>
            </select>
            <label class="toggle-label" title="Dim superseded or expired nodes">
                <input type="checkbox" id="toggle-dim-superseded" checked onchange="handleDimToggle()">
                <span>Dim Superseded</span>
            </label>
            <button class="btn" onclick="cy.fit(null, 40)">Fit View</button>
            <button class="btn" onclick="resetCurrentLayout()">Reset</button>
        </div>
        <div id="timeline-bar">
            <div id="timeline-controls">
                <button class="btn btn-primary" id="btn-play" onclick="togglePlayReplay()">▶ Play</button>
                <button class="btn" id="btn-step-prev" onclick="stepTimeline(-1)" title="Previous Milestone">⏮</button>
                <button class="btn" id="btn-step-next" onclick="stepTimeline(1)" title="Next Milestone">⏭</button>
                <button class="btn" id="btn-all-time" onclick="resetToAllTime()" title="Show All History">All Time</button>
            </div>
            <input type="range" id="timeline-slider" min="0" max="0" value="0" oninput="handleSliderChange(this.value)">
            <span id="timeline-label">Epoch: All Time</span>
        </div>
    </div>

    <script id="sst-data" type="application/json">{data_json}</script>

    <script>
        function escapeHtml(text) {{
            if (!text) return "";
            const div = document.createElement("div");
            div.textContent = String(text);
            return div.innerHTML;
        }}

        function renderMarkdown(md) {{
            if (!md) return "";
            if (window.marked && typeof window.marked.parse === 'function') {{
                try {{
                    return window.marked.parse(md);
                }} catch (e) {{}}
            }}
            // Built-in fallback parser
            let html = escapeHtml(md);
            // Code blocks
            html = html.replace(/```([a-zA-Z0-9_]*)\\n([\\s\\S]*?)```/g, '<pre class="code-box"><code>$2</code></pre>');
            // Inline code
            html = html.replace(/`([^`]+)`/g, '<code style="background:#21262d; padding:2px 4px; border-radius:4px; color:#7ee787;">$1</code>');
            // Headers
            html = html.replace(/^### (.*$)/gim, '<h4 style="color:#58a6ff; margin:10px 0 4px;">$1</h4>');
            html = html.replace(/^## (.*$)/gim, '<h3 style="color:#58a6ff; margin:12px 0 6px;">$1</h3>');
            html = html.replace(/^# (.*$)/gim, '<h2 style="color:#58a6ff; margin:14px 0 8px;">$1</h2>');
            // Wikilinks [[Target|Display]] and [[Target]]
            html = html.replace(/\\[\\[([^\\]|]+)\\|([^\\]]+)\\]\\]/g, '<span class="badge badge-asd" style="cursor:pointer;" onclick="selectNodeById(\\'$1\\')">🔗 $2</span>');
            html = html.replace(/\\[\\[([^\\]]+)\\]\\]/g, '<span class="badge badge-asd" style="cursor:pointer;" onclick="selectNodeById(\\'$1\\')">🔗 $1</span>');
            // Callouts > [!...]\n> ...
            html = html.replace(/^>\\s*\\[!([a-zA-Z]+)\\]\\s*(.*)\\n((?:^>.*$\\n?)*)/gim, function(match, type, title, body) {{
                const cleanBody = body.replace(/^>\\s?/gm, '').trim();
                return `<div style="background:#21262d; border-left:3px solid #58a6ff; padding:8px 12px; margin:8px 0; border-radius:4px;"><strong style="color:#58a6ff;">[${{type.toUpperCase()}}] ${{title}}</strong><div style="margin-top:4px;">${{cleanBody}}</div></div>`;
            }});
            // Bold & italic
            html = html.replace(/\\*\\*([^\\*]+)\\*\\*/g, '<strong>$1</strong>');
            html = html.replace(/\\*([^\\*]+)\\*/g, '<em>$1</em>');
            // Bullet lists
            html = html.replace(/^\\s*-\\s+(.*$)/gim, '<li style="margin-left:16px;">$1</li>');
            // Line breaks
            html = html.replace(/\\n\\n/g, '<br><br>');
            return html;
        }}

        function selectNodeById(targetId) {{
            if (!targetId) return;
            let cleanId = targetId.split('/').pop().replace(/\\.md$/, '');
            let target = cy.getElementById(targetId);
            if (!target || target.length === 0) {{
                target = cy.getElementById(cleanId);
            }}
            if (!target || target.length === 0) {{
                target = cy.nodes().filter(n => {{
                    const nid = String(n.data('id')).toLowerCase();
                    const full = String(n.data('fullTitle') || '').toLowerCase();
                    const query = cleanId.toLowerCase();
                    return nid === query || full.includes(query);
                }});
            }}
            if (target && target.length > 0) {{
                cy.center(target);
                target.emit('tap');
            }}
        }}

        const cy = cytoscape({{
            container: document.getElementById('cy'),
            elements: [],
            style: [
                {{
                    selector: 'node',
                    style: {{
                        'background-color': 'data(bgColor)',
                        'border-color': 'data(borderColor)',
                        'border-width': 'data(borderWidth)',
                        'border-style': 'data(borderStyle)',
                        'label': 'data(label)',
                        'color': '#f0f6fc',
                        'font-size': '11px',
                        'text-valign': 'bottom',
                        'text-margin-y': 6,
                        'width': 'data(nodeSize)',
                        'height': 'data(nodeSize)',
                        'shape': 'data(shape)',
                        'opacity': 'data(opacity)'
                    }}
                }},
                {{
                    selector: 'node:selected',
                    style: {{
                        'border-color': '#58a6ff',
                        'border-width': 4,
                        'shadow-blur': 12,
                        'shadow-color': '#58a6ff'
                    }}
                }},
                {{
                    selector: 'edge',
                    style: {{
                        'width': 'data(lineWidth)',
                        'line-color': 'data(lineColor)',
                        'target-arrow-color': 'data(targetArrowColor)',
                        'target-arrow-shape': 'triangle',
                        'curve-style': 'bezier',
                        'arrow-scale': 1.2,
                        'line-style': 'data(lineStyle)',
                        'opacity': 'data(opacity)'
                    }}
                }}
            ],
            layout: {{
                name: 'dagre',
                rankDir: 'TB',
                nodeSep: 60,
                rankSep: 80
            }}
        }});

        // State variables
        let currentTreeData = null;
        let timelineMilestones = [];
        let replayTimer = null;
        let currentLayoutName = 'TB';

        function switchLayout(layoutName) {{
            currentLayoutName = layoutName;
            resetCurrentLayout();
        }}

        function resetCurrentLayout() {{
            if (currentLayoutName === 'TB') {{
                cy.layout({{ name: 'dagre', rankDir: 'TB', nodeSep: 60, rankSep: 80 }}).run();
            }} else if (currentLayoutName === 'LR') {{
                cy.layout({{ name: 'dagre', rankDir: 'LR', nodeSep: 50, rankSep: 90 }}).run();
            }} else if (currentLayoutName === 'concentric') {{
                cy.layout({{
                    name: 'concentric',
                    concentric: function(node) {{
                        return node.data('epoch') !== undefined ? node.data('epoch') : (node.data('depth') || 0);
                    }},
                    levelWidth: function() {{ return 1; }},
                    padding: 40
                }}).run();
            }} else if (currentLayoutName === 'breadthfirst') {{
                cy.layout({{ name: 'breadthfirst', directed: true, padding: 40, spacingFactor: 1.3 }}).run();
            }}
        }}

        function buildMilestones(nodes) {{
            if (!nodes || nodes.length === 0) return [];
            const milestoneMap = new Map();

            nodes.forEach(node => {{
                let ts = null;
                if (node.createdAt) {{
                    const d = new Date(node.createdAt);
                    if (!isNaN(d.getTime())) ts = d.getTime();
                }}
                const epoch = node.epoch !== undefined ? node.epoch : (node.depth !== undefined ? node.depth : 0);
                const dateKey = node.createdAt ? node.createdAt.slice(0, 10) : `Epoch ${{epoch}}`;
                const key = `${{epoch}}_${{dateKey}}`;

                if (!milestoneMap.has(key)) {{
                    milestoneMap.set(key, {{
                        key: key,
                        epoch: epoch,
                        timestamp: ts,
                        dateStr: dateKey,
                        label: `Epoch ${{epoch}} (${{dateKey}})`
                    }});
                }}
            }});

            const sorted = Array.from(milestoneMap.values()).sort((a, b) => {{
                if (a.epoch !== b.epoch) return a.epoch - b.epoch;
                if (a.timestamp && b.timestamp) return a.timestamp - b.timestamp;
                return a.dateStr.localeCompare(b.dateStr);
            }});

            return sorted;
        }}

        function applyTreeData(treeData) {{
            if (!treeData) return;
            currentTreeData = treeData;

            document.getElementById('tree-goal').textContent = treeData.rootGoal || "SST Search Goal";
            document.getElementById('stat-nodes').textContent = treeData.totalNodeCount !== undefined ? treeData.totalNodeCount : (treeData.nodes ? treeData.nodes.length : 0);
            document.getElementById('stat-active').textContent = treeData.activeFrontierCount || 0;
            document.getElementById('stat-pruned').textContent = treeData.prunedNodeCount || 0;

            const elements = [];
            const winningSet = new Set(treeData.winningPath || []);

            if (treeData.nodes) {{
                treeData.nodes.forEach(node => {{
                    const isWinning = winningSet.has(node.id);
                    const status = String(node.status || 'ACTIVE').toUpperCase();
                    const role = String(node.role || 'NODE');
                    const epoch = node.epoch !== undefined ? node.epoch : (node.depth !== undefined ? node.depth : 0);

                    let bgColor = '#30363d';
                    let borderColor = '#8b949e';
                    let shape = 'ellipse';
                    let nodeSize = 36;
                    let borderStyle = 'solid';
                    let opacity = 1.0;

                    const isBridge = role.includes('SYNTHESIZE') || String(node.id).startsWith('bridge_') || node.payloadType === 'SYNTHESIS';
                    const isProject = role.includes('PLANNER') && node.depth === 0 || String(node.id).startsWith('proj_');
                    const isSuperseded = status === 'SUPERSEDED' || (node.validTo && new Date(node.validTo).getTime() <= Date.now());

                    if (isProject) {{
                        shape = 'round-rectangle';
                        nodeSize = 42;
                        bgColor = '#1f6feb';
                        borderColor = '#58a6ff';
                    }} else if (isBridge) {{
                        shape = 'diamond';
                        nodeSize = 40;
                        bgColor = '#8957e5';
                        borderColor = '#d2a8ff';
                    }} else if (status === 'APPROVED_CORTEX' || status === 'SYNTHESIZED' || status === 'VALIDATED' || status === 'ACTIVE') {{
                        bgColor = '#238636';
                        borderColor = '#3fb950';
                    }} else if (status.includes('FAIL') || status.includes('PRUNED')) {{
                        bgColor = '#da3633';
                        borderColor = '#f85149';
                    }} else if (status === 'PASS_DETERMINISTIC') {{
                        bgColor = '#1f6feb';
                        borderColor = '#58a6ff';
                    }} else if (status === 'HYPOTHESIS' || status === 'UNEXPANDED') {{
                        shape = 'hexagon';
                        bgColor = '#9e6a03';
                        borderColor = '#d29922';
                    }}

                    if (isSuperseded) {{
                        borderStyle = 'dashed';
                        opacity = 0.35;
                        borderColor = '#8b949e';
                    }}

                    if (isWinning) {{
                        borderColor = '#e3b341';
                    }}

                    elements.push({{
                        data: {{
                            id: node.id,
                            label: node.title.length > 25 ? node.title.substring(0, 22) + '...' : node.title,
                            fullTitle: node.title,
                            role: node.role,
                            status: node.status,
                            epoch: epoch,
                            createdAt: node.createdAt,
                            updatedAt: node.updatedAt,
                            validTo: node.validTo,
                            branchedFrom: node.branchedFrom,
                            supersededBy: node.supersededBy,
                            notes: node.notes,
                            metadata: node.metadata,
                            valueScore: node.valueScore,
                            uctScore: node.uctScore,
                            diffPreview: node.diffPreview,
                            pruneReason: node.pruneReason,
                            cortexCritique: node.cortexCritique,
                            isWinning: isWinning,
                            bgColor: bgColor,
                            borderColor: borderColor,
                            borderWidth: isWinning ? 4 : 2,
                            borderStyle: borderStyle,
                            shape: shape,
                            nodeSize: nodeSize,
                            opacity: opacity
                        }}
                    }});
                }});
            }}

            if (treeData.edges) {{
                treeData.edges.forEach(edge => {{
                    const isWinningEdge = winningSet.has(edge.source) && winningSet.has(edge.target);
                    const isMuted = edge.status && (edge.status.includes('FAIL') || edge.status === 'SUPERSEDED');
                    elements.push({{
                        data: {{
                            id: edge.id,
                            source: edge.source,
                            target: edge.target,
                            lineColor: isWinningEdge ? '#e3b341' : (isMuted ? '#484f58' : '#30363d'),
                            lineWidth: isWinningEdge ? 3 : 1.6,
                            lineStyle: isMuted ? 'dashed' : 'solid',
                            opacity: isMuted ? 0.35 : 0.85,
                            targetArrowColor: isWinningEdge ? '#e3b341' : (isMuted ? '#484f58' : '#8b949e')
                        }}
                    }});
                }});
            }}

            cy.elements().remove();
            cy.add(elements);
            resetCurrentLayout();

            // Set up timeline milestones
            timelineMilestones = buildMilestones(treeData.nodes || []);
            const slider = document.getElementById('timeline-slider');
            slider.max = timelineMilestones.length;
            slider.value = timelineMilestones.length; // Default to All Time
            updateTimelineDisplay(timelineMilestones.length);
        }}

        function handleSliderChange(val) {{
            const idx = parseInt(val, 10);
            updateTimelineDisplay(idx);
        }}

        function handleDimToggle() {{
            const slider = document.getElementById('timeline-slider');
            updateTimelineDisplay(parseInt(slider.value, 10));
        }}

        function stepTimeline(delta) {{
            const slider = document.getElementById('timeline-slider');
            let cur = parseInt(slider.value, 10);
            let next = Math.max(0, Math.min(timelineMilestones.length, cur + delta));
            slider.value = next;
            updateTimelineDisplay(next);
        }}

        function resetToAllTime() {{
            stopReplay();
            const slider = document.getElementById('timeline-slider');
            slider.value = timelineMilestones.length;
            updateTimelineDisplay(timelineMilestones.length);
        }}

        function togglePlayReplay() {{
            if (replayTimer) {{
                stopReplay();
            }} else {{
                startReplay();
            }}
        }}

        function startReplay() {{
            const slider = document.getElementById('timeline-slider');
            if (parseInt(slider.value, 10) >= timelineMilestones.length) {{
                slider.value = 0;
                updateTimelineDisplay(0);
            }}
            document.getElementById('btn-play').textContent = '⏸ Pause';
            document.getElementById('btn-play').classList.remove('btn-primary');
            replayTimer = setInterval(() => {{
                let cur = parseInt(slider.value, 10);
                if (cur < timelineMilestones.length) {{
                    cur += 1;
                    slider.value = cur;
                    updateTimelineDisplay(cur);
                }} else {{
                    stopReplay();
                }}
            }}, 1200);
        }}

        function stopReplay() {{
            if (replayTimer) {{
                clearInterval(replayTimer);
                replayTimer = null;
            }}
            const btn = document.getElementById('btn-play');
            btn.textContent = '▶ Play';
            btn.classList.add('btn-primary');
        }}

        function updateTimelineDisplay(index) {{
            const label = document.getElementById('timeline-label');
            const dimSuperseded = document.getElementById('toggle-dim-superseded').checked;

            if (index >= timelineMilestones.length) {{
                // All Time (Full History View)
                label.textContent = "Epoch: All Time (Full History)";
                cy.nodes().forEach(n => {{
                    n.style('display', 'element');
                    const status = String(n.data('status') || '').toUpperCase();
                    const isSuperseded = status === 'SUPERSEDED' || (n.data('validTo') && new Date(n.data('validTo')).getTime() <= Date.now());
                    if (isSuperseded && dimSuperseded) {{
                        n.style('opacity', 0.25);
                        n.style('border-style', 'dashed');
                    }} else {{
                        n.style('opacity', 1.0);
                        n.style('border-style', 'solid');
                    }}
                }});
                cy.edges().forEach(e => {{
                    e.style('display', 'element');
                }});
                return;
            }}

            const milestone = timelineMilestones[index];
            label.textContent = `Milestone ${{index + 1}}/${{timelineMilestones.length}}: ${{milestone.label}}`;

            cy.nodes().forEach(n => {{
                const nEpoch = n.data('epoch') !== undefined ? n.data('epoch') : (n.data('depth') || 0);
                let nTs = null;
                if (n.data('createdAt')) {{
                    const d = new Date(n.data('createdAt'));
                    if (!isNaN(d.getTime())) nTs = d.getTime();
                }}

                // Check if node exists at this milestone
                let isBorn = false;
                if (milestone.timestamp && nTs) {{
                    isBorn = nTs <= milestone.timestamp;
                }} else {{
                    isBorn = nEpoch <= milestone.epoch;
                }}

                if (!isBorn) {{
                    n.style('display', 'none');
                }} else {{
                    n.style('display', 'element');
                    let isExpired = false;
                    if (n.data('validTo')) {{
                        const vDate = new Date(n.data('validTo'));
                        if (!isNaN(vDate.getTime()) && milestone.timestamp) {{
                            isExpired = vDate.getTime() <= milestone.timestamp;
                        }}
                    }}
                    const status = String(n.data('status') || '').toUpperCase();
                    if (status === 'SUPERSEDED' && dimSuperseded) {{
                        isExpired = true;
                    }}

                    if (isExpired && dimSuperseded) {{
                        n.style('opacity', 0.22);
                        n.style('border-style', 'dashed');
                    }} else {{
                        n.style('opacity', 1.0);
                        n.style('border-style', 'solid');
                    }}
                }}
            }});

            cy.edges().forEach(e => {{
                const src = cy.getElementById(e.data('source'));
                const tgt = cy.getElementById(e.data('target'));
                if (src.style('display') !== 'none' && tgt.style('display') !== 'none') {{
                    e.style('display', 'element');
                }} else {{
                    e.style('display', 'none');
                }}
            }});
        }}

        // Initial render from embedded data
        const initialData = JSON.parse(document.getElementById('sst-data').textContent);
        applyTreeData(initialData);

        cy.on('tap', 'node', function(evt) {{
            const d = evt.target.data();
            const details = document.getElementById('details');
            
            let roleBadge = 'badge-cortex';
            const rStr = String(d.role || '').toUpperCase();
            if (rStr.includes('ADHD') || rStr.includes('DIVERGE')) roleBadge = 'badge-adhd';
            if (rStr.includes('ASD') || rStr.includes('REFINE')) roleBadge = 'badge-asd';
            if (rStr.includes('SYNTHESIZE')) roleBadge = 'badge-concept';

            const sStr = String(d.status || '').toUpperCase();
            let statusBadge = sStr.includes('FAIL') || sStr.includes('PRUNED') ? 'badge-pruned' : 'badge-pass';
            if (sStr === 'SUPERSEDED') statusBadge = 'badge-superseded';
            if (sStr === 'HYPOTHESIS') statusBadge = 'badge-hypothesis';

            const contentText = d.notes || d.diffPreview || "No notes or content recorded.";

            details.innerHTML = `
                <div class="detail-row">
                    <div class="detail-label">Node Title</div>
                    <div style="font-weight:bold; font-size:1rem; color:#f0f6fc;">${{escapeHtml(d.fullTitle)}}</div>
                </div>
                <div class="detail-row" style="display:flex; flex-wrap:wrap; gap:6px;">
                    <span class="badge ${{roleBadge}}">${{escapeHtml(d.role)}}</span>
                    <span class="badge ${{statusBadge}}">${{escapeHtml(d.status)}}</span>
                    <span class="badge badge-epoch">Epoch ${{d.epoch}}</span>
                    ${{d.isWinning ? '<span class="badge" style="background:#e3b34133; color:#e3b341; border:1px solid #e3b341;">WINNING PATH</span>' : ''}}
                </div>

                <div class="detail-row" style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:10px;">
                    <div class="detail-label">Lineage & Temporal Coordinates</div>
                    <div style="font-size:0.75rem; color:#8b949e; line-height:1.6;">
                        ${{d.createdAt ? `<div>📅 Created: <span style="color:#c9d1d9">${{escapeHtml(d.createdAt)}}</span></div>` : ''}}
                        ${{d.validTo ? `<div>⏳ Valid To: <span style="color:#ff7b72">${{escapeHtml(d.validTo)}}</span></div>` : ''}}
                        ${{d.branchedFrom ? `<div>🌲 Branched From: <span class="badge badge-asd" style="cursor:pointer;" onclick="selectNodeById('${{escapeHtml(d.branchedFrom)}}')">🔗 ${{escapeHtml(d.branchedFrom)}}</span></div>` : ''}}
                        ${{d.supersededBy ? `<div>⚡ Superseded By: <span class="badge badge-pruned" style="cursor:pointer;" onclick="selectNodeById('${{escapeHtml(d.supersededBy)}}')">🔗 ${{escapeHtml(d.supersededBy)}}</span></div>` : ''}}
                    </div>
                </div>

                <div class="detail-row" style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                    <div class="stat-box"><div>Value Score</div><div class="stat-val" style="color:#7ee787">${{escapeHtml(d.valueScore !== undefined ? d.valueScore : "-")}}</div></div>
                    <div class="stat-box"><div>UCT Score</div><div class="stat-val" style="color:#58a6ff">${{escapeHtml(d.uctScore !== undefined ? d.uctScore : "-")}}</div></div>
                </div>

                ${{d.cortexCritique ? `
                <div class="detail-row">
                    <div class="detail-label">Cortex Critic Review</div>
                    <div style="color:#c9d1d9; font-style:italic; background:#21262d; padding:8px; border-radius:6px;">${{escapeHtml(d.cortexCritique)}}</div>
                </div>` : ''}}
                ${{d.pruneReason ? `
                <div class="detail-row">
                    <div class="detail-label">Prune Reason</div>
                    <div style="color:#ff7b72; background:#ff7b7211; padding:8px; border-radius:6px; border:1px solid #ff7b7244;">${{escapeHtml(d.pruneReason)}}</div>
                </div>` : ''}}

                <div class="detail-row">
                    <div class="detail-label">Concept / Notes / Code</div>
                    <div class="markdown-rendered" style="background:#0d1117; border:1px solid #30363d; border-radius:6px; padding:12px; max-height:360px; overflow-y:auto;">
                        ${{renderMarkdown(contentText)}}
                    </div>
                </div>
            `;
        }});

        // SSE Real-Time Streaming & Polling Fallback
        let isSSEConnected = false;
        let pollTimer = null;

        function startPolling() {{
            if (pollTimer) return;
            pollTimer = setInterval(async () => {{
                if (isSSEConnected) return;
                try {{
                    const res = await fetch('/api/tree');
                    if (res.ok) {{
                        const data = await res.json();
                        applyTreeData(data);
                    }}
                }} catch (e) {{}}
            }}, 2500);
        }}

        if (window.EventSource) {{
            try {{
                const evtSource = new EventSource('/api/stream');
                evtSource.onopen = function() {{
                    isSSEConnected = true;
                    const ind = document.getElementById('live-indicator');
                    if (ind) {{ ind.textContent = '● LIVE SSE'; ind.style.color = '#3fb950'; }}
                }};
                evtSource.onmessage = function(e) {{
                    try {{
                        const msg = JSON.parse(e.data);
                        if (msg.type === 'snapshot' && msg.tree) {{
                            applyTreeData(msg.tree);
                        }} else if (msg.type === 'delta' && msg.tree) {{
                            applyTreeData(msg.tree);
                        }} else if (msg.nodes) {{
                            applyTreeData(msg);
                        }}
                    }} catch (err) {{}}
                }};
                evtSource.onerror = function() {{
                    isSSEConnected = false;
                    const ind = document.getElementById('live-indicator');
                    if (ind) {{ ind.textContent = '● POLLING'; ind.style.color = '#e3b341'; }}
                    startPolling();
                }};
            }} catch (e) {{
                startPolling();
            }}
        }} else {{
            startPolling();
        }}
    </script>
</body>
</html>
"""


class VisualizerHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler serving interactive DAG UI, REST endpoints, and SSE stream."""

    tree_provider: Any = None
    events_provider: Any = None
    store: Any = None
    tree_id: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            tree_data = self._resolve_tree_data()
            html_content = render_html_visualizer(tree_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content)

        elif path == "/api/tree":
            tree_data = self._resolve_tree_data()
            body = json.dumps(tree_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/events":
            events_data = self._resolve_events_data()
            body = json.dumps(events_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            # Initial Snapshot Event
            tree_data = self._resolve_tree_data()
            events_data = self._resolve_events_data()
            init_payload = json.dumps({"type": "snapshot", "tree": tree_data, "events": events_data})
            self.wfile.write(f"data: {init_payload}\n\n".encode())
            self.wfile.flush()

            # Live streaming loop
            last_count = len(events_data) if isinstance(events_data, list) else 0
            while getattr(self.server, "_is_running", True):
                try:
                    time.sleep(0.5)
                    curr_events = self._resolve_events_data()
                    if isinstance(curr_events, list) and len(curr_events) > last_count:
                        new_deltas = curr_events[last_count:]
                        last_count = len(curr_events)
                        curr_tree = self._resolve_tree_data()
                        delta_msg = json.dumps({"type": "delta", "new_events": new_deltas, "tree": curr_tree})
                        self.wfile.write(f"data: {delta_msg}\n\n".encode())
                        self.wfile.flush()
                    else:
                        # Periodic Heartbeat
                        hb = json.dumps({"type": "heartbeat", "timestamp": datetime.now(UTC).isoformat()})
                        self.wfile.write(f"data: {hb}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    break

        else:
            self.send_error(404, "Endpoint not found")

    def _resolve_tree_data(self) -> dict[str, Any]:
        provider = getattr(self, "tree_provider", None)
        if callable(provider):
            res = provider()
            if isinstance(res, SSTTree):
                return serialize_sst_tree(res)
            elif isinstance(res, dict):
                return res
        elif isinstance(provider, SSTTree):
            return serialize_sst_tree(provider)
        elif isinstance(provider, dict):
            return provider

        # Fallback to store
        store = getattr(self, "store", None)
        tree_id = getattr(self, "tree_id", None)
        if store and tree_id:
            try:
                tree = store.load_tree(tree_id)
                if tree:
                    return serialize_sst_tree(tree)
            except Exception:
                pass
        return {"treeId": tree_id or "tree_unknown", "nodes": [], "edges": [], "rootGoal": "State Space Tree"}

    def _resolve_events_data(self) -> list[dict[str, Any]]:
        ev_provider = getattr(self, "events_provider", None)
        if callable(ev_provider):
            res = ev_provider()
            if isinstance(res, list):
                if res and hasattr(res[0], "event_id"):
                    return to_event_delta_payload(res)
                return res
        elif isinstance(ev_provider, list):
            if ev_provider and hasattr(ev_provider[0], "event_id"):
                return to_event_delta_payload(ev_provider)
            return ev_provider

        store = getattr(self, "store", None)
        tree_id = getattr(self, "tree_id", None)
        if store and tree_id:
            try:
                events = store.get_events(tree_id)
                return to_event_delta_payload(events)
            except Exception:
                pass
        return []

    def log_message(self, format: str, *args: Any) -> None:
        pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_visualizer_server(
    tree_data: dict[str, Any] | SSTTree | Callable[[], dict[str, Any] | SSTTree],
    port: int = 8501,
    host: str = "127.0.0.1",
    events_data: list[dict[str, Any]] | list[Any] | Callable[[], list[dict[str, Any]]] | None = None,
    store: Any | None = None,
    tree_id: str | None = None,
) -> socketserver.TCPServer:
    """Starts a local HTTP server serving the SST visualizer UI, REST API, and SSE stream."""

    class BoundHandler(VisualizerHandler):
        pass

    BoundHandler.tree_provider = tree_data
    BoundHandler.events_provider = events_data
    BoundHandler.store = store
    BoundHandler.tree_id = tree_id

    server = ThreadedTCPServer((host, port), BoundHandler)
    server._is_running = True  # type: ignore

    original_shutdown = server.shutdown

    def shutdown_with_flag() -> None:
        server._is_running = False  # type: ignore
        original_shutdown()

    server.shutdown = shutdown_with_flag  # type: ignore

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def to_cytoscape_elements(tree: SSTTree) -> list[dict[str, Any]]:
    """Converts an SSTTree DAG projection into Cytoscape.js nodes and edges elements."""
    elements: list[dict[str, Any]] = []
    winning_set = set(tree.winning_path or [])

    for node_id, node in tree.nodes.items():
        v_score = node.cortex_evaluation.value_score if node.cortex_evaluation else 0.0
        critique = node.cortex_evaluation.critique if node.cortex_evaluation else ""

        elements.append(
            {
                "group": "nodes",
                "data": {
                    "id": node_id,
                    "label": node.title[:30],
                    "role": node.role.value,
                    "status": node.status.value,
                    "depth": node.depth,
                    "valueScore": v_score,
                    "isWinning": node_id in winning_set,
                    "cortexCritique": critique,
                    "diffPreview": node.content[:500],
                    "createdAt": node.created_at.isoformat(),
                    "updatedAt": node.updated_at.isoformat(),
                    "epoch": node.metadata.get("epoch", node.depth),
                    "validTo": node.metadata.get("valid_to"),
                    "notes": node.metadata.get("notes", node.content),
                    "branchedFrom": node.metadata.get("branched_from", node.parent_id),
                    "supersededBy": node.metadata.get("superseded_by"),
                    "metadata": node.metadata,
                },
            }
        )

        parent_ids: list[str] = list(node.metadata.get("parent_ids", []))
        if node.parent_id and node.parent_id not in parent_ids:
            parent_ids.append(node.parent_id)

        for pid in parent_ids:
            if pid in tree.nodes:
                is_win_edge = (pid in winning_set) and (node_id in winning_set)
                elements.append(
                    {
                        "group": "edges",
                        "data": {
                            "id": f"e_{pid}_{node_id}",
                            "source": pid,
                            "target": node_id,
                            "isWinning": is_win_edge,
                            "createdAt": node.created_at.isoformat(),
                            "epoch": node.metadata.get("epoch", node.depth),
                            "relation": node.metadata.get("edge_relations", {}).get(pid, "CONNECTS_TO"),
                        },
                    }
                )

    return elements


def to_event_delta_payload(events: Any) -> list[dict[str, Any]]:
    """Converts a sequence of SSTEvents into a serializable delta payload for streaming clients."""
    deltas: list[dict[str, Any]] = []
    for e in events:
        deltas.append(
            {
                "event_id": e.event_id,
                "tree_id": e.tree_id,
                "node_id": e.node_id,
                "kind": e.kind.value if hasattr(e.kind, "value") else str(e.kind),
                "actor": e.actor,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if hasattr(e.created_at, "isoformat") else str(e.created_at),
            }
        )
    return deltas


def export_html_visualization(
    tree: dict[str, Any] | SSTTree,
    output_path: str | Path,
) -> Path:
    """Exports a standalone interactive HTML/JS visualization file for an SST tree."""
    tree_data = serialize_sst_tree(tree) if isinstance(tree, SSTTree) else tree
    html_content = render_html_visualizer(tree_data)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_content, encoding="utf-8")
    return out
