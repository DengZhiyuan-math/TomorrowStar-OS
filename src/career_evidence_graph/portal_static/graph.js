/* Local, documentary graph. Node size describes connections, never mastery. */
(() => {
  "use strict";

  const TYPES = {
    project: { label: "项目", color: "#dbbc7d" },
    skill: { label: "技能", color: "#86c8cb" },
    document: { label: "文档", color: "#a1aab5" },
  };
  const RELATIONS = { mentions: "文档提及", documents: "文档归属", references: "来源引用" };
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const button = (text, label, handler, className = "career-graph-button") => {
    const node = element("button", className, text);
    node.type = "button";
    if (label) { node.setAttribute("aria-label", label); node.title = label; }
    node.addEventListener("click", handler);
    return node;
  };

  function mount(container, graph, options = {}) {
    const nodes = [];
    const byId = new Map();
    for (const data of graph.nodes || []) {
      if (!data || !TYPES[data.type] || byId.has(data.id)) continue;
      const node = { ...data, label: String(data.label || "未命名"), x: 0, y: 0, vx: 0, vy: 0, degree: 0 };
      nodes.push(node);
      byId.set(node.id, node);
    }
    const links = (graph.edges || []).filter(edge => byId.has(edge.source) && byId.has(edge.target) && edge.source !== edge.target);
    const adjacency = new Map(nodes.map(node => [node.id, new Set()]));
    for (const edge of links) {
      adjacency.get(edge.source).add(edge.target);
      adjacency.get(edge.target).add(edge.source);
    }
    for (const node of nodes) node.degree = adjacency.get(node.id).size;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let destroyed = false, selected = null, hovered = null, visible = [], visibleLinks = [];
    let query = "", typeFilter = new Set(["project", "skill"]), neighborsOnly = false;
    let width = 800, height = 600, zoom = 1, panX = 400, panY = 300;
    let frame = 0, ticks = 0, dragging = null, inView = true, hasFitted = false;
    const root = element("section", "career-graph");
    root.setAttribute("aria-label", "项目与技能关系图");

    const toolbar = element("div", "career-graph-toolbar");
    const searchLabel = element("label", "career-graph-search");
    searchLabel.append(element("span", "", "⌕"));
    const search = element("input");
    search.type = "search";
    search.placeholder = "查找项目、技能或文档…";
    search.setAttribute("aria-label", "搜索关系图中的节点");
    searchLabel.append(search);
    toolbar.append(searchLabel);
    const filters = element("div", "career-graph-filters");
    filters.setAttribute("role", "group");
    filters.setAttribute("aria-label", "显示节点类型");
    const typeInputs = new Map();
    for (const [type, spec] of Object.entries(TYPES)) {
      const label = element("label", `career-graph-filter career-graph-type-${type}`);
      const input = element("input");
      input.type = "checkbox";
      input.checked = typeFilter.has(type);
      input.addEventListener("change", () => {
        if (input.checked) typeFilter.add(type); else typeFilter.delete(type);
        updateFilter();
      });
      typeInputs.set(type, input);
      label.append(input, element("span", "career-graph-dot"), document.createTextNode(spec.label));
      filters.append(label);
    }
    toolbar.append(filters);
    const body = element("div", "career-graph-body");
    const stage = element("div", "career-graph-stage");
    const canvas = element("canvas", "career-graph-canvas");
    canvas.tabIndex = 0;
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "职业关系图。拖动节点或空白区域，滚轮缩放。键盘方向键移动，加减键缩放，Home 显示全图。也可使用右侧节点列表。");
    const context = canvas.getContext("2d");
    if (!context) {
      container.replaceChildren(element("p", "career-graph-error", "当前浏览器无法显示关系图，请使用文档列表浏览职业证据。"));
      return { destroy() {}, focus() {}, fit() {}, setFilter() {} };
    }
    const stageTop = element("div", "career-graph-stage-top");
    const stageTitle = element("div", "career-graph-stage-title");
    stageTitle.append(element("span", "career-graph-eyebrow", "CAREER CONSTELLATION"), element("strong", "", "从技能，看见经历之间的联系"));
    const counts = element("span", "career-graph-counts");
    stageTitle.append(counts);
    stageTop.append(stageTitle);
    const focusToggle = element("label", "career-graph-focus-toggle");
    const focusInput = element("input");
    focusInput.type = "checkbox";
    focusInput.addEventListener("change", () => { neighborsOnly = focusInput.checked; updateFilter(); });
    focusToggle.append(focusInput, document.createTextNode("只看选中节点的关联"));
    stageTop.append(focusToggle);
    const controls = element("div", "career-graph-controls");
    const zoomLabel = element("output", "career-graph-zoom", "100%");
    controls.append(
      button("＋", "放大关系图", () => zoomAt(1.25)),
      zoomLabel,
      button("−", "缩小关系图", () => zoomAt(0.8)),
      button("⛶", "显示完整关系图", fit),
      button("↺", "重置选择与筛选", reset),
    );
    const stageHint = element("p", "career-graph-stage-hint", "拖动探索 · 滚轮缩放 · 点击节点查看来源");
    const empty = element("div", "career-graph-empty");
    empty.append(element("strong", "", "暂时没有可显示的节点"), element("p", "", "试试其他关键词，或显示文档节点。"), button("重置筛选", "重置关系图筛选", reset));
    empty.hidden = true;
    stage.append(canvas, stageTop, controls, stageHint, empty);

    const sidebar = element("aside", "career-graph-sidebar");
    sidebar.setAttribute("aria-label", "节点详情与列表");
    const detail = element("div", "career-graph-detail");
    const listSection = element("section", "career-graph-list-section");
    const listHeading = element("h3", "career-graph-list-heading", "探索节点");
    const list = element("div", "career-graph-node-list");
    list.setAttribute("role", "list");
    listSection.append(listHeading, list);
    sidebar.append(detail, listSection);
    body.append(stage, sidebar);
    const footer = element("div", "career-graph-footer");
    footer.append(element("p", "", "节点大小表示关联数量 · 连线来自文档记录 · 关联不代表能力评分"));
    const live = element("span", "career-graph-sr-only");
    live.setAttribute("role", "status");
    live.setAttribute("aria-live", "polite");
    footer.append(live);
    root.append(toolbar, body, footer);
    if (graph.warnings?.length) {
      const warnings = element("details", "career-graph-warnings");
      warnings.append(element("summary", "", `来源说明 · ${graph.warnings.length}`));
      for (const warning of graph.warnings) warnings.append(element("p", "", String(warning)));
      root.append(warnings);
    }
    container.replaceChildren(root);

    function seed() {
      const projects = nodes.filter(node => node.type === "project");
      const radius = Math.max(170, Math.sqrt(projects.length) * 115);
      projects.forEach((node, index) => {
        const angle = index * Math.PI * 2 / Math.max(projects.length, 1) - Math.PI / 2;
        node.x = Math.cos(angle) * radius;
        node.y = Math.sin(angle) * radius * 0.72;
      });
      const rest = nodes.filter(node => node.type !== "project");
      rest.forEach((node, index) => {
        const linkedProjects = [...adjacency.get(node.id)].map(id => byId.get(id)).filter(item => item.type === "project");
        const angle = index * 2.399963;
        const distance = 50 + Math.sqrt(index + 1) * 16;
        const centerX = linkedProjects.length ? linkedProjects.reduce((sum, item) => sum + item.x, 0) / linkedProjects.length : 0;
        const centerY = linkedProjects.length ? linkedProjects.reduce((sum, item) => sum + item.y, 0) / linkedProjects.length : 0;
        node.x = centerX + Math.cos(angle) * distance;
        node.y = centerY + Math.sin(angle) * distance;
      });
    }

    function radius(node) { return (node.type === "project" ? 7 : node.type === "skill" ? 4.5 : 3.5) + Math.min(8, Math.sqrt(node.degree) * 1.3); }
    function isNearSelection(node) { return !selected || node.id === selected || adjacency.get(selected)?.has(node.id); }

    function updateFilter() {
      const term = query.trim().toLocaleLowerCase();
      const matches = new Set(nodes.filter(node => `${node.label} ${node.summary || ""}`.toLocaleLowerCase().includes(term)).map(node => node.id));
      const related = new Set(matches);
      if (term) for (const id of matches) for (const other of adjacency.get(id)) related.add(other);
      visible = nodes.filter(node => typeFilter.has(node.type) && (!term || related.has(node.id)) && (!neighborsOnly || !selected || isNearSelection(node)));
      const ids = new Set(visible.map(node => node.id));
      visibleLinks = links.filter(edge => ids.has(edge.source) && ids.has(edge.target));
      focusInput.disabled = !selected;
      focusInput.checked = neighborsOnly;
      counts.textContent = `${visible.filter(node => node.type === "project").length} 个项目 · ${visible.filter(node => node.type === "skill").length} 项技能 · ${visibleLinks.length} 条关联`;
      empty.hidden = visible.length > 0;
      stageHint.hidden = visible.length === 0;
      renderList(term, matches);
      live.textContent = `显示 ${visible.length} 个节点，${visibleLinks.length} 条关联。`;
      if (!selected) renderDetail();
      ticks = 0;
      hasFitted = false;
      fit();
      schedule();
    }

    function renderList(term = query.trim().toLocaleLowerCase(), matches = null) {
      const ordered = [...visible].sort((a, b) => b.degree - a.degree || a.label.localeCompare(b.label, "zh-CN"));
      const matchingNodes = term ? ordered.filter(node => matches ? matches.has(node.id) : `${node.label} ${node.summary || ""}`.toLocaleLowerCase().includes(term)) : ordered;
      listHeading.textContent = `${term ? "搜索结果" : "探索节点"} · ${matchingNodes.length}`;
      list.replaceChildren();
      for (const node of matchingNodes) {
        const item = element("div", "career-graph-node-item");
        item.setAttribute("role", "listitem");
        const entry = button("", null, () => select(node.id), `career-graph-node-button career-graph-type-${node.type}`);
        entry.setAttribute("aria-pressed", String(selected === node.id));
        entry.append(element("span", "career-graph-dot"), element("span", "career-graph-node-label", node.label), element("small", "", `${node.degree}`));
        entry.title = `${TYPES[node.type].label}：${node.label}，${node.degree} 个关联节点`;
        item.append(entry);
        list.append(item);
      }
      if (!matchingNodes.length) list.append(element("p", "career-graph-list-empty", "没有匹配的节点。"));
    }

    function renderDetail() {
      detail.replaceChildren();
      sidebar.scrollTop = 0;
      const node = selected && byId.get(selected);
      if (!node) {
        const shared = nodes.filter(item => item.type === "skill" && [...adjacency.get(item.id)].filter(id => byId.get(id).type === "project").length > 1).length;
        detail.append(element("div", "career-graph-eyebrow", "FOLLOW THE CONNECTIONS"), element("h2", "", "每项技能，都有来处。"), element("p", "career-graph-intro", "选择一个项目，查看其中出现的技能；选择一项技能，发现它连接的不同经历。"));
        const stat = element("p", "career-graph-shared");
        stat.append(element("strong", "", String(shared)), document.createTextNode(" 项技能连接多个项目"));
        detail.append(stat, element("p", "career-graph-boundary", "这里只展示文档中记录的关联，掌握程度仍需独立审核。"));
        return;
      }
      const heading = element("div", "career-graph-detail-heading");
      heading.append(element("span", `career-graph-type-label career-graph-type-${node.type}`, TYPES[node.type].label), button("×", "取消选择节点", () => select(null), "career-graph-clear"));
      detail.append(heading, element("h2", "", node.label));
      const state = node.status === "candidate" ? "候选关联 · 待审核" : "文档记录 · 未评估能力";
      detail.append(element("span", "career-graph-status", state));
      if (node.summary) detail.append(element("p", "career-graph-summary", String(node.summary)));
      const connected = [...adjacency.get(node.id)].map(id => byId.get(id)).sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
      for (const [type, spec] of Object.entries(TYPES)) {
        const group = connected.filter(item => item.type === type);
        if (!group.length) continue;
        const section = element("section", "career-graph-related");
        section.append(element("h3", "", `关联${spec.label} · ${group.length}`));
        const chips = element("div", "career-graph-chips");
        for (const other of group) chips.append(button(other.label, `查看${spec.label} ${other.label}`, () => focus(other.id), `career-graph-chip career-graph-type-${type}`));
        section.append(chips);
        detail.append(section);
      }
      const sourceIds = new Set(node.evidence_ids || []);
      const nodeLinks = links.filter(edge => edge.source === node.id || edge.target === node.id);
      for (const edge of nodeLinks) for (const id of edge.evidence_ids || []) sourceIds.add(id);
      if (sourceIds.size) {
        const sources = element("section", "career-graph-sources");
        sources.append(element("h3", "", `原始证据 · ${sourceIds.size}`));
        let count = 0;
        for (const id of sourceIds) {
          const evidenceNode = nodes.find(item => item.type === "document" && (item.id === id || item.evidence_ids?.includes(id)));
          const label = evidenceNode?.label || `查看来源文档 ${++count}`;
          sources.append(button(`${label} ↗`, `打开原始证据：${label}`, () => options.onOpenEvidence?.(id), "career-graph-source"));
        }
        detail.append(sources);
      }
      if (nodeLinks.length) {
        const bases = element("details", "career-graph-bases");
        bases.append(element("summary", "", `查看 ${nodeLinks.length} 条关联的依据`));
        for (const edge of nodeLinks) {
          const other = byId.get(edge.source === node.id ? edge.target : edge.source);
          const item = element("div", "career-graph-basis");
          item.append(element("strong", "", other.label), element("p", "", `${edge.label || RELATIONS[edge.type] || "文档关联"} · ${edge.basis || "来源文档中的显式关联"}`));
          bases.append(item);
        }
        detail.append(bases);
      }
      detail.append(element("p", "career-graph-boundary", "关联不代表能力评分。节点大小仅表示关联数量。"));
    }

    function select(id) {
      selected = id && byId.has(id) ? id : null;
      if (!selected) neighborsOnly = false;
      focusInput.disabled = !selected;
      focusInput.checked = neighborsOnly;
      renderDetail();
      if (neighborsOnly || !selected) updateFilter(); else { renderList(); draw(); }
      live.textContent = selected ? `已选择 ${byId.get(selected).label}，${byId.get(selected).degree} 个关联节点。详情在右侧。` : "已取消选择节点。";
      options.onSelection?.(selected ? byId.get(selected) : null);
    }

    function focus(id) {
      const node = byId.get(id);
      if (!node) return;
      query = "";
      search.value = "";
      typeFilter.add(node.type);
      typeInputs.get(node.type).checked = true;
      selected = id;
      updateFilter();
      select(id);
      zoom = Math.max(zoom, 0.85);
      panX = width / 2 - node.x * zoom;
      panY = height / 2 - node.y * zoom;
      hasFitted = true;
      draw();
    }

    function reset() {
      selected = null;
      hovered = null;
      neighborsOnly = false;
      query = "";
      search.value = "";
      typeFilter = new Set(["project", "skill"]);
      for (const [type, input] of typeInputs) input.checked = typeFilter.has(type);
      renderDetail();
      updateFilter();
      options.onSelection?.(null);
    }

    function fit() {
      if (!visible.length) { draw(); return; }
      const xs = visible.map(node => node.x), ys = visible.map(node => node.y);
      const minX = Math.min(...xs) - 80, maxX = Math.max(...xs) + 80;
      const minY = Math.min(...ys) - 65, maxY = Math.max(...ys) + 65;
      zoom = clamp(Math.min((width - 65) / (maxX - minX), (height - 160) / (maxY - minY)), 0.15, 1.6);
      panX = width / 2 - (minX + maxX) / 2 * zoom;
      panY = height / 2 + 20 - (minY + maxY) / 2 * zoom;
      draw();
    }

    function zoomAt(factor, x = width / 2, y = height / 2) {
      const next = clamp(zoom * factor, 0.12, 4);
      panX = x - (x - panX) * next / zoom;
      panY = y - (y - panY) * next / zoom;
      zoom = next;
      draw();
    }

    function draw() {
      if (destroyed) return;
      context.clearRect(0, 0, width, height);
      zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
      const active = hovered || selected;
      const related = active ? adjacency.get(active) : null;
      const highlighted = node => !active || node.id === active || related.has(node.id);
      const point = node => ({ x: node.x * zoom + panX, y: node.y * zoom + panY });
      for (const edge of visibleLinks) {
        const source = point(byId.get(edge.source)), target = point(byId.get(edge.target));
        const emphasis = active && (edge.source === active || edge.target === active);
        context.beginPath();
        context.moveTo(source.x, source.y);
        context.lineTo(target.x, target.y);
        context.strokeStyle = emphasis ? "rgba(165,199,197,.68)" : active ? "rgba(119,137,147,.055)" : "rgba(135,151,162,.21)";
        context.lineWidth = emphasis ? 1.15 : 0.7;
        context.stroke();
      }
      for (const node of visible) {
        const p = point(node), r = clamp(radius(node) * Math.sqrt(zoom), 3, 23);
        const focused = node.id === active;
        context.globalAlpha = highlighted(node) ? 1 : 0.19;
        if (focused) {
          context.beginPath(); context.arc(p.x, p.y, r + 5, 0, Math.PI * 2);
          context.strokeStyle = TYPES[node.type].color; context.lineWidth = 1; context.stroke();
        }
        context.beginPath(); context.arc(p.x, p.y, r, 0, Math.PI * 2);
        context.fillStyle = TYPES[node.type].color; context.fill();
      }
      context.globalAlpha = 1;
      const occupied = [];
      const labelOrder = [...visible].sort((a, b) => (b.id === active) - (a.id === active) || Number(highlighted(b)) - Number(highlighted(a)) || Number(b.type === "project") - Number(a.type === "project") || b.degree - a.degree);
      for (const node of labelOrder) {
        if (active && !highlighted(node)) continue;
        if (node.type === "document" && zoom < 0.55 && node.id !== active) continue;
        const p = point(node), r = clamp(radius(node) * Math.sqrt(zoom), 3, 23);
        if (p.x < -30 || p.x > width + 30 || p.y < 40 || p.y > height - 30) continue;
        const fontSize = node.type === "project" ? 12 : 11;
        context.font = `${node.type === "project" ? "550" : "400"} ${fontSize}px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif`;
        const chars = Array.from(node.label);
        const text = chars.length > 27 && node.id !== active ? chars.slice(0, 25).join("") + "…" : node.label;
        const measured = context.measureText(text).width;
        const box = { x: p.x - measured / 2 - 4, y: p.y + r + 5, w: measured + 8, h: fontSize + 6 };
        if (node.id !== active && occupied.some(other => box.x < other.x + other.w && box.x + box.w > other.x && box.y < other.y + other.h && box.y + box.h > other.y)) continue;
        occupied.push(box);
        context.fillStyle = "rgba(28,34,40,.9)";
        context.fillRect(box.x, box.y, box.w, box.h);
        context.fillStyle = node.id === active ? "#f0f3ed" : node.type === "project" ? "#d5c9ad" : "#b4c1c7";
        context.textAlign = "center"; context.textBaseline = "top";
        context.fillText(text, p.x, box.y + 3);
      }
    }

    function step() {
      const cooling = Math.max(0.025, 1 - ticks / 170);
      for (let i = 0; i < visible.length; i++) {
        const a = visible[i];
        for (let j = i + 1; j < visible.length; j++) {
          const b = visible[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          if (dx === 0 && dy === 0) { dx = 0.1; dy = 0.1; }
          const d2 = Math.max(dx * dx + dy * dy, 100), d = Math.sqrt(d2);
          const force = Math.min(4, 1700 / d2) * cooling;
          a.vx -= dx / d * force; a.vy -= dy / d * force;
          b.vx += dx / d * force; b.vy += dy / d * force;
        }
      }
      for (const edge of visibleLinks) {
        const a = byId.get(edge.source), b = byId.get(edge.target);
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.max(1, Math.hypot(dx, dy));
        const target = 96 + Math.min(80, Math.sqrt(a.degree + b.degree) * 10);
        const force = (d - target) * 0.012 * cooling;
        a.vx += dx / d * force; a.vy += dy / d * force;
        b.vx -= dx / d * force; b.vy -= dy / d * force;
      }
      for (const node of visible) {
        if (dragging?.node === node) { node.vx = 0; node.vy = 0; continue; }
        node.vx = (node.vx - node.x * 0.00065 * cooling) * 0.72;
        node.vy = (node.vy - node.y * 0.00065 * cooling) * 0.72;
        node.x += clamp(node.vx, -9, 9); node.y += clamp(node.vy, -9, 9);
      }
      ticks++;
    }

    function schedule() {
      if (frame || destroyed || document.hidden || !inView || ticks >= 170 || !visible.length) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        for (let i = 0; i < (reducedMotion ? 12 : 3) && ticks < 170; i++) step();
        if (!reducedMotion || ticks >= 170) draw();
        if (ticks >= 170 && !hasFitted && !dragging) { hasFitted = true; fit(); }
        schedule();
      });
    }

    function position(event) {
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }
    function hit(point) {
      let result = null, nearest = Infinity;
      for (const node of visible) {
        const distance = Math.hypot(node.x * zoom + panX - point.x, node.y * zoom + panY - point.y);
        if (distance < Math.max(10, radius(node) * Math.sqrt(zoom) + 5) && distance < nearest) { result = node; nearest = distance; }
      }
      return result;
    }
    canvas.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      const point = position(event);
      dragging = { node: hit(point), x: point.x, y: point.y, startX: point.x, startY: point.y, moved: false };
      canvas.setPointerCapture(event.pointerId);
      canvas.classList.add("is-dragging");
    });
    canvas.addEventListener("pointermove", event => {
      const point = position(event);
      if (dragging) {
        if (Math.hypot(point.x - dragging.startX, point.y - dragging.startY) > 4) dragging.moved = true;
        if (dragging.node) {
          dragging.node.x += (point.x - dragging.x) / zoom;
          dragging.node.y += (point.y - dragging.y) / zoom;
          dragging.node.vx = 0; dragging.node.vy = 0;
        } else { panX += point.x - dragging.x; panY += point.y - dragging.y; }
        dragging.x = point.x; dragging.y = point.y;
        hasFitted = true;
        draw();
      } else {
        const next = hit(point)?.id || null;
        if (next !== hovered) { hovered = next; canvas.classList.toggle("is-over-node", Boolean(next)); draw(); }
      }
    });
    const endDrag = event => {
      if (!dragging) return;
      const last = dragging;
      dragging = null;
      canvas.classList.remove("is-dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
      if (event.type !== "pointercancel" && !last.moved) select(last.node?.id || null);
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("pointerleave", () => { if (!dragging) { hovered = null; canvas.classList.remove("is-over-node"); draw(); } });
    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      const point = position(event);
      hasFitted = true;
      zoomAt(Math.exp(-clamp(event.deltaY, -100, 100) * 0.004), point.x, point.y);
    }, { passive: false });
    canvas.addEventListener("keydown", event => {
      const move = { ArrowLeft: [45, 0], ArrowRight: [-45, 0], ArrowUp: [0, 45], ArrowDown: [0, -45] }[event.key];
      if (move) { event.preventDefault(); panX += move[0]; panY += move[1]; draw(); }
      else if (["+", "=", "-", "Home", "Escape"].includes(event.key)) {
        event.preventDefault();
        if (event.key === "Home") fit();
        else if (event.key === "Escape") select(null);
        else zoomAt(event.key === "-" ? 0.8 : 1.25);
      }
    });
    search.addEventListener("input", () => { query = search.value; updateFilter(); });

    function resize() {
      const rect = stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      width = rect.width; height = rect.height;
      const scale = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
      context.setTransform(scale, 0, 0, scale, 0, 0);
      fit();
    }
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(stage);
    const intersectionObserver = new IntersectionObserver(entries => {
      inView = entries[0].isIntersecting;
      if (inView) schedule(); else if (frame) { cancelAnimationFrame(frame); frame = 0; }
    });
    intersectionObserver.observe(stage);
    function visibility() {
      if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
      else schedule();
    }
    document.addEventListener("visibilitychange", visibility);
    seed();
    resize();
    renderDetail();
    updateFilter();
    return {
      destroy() {
        destroyed = true;
        if (frame) cancelAnimationFrame(frame);
        resizeObserver.disconnect(); intersectionObserver.disconnect();
        document.removeEventListener("visibilitychange", visibility);
        root.remove();
      },
      focus,
      fit,
      setFilter(filter = {}) {
        if (filter.query !== undefined) { query = String(filter.query); search.value = query; }
        if (filter.types !== undefined) {
          typeFilter = new Set([...filter.types].filter(type => TYPES[type]));
          for (const [type, input] of typeInputs) input.checked = typeFilter.has(type);
        }
        if (filter.neighborsOnly !== undefined) neighborsOnly = Boolean(filter.neighborsOnly) && Boolean(selected);
        updateFilter();
      },
    };
  }

  window.CareerGraph = Object.freeze({ mount });
})();
