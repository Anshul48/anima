/**
 * AuDHD State Space Tree Visualizer Client Script
 */

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

function initVisualizer(containerId, options = {}) {
    const cy = cytoscape({
        container: document.getElementById(containerId),
        elements: [],
        style: [
            {
                selector: 'node',
                style: {
                    'background-color': 'data(bgColor)',
                    'border-color': 'data(borderColor)',
                    'border-width': 'data(borderWidth)',
                    'label': 'data(label)',
                    'color': '#f0f6fc',
                    'font-size': '11px',
                    'text-valign': 'bottom',
                    'text-margin-y': 6,
                    'width': 36,
                    'height': 36
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 'data(lineWidth)',
                    'line-color': 'data(lineColor)',
                    'target-arrow-color': 'data(targetArrowColor)',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'arrow-scale': 1.2
                }
            }
        ],
        layout: {
            name: 'dagre',
            rankDir: 'TB',
            nodeSep: 60,
            rankSep: 80
        }
    });

    return cy;
}
