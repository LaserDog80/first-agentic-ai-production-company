// Sidebar — slide-in inspector for the selected node.
//
// Two-way binds to the underlying graph node through editor.updateSelected().
// No "Save" button: the graph autosaves via the page's onChange hook.

const KIND_LABEL = {
  input:    "INPUT",
  output:   "OUTPUT",
  delegate: "DELEGATE",
  skill:    "SKILL",
};

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function escAttr(s) { return escapeHtml(s).replace(/"/g, "&quot;"); }

export class Sidebar {
  constructor(rootEl, editor) {
    this.root = rootEl;
    this.editor = editor;
    this.currentNodeId = null;
    this._body = rootEl.querySelector("[data-sb-body]");

    window.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      if (!this.currentNodeId) return;
      const tag = e.target && e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
        e.target.blur();
        return;
      }
      this._closeFromUser();
    });
  }

  open(node) {
    if (!node) { this.close(); return; }
    this.currentNodeId = node.id;
    this._render(node);
    this.root.classList.add("open");
  }

  close() {
    this.currentNodeId = null;
    this.root.classList.remove("open");
  }

  // Called when the graph mutates (edges/nodes change). If the currently shown
  // node still exists, refresh derived sections without disturbing focus.
  refresh() {
    if (!this.currentNodeId) return;
    const node = this.editor.graph.nodes.find(n => n.id === this.currentNodeId);
    if (!node) { this.close(); return; }
    const slot = this._body.querySelector("[data-sb-connections]");
    if (slot) slot.innerHTML = this._renderConnectionsHtml(node);
  }

  _closeFromUser() {
    this.editor.selectedId = null;
    this.close();
  }

  _render(node) {
    const isAgent = node.type === "agent";
    const isSkill = node.type === "skill";
    const isSource = node.type === "source";
    const isOutput = node.type === "output";

    const head = this.root.querySelector("[data-sb-head]");
    head.innerHTML = `
      <span class="sb-kind sb-kind-${escAttr(node.type)}">${escapeHtml(node.type.toUpperCase())}</span>
      <input data-sb-field="label" type="text" class="sb-title" value="${escAttr(node.label || "")}" placeholder="(unnamed)" />
      <button data-sb-close class="sb-close" title="Close (Esc)">×</button>
    `;
    const closeBtn = head.querySelector("[data-sb-close]");
    if (closeBtn) closeBtn.addEventListener("click", () => this._closeFromUser());

    let html = "";

    if (isAgent) {
      html += `
        <div class="sb-section">
          <h3>SYSTEM PROMPT</h3>
          <textarea data-sb-field="system_prompt" class="sb-prompt" spellcheck="false" placeholder="Describe this agent's role, voice, constraints…">${escapeHtml(node.system_prompt || "")}</textarea>
        </div>
        <div class="sb-section">
          <h3>MODEL</h3>
          <div class="sb-row">
            <label>MODEL TIER</label>
            <select data-sb-field="model_tier">
              <option value="strong">strong</option>
              <option value="research">research</option>
              <option value="utility">utility</option>
            </select>
          </div>
          <div class="sb-row">
            <label>MAX ITERATIONS</label>
            <input data-sb-field="max_iterations" type="number" min="1" max="20" value="${node.max_iterations ?? 5}" />
          </div>
          <div class="sb-row">
            <label>HIERARCHY TIER (T0 = top)</label>
            <input data-sb-field="tier" type="number" min="0" max="9" value="${node.tier ?? 0}" />
          </div>
        </div>
      `;
    }
    if (isSkill) {
      html += `
        <div class="sb-section">
          <h3>SKILL</h3>
          <div class="sb-row">
            <label>SKILL ID</label>
            <input type="text" value="${escAttr(node.skill_id || "")}" disabled />
          </div>
        </div>
      `;
      if (node.skill_id === "generate_image") {
        const p = node.params || {};
        html += `
          <div class="sb-section">
            <h3>FAL.AI PARAMS</h3>
            <div class="sb-row">
              <label>MODEL</label>
              <input data-sb-param="model" type="text" value="${escAttr(p.model || "fal-ai/flux/schnell")}" placeholder="fal-ai/flux/schnell" spellcheck="false" />
            </div>
            <div class="sb-row">
              <label>IMAGE SIZE</label>
              <select data-sb-param="image_size">
                <option value="square_hd">square_hd</option>
                <option value="square">square</option>
                <option value="portrait_4_3">portrait_4_3</option>
                <option value="portrait_16_9">portrait_16_9</option>
                <option value="landscape_4_3">landscape_4_3</option>
                <option value="landscape_16_9">landscape_16_9</option>
              </select>
            </div>
            <div class="sb-row" style="font-size:6px;color:var(--text-dim);line-height:1.7;letter-spacing:0.5px;">
              Common models: <strong>fal-ai/flux/schnell</strong> (fast, cheap) ·
              <strong>fal-ai/flux/dev</strong> (higher quality) ·
              <strong>fal-ai/flux-pro</strong> (best quality, costliest).
              See <a href="https://fal.ai/models" target="_blank" style="color:var(--gold)">fal.ai/models</a>.
            </div>
          </div>
        `;
      }
    }
    if (isSource) {
      html += `
        <div class="sb-section">
          <h3>SOURCE TEXT</h3>
          <textarea data-sb-field="source_value" class="sb-prompt" spellcheck="false" placeholder="Static text exposed as a tool.">${escapeHtml(node.source_value || "")}</textarea>
        </div>
      `;
    }
    if (isOutput) {
      html += `
        <div class="sb-section">
          <h3>OUTPUT</h3>
          <div class="sb-row">
            <label>SUBTYPE (e.g. pitch_deck → PPTX export)</label>
            <input data-sb-field="subtype" type="text" value="${escAttr(node.subtype || "text")}" />
          </div>
        </div>
      `;
    }

    html += `
      <div class="sb-section sb-connections">
        <h3>CONNECTIONS</h3>
        <div data-sb-connections>${this._renderConnectionsHtml(node)}</div>
      </div>
      <div class="sb-section">
        <div class="sb-row"><label>ID</label><input type="text" value="${escAttr(node.id)}" disabled /></div>
      </div>
      <div class="sb-actions">
        <button data-sb-action="delete" class="danger">DELETE</button>
      </div>
    `;

    this._body.innerHTML = html;

    // Initial select value (HTML can't render <select> value without JS).
    if (isAgent) {
      const sel = this._body.querySelector('[data-sb-field="model_tier"]');
      if (sel) sel.value = node.model_tier || "strong";
    }
    if (isSkill && node.skill_id === "generate_image") {
      const sel = this._body.querySelector('[data-sb-param="image_size"]');
      const p = node.params || {};
      if (sel) sel.value = p.image_size || "landscape_16_9";
    }

    this._bindFields();
    this._bindParamFields(node);
    const del = this._body.querySelector('[data-sb-action="delete"]');
    if (del) del.addEventListener("click", () => {
      this.editor.deleteSelected();
      this.close();
    });
  }

  _bindFields() {
    const fields = this.root.querySelectorAll("[data-sb-field]");
    for (const el of fields) {
      const key = el.dataset.sbField;
      el.addEventListener("input", () => this._writeBack(el, key));
      // Some fields (selects, numbers) prefer "change" too.
      el.addEventListener("change", () => this._writeBack(el, key));
    }
  }

  _writeBack(el, key) {
    let value;
    if (el.type === "number") {
      const n = parseInt(el.value, 10);
      if (Number.isNaN(n)) return;
      value = n;
    } else {
      value = el.value;
    }
    this.editor.updateSelected({ [key]: value });
  }

  _bindParamFields(node) {
    const fields = this.root.querySelectorAll("[data-sb-param]");
    for (const el of fields) {
      const key = el.dataset.sbParam;
      const write = () => {
        const current = (this._currentNode() || {}).params || {};
        const next = { ...current, [key]: el.value };
        this.editor.updateSelected({ params: next });
      };
      el.addEventListener("input", write);
      el.addEventListener("change", write);
    }
  }

  _currentNode() {
    if (!this.currentNodeId) return null;
    return this.editor.graph.nodes.find(n => n.id === this.currentNodeId) || null;
  }

  _renderConnectionsHtml(node) {
    const incoming = this.editor.graph.edges.filter(e => e.to === node.id);
    const outgoing = this.editor.graph.edges.filter(e => e.from === node.id);
    const nodeOf = (id) => this.editor.graph.nodes.find(n => n.id === id);

    const renderList = (edges, dir) => {
      if (!edges.length) return `<div class="conn-empty">(none ${dir})</div>`;
      const items = edges.map(e => {
        const other = nodeOf(dir === "in" ? e.from : e.to);
        const label = other ? (other.label || other.id) : "(missing)";
        const kindLabel = KIND_LABEL[e.kind] || (e.kind || "").toUpperCase();
        return `<li><span class="kind kind-${escAttr(e.kind || "")}">${escapeHtml(kindLabel)}</span>${escapeHtml(label)}</li>`;
      }).join("");
      return `<ul class="conn-list">${items}</ul>`;
    };

    return `
      <div class="conn-group">
        <div class="conn-head">↓ INCOMING (${incoming.length})</div>
        ${renderList(incoming, "in")}
      </div>
      <div class="conn-group">
        <div class="conn-head">↑ OUTGOING (${outgoing.length})</div>
        ${renderList(outgoing, "out")}
      </div>
    `;
  }
}
