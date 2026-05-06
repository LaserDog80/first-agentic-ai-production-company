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
    this.selectedId = null;
    this.runStates = {}; // node_id -> 'running' | 'finished' | 'error'
    this.activeEdges = new Set(); // "from->to" strings briefly highlighted

    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;

    this._drag = null;       // dragging a node
    this._pan = null;         // panning the canvas
    this._connecting = null;  // creating an edge {fromId, mx, my}
    this._sparks = [];        // animated dots travelling along edges

    this.onSelect = opts.onSelect || (() => {});
    this.onChange = opts.onChange || (() => {});

    this._wireEvents();
    this._resize();
    window.addEventListener("resize", () => this._resize());
    requestAnimationFrame(() => this._loop());
  }

  // ── public API ────────────────────────────────────────────────────────────
  loadGraph(graph) {
    // Defensive defaults; ensure positions exist.
    this.graph = JSON.parse(JSON.stringify(graph));
    for (const n of this.graph.nodes) {
      n.position = n.position || { x: 100, y: 100 };
    }
    this.selectedId = null;
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
    this.selectedId = node.id;
    this.onSelect(node);
    this.onChange(this.graph);
  }

  deleteSelected() {
    if (!this.selectedId) return;
    const id = this.selectedId;
    this.graph.nodes = this.graph.nodes.filter(n => n.id !== id);
    this.graph.edges = this.graph.edges.filter(e => e.from !== id && e.to !== id);
    this.selectedId = null;
    this.onSelect(null);
    this.onChange(this.graph);
  }

  updateSelected(updates) {
    if (!this.selectedId) return;
    const n = this.graph.nodes.find(n => n.id === this.selectedId);
    if (!n) return;
    Object.assign(n, updates);
    this.onChange(this.graph);
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
    // Spawn a spark.
    const a = this._slotOut(this._node(fromId));
    const b = this._slotIn(this._node(toId));
    if (a && b) this._sparks.push({ ax: a.x, ay: a.y, bx: b.x, by: b.y, t: 0 });
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

    // Edges first (behind nodes).
    for (const e of this.graph.edges) {
      const from = this._node(e.from);
      const to = this._node(e.to);
      if (!from || !to) continue;
      this._drawEdge(from, to, e.kind);
    }

    // In-progress connection.
    if (this._connecting) {
      const from = this._node(this._connecting.fromId);
      if (from) {
        const a = this._slotOut(from);
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
    const isSelected = this.selectedId === n.id;
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

    // Slots.
    if (this._hasInSlot(n)) {
      const s = this._slotIn(n);
      ctx.fillStyle = border;
      ctx.fillRect(s.x - SLOT_SIZE / 2, s.y - SLOT_SIZE / 2, SLOT_SIZE, SLOT_SIZE);
      ctx.fillStyle = PALETTE.bgDark;
      ctx.fillRect(s.x - 3, s.y - 3, 6, 6);
    }
    if (this._hasOutSlot(n)) {
      const s = this._slotOut(n);
      ctx.fillStyle = border;
      ctx.fillRect(s.x - SLOT_SIZE / 2, s.y - SLOT_SIZE / 2, SLOT_SIZE, SLOT_SIZE);
      ctx.fillStyle = PALETTE.bgDark;
      ctx.fillRect(s.x - 3, s.y - 3, 6, 6);
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

  _drawEdge(from, to, kind) {
    const ctx = this.ctx;
    const a = this._slotOut(from);
    const b = this._slotIn(to);
    if (!a || !b) return;
    const colour = KIND_COLOR[kind] || PALETTE.textDim;
    const isActive = this.activeEdges.has(`${from.id}->${to.id}`);

    ctx.strokeStyle = colour;
    ctx.lineWidth = isActive ? 5 / this.scale : (kind === "skill" ? 2 : 3) / this.scale;

    // Stepped path: a -> midY -> b.
    const midY = (a.y + b.y) / 2;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(a.x, midY);
    ctx.lineTo(b.x, midY);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();

    // Arrow head at b.
    const arrow = 6 / this.scale;
    ctx.fillStyle = colour;
    ctx.beginPath();
    ctx.moveTo(b.x, b.y);
    ctx.lineTo(b.x - arrow, b.y - arrow);
    ctx.lineTo(b.x + arrow, b.y - arrow);
    ctx.closePath();
    ctx.fill();
  }

  // ── geometry helpers ──────────────────────────────────────────────────────
  _node(id) { return this.graph.nodes.find(n => n.id === id) || null; }
  _hasInSlot(n) { return n.type !== "input"; }
  _hasOutSlot(n) { return n.type !== "output"; }
  _nodeH(n) { return n.type === "agent" ? NODE_H : NODE_H_SMALL; }
  _slotIn(n) {
    return { x: n.position.x + NODE_W / 2, y: n.position.y };
  }
  _slotOut(n) {
    return { x: n.position.x + NODE_W / 2, y: n.position.y + this._nodeH(n) };
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
      if (!this._hasOutSlot(n)) continue;
      const s = this._slotOut(n);
      if (Math.abs(graphX - s.x) < 8 && Math.abs(graphY - s.y) < 8) return n;
    }
    return null;
  }

  _hitInSlot(graphX, graphY) {
    for (const n of this.graph.nodes) {
      if (!this._hasInSlot(n)) continue;
      const s = this._slotIn(n);
      if (Math.abs(graphX - s.x) < 8 && Math.abs(graphY - s.y) < 8) return n;
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
    c.addEventListener("mouseleave",() => { this._drag = this._pan = this._connecting = null; });
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

    if (e.button === 1 || e.shiftKey) {
      this._pan = { mx, my, ox: this.offsetX, oy: this.offsetY };
      return;
    }

    const out = this._hitOutSlot(g.x, g.y);
    if (out) {
      this._connecting = { fromId: out.id, mx, my };
      return;
    }
    const node = this._hitNode(g.x, g.y);
    if (node) {
      this.selectedId = node.id;
      this.onSelect(node);
      this._drag = { id: node.id, dx: g.x - node.position.x, dy: g.y - node.position.y };
      return;
    }
    // empty space click — start panning
    this.selectedId = null;
    this.onSelect(null);
    this._pan = { mx, my, ox: this.offsetX, oy: this.offsetY };
  }

  _onMove(e) {
    const r = this.canvas.getBoundingClientRect();
    const mx = e.clientX - r.left;
    const my = e.clientY - r.top;
    if (this._drag) {
      const g = this._toGraph(mx, my);
      const n = this._node(this._drag.id);
      if (n) {
        n.position.x = Math.round((g.x - this._drag.dx) / 8) * 8;
        n.position.y = Math.round((g.y - this._drag.dy) / 8) * 8;
        this.onChange(this.graph);
      }
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
      if (target && target.id !== this._connecting.fromId) {
        this._tryConnect(this._connecting.fromId, target.id);
      }
    }
    this._drag = this._pan = this._connecting = null;
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
    // Double-click an edge midpoint to delete it.
    for (let i = 0; i < this.graph.edges.length; i++) {
      const ed = this.graph.edges[i];
      const from = this._node(ed.from);
      const to = this._node(ed.to);
      if (!from || !to) continue;
      const a = this._slotOut(from);
      const b = this._slotIn(to);
      const midY = (a.y + b.y) / 2;
      // Hit-test midline segment.
      if (Math.abs(g.y - midY) < 8 && g.x > Math.min(a.x, b.x) - 4 && g.x < Math.max(a.x, b.x) + 4) {
        this.graph.edges.splice(i, 1);
        this.onChange(this.graph);
        return;
      }
    }
  }

  _onKey(e) {
    if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
    if ((e.key === "Delete" || e.key === "Backspace") && this.selectedId) {
      this.deleteSelected();
      e.preventDefault();
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
