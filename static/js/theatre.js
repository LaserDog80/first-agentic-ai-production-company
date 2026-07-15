// Agent Theatre — replay or live-watch a real agentic run as an animated,
// narrated show. Consumes normalized traces from the /api/trace endpoints
// (see src/trace/claude_adapter.py for the event vocabulary) or live events
// over /ws/live. Pixel characters, smooth stage: sprites stay crunchy,
// everything around them (edges, glows, panels, type) is antialiased.
(function () {
    'use strict';

    const S = window.THEATRE_SPRITES;

    // ── DOM handles ─────────────────────────────────────────────────────
    const el = id => document.getElementById(id);
    const actorsEl = el('actors'), feedEl = el('feed'), captionTextEl = el('captionText'),
          captionWhoEl = el('captionWho'), scrubber = el('scrubber'), playBtn = el('playBtn'),
          mapCanvas = el('mapCanvas');

    // ── world state (rebuilt on scrub) ──────────────────────────────────
    let world = null;
    function freshWorld() {
        return {
            agents: new Map(),      // id -> {def, elm, tint, ctx, tokensOut, tools, bubbleTimer}
            totals: { tools: 0, tokens: 0, ctxPeak: 1 },
            clock: 0,
            spawnsSeen: 0,
            toolKindsSeen: new Set(),
            captionsSeen: new Set(),
            openChildren: new Set(),
            lastWave: null,      // current .wave column — parallel hires stack here
        };
    }

    // ── player ──────────────────────────────────────────────────────────
    const player = {
        mode: 'replay',        // 'replay' | 'live'
        trace: null,
        events: [],
        agentDefs: new Map(),  // id -> agent metadata from the trace
        idx: 0,
        playing: false,
        speed: 1,
        timer: null,
        ws: null,
        draining: false,
    };

    // ─────────────────────────────────────────────────────────────────────
    // Loading
    // ─────────────────────────────────────────────────────────────────────

    function loadTrace(trace, sourceLabel) {
        stopLive();
        player.mode = 'replay';
        player.trace = trace;
        player.reveal = trace.reveal || null;   // finale deck/images, if any
        if (player.reveal) {                     // warm the cache so the reveal is instant
            (player.reveal.images || []).forEach(img => { new Image().src = img.src; });
        }
        player.events = trace.events || [];
        player.agentDefs = new Map((trace.agents || []).map(a => [a.id, a]));
        player.idx = 0;
        document.body.classList.remove('live');
        el('runTitle').textContent = trace.title || '';
        el('modeBadge').textContent = sourceLabel || 'REPLAY';
        el('modeBadge').classList.remove('live');
        scrubber.max = Math.max(0, player.events.length - 1);
        el('timeTotal').textContent = fmtClock(trace.duration_s || 0);
        el('loader').classList.add('hidden');
        resetWorld();
        setPlaying(true);
    }

    async function fetchTrace(url, label) {
        try {
            const resp = await fetch(url);
            if (!resp.ok) throw new Error((await resp.json()).error || resp.statusText);
            loadTrace(await resp.json(), label);
        } catch (err) {
            alert('Could not load run: ' + err.message);
        }
    }

    async function loadSessions() {
        const list = el('sessionList');
        try {
            const resp = await fetch('/api/sessions');
            const sessions = (await resp.json()).sessions || [];
            if (!sessions.length) {
                list.innerHTML = '<div class="empty">No transcripts found on this machine. ' +
                    'Runs appear here after you use Claude Code locally — or drop a .jsonl below.</div>';
                return;
            }
            list.innerHTML = '';
            sessions.slice(0, 30).forEach(s => {
                const btn = document.createElement('button');
                btn.className = 'session-item';
                const when = new Date(s.mtime * 1000).toLocaleString();
                btn.innerHTML = `<span class="snip">${esc(s.snippet || s.filename)}</span>` +
                    `<span class="meta2">${esc(s.project)} · ${when} · ${s.size_kb} KB</span>`;
                btn.onclick = () => fetchTrace(`/api/sessions/${s.id}/trace`, 'REPLAY · LOCAL');
                list.appendChild(btn);
            });
        } catch {
            list.innerHTML = '<div class="empty">Could not scan for local sessions.</div>';
        }
    }

    async function refreshLive() {
        const list = el('liveList');
        try {
            const resp = await fetch('/api/live');
            const sessions = (await resp.json()).sessions || [];
            if (!sessions.length) {
                list.innerHTML = '<div class="empty">No live sessions right now.</div>';
                return;
            }
            list.innerHTML = '';
            sessions.forEach(s => {
                const btn = document.createElement('button');
                btn.className = 'session-item';
                btn.innerHTML = `<span class="snip">⦿ ${esc(s.session_id.slice(0, 18))}…</span>` +
                    `<span class="meta2">${s.events} events · active ${s.last_seen_s_ago}s ago</span>`;
                btn.onclick = () => startLive(s.session_id);
                list.appendChild(btn);
            });
        } catch {
            list.innerHTML = '<div class="empty">Server unreachable.</div>';
        }
    }

    function setupDropzone() {
        const dz = el('dropzone'), fi = el('fileInput');
        dz.onclick = () => fi.click();
        fi.onchange = () => fi.files[0] && uploadFile(fi.files[0]);
        ['dragover', 'dragenter'].forEach(t => dz.addEventListener(t, e => {
            e.preventDefault(); dz.classList.add('over');
        }));
        ['dragleave', 'drop'].forEach(t => dz.addEventListener(t, e => {
            e.preventDefault(); dz.classList.remove('over');
        }));
        dz.addEventListener('drop', e => {
            const file = e.dataTransfer.files[0];
            if (file) uploadFile(file);
        });
    }

    async function uploadFile(file) {
        try {
            const resp = await fetch('/api/trace/upload', { method: 'POST', body: await file.text() });
            if (!resp.ok) throw new Error((await resp.json()).error || resp.statusText);
            loadTrace(await resp.json(), 'REPLAY · UPLOAD');
        } catch (err) {
            alert('Could not read that file: ' + err.message);
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Live mode
    // ─────────────────────────────────────────────────────────────────────

    function startLive(sessionId) {
        stopLive();
        player.mode = 'live';
        player.trace = null;
        player.events = [];
        player.agentDefs = new Map();
        player.idx = 0;
        document.body.classList.add('live');
        el('runTitle').textContent = 'live session';
        el('modeBadge').textContent = '⦿ LIVE';
        el('modeBadge').classList.add('live');
        el('loader').classList.add('hidden');
        resetWorld();

        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${location.host}/ws/live?session=${encodeURIComponent(sessionId)}`);
        player.ws = ws;
        ws.onmessage = e => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'backlog') {
                (msg.events || []).forEach(ev => player.events.push(ev));
            } else if (msg.type === 'trace_event') {
                player.events.push(msg.event);
            } else if (msg.type === 'error') {
                alert(msg.message);
                openLoader();
                return;
            }
            el('liveSub').textContent = `${player.events.length} events`;
            drainLive();
        };
        ws.onclose = () => { if (player.mode === 'live') el('modeBadge').textContent = '⦿ LIVE (disconnected)'; };
        const ping = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send('ping'); else clearInterval(ping);
        }, 25000);
    }

    function stopLive() {
        if (player.ws) { try { player.ws.close(); } catch {} player.ws = null; }
    }

    // Drain queued live events with a minimum on-screen dwell per beat,
    // compressing when a burst has piled up so we never fall far behind.
    function drainLive() {
        if (player.draining || player.mode !== 'live') return;
        player.draining = true;
        (function step() {
            if (player.mode !== 'live') { player.draining = false; return; }
            if (player.idx >= player.events.length) { player.draining = false; return; }
            const ev = player.events[player.idx++];
            const backlog = player.events.length - player.idx;
            applyEvent(ev, true);
            const dwell = Math.max(250, dwellFor(ev) / Math.max(1, backlog / 3));
            setTimeout(step, dwell);
        })();
    }

    // ─────────────────────────────────────────────────────────────────────
    // Replay engine
    // ─────────────────────────────────────────────────────────────────────

    function setPlaying(on) {
        player.playing = on;
        playBtn.textContent = on ? '❚❚' : '▶';
        clearTimeout(player.timer);
        if (on) tick();
    }

    function tick() {
        if (!player.playing || player.mode !== 'replay') return;
        if (player.idx >= player.events.length) { setPlaying(false); return; }
        const ev = player.events[player.idx];
        applyEvent(ev, true);
        player.idx++;
        syncScrubber();
        player.timer = setTimeout(tick, dwellFor(ev) / player.speed);
    }

    function dwellFor(ev) {
        switch (ev.type) {
            case 'user_message': return 3200;
            case 'say': return Math.min(1800 + (ev.text || '').length * 16, 5200);
            case 'thinking': return 1000;
            case 'tool_start': return 1500;
            case 'tool_end': return ev.ok === false ? 2200 : 650;
            case 'todo': return 2200;
            case 'spawn': return 2600;
            case 'return': return 2800;
            case 'done': return 3000;
            default: return 900;
        }
    }

    function syncScrubber() {
        scrubber.value = Math.max(0, player.idx - 1);
        const pct = player.events.length > 1 ? (player.idx - 1) / (player.events.length - 1) * 100 : 0;
        scrubber.style.setProperty('--progress', pct + '%');
        el('eventCount').textContent = `event ${player.idx}/${player.events.length}`;
    }

    // Rebuild world state up to (and including) index — the scrub jump.
    function rebuildTo(idx) {
        resetWorld();
        for (let i = 0; i <= idx && i < player.events.length; i++) {
            applyEvent(player.events[i], false);
        }
        player.idx = idx + 1;
        syncScrubber();
    }

    // ─────────────────────────────────────────────────────────────────────
    // World reset + actors
    // ─────────────────────────────────────────────────────────────────────

    function resetWorld() {
        world = freshWorld();
        hideReveal();
        actorsEl.innerHTML = '<div class="wave" id="mainSlot"></div><div class="ensemble" id="ensemble"></div>';
        feedEl.innerHTML = '';
        el('todoCard').classList.remove('visible');
        setCaption('', '');
        mapParticles.length = 0;
        addActor('main');
        updateStats(0);
    }

    function agentDef(id) {
        // The orchestrator always appears as the SERIES PRODUCER, whatever
        // the trace calls it — the theatre casts the run as a production.
        if (player.agentDefs.has(id)) {
            const def = player.agentDefs.get(id);
            return id === 'main' ? { ...def, name: 'SERIES PRODUCER' } : def;
        }
        return { id, name: id === 'main' ? 'SERIES PRODUCER' : id.toUpperCase(),
                 agent_type: id === 'main' ? 'orchestrator' : 'agent', parent: 'main' };
    }

    // A "wave" is one column of the ensemble. Agents hired while others are
    // still in flight (a parallel burst) stack vertically in the same wave;
    // a hire made with nobody in flight starts a fresh column.
    function waveFor(sameWave) {
        let col = world.lastWave;
        if (sameWave && col && col.isConnected && col.childElementCount < 2) return col;
        col = document.createElement('div');
        col.className = 'wave';
        el('ensemble').appendChild(col);
        world.lastWave = col;
        return col;
    }

    function addActor(id, animate, sameWave) {
        if (world.agents.has(id)) return world.agents.get(id);
        const def = agentDef(id);
        const sprite = id === 'main' ? S.CLAUDE_SPRITE
                                     : S.makeAgentSprite(id, def.name, def.agent_type);
        const px = id === 'main' ? 9 : 7;
        const rows = sprite.rows || 12;

        const elm = document.createElement('div');
        elm.className = 'actor' + (animate ? ' entering' : '');
        elm.style.setProperty('--actor-tint', sprite.tint);
        elm.innerHTML =
            `<div class="bubble"></div>` +
            `<div class="toolchip"><span class="ticon"></span><span class="tname"></span></div>` +
            `<div class="sprite-wrap"><canvas class="sprite" width="${8 * px}" height="${rows * px}"></canvas></div>` +
            `<div class="platform"></div>` +
            `<div class="badge">${esc(def.name)}<span class="role">${esc(def.agent_type || '')}</span></div>` +
            `<div class="ctxbar"><div class="fill"></div></div>` +
            `<div class="tokens">0 tok</div>`;
        (id === 'main' ? el('mainSlot') : waveFor(sameWave)).appendChild(elm);
        S.drawSprite(elm.querySelector('canvas.sprite'), sprite, px);
        if (animate) requestAnimationFrame(() => requestAnimationFrame(() => elm.classList.remove('entering')));

        const actor = { def, elm, tint: sprite.tint, ctx: 0, tokensOut: 0, tools: 0, bubbleTimer: null };
        world.agents.set(id, actor);
        mapAddNode(id, def, sprite.tint);
        return actor;
    }

    function setActorState(id, state) {
        const a = world.agents.get(id);
        if (!a) return;
        // 'retired' is sticky — a returned subagent stays dimmed.
        a.elm.classList.remove('working', 'thinking', 'error');
        if (state) a.elm.classList.add(state);
        mapSetActive(id, state === 'working' || state === 'thinking');
    }

    function setBubble(id, html, opts) {
        const a = world.agents.get(id);
        if (!a) return;
        const bubble = a.elm.querySelector('.bubble');
        bubble.innerHTML = html;
        bubble.classList.toggle('err', !!(opts && opts.error));
        bubble.classList.add('visible');
        clearTimeout(a.bubbleTimer);
        a.bubbleTimer = setTimeout(() => bubble.classList.remove('visible'), (opts && opts.ms) || 4000);
    }

    function bumpTokens(id, tokens) {
        const a = world.agents.get(id);
        if (!a || !tokens) return;
        a.tokensOut += tokens.out || 0;
        a.ctx = tokens.ctx || a.ctx;
        world.totals.tokens += tokens.out || 0;
        world.totals.ctxPeak = Math.max(world.totals.ctxPeak, a.ctx);
        a.elm.querySelector('.tokens').textContent = fmtTokens(a.tokensOut) + ' tok';
        // Refresh every context bar against the (possibly new) peak.
        world.agents.forEach(other => {
            other.elm.querySelector('.ctxbar .fill').style.width =
                Math.min(100, other.ctx / world.totals.ctxPeak * 100) + '%';
        });
    }

    // ─────────────────────────────────────────────────────────────────────
    // Event application
    // ─────────────────────────────────────────────────────────────────────

    const TOOL_ICONS = {
        Read: '📄', Write: '✏️', Edit: '✏️', MultiEdit: '✏️', NotebookEdit: '✏️',
        Bash: '⌨️', Grep: '🔍', Glob: '🔍', WebSearch: '🌐', WebFetch: '🌐',
        Task: '🤝', Agent: '🤝', TodoWrite: '📋', ToolSearch: '🔍', Skill: '✨',
    };
    const iconFor = tool => TOOL_ICONS[tool] || '⚙️';

    // Persistent current-tool chip at the agent's shoulder. Counts overlapping
    // calls so parallel tool use doesn't hide the chip early.
    function setToolChip(id, tool) {
        const a = world.agents.get(id);
        if (!a) return;
        const chip = a.elm.querySelector('.toolchip');
        if (tool) {
            a.openTools = (a.openTools || 0) + 1;
            chip.querySelector('.ticon').textContent = iconFor(tool);
            chip.querySelector('.tname').textContent = String(tool).toUpperCase().slice(0, 12);
            chip.classList.add('visible');
            chip.classList.remove('pop');
            void chip.offsetWidth; // restart the pop animation
            chip.classList.add('pop');
        } else {
            a.openTools = Math.max(0, (a.openTools || 0) - 1);
            if (!a.openTools) chip.classList.remove('visible');
        }
    }

    function clearToolChip(id) {
        const a = world.agents.get(id);
        if (!a) return;
        a.openTools = 0;
        a.elm.querySelector('.toolchip').classList.remove('visible');
    }

    function applyEvent(ev, animate) {
        world.clock = ev.t || world.clock;
        const id = ev.agent || 'main';
        if (!world.agents.has(id)) addActor(id, animate);

        switch (ev.type) {
            case 'user_message': {
                setActorState('main', 'thinking');
                feed(ev, 'user', `<span class="who">YOU</span> ${esc(ev.text)}`);
                caption(ev, animate, 'THE BRIEF', clip(ev.text, 240), 'brief:' + ev.t);
                break;
            }
            case 'thinking': {
                setActorState(id, 'thinking');
                setBubble(id, '<span class="tool-tag">THINKING</span>· · ·', { ms: 2500 });
                caption(ev, animate, null,
                    'It thinks before it acts — reasoning privately about what the job actually needs.',
                    'first-thinking');
                break;
            }
            case 'say': {
                setActorState(id, 'working');
                setBubble(id, esc(clip(ev.text, 150)), { ms: 5000 });
                feed(ev, 'say', `<span class="who">${who(id)}</span> ${esc(clip(ev.text, 400))}`);
                if (id !== 'main') {
                    caption(ev, animate, who(id), clip(ev.text, 220), 'say:' + ev.t);
                }
                break;
            }
            case 'todo': {
                renderTodo(ev.items || []);
                feed(ev, '', `<span class="who">${who(id)}</span> updated the plan (${(ev.items || []).length} steps)`);
                const allDone = (ev.items || []).every(i => i.status === 'completed');
                if (allDone && ev.items.length) {
                    caption(ev, animate, null, 'Every box ticked — the plan it wrote for itself is complete.', 'todo-done');
                } else {
                    caption(ev, animate, null,
                        'First move: write a plan. The agent breaks the job into steps it can tick off as it works.',
                        'todo-first');
                }
                break;
            }
            case 'tool_start': {
                setActorState(id, 'working');
                const a = world.agents.get(id);
                if (a) a.tools++;
                world.totals.tools++;
                setToolChip(id, ev.tool || 'TOOL');
                setBubble(id, `<span class="tool-tag">${iconFor(ev.tool)} ${esc(ev.tool || 'TOOL')}</span>${esc(ev.summary || '')}`, { ms: 4500 });
                feed(ev, '', `<span class="who">${who(id)}</span> ${esc(ev.summary || ev.tool)}`);
                captionToolStart(ev, animate);
                break;
            }
            case 'tool_end': {
                setToolChip(id, null);
                if (ev.ok === false) {
                    setActorState(id, 'error');
                    setBubble(id, `<span class="tool-tag">✗ FAILED</span>${esc(clip(ev.summary, 120))}`, { error: true, ms: 3500 });
                    feed(ev, 'error', `<span class="who">${who(id)}</span> ${esc(clip(ev.summary, 200))}`);
                    caption(ev, animate, null,
                        'That didn\'t work. Watch what happens next: the agent reads the error and adjusts. Failure is just information here.',
                        'first-failure');
                } else {
                    setActorState(id, null);
                    feed(ev, '', `<span class="who">${who(id)}</span> ↳ ${esc(clip(ev.summary, 160))}`);
                }
                break;
            }
            case 'spawn': {
                world.spawnsSeen++;
                const sameWave = world.openChildren.size > 0;
                world.openChildren.add(ev.child);
                addActor(ev.child, animate, sameWave);
                setActorState(ev.child, 'working');
                setBubble(id, `<span class="tool-tag">🤝 DELEGATE</span>${esc(ev.task || '')}`, { ms: 4000 });
                feed(ev, 'spawn', `<span class="who">${who(id)}</span> hired <span class="who">${who(ev.child)}</span> — ${esc(ev.task || '')}`);
                mapSpark(id, ev.child, 'forward');
                if (world.spawnsSeen === 1) {
                    caption(ev, animate, null,
                        `The series producer just hired a specialist for “${clip(ev.task, 60)}”. Nobody drew this org chart — the AI decided, mid-run, that delegation was worth it.`,
                        'spawn-1');
                } else if (world.openChildren.size > 1) {
                    caption(ev, animate, null,
                        'A second agent, working in parallel with the first. Each gets its own private context window — that\'s the point of delegating.',
                        'spawn-parallel');
                } else {
                    caption(ev, animate, null,
                        `Another hire: “${clip(ev.task, 70)}”. The team grows exactly as large as the problem demands.`,
                        'spawn:' + ev.child);
                }
                break;
            }
            case 'return': {
                world.openChildren.delete(ev.child);
                const childName = who(ev.child);
                setActorState(ev.child, null);
                clearToolChip(ev.child);
                const childActor = world.agents.get(ev.child);
                if (childActor) childActor.elm.classList.add('retired');
                setBubble(id, `<span class="tool-tag">📥 REPORT IN</span>${esc(clip(ev.summary, 130))}`, { ms: 5000 });
                feed(ev, 'return', `<span class="who">${childName}</span> reported back — ${esc(clip(ev.summary, 260))}`);
                mapSpark(ev.child, ev.agent || 'main', 'back');
                caption(ev, animate, null,
                    `${childName} reports back. Only the summary survives — the subagent's whole working context is thrown away, keeping the series producer's own head clear.`,
                    'return-1');
                break;
            }
            case 'done': {
                world.agents.forEach((_, aid) => { setActorState(aid, null); clearToolChip(aid); });
                caption(ev, animate, 'CURTAIN',
                    `Run complete — ${world.agents.size} agent${world.agents.size > 1 ? 's' : ''}, ` +
                    `${world.totals.tools} tool calls, ${fmtTokens(world.totals.tokens)} tokens generated in ${fmtClock(world.clock)}.`,
                    'done:' + ev.t);
                feed(ev, 'say', `<span class="who">■</span> run complete`);
                if (player.reveal && animate) showReveal(player.reveal);
                break;
            }
            case 'session_start':
                feed(ev, '', 'session started');
                break;
        }

        if (ev.tokens) bumpTokens(id, ev.tokens);
        updateStats(ev.t || 0);
    }

    function captionToolStart(ev, animate) {
        const kind = ev.tool || '';
        const family =
            /^(Read|Grep|Glob)$/.test(kind) ? 'recon' :
            /^(Edit|Write|MultiEdit|NotebookEdit)$/.test(kind) ? 'act' :
            /^(WebSearch|WebFetch)$/.test(kind) ? 'web' :
            kind === 'Bash' ? 'bash' : 'other';
        if (world.toolKindsSeen.has(family)) return;
        world.toolKindsSeen.add(family);
        const lines = {
            recon: 'Before touching anything, it reads. Gathering context is most of the job — the agent builds its own picture of the territory.',
            act: 'Now it acts — editing real files. Everything until this moment was preparation.',
            web: 'It reaches beyond its own training — a live search for facts it doesn\'t have.',
            bash: 'It runs real commands and reads the real output. No simulation — this is the actual machine.',
            other: null,
        };
        if (lines[family]) caption(ev, animate, null, lines[family], 'tool:' + family);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Caption bar (typewriter commentary)
    // ─────────────────────────────────────────────────────────────────────

    let typeInterval = null;
    function caption(ev, animate, whoLabel, text, onceKey) {
        if (onceKey && world.captionsSeen.has(onceKey)) return;
        if (onceKey) world.captionsSeen.add(onceKey);
        if (!animate) return; // scrubbing: record as seen, don't re-narrate
        setCaption(whoLabel || '', text || '');
    }

    function setCaption(whoLabel, text) {
        captionWhoEl.textContent = whoLabel;
        clearInterval(typeInterval);
        if (!text) { captionTextEl.innerHTML = ''; return; }
        let i = 0;
        // One char at a time, ~2-3.5s per caption regardless of length —
        // calm enough to read along with, still done before the beat moves on.
        const speed = Math.max(14, Math.min(36, 3400 / text.length));
        typeInterval = setInterval(() => {
            i += 1;
            captionTextEl.innerHTML = esc(text.slice(0, i)) + '<span class="caption-cursor"></span>';
            if (i >= text.length) {
                clearInterval(typeInterval);
                captionTextEl.textContent = text;
            }
        }, speed);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Feed, stats, todo
    // ─────────────────────────────────────────────────────────────────────

    function feed(ev, cls, html) {
        const entry = document.createElement('div');
        entry.className = 'entry' + (cls ? ' ' + cls : '');
        entry.innerHTML = `<span style="opacity:.55">[${fmtClock(ev.t || 0)}]</span> ${html}`;
        feedEl.appendChild(entry);
        while (feedEl.children.length > 250) feedEl.removeChild(feedEl.firstChild);
        feedEl.scrollTop = feedEl.scrollHeight;
    }

    function updateStats(t) {
        el('statAgents').textContent = world.agents.size;
        el('statTools').textContent = world.totals.tools;
        el('statTokens').textContent = fmtTokens(world.totals.tokens);
        el('statClock').textContent = fmtClock(t);
        el('timeNow').textContent = fmtClock(t);
    }

    function renderTodo(items) {
        const card = el('todoCard'), list = el('todoList');
        list.innerHTML = '';
        items.forEach(item => {
            const li = document.createElement('li');
            li.className = item.status;
            const tick = item.status === 'completed' ? '☑' : item.status === 'in_progress' ? '▸' : '☐';
            li.innerHTML = `<span class="tick">${tick}</span> ${esc(item.text)}`;
            list.appendChild(li);
        });
        card.classList.toggle('visible', items.length > 0);
    }

    function who(id) {
        const a = world.agents.get(id);
        return a ? a.def.name : id;
    }

    // ─────────────────────────────────────────────────────────────────────
    // Delegation map — smooth glowing beziers, not pixel steps
    // ─────────────────────────────────────────────────────────────────────

    const mapNodes = new Map();   // id -> {x, y, tint, label, active}
    const mapParticles = [];      // {from, to, t, dir, color}

    function mapAddNode(id, def, tint) {
        if (mapNodes.has(id)) { mapNodes.get(id).tint = tint; return; }
        if (id === 'main') {
            mapNodes.set(id, { x: 0.16, y: 0.5, tint, label: 'SERIES PRODUCER', active: false });
            return;
        }
        const children = [...mapNodes.keys()].filter(k => k !== 'main').length;
        const slots = [0.25, 0.75, 0.5, 0.1, 0.9, 0.35, 0.65];
        mapNodes.set(id, {
            x: 0.72, y: slots[children % slots.length],
            tint, label: clip(def.name || id, 14), active: false,
        });
    }

    function mapSetActive(id, on) {
        const n = mapNodes.get(id);
        if (n) n.active = on;
    }

    function mapSpark(fromId, toId, dir) {
        mapParticles.push({ from: fromId, to: toId, t: 0,
            color: dir === 'back' ? '#4ecca3' : '#f5c542' });
    }

    function drawMap() {
        const ctx = mapCanvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const w = mapCanvas.clientWidth, h = mapCanvas.clientHeight;
        if (mapCanvas.width !== w * dpr) { mapCanvas.width = w * dpr; mapCanvas.height = h * dpr; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);
        if (!world) { requestAnimationFrame(drawMap); return; }

        const P = id => { const n = mapNodes.get(id); return n ? [n.x * w, n.y * h] : [0, 0]; };
        const curve = (x1, y1, x2, y2) => {
            const mx = (x1 + x2) / 2;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.bezierCurveTo(mx, y1, mx, y2, x2, y2);
        };

        // edges: every non-main node connects to its parent (main)
        mapNodes.forEach((n, id) => {
            if (id === 'main' || !world.agents.has(id)) return;
            const parent = (world.agents.get(id).def.parent) || 'main';
            const [x1, y1] = P(parent), [x2, y2] = P(id);
            curve(x1, y1, x2, y2);
            ctx.strokeStyle = 'rgba(140,150,200,0.35)';
            ctx.lineWidth = 1.5;
            ctx.shadowColor = n.active ? n.tint : 'transparent';
            ctx.shadowBlur = n.active ? 8 : 0;
            ctx.stroke();
            ctx.shadowBlur = 0;
        });

        // particles travelling along edges
        for (let i = mapParticles.length - 1; i >= 0; i--) {
            const p = mapParticles[i];
            p.t += 0.014;
            if (p.t >= 1) { mapParticles.splice(i, 1); continue; }
            const [x1, y1] = P(p.from), [x2, y2] = P(p.to);
            const mx = (x1 + x2) / 2;
            const t = p.t, u = 1 - t;
            const x = u*u*u*x1 + 3*u*u*t*mx + 3*u*t*t*mx + t*t*t*x2;
            const y = u*u*u*y1 + 3*u*u*t*y1 + 3*u*t*t*y2 + t*t*t*y2;
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fillStyle = p.color;
            ctx.shadowColor = p.color;
            ctx.shadowBlur = 10;
            ctx.fill();
            ctx.shadowBlur = 0;
        }

        // nodes
        mapNodes.forEach((n, id) => {
            if (!world.agents.has(id)) return;
            const [x, y] = P(id);
            const r = id === 'main' ? 8 : 6;
            if (n.active) {
                ctx.beginPath();
                ctx.arc(x, y, r + 4 + Math.sin(Date.now() / 220) * 1.5, 0, Math.PI * 2);
                ctx.strokeStyle = n.tint;
                ctx.globalAlpha = 0.5;
                ctx.stroke();
                ctx.globalAlpha = 1;
            }
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fillStyle = n.tint;
            ctx.shadowColor = n.tint;
            ctx.shadowBlur = n.active ? 14 : 5;
            ctx.fill();
            ctx.shadowBlur = 0;
            ctx.font = '9px ui-monospace, monospace';
            ctx.fillStyle = 'rgba(232,234,242,0.85)';
            ctx.textAlign = 'center';
            ctx.fillText(n.label, x, y + r + 12);
        });

        requestAnimationFrame(drawMap);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Controls
    // ─────────────────────────────────────────────────────────────────────

    function togglePlay() {
        if (player.mode !== 'replay' || !player.events.length) return;
        if (!player.playing && player.idx >= player.events.length) rebuildTo(-1);
        setPlaying(!player.playing);
    }

    scrubber.addEventListener('input', () => {
        if (player.mode !== 'replay') return;
        setPlaying(false);
        hideReveal();
        rebuildTo(parseInt(scrubber.value, 10));
    });

    el('speedBtns').addEventListener('click', e => {
        const btn = e.target.closest('button[data-speed]');
        if (!btn) return;
        player.speed = parseFloat(btn.dataset.speed);
        document.querySelectorAll('#speedBtns button').forEach(b => b.classList.toggle('active', b === btn));
    });

    document.addEventListener('keydown', e => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
        if (e.code === 'ArrowRight' && player.mode === 'replay') {
            setPlaying(false);
            rebuildTo(Math.min(player.events.length - 1, player.idx));
        }
        if (e.code === 'ArrowLeft' && player.mode === 'replay') {
            setPlaying(false);
            rebuildTo(Math.max(-1, player.idx - 2));
        }
    });

    function openLoader() {
        setPlaying(false);
        stopLive();
        hideReveal();
        document.body.classList.remove('live');
        el('loader').classList.remove('hidden');
        loadSessions();
        refreshLive();
    }

    // ── Finale reveal: the real deck + cover images for demos that carry them ─
    function showReveal(reveal) {
        const card = el('revealCard');
        if (!card) return;
        el('revealTitle').textContent = reveal.title || 'THE FINISHED DECK';
        el('revealTagline').textContent = reveal.tagline || '';
        const strip = el('revealImages');
        strip.innerHTML = '';
        (reveal.images || []).forEach(img => {
            const fig = document.createElement('figure');
            fig.className = 'reveal-shot';
            fig.innerHTML = `<img src="${esc(img.src)}" alt="${esc(img.caption || '')}" loading="lazy">` +
                            `<figcaption>${esc(img.caption || '')}</figcaption>`;
            fig.onclick = () => window.open(img.src, '_blank', 'noopener');
            strip.appendChild(fig);
        });
        const deckBtn = el('revealDeckBtn');
        if (reveal.deck) { deckBtn.href = reveal.deck; deckBtn.style.display = ''; }
        else { deckBtn.style.display = 'none'; }
        card.classList.remove('hidden');
    }

    function hideReveal() {
        const card = el('revealCard');
        if (card) card.classList.add('hidden');
    }

    // ─────────────────────────────────────────────────────────────────────
    // Utils + boot
    // ─────────────────────────────────────────────────────────────────────

    function esc(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
    function clip(s, n) { s = String(s == null ? '' : s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
    function fmtClock(sec) {
        sec = Math.max(0, Math.floor(sec));
        const m = Math.floor(sec / 60), s = sec % 60;
        return `${m}:${String(s).padStart(2, '0')}`;
    }
    function fmtTokens(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k';
        return String(n);
    }

    window.Theatre = {
        openLoader, togglePlay, refreshLive, closeReveal: hideReveal,
        loadDemo: () => fetchTrace('/api/trace/demo', 'REPLAY · DEMO'),
        loadCasting: () => fetchTrace('/api/trace/demo/casting', 'REPLAY · THE CASTING'),
    };

    resetWorld();
    setupDropzone();
    loadSessions();
    refreshLive();
    drawMap();
})();
