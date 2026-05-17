// Pixel-art Canvas2D node editor.
//
// One <canvas> renders the graph. Nodes draw as bordered rectangles with a
// single input slot on top and a single output slot on the bottom. Edge kind
// is derived from source+target node types (skill->agent = "skill",
// agent->agent = "delegate", input->agent = "input", agent->output = "output").

const PALETTE = {
  bgDark:   "#1a1a2e",
  bgMid:    "#16213e",
  bgLight:  "#0f3460",
  accent:   "#e94560",
  gold:     "#f5c542",
  green:    "#4ecca3",
  text:     "#eaeaea",
  textDim:  "#8892b0",
  red:      "#ff6b6b",
};

const NODE_W = 200;
const NODE_H = 96;
const NODE_H_SMALL = 56;
const SLOT_SIZE = 10;
const GRID = 16;

const KIND_FOR = (srcType, dstType) => {
  if (srcType === "input")   return "input";
  if (dstType === "output")  return "output";
  if (srcType === "skill" || srcType === "source") return "skill";
  if (srcType === "agent" && dstType === "agent")  return "delegate";
  return null;
};

const KIND_COLOR = {
  input:    PALETTE.gold,
  output:   PALETTE.gold,
  delegate: PALETTE.accent,
  skill:    PALETTE.green,
};

export class NodeEditor {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.ctx.imageSmoothingEnabled = false;

    this.graph = { id: "untitled", name: "Untitled", entry_node_id: "", nodes: [], edges: [] };
    this.selectedIds = new Set();
    this.runStates = {}; // node_id -> 'running' | 'finished' | 'error'
    this.activeEdges = new Set(); // "from->to" strings briefly highlighted

    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;

    this._drag = null;        // dragging one or more nodes
    this._pan = null;         // panning the canvas
    this._connecting = null;  // creating an edge {fromId, fromSide, mx, my}
    this._sparks = [];        // animated dots travelling along edges
    this._snapGuides = null;  // { x: number|null, y: number|null } while dragging
    this._lasso = null;       // box-select rect in graph coords

    this.onSelect = opts.onSelect || (() => {});
    this.onChange = opts.onChange || (() => {});

    this._wireEvents();
    this._resize();
    window.addEventListener("resize", () => this._resize());
    requestAnimationFrame(() => this._loop());
  }

  // Backwards-compat shim: callers (e.g. the sidebar) read/write a singular
  // selectedId. Treat assignment as "set selection to this one id, or clear".
  get selectedId() {
    return this.selectedIds.size === 1 ? [...this.selectedIds][0] : null;
  }
  set selectedId(id) {
    if (id) this.selectedIds = new Set([id]);
    else this.selectedIds.clear();
  }

  // Set the entire selection at once. Fires onSelect with the single node
  // when the resulting selection has size 1, else null (so the sidebar
  // closes during multi-select — there's no multi-edit UI).
  _setSelection(ids) {
    this.selectedIds = new Set(ids);
    this._notifySelection();
  }

  _toggleSelection(id) {
    if (this.selectedIds.has(id)) this.selectedIds.delete(id);
    else this.selectedIds.add(id);
    this._notifySelection();
  }

  _notifySelection() {
    if (this.selectedIds.size === 1) {
      const id = [...this.selectedIds][0];
      const node = this._node(id);
      this.onSelect(node);
    } else {
      this.onSelect(null);
    }
  }

  // ── public API ────────────────────────────────────────────────────────────
  loadGraph(graph) {
    // Defensive defaults; ensure positions exist.
    this.graph = JSON.parse(JSON.stringify(graph));
    for (const n of this.graph.nodes) {
      n.position = n.position || { x: 100, y: 100 };
    }
    this.selectedIds.clear();
    this.runStates = {};
    this.activeEdges.clear();
    this._sparks = [];
    this._fitToView();
    this.onChange(this.graph);
  }

  exportGraph() {
    return JSON.parse(JSON.stringify(this.graph));
  }

  addNode(node) {
    if (!node.id) node.id = "n_" + Math.random().toString(36).slice(2, 8);
    if (!node.position) {
      // Centre of viewport in graph coords.
      const cx = (this.canvas.width / 2 - this.offsetX) / this.scale - NODE_W / 2;
      const cy = (this.canvas.height / 2 - this.offsetY) / this.scale - NODE_H / 2;
      node.position = { x: cx, y: cy };
    }
    if (node.type === "agent" && !node.system_prompt) node.system_prompt = "";
    if (node.type === "agent" && !node.model_tier) node.model_tier = "strong";
    if (node.type === "agent" && !node.max_iterations) node.max_iterations = 5;
    this.graph.nodes.push(node);
    this._setSelection([node.id]);
    this.onChange(this.graph);
  }

  // Deletes every node in the current selection (and any edges that touched
  // them). No-op when the selection is empty.
  deleteSelected() {
    if (!this.selectedIds.size) return;
    const ids = this.selectedIds;
    this.graph.nodes = this.graph.nodes.filter(n => !ids.has(n.id));
    this.graph.edges = this.graph.edges.filter(e => !ids.has(e.from) && !ids.has(e.to));
    this._setSelection([]);
    this.onChange(this.graph);
  }

  // Updates fields on the *singly-selected* node. No-op during multi-select —
  // the sidebar isn't shown then so this isn't normally reachable, but the
  // guard keeps the API safe.
  updateSelected(updates) {
    if (this.selectedIds.size !== 1) return;
    const id = [...this.selectedIds][0];
    const n = this._node(id);
    if (!n) return;
    Object.assign(n, updates);
    this.onChange(this.graph);
  }

  // Convert page coords (e.g. from a drop event) into graph coords so the
  // caller can position a spawned node at the cursor.
  screenToGraph(clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    return this._toGraph(clientX - r.left, clientY - r.top);
  }

  setNodeRunState(nodeId, state) {
    if (state == null) delete this.runStates[nodeId];
    else this.runStates[nodeId] = state;
  }

  resetRunState() {
    this.runStates = {};
    this.activeEdges.clear();
    this._sparks = [];
  }

  fireEdge(fromId, toId) {
    const key = `${fromId}->${toId}`;
    this.activeEdges.add(key);
    setTimeout(() => this.activeEdges.delete(key), 1200);
    // Spawn a spark, routed via the same endpoints the renderer uses so the
    // dot follows the actual edge geometry (horizontal for skill, vertical
    // otherwise).
    const edge = this.graph.edges.find(e => e.from === fromId && e.to === toId);
    if (!edge) return;
    const endpoints = this._edgeEndpoints(edge);
    if (!endpoints) return;
    const { a, b } = endpoints;
    this._sparks.push({ ax: a.x, ay: a.y, bx: b.x, by: b.y, t: 0 });
  }

  // ── rendering ─────────────────────────────────────────────────────────────
  _loop() {
    this._draw();
    requestAnimationFrame(() => this._loop());
  }

  _draw() {
    const ctx = this.ctx;
    ctx.fillStyle = PALETTE.bgDark;
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    ctx.save();
    ctx.translate(this.offsetX, this.offsetY);
    ctx.scale(this.scale, this.scale);

    this._drawGrid();
    this._drawSnapGuides();

    // Edges first (behind nodes).
    for (const e of this.graph.edges) {
      this._drawEdge(e);
    }

    // In-progress connection.
    if (this._connecting) {
      const from = this._node(this._connecting.fromId);
      if (from) {
        const a = this._slotPos(from, this._connecting.fromSide);
        const screenX = (this._connecting.mx - this.offsetX) / this.scale;
        const screenY = (this._connecting.my - this.offsetY) / this.scale;
        ctx.strokeStyle = PALETTE.textDim;
        ctx.lineWidth = 2 / this.scale;
        ctx.setLineDash([6 / this.scale, 4 / this.scale]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(screenX, screenY);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // Sparks.
    for (const s of this._sparks) {
      const t = s.t;
      const x = s.ax + (s.bx - s.ax) * t;
      const y = s.ay + (s.by - s.ay) * t;
      ctx.fillStyle = PALETTE.gold;
      ctx.fillRect(Math.round(x) - 3, Math.round(y) - 3, 6, 6);
    }
    this._sparks = this._sparks.filter(s => (s.t += 0.02) < 1);

    // Nodes.
    for (const n of this.graph.nodes) this._drawNode(n);

    this._drawLasso();

    ctx.restore();
  }

  _drawLasso() {
    if (!this._lasso) return;
    const ctx = this.ctx;
    const { x0, y0, x1, y1 } = this._lasso;
    const x = Math.min(x0, x1);
    const y = Math.min(y0, y1);
    const w = Math.abs(x1 - x0);
    const h = Math.abs(y1 - y0);
    ctx.save();
    ctx.fillStyle = "rgba(245, 197, 66, 0.08)";
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = PALETTE.gold;
    ctx.lineWidth = 1 / this.scale;
    ctx.setLineDash([4 / this.scale, 3 / this.scale]);
    ctx.strokeRect(x + 0.5 / this.scale, y + 0.5 / this.scale, w, h);
    ctx.setLineDash([]);
    ctx.restore();
  }

  _drawSnapGuides() {
    if (!this._drag || !this._snapGuides) return;
    const { x, y } = this._snapGuides;
    if (x === null && y === null) return;
    const ctx = this.ctx;
    const ox = -this.offsetX / this.scale;
    const oy = -this.offsetY / this.scale;
    const w = this.canvas.width / this.scale;
    const h = this.canvas.height / this.scale;
    ctx.save();
    ctx.strokeStyle = "rgba(245, 197, 66, 0.55)";
    ctx.lineWidth = 1 / this.scale;
    ctx.setLineDash([4 / this.scale, 4 / this.scale]);
    if (x !== null) {
      // Vertical guide through the centre of the snapped column.
      const gx = x + NODE_W / 2;
      ctx.beginPath();
      ctx.moveTo(gx, oy);
      ctx.lineTo(gx, oy + h);
      ctx.stroke();
    }
    if (y !== null) {
      // Horizontal guide along the snapped row (top edge of nodes at this depth).
      ctx.beginPath();
      ctx.moveTo(ox, y);
      ctx.lineTo(ox + w, y);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.restore();
  }

  _drawGrid() {
    const ctx = this.ctx;
    const w = this.canvas.width / this.scale;
    const h = this.canvas.height / this.scale;
    const ox = -this.offsetX / this.scale;
    const oy = -this.offsetY / this.scale;
    ctx.strokeStyle = "#22243a";
    ctx.lineWidth = 1 / this.scale;
    const startX = Math.floor(ox / GRID) * GRID;
    const startY = Math.floor(oy / GRID) * GRID;
    for (let x = startX; x < ox + w + GRID; x += GRID) {
      ctx.beginPath(); ctx.moveTo(x, oy); ctx.lineTo(x, oy + h); ctx.stroke();
    }
    for (let y = startY; y < oy + h + GRID; y += GRID) {
      ctx.beginPath(); ctx.moveTo(ox, y); ctx.lineTo(ox + w, y); ctx.stroke();
    }
  }

  _drawNode(n) {
    const ctx = this.ctx;
    const { x, y } = n.position;
    const w = NODE_W;
    const h = (n.type === "agent") ? NODE_H : NODE_H_SMALL;
    const isSelected = this.selectedIds.has(n.id);
    const runState = this.runStates[n.id];

    // Border colour.
    let border = PALETTE.bgLight;
    if (n.type === "agent") border = PALETTE.accent;
    else if (n.type === "skill") border = PALETTE.green;
    else if (n.type === "source") border = PALETTE.green;
    else if (n.type === "input")  border = PALETTE.gold;
    else if (n.type === "output") border = PALETTE.gold;

    if (runState === "running") border = PALETTE.gold;
    else if (runState === "finished") border = PALETTE.green;
    else if (runState === "error") border = PALETTE.red;

    // Body.
    ctx.fillStyle = PALETTE.bgMid;
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = border;
    ctx.lineWidth = isSelected ? 4 : 3;
    ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);

    // Pulsing border for running.
    if (runState === "running") {
      const t = (Date.now() / 200) % (Math.PI * 2);
      ctx.strokeStyle = `rgba(245, 197, 66, ${0.3 + 0.3 * Math.sin(t)})`;
      ctx.lineWidth = 6;
      ctx.strokeRect(x - 2, y - 2, w + 4, h + 4);
    }

    // Title bar.
    ctx.fillStyle = border;
    ctx.fillRect(x, y, w, 22);
    ctx.fillStyle = PALETTE.bgDark;
    ctx.font = '10px "Press Start 2P", monospace';
    ctx.textBaseline = "middle";
    const title = (n.label || n.id).slice(0, 22);
    ctx.fillText(title, x + 8, y + 11);

    // Tier badge.
    if (n.type === "agent" && n.tier !== undefined) {
      ctx.fillStyle = PALETTE.bgDark;
      ctx.fillRect(x + w - 28, y + 4, 24, 14);
      ctx.fillStyle = border;
      ctx.font = '8px "Press Start 2P", monospace';
      ctx.fillText("T" + n.tier, x + w - 24, y + 12);
    }

    // Body content.
    ctx.font = '7px "Press Start 2P", monospace';
    ctx.fillStyle = PALETTE.textDim;
    if (n.type === "agent") {
      const sp = (n.system_prompt || "").replace(/\s+/g, " ").slice(0, 80);
      this._wrapText(sp, x + 8, y + 32, w - 16, 10);
      ctx.fillStyle = PALETTE.text;
      ctx.font = '7px "Press Start 2P", monospace';
      ctx.fillText("MODEL: " + (n.model_tier || "strong").toUpperCase(), x + 8, y + h - 12);
    } else if (n.type === "skill") {
      ctx.fillStyle = PALETTE.text;
      ctx.fillText("SKILL", x + 8, y + 36);
      ctx.fillStyle = PALETTE.textDim;
      ctx.fillText((n.skill_id || "").slice(0, 22), x + 8, y + 48);
    } else if (n.type === "source") {
      ctx.fillStyle = PALETTE.text;
      ctx.fillText("SOURCE", x + 8, y + 36);
      ctx.fillStyle = PALETTE.textDim;
      const preview = (n.source_value || "(empty)").replace(/\s+/g, " ").slice(0, 22);
      ctx.fillText(preview, x + 8, y + 48);
    } else if (n.type === "input") {
      ctx.fillStyle = PALETTE.text;
      ctx.fillText("BRIEF IN", x + 8, y + 38);
    } else if (n.type === "output") {
      ctx.fillStyle = PALETTE.text;
      ctx.fillText("OUTPUT", x + 8, y + 38);
    }

    // Slots — render every slot this node type exposes.
    const slots = this._slotsForType(n.type);
    for (const s of [...slots.ins, ...slots.outs]) {
      const p = this._slotPos(n, s.side);
      ctx.fillStyle = border;
      ctx.fillRect(p.x - SLOT_SIZE / 2, p.y - SLOT_SIZE / 2, SLOT_SIZE, SLOT_SIZE);
      ctx.fillStyle = PALETTE.bgDark;
      ctx.fillRect(p.x - 3, p.y - 3, 6, 6);
    }
  }

  _wrapText(text, x, y, maxW, lineH) {
    const ctx = this.ctx;
    const words = text.split(/\s+/);
    let line = "";
    let yy = y;
    let lines = 0;
    for (const word of words) {
      const test = line ? line + " " + word : word;
      if (ctx.measureText(test).width > maxW && line) {
        ctx.fillText(line, x, yy);
        yy += lineH;
        lines++;
        if (lines >= 3) { ctx.fillText("…", x, yy); return; }
        line = word;
      } else line = test;
    }
    if (line) ctx.fillText(line, x, yy);
  }

  _drawEdge(edge) {
    const ctx = this.ctx;
    const endpoints = this._edgeEndpoints(edge);
    if (!endpoints) return;
    const { a, b } = endpoints;
    const kind = edge.kind;
    const colour = KIND_COLOR[kind] || PALETTE.textDim;
    const isActive = this.activeEdges.has(`${edge.from}->${edge.to}`);
    const lineW = isActive ? 5 / this.scale : (kind === "skill" ? 2 : 3) / this.scale;
    const arrow = 6 / this.scale;
    const horizontal = (kind === "skill");

    // Stepped path nodes — horizontal kinds route through a midX (left↔right),
    // vertical kinds route through a midY (top↔bottom).
    const path = horizontal
      ? (() => {
          const midX = (a.x + b.x) / 2;
          return [[a.x, a.y], [midX, a.y], [midX, b.y], [b.x, b.y]];
        })()
      : (() => {
          const midY = (a.y + b.y) / 2;
          return [[a.x, a.y], [a.x, midY], [b.x, midY], [b.x, b.y]];
        })();

    // Input/output edges signal where information enters/exits the system.
    // When they span >200px they'd cross other nodes — render solid chevron
    // stubs at each endpoint with a faint dashed bridge between, so the
    // entry/exit reads clearly without the line dominating the middle of the
    // graph. Active state overrides (full glow during a run).
    const isThrough = (kind === "input" || kind === "output");
    const longSpan = Math.abs(b.y - a.y) > 200;
    if (isThrough && longSpan && !isActive) {
      ctx.save();
      ctx.strokeStyle = colour;
      ctx.globalAlpha = 0.28;
      ctx.lineWidth = 1 / this.scale;
      ctx.setLineDash([3 / this.scale, 4 / this.scale]);
      ctx.beginPath();
      ctx.moveTo(path[0][0], path[0][1]);
      for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0], path[i][1]);
      ctx.stroke();
      ctx.restore();

      const stub = 22 / this.scale;
      ctx.strokeStyle = colour;
      ctx.lineWidth = lineW;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(a.x, a.y + stub);
      ctx.moveTo(b.x, b.y - stub);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();

      ctx.fillStyle = colour;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y + stub);
      ctx.lineTo(a.x - arrow, a.y + stub - arrow);
      ctx.lineTo(a.x + arrow, a.y + stub - arrow);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(b.x, b.y);
      ctx.lineTo(b.x - arrow, b.y - arrow);
      ctx.lineTo(b.x + arrow, b.y - arrow);
      ctx.closePath();
      ctx.fill();
      return;
    }

    // Default: solid stepped path with one arrowhead at the destination.
    ctx.strokeStyle = colour;
    ctx.lineWidth = lineW;
    ctx.beginPath();
    ctx.moveTo(path[0][0], path[0][1]);
    for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0], path[i][1]);
    ctx.stroke();

    // Arrowhead at destination — orient based on the direction of entry.
    ctx.fillStyle = colour;
    ctx.beginPath();
    if (horizontal) {
      // Skill arrows enter sideways; flip based on which side we entered on.
      const enteringFromLeft = a.x <= b.x;
      const tipX = b.x;
      const baseX = enteringFromLeft ? b.x - arrow : b.x + arrow;
      ctx.moveTo(tipX, b.y);
      ctx.lineTo(baseX, b.y - arrow);
      ctx.lineTo(baseX, b.y + arrow);
    } else {
      ctx.moveTo(b.x, b.y);
      ctx.lineTo(b.x - arrow, b.y - arrow);
      ctx.lineTo(b.x + arrow, b.y - arrow);
    }
    ctx.closePath();
    ctx.fill();
  }

  // ── hierarchy / snap ──────────────────────────────────────────────────────
  // BFS depth from input (or roots with no incoming flow edges). Skill/source
  // edges are ignored — they're tool wires, not part of the agent hierarchy.
  // Skill and source nodes get no depth and are excluded from hierarchy snap.
  _computeDepths() {
    const FLOW = new Set(["input", "delegate", "output"]);
    const outgoing = {};
    const incoming = {};
    for (const n of this.graph.nodes) { outgoing[n.id] = []; incoming[n.id] = []; }
    for (const e of this.graph.edges) {
      if (!FLOW.has(e.kind)) continue;
      if (outgoing[e.from]) outgoing[e.from].push(e.to);
      if (incoming[e.to]) incoming[e.to].push(e.from);
    }
    let roots = this.graph.nodes.filter(n => n.type === "input").map(n => n.id);
    if (!roots.length) {
      roots = this.graph.nodes
        .filter(n => (n.type === "agent" || n.type === "output") && incoming[n.id].length === 0)
        .map(n => n.id);
    }
    const depths = {};
    const queue = [];
    for (const r of roots) { depths[r] = 0; queue.push(r); }
    while (queue.length) {
      const id = queue.shift();
      for (const nx of outgoing[id]) {
        if (depths[nx] === undefined) { depths[nx] = depths[id] + 1; queue.push(nx); }
      }
    }
    return depths;
  }

  // Returns { x, y, guides } — final snapped position plus the snap targets used
  // (so the draw loop can render guide lines). Falls back to 8px sub-grid.
  _snapDraggedPosition(draggedId, rawX, rawY) {
    const THRESHOLD = 12;
    let nx = Math.round(rawX / 8) * 8;
    let ny = Math.round(rawY / 8) * 8;
    let guideX = null, guideY = null;

    const depths = this._computeDepths();
    const d = depths[draggedId];
    if (d !== undefined) {
      // Y-snap: same-depth nodes form a row.
      let bestDy = THRESHOLD, bestY = null;
      // X-snap: align with nodes at a *different* depth (parents, grandparents,
      // cousins) — same-depth nodes share a y, so x-aligning them would overlap.
      let bestDx = THRESHOLD, bestX = null;
      for (const o of this.graph.nodes) {
        if (o.id === draggedId) continue;
        const od = depths[o.id];
        if (od === undefined) continue;
        if (od === d) {
          const dy = Math.abs(ny - o.position.y);
          if (dy < bestDy) { bestDy = dy; bestY = o.position.y; }
        } else {
          const dx = Math.abs(nx - o.position.x);
          if (dx < bestDx) { bestDx = dx; bestX = o.position.x; }
        }
      }
      if (bestY !== null) { ny = bestY; guideY = bestY; }
      if (bestX !== null) { nx = bestX; guideX = bestX; }
    }
    return { x: nx, y: ny, guides: { x: guideX, y: guideY } };
  }

  // ── geometry helpers ──────────────────────────────────────────────────────
  _node(id) { return this.graph.nodes.find(n => n.id === id) || null; }
  _nodeH(n) { return n.type === "agent" ? NODE_H : NODE_H_SMALL; }

  // Slot inventory per node type.
  //   - Agent: top + bottom for delegate/input/output flow; left + right for
  //     skill tools (so they enter from the side, not jammed on top with
  //     delegation).
  //   - Skill / source: left + right out-slots — picks whichever side is
  //     closer to the consuming agent at draw time.
  //   - Input: bottom out-slot only.
  //   - Output: top in-slot only.
  _slotsForType(type) {
    switch (type) {
      case "agent":  return {
        ins:  [{ side: "top",    kinds: ["delegate", "input"] },
               { side: "left",   kinds: ["skill"] },
               { side: "right",  kinds: ["skill"] }],
        outs: [{ side: "bottom", kinds: ["delegate", "output"] }],
      };
      case "skill":
      case "source": return {
        ins:  [],
        outs: [{ side: "left",  kinds: ["skill"] },
               { side: "right", kinds: ["skill"] }],
      };
      case "input":  return {
        ins:  [],
        outs: [{ side: "bottom", kinds: ["input"] }],
      };
      case "output": return {
        ins:  [{ side: "top", kinds: ["output"] }],
        outs: [],
      };
    }
    return { ins: [], outs: [] };
  }

  _slotPos(n, side) {
    const x = n.position.x;
    const y = n.position.y;
    const w = NODE_W;
    const h = this._nodeH(n);
    if (side === "top")    return { x: x + w / 2, y: y };
    if (side === "bottom") return { x: x + w / 2, y: y + h };
    if (side === "left")   return { x: x,         y: y + h / 2 };
    if (side === "right")  return { x: x + w,     y: y + h / 2 };
    return null;
  }

  // Endpoints to use when rendering / sparking a given edge — vertical
  // (top↔bottom) for input/delegate/output, horizontal (left↔right) for skill,
  // with the skill source's side chosen by which is closer to the target.
  _edgeEndpoints(edge) {
    const from = this._node(edge.from);
    const to = this._node(edge.to);
    if (!from || !to) return null;
    if (edge.kind === "skill") {
      const fromCx = from.position.x + NODE_W / 2;
      const toCx   = to.position.x + NODE_W / 2;
      if (fromCx <= toCx) {
        return { a: this._slotPos(from, "right"), b: this._slotPos(to, "left") };
      }
      return { a: this._slotPos(from, "left"), b: this._slotPos(to, "right") };
    }
    return { a: this._slotPos(from, "bottom"), b: this._slotPos(to, "top") };
  }

  _hitNode(graphX, graphY) {
    // Topmost first.
    for (let i = this.graph.nodes.length - 1; i >= 0; i--) {
      const n = this.graph.nodes[i];
      const h = this._nodeH(n);
      if (graphX >= n.position.x && graphX <= n.position.x + NODE_W &&
          graphY >= n.position.y && graphY <= n.position.y + h) return n;
    }
    return null;
  }

  _hitOutSlot(graphX, graphY) {
    for (const n of this.graph.nodes) {
      for (const s of this._slotsForType(n.type).outs) {
        const p = this._slotPos(n, s.side);
        if (Math.abs(graphX - p.x) < 8 && Math.abs(graphY - p.y) < 8) {
          return { node: n, side: s.side };
        }
      }
    }
    return null;
  }

  _hitInSlot(graphX, graphY) {
    for (const n of this.graph.nodes) {
      for (const s of this._slotsForType(n.type).ins) {
        const p = this._slotPos(n, s.side);
        if (Math.abs(graphX - p.x) < 8 && Math.abs(graphY - p.y) < 8) {
          return { node: n, side: s.side };
        }
      }
    }
    return null;
  }

  _toGraph(mx, my) {
    return {
      x: (mx - this.offsetX) / this.scale,
      y: (my - this.offsetY) / this.scale,
    };
  }

  _resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = Math.floor(r.width);
    this.canvas.height = Math.floor(r.height);
    this.ctx.imageSmoothingEnabled = false;
  }

  _fitToView() {
    if (!this.graph.nodes.length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of this.graph.nodes) {
      minX = Math.min(minX, n.position.x);
      minY = Math.min(minY, n.position.y);
      maxX = Math.max(maxX, n.position.x + NODE_W);
      maxY = Math.max(maxY, n.position.y + this._nodeH(n));
    }
    const pad = 60;
    const w = (maxX - minX) + pad * 2;
    const h = (maxY - minY) + pad * 2;
    const sx = this.canvas.width / w;
    const sy = this.canvas.height / h;
    this.scale = Math.min(1, Math.min(sx, sy));
    this.offsetX = (this.canvas.width - (maxX - minX) * this.scale) / 2 - minX * this.scale;
    this.offsetY = (this.canvas.height - (maxY - minY) * this.scale) / 2 - minY * this.scale;
  }

  // ── input ─────────────────────────────────────────────────────────────────
  _wireEvents() {
    const c = this.canvas;
    c.addEventListener("mousedown", (e) => this._onDown(e));
    c.addEventListener("mousemove", (e) => this._onMove(e));
    c.addEventListener("mouseup",   (e) => this._onUp(e));
    c.addEventListener("mouseleave",() => { this._drag = this._pan = this._connecting = this._lasso = null; this._snapGuides = null; });
    c.addEventListener("wheel",     (e) => this._onWheel(e), { passive: false });
    c.addEventListener("dblclick",  (e) => this._onDblClick(e));
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    window.addEventListener("keydown", (e) => this._onKey(e));
  }

  _onDown(e) {
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const g = this._toGraph(mx, my);

    // Middle-click anywhere = pan.
    if (e.button === 1) {
      this._pan = { mx, my, ox: this.offsetX, oy: this.offsetY };
      return;
    }

    // Slot drag for connecting nodes takes priority over selection.
    const out = this._hitOutSlot(g.x, g.y);
    if (out) {
      this._connecting = { fromId: out.node.id, fromSide: out.side, mx, my };
      return;
    }

    const node = this._hitNode(g.x, g.y);

    // Shift+click on a node toggles its selection without starting a drag.
    if (node && e.shiftKey) {
      this._toggleSelection(node.id);
      return;
    }

    // Shift+drag on empty canvas = lasso box-select.
    if (!node && e.shiftKey) {
      this._lasso = { x0: g.x, y0: g.y, x1: g.x, y1: g.y };
      return;
    }

    if (node) {
      // Click on a node that's already part of a multi-selection keeps the
      // whole selection (so the drag moves the group). Otherwise replace
      // selection with just this node.
      if (!this.selectedIds.has(node.id)) {
        this._setSelection([node.id]);
      }
      // Build per-node drag offsets relative to the cursor.
      const offsets = {};
      for (const id of this.selectedIds) {
        const n = this._node(id);
        if (!n) continue;
        offsets[id] = { dx: g.x - n.position.x, dy: g.y - n.position.y };
      }
      this._drag = { ids: [...this.selectedIds], offsets };
      return;
    }

    // Empty canvas, no shift: clear selection and start panning.
    this._setSelection([]);
    this._pan = { mx, my, ox: this.offsetX, oy: this.offsetY };
  }

  _onMove(e) {
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    if (this._drag) {
      const g = this._toGraph(mx, my);
      // Single-node drag: apply snap-to-hierarchy. Multi-node drag: move all
      // in lockstep with grid-aligned positions, no hierarchy snap (snapping
      // each independently produces overlaps and is rarely what you want).
      if (this._drag.ids.length === 1) {
        const id = this._drag.ids[0];
        const off = this._drag.offsets[id];
        const n = this._node(id);
        if (n) {
          const snapped = this._snapDraggedPosition(id, g.x - off.dx, g.y - off.dy);
          n.position.x = snapped.x;
          n.position.y = snapped.y;
          this._snapGuides = snapped.guides;
          this.onChange(this.graph);
        }
      } else {
        for (const id of this._drag.ids) {
          const n = this._node(id);
          const off = this._drag.offsets[id];
          if (!n || !off) continue;
          n.position.x = Math.round((g.x - off.dx) / 8) * 8;
          n.position.y = Math.round((g.y - off.dy) / 8) * 8;
        }
        this._snapGuides = null;
        this.onChange(this.graph);
      }
    } else if (this._lasso) {
      const g = this._toGraph(mx, my);
      this._lasso.x1 = g.x;
      this._lasso.y1 = g.y;
    } else if (this._pan) {
      this.offsetX = this._pan.ox + (mx - this._pan.mx);
      this.offsetY = this._pan.oy + (my - this._pan.my);
    } else if (this._connecting) {
      this._connecting.mx = mx;
      this._connecting.my = my;
    }
  }

  _onUp(e) {
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const g = this._toGraph(mx, my);
    if (this._connecting) {
      const target = this._hitInSlot(g.x, g.y);
      if (target && target.node.id !== this._connecting.fromId) {
        this._tryConnect(this._connecting.fromId, target.node.id);
      }
    }
    if (this._lasso) {
      const { x0, y0, x1, y1 } = this._lasso;
      const minX = Math.min(x0, x1), maxX = Math.max(x0, x1);
      const minY = Math.min(y0, y1), maxY = Math.max(y0, y1);
      // Only treat as a lasso if the user actually dragged a meaningful area;
      // a near-zero rect is just a stray shift+click on empty canvas.
      if (Math.abs(maxX - minX) > 4 || Math.abs(maxY - minY) > 4) {
        const picked = [];
        for (const n of this.graph.nodes) {
          const nx = n.position.x;
          const ny = n.position.y;
          const nw = NODE_W;
          const nh = this._nodeH(n);
          // Rect-vs-rect intersection (any overlap = selected).
          if (nx < maxX && nx + nw > minX && ny < maxY && ny + nh > minY) {
            picked.push(n.id);
          }
        }
        this._setSelection(picked);
      }
    }
    this._drag = this._pan = this._connecting = this._lasso = null;
    this._snapGuides = null;
  }

  _onWheel(e) {
    e.preventDefault();
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.max(0.3, Math.min(2, this.scale * factor));
    // zoom around mouse
    const gx = (mx - this.offsetX) / this.scale;
    const gy = (my - this.offsetY) / this.scale;
    this.scale = newScale;
    this.offsetX = mx - gx * this.scale;
    this.offsetY = my - gy * this.scale;
  }

  _onDblClick(e) {
    const r = this.canvas.getBoundingClientRect();
    const g = this._toGraph(e.clientX - r.left, e.clientY - r.top);
    // Double-click on the middle segment of an edge to delete it. For vertical
    // edges this is a horizontal midline at midY; for skill (horizontal)
    // edges it's a vertical midline at midX.
    for (let i = 0; i < this.graph.edges.length; i++) {
      const ed = this.graph.edges[i];
      const endpoints = this._edgeEndpoints(ed);
      if (!endpoints) continue;
      const { a, b } = endpoints;
      let hit;
      if (ed.kind === "skill") {
        const midX = (a.x + b.x) / 2;
        hit = Math.abs(g.x - midX) < 8 &&
              g.y > Math.min(a.y, b.y) - 4 && g.y < Math.max(a.y, b.y) + 4;
      } else {
        const midY = (a.y + b.y) / 2;
        hit = Math.abs(g.y - midY) < 8 &&
              g.x > Math.min(a.x, b.x) - 4 && g.x < Math.max(a.x, b.x) + 4;
      }
      if (hit) {
        this.graph.edges.splice(i, 1);
        this.onChange(this.graph);
        return;
      }
    }
  }

  _onKey(e) {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if ((e.key === "Delete" || e.key === "Backspace") && this.selectedIds.size) {
      this.deleteSelected();
      e.preventDefault();
    } else if (e.key === "Escape" && this.selectedIds.size) {
      this._setSelection([]);
    } else if (e.key === "f" || e.key === "F") {
      this._fitToView();
    }
  }

  _tryConnect(fromId, toId) {
    const from = this._node(fromId);
    const to = this._node(toId);
    if (!from || !to) return;
    const kind = KIND_FOR(from.type, to.type);
    if (!kind) return;
    // Disallow duplicate.
    if (this.graph.edges.some(e => e.from === fromId && e.to === toId)) return;
    // For input/output edges, replace any existing.
    if (kind === "input") {
      this.graph.edges = this.graph.edges.filter(e => e.kind !== "input");
    }
    this.graph.edges.push({
      id: "e_" + Math.random().toString(36).slice(2, 8),
      from: fromId, to: toId, kind,
    });
    this.onChange(this.graph);
  }
}
