/**
 * Reflex DOM Distiller
 * Extracts semantic, interactive, and structural UI elements from Chromium DOM,
 * including Shadow DOM roots and nested accessible iframes.
 * Computes bounding boxes and evaluates topmost element occlusion (elementFromPoint).
 */

(function () {
  'use strict';

  const IGNORED_TAGS = new Set([
    'SCRIPT', 'STYLE', 'META', 'HEAD', 'LINK', 'NOSCRIPT',
    'TEMPLATE', 'DEFS', 'PARAM', 'SOURCE', 'TRACK'
  ]);

  const INTERACTIVE_TAGS = new Set([
    'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'OPTION',
    'DETAILS', 'SUMMARY', 'A'
  ]);

  const TEXT_TAGS = new Set([
    'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
    'P', 'SPAN', 'LABEL', 'STRONG', 'EM', 'B', 'I', 'U', 'LI', 'CODE', 'PRE'
  ]);

  const CONTAINER_TAGS = new Set([
    'NAV', 'MAIN', 'SECTION', 'ARTICLE', 'FORM', 'HEADER', 'FOOTER',
    'TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH', 'UL', 'OL', 'DIALOG', 'DIV'
  ]);

  let nodeCounter = 0;

  function generateNodeId(el, prefix = 'node') {
    if (el.id && typeof el.id === 'string' && el.id.trim() !== '') {
      return `${prefix}_${el.id.trim()}`;
    }
    nodeCounter += 1;
    return `${prefix}_${nodeCounter}`;
  }

  function getEffectiveBounds(el, frameOffsetX = 0, frameOffsetY = 0) {
    const rect = el.getBoundingClientRect();
    return {
      x1: Math.round(rect.left + frameOffsetX),
      y1: Math.round(rect.top + frameOffsetY),
      x2: Math.round(rect.right + frameOffsetX),
      y2: Math.round(rect.bottom + frameOffsetY),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      rawLeft: rect.left + frameOffsetX,
      rawTop: rect.top + frameOffsetY,
      rawWidth: rect.width,
      rawHeight: rect.height,
    };
  }

  function isVisible(el, bounds, style) {
    if (!style) {
      style = window.getComputedStyle(el);
    }
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden' || style.visibility === 'collapse') return false;
    if (parseFloat(style.opacity || '1') <= 0) return false;
    if (bounds.width <= 0 && bounds.height <= 0) {
      // Element may only contain visible absolute/child elements
      return el.children.length > 0;
    }
    return true;
  }

  function checkTopmost(el, bounds) {
    if (bounds.width <= 0 || bounds.height <= 0) return false;

    // Viewport coordinates
    const rect = el.getBoundingClientRect();
    const cx = Math.floor(rect.left + rect.width / 2);
    const cy = Math.floor(rect.top + rect.height / 2);

    const vpWidth = window.innerWidth || document.documentElement.clientWidth;
    const vpHeight = window.innerHeight || document.documentElement.clientHeight;

    // Check if center is in viewport
    if (cx < 0 || cx > vpWidth || cy < 0 || cy > vpHeight) {
      // Check if any corner is in viewport
      const testPoints = [
        [Math.floor(rect.left + 2), Math.floor(rect.top + 2)],
        [Math.floor(rect.right - 2), Math.floor(rect.top + 2)],
        [Math.floor(rect.left + 2), Math.floor(rect.bottom - 2)],
        [Math.floor(rect.right - 2), Math.floor(rect.bottom - 2)],
      ];
      for (const [px, py] of testPoints) {
        if (px >= 0 && px <= vpWidth && py >= 0 && py <= vpHeight) {
          const topEl = document.elementFromPoint(px, py);
          if (topEl && (topEl === el || el.contains(topEl) || topEl.contains(el))) {
            return true;
          }
        }
      }
      return false;
    }

    const topEl = document.elementFromPoint(cx, cy);
    if (!topEl) return false;

    if (topEl === el || el.contains(topEl)) {
      return true;
    }

    // If topEl is an ancestor, check if topEl has pointer-events or is a container
    if (topEl.contains(el)) {
      // If el is covered by a modal/overlay backdrop that is a sibling or outside ancestor, topEl would be the overlay
      return true;
    }

    return false;
  }

  function inferRole(el, tag, explicitRole, style) {
    if (explicitRole) {
      const lower = explicitRole.toLowerCase().trim();
      if (lower === 'button') return 'button';
      if (lower === 'textbox' || lower === 'searchbox') return 'input';
      if (lower === 'checkbox') return 'checkbox';
      if (lower === 'radio') return 'radio';
      if (lower === 'switch') return 'toggle';
      if (lower === 'link') return 'link';
      if (lower === 'dialog' || lower === 'alertdialog') return 'modal';
      if (lower === 'scrollbar') return 'scrollbar';
      if (lower === 'img' || lower === 'image') return 'image';
      if (lower === 'region' || lower === 'group' || lower === 'main' || lower === 'navigation' || lower === 'form') return 'container';
      return lower;
    }

    if (tag === 'BUTTON') return 'button';
    if (tag === 'A' && (el.hasAttribute('href') || el.hasAttribute('onclick') || el.getAttribute('role') === 'link')) return 'link';
    if (tag === 'INPUT') {
      const type = (el.type || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button' || type === 'reset') return 'button';
      return 'input';
    }
    if (tag === 'TEXTAREA' || tag === 'SELECT') return 'input';
    if (tag === 'IMG' || tag === 'CANVAS') return 'image';
    if (tag === 'DIALOG' || el.getAttribute('aria-modal') === 'true') return 'modal';
    if (TEXT_TAGS.has(tag)) return 'text';
    if (CONTAINER_TAGS.has(tag)) return 'container';

    if (style && style.cursor === 'pointer') return 'button';
    return 'unknown';
  }

  function extractLabel(el, tag, explicitRole) {
    // 1. aria-label
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();

    // 2. aria-labelledby
    const ariaLabelledby = el.getAttribute('aria-labelledby');
    if (ariaLabelledby) {
      const target = document.getElementById(ariaLabelledby.trim());
      if (target && target.innerText && target.innerText.trim()) {
        return target.innerText.trim();
      }
    }

    // 3. title or alt
    if (el.title && el.title.trim()) return el.title.trim();
    if (el.alt && el.alt.trim()) return el.alt.trim();

    // 4. placeholder
    if (el.placeholder && el.placeholder.trim()) return el.placeholder.trim();

    // 5. associated <label for="...">
    if (el.id) {
      const labelEl = document.querySelector(`label[for="${el.id}"]`);
      if (labelEl && labelEl.innerText && labelEl.innerText.trim()) {
        return labelEl.innerText.trim();
      }
    }

    // 6. submit/button value
    if (tag === 'INPUT' && ['submit', 'button', 'reset'].includes((el.type || '').toLowerCase())) {
      if (el.value && el.value.trim()) return el.value.trim();
    }

    // 7. innerText / textContent for leaf/interactive/text nodes
    if (tag === 'BUTTON' || tag === 'A' || tag === 'OPTION' || tag === 'SUMMARY' || TEXT_TAGS.has(tag)) {
      const text = el.innerText || el.textContent || '';
      const clean = text.replace(/\s+/g, ' ').trim();
      if (clean) return clean;
    }

    return '';
  }

  function extractValue(el, tag) {
    if (tag === 'INPUT') {
      const type = (el.type || '').toLowerCase();
      if (type === 'checkbox' || type === 'radio') {
        return el.checked ? 'checked' : 'unchecked';
      }
      return el.value || '';
    }
    if (tag === 'TEXTAREA') return el.value || '';
    if (tag === 'SELECT') {
      if (el.selectedOptions && el.selectedOptions.length > 0) {
        return el.selectedOptions[0].text || el.value || '';
      }
      return el.value || '';
    }
    if (el.getAttribute('contenteditable') === 'true') {
      return (el.innerText || el.textContent || '').trim();
    }
    return '';
  }

  function extractAttributes(el, isTopmost) {
    const attrs = {};
    if (el.id) attrs['id'] = el.id;
    if (el.className && typeof el.className === 'string') attrs['class'] = el.className.trim();
    if (el.name) attrs['name'] = el.name;
    if (el.type) attrs['type'] = el.type;
    if (el.placeholder) attrs['placeholder'] = el.placeholder;
    if (el.href) attrs['href'] = el.href;
    if (el.src) attrs['src'] = el.src;
    if (el.title) attrs['title'] = el.title;
    if (el.hasAttribute('role')) attrs['role'] = el.getAttribute('role');
    if (el.hasAttribute('aria-label')) attrs['aria-label'] = el.getAttribute('aria-label');
    if (el.hasAttribute('aria-modal')) attrs['aria-modal'] = el.getAttribute('aria-modal');
    if (el.hasAttribute('aria-hidden')) attrs['aria-hidden'] = el.getAttribute('aria-hidden');
    if (el.hasAttribute('aria-disabled')) attrs['aria-disabled'] = el.getAttribute('aria-disabled');
    if (el.hasAttribute('data-testid')) attrs['data-testid'] = el.getAttribute('data-testid');

    attrs['is_topmost'] = isTopmost;
    return attrs;
  }

  function traverseNode(domNode, parentNodeId, frameOffsetX, frameOffsetY, prefix, collectedNodes) {
    if (!domNode || domNode.nodeType !== 1) return null; // Only Element nodes

    const tag = domNode.tagName.toUpperCase();
    if (IGNORED_TAGS.has(tag)) return null;

    const style = window.getComputedStyle(domNode);
    const bounds = getEffectiveBounds(domNode, frameOffsetX, frameOffsetY);

    if (!isVisible(domNode, bounds, style)) {
      return null;
    }

    const explicitRole = domNode.getAttribute('role');
    const roleStr = inferRole(domNode, tag, explicitRole, style);
    const isTopmost = checkTopmost(domNode, bounds);
    const label = extractLabel(domNode, tag, explicitRole);
    const value = extractValue(domNode, tag);

    const isInteractive = INTERACTIVE_TAGS.has(tag) ||
      ['button', 'input', 'checkbox', 'radio', 'toggle', 'link', 'modal'].includes(roleStr) ||
      domNode.hasAttribute('onclick') ||
      domNode.onclick !== null ||
      domNode.tabIndex >= 0 ||
      domNode.getAttribute('contenteditable') === 'true' ||
      (style && style.cursor === 'pointer');

    const isEditable = (tag === 'INPUT' && !['submit', 'button', 'reset', 'checkbox', 'radio'].includes((domNode.type || '').toLowerCase())) ||
      tag === 'TEXTAREA' ||
      domNode.getAttribute('contenteditable') === 'true';

    const isFocused = document.activeElement === domNode;
    const isEnabled = !domNode.disabled && domNode.getAttribute('aria-disabled') !== 'true';
    const isClickable = isInteractive && isEnabled && isTopmost;

    const nodeId = generateNodeId(domNode, prefix);
    const attributes = extractAttributes(domNode, isTopmost);

    const nodeRecord = {
      node_id: nodeId,
      role: roleStr,
      bounds: {
        x1: bounds.x1,
        y1: bounds.y1,
        x2: bounds.x2,
        y2: bounds.y2,
      },
      label: label,
      value: value,
      is_clickable: isClickable,
      is_editable: isEditable,
      is_focused: isFocused,
      is_enabled: isEnabled,
      parent_id: parentNodeId,
      children_ids: [],
      source: 'dom',
      confidence: 1.0,
      attributes: attributes,
      tag: tag.toLowerCase(),
      _isInteractive: isInteractive,
      _hasText: label.length > 0,
      _isSemanticContainer: ['modal', 'container'].includes(roleStr) && ['DIALOG', 'FORM', 'TABLE', 'NAV', 'MAIN', 'SECTION', 'ARTICLE', 'HEADER', 'FOOTER', 'TR'].includes(tag),
    };

    // Traverse Shadow DOM Root if present
    const childIds = [];
    if (domNode.shadowRoot) {
      const shadowChildren = domNode.shadowRoot.children;
      for (let i = 0; i < shadowChildren.length; i++) {
        const childId = traverseNode(shadowChildren[i], nodeId, frameOffsetX, frameOffsetY, `${prefix}_shadow`, collectedNodes);
        if (childId) childIds.push(childId);
      }
    }

    // Traverse Iframe document if accessible
    if (tag === 'IFRAME') {
      try {
        const iframeDoc = domNode.contentDocument || (domNode.contentWindow && domNode.contentWindow.document);
        if (iframeDoc && iframeDoc.body) {
          const iframeRect = domNode.getBoundingClientRect();
          const iframeOffsetX = frameOffsetX + iframeRect.left;
          const iframeOffsetY = frameOffsetY + iframeRect.top;
          const iframeChildren = iframeDoc.body.children;
          for (let i = 0; i < iframeChildren.length; i++) {
            const childId = traverseNode(iframeChildren[i], nodeId, iframeOffsetX, iframeOffsetY, `${prefix}_frame`, collectedNodes);
            if (childId) childIds.push(childId);
          }
        }
      } catch (e) {
        // Cross-origin iframe security error, skip iframe subtree
      }
    }

    // Traverse standard DOM children
    const domChildren = domNode.children;
    for (let i = 0; i < domChildren.length; i++) {
      const child = domChildren[i];
      const childId = traverseNode(child, nodeId, frameOffsetX, frameOffsetY, prefix, collectedNodes);
      if (childId) childIds.push(childId);
    }

    nodeRecord.children_ids = childIds;

    // Prune rule: Retain node if:
    // 1. Interactive
    // 2. Has text / label
    // 3. Semantic container
    // 4. Or has retained child nodes
    const shouldRetain = nodeRecord._isInteractive ||
      nodeRecord._hasText ||
      nodeRecord._isSemanticContainer ||
      childIds.length > 0;

    if (shouldRetain) {
      delete nodeRecord._isInteractive;
      delete nodeRecord._hasText;
      delete nodeRecord._isSemanticContainer;
      collectedNodes[nodeId] = nodeRecord;
      return nodeId;
    }

    return null;
  }

  function distill() {
    nodeCounter = 0;
    const collectedNodes = {};
    const root = document.body || document.documentElement;

    if (root) {
      traverseNode(root, null, 0, 0, 'node', collectedNodes);
    }

    const focusedId = document.activeElement && document.activeElement !== document.body
      ? (document.activeElement.id ? `node_${document.activeElement.id}` : null)
      : null;

    return {
      url: window.location.href || '',
      title: document.title || '',
      viewport_size: [
        window.innerWidth || document.documentElement.clientWidth || 1920,
        window.innerHeight || document.documentElement.clientHeight || 1080
      ],
      focused_node_id: focusedId,
      nodes: collectedNodes,
    };
  }

  // Execute and return result
  return distill();
})();
