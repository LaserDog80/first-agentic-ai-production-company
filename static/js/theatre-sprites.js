// Pixel-art sprite factory for the Theatre's dynamic cast.
//
// Unlike the presentation view's hand-drawn CHARACTERS (sprites.js), the
// Theatre can't know its cast in advance — subagents are hired mid-run by
// the AI. Sprites are therefore built from small ASCII-grid templates with
// colour slots, tinted deterministically from the agent's name, so the
// same agent always looks the same.
//
// Exposes globals: THEATRE_SPRITES.{makeAgentSprite, CLAUDE_SPRITE, drawSprite}
(function () {
    'use strict';

    // Each row is exactly 8 chars. Slot chars:
    //   s skin  h hair  t top  b bottom  x shoes  a accent
    //   w secondary  k dark  e eye-glow  r accent2  . empty
    const TEMPLATES = {
        // Hooded developer with a laptop.
        dev: [
            '.tttttt.',
            'tthhhhtt',
            'thssssht',
            'thskskht',
            'thssssht',
            '.tttttt.',
            'tttaattt',
            't.taat.t',
            '.twwwwt.',
            '..bbbb..',
            '..b..b..',
            '.xx..xx.',
        ],
        // Field researcher: cap, satchel straps, magnifier in hand.
        scout: [
            '.aaaaaa.',
            'aahhhhaa',
            '.hssssh.',
            '.hskskh.',
            '.hssssh.',
            '.tttttt.',
            'wttttttw',
            't.tttt.a',
            '.tbbbbt.',
            '..b..b..',
            '.xx..xx.',
        ],
        // Planner/reviewer: blazer, shirt, clipboard.
        suit: [
            '..hhhh..',
            '.hhhhhh.',
            '.hssssh.',
            '.hskskh.',
            '.hssssh.',
            '.tttttt.',
            'ttwwwwtt',
            't.tttt.w',
            '.tttttt.',
            '..bbbb..',
            '..b..b..',
            '.xx..xx.',
        ],
        // Little worker robot.
        bot: [
            '...a....',
            '.tttttt.',
            '.tettet.',
            '.tttttt.',
            '..aaaa..',
            '.wwwwww.',
            'w.waaw.w',
            'w.wwww.w',
            '..w..w..',
            '.xx..xx.',
        ],
    };

    // The orchestrator: ivory robot-conductor with gold headset, glowing
    // eyes and a coral scarf. Always the same — the star of the show.
    const CLAUDE_GRID = [
        '..aaaa..',
        '.atttta.',
        '.tettet.',
        '.tttttt.',
        '.rrrrrr.',
        't.tttt.t',
        'tttttttt',
        't.raar.t',
        '.tttttt.',
        '..t..t..',
        '.xx..xx.',
    ];
    const CLAUDE_COLORS = {
        t: '#e8e3da', a: '#f5c542', e: '#ff9d52', r: '#d97757',
        w: '#ffffff', k: '#2a2a35', x: '#4a4440', b: '#c9c2b4',
        s: '#e8e3da', h: '#e8e3da',
    };

    const SKINS = ['#f4c089', '#d4a574', '#c9956b', '#fdd9b5', '#e8b88a', '#a9714b'];
    const HAIRS = ['#2c1810', '#8b4513', '#b33a2d', '#1a1a1a', '#5d4037', '#e8c26e'];
    const TOPS = ['#7c5cff', '#4ecca3', '#4fc3f7', '#ff8a5c', '#e94560',
                  '#f5c542', '#64dd88', '#b06ee8', '#5c9dff', '#ff6ea0'];
    const BOTTOMS = ['#37474f', '#455a64', '#0d1b4a', '#3a3a4a'];

    function hashString(str) {
        let h = 2166136261;
        for (let i = 0; i < str.length; i++) {
            h ^= str.charCodeAt(i);
            h = Math.imul(h, 16777619);
        }
        return h >>> 0;
    }

    function lighten(hex, amt) {
        const n = parseInt(hex.slice(1), 16);
        const r = Math.min(255, ((n >> 16) & 255) + amt);
        const g = Math.min(255, ((n >> 8) & 255) + amt);
        const b = Math.min(255, (n & 255) + amt);
        return `rgb(${r},${g},${b})`;
    }

    function templateFor(agentType) {
        const t = (agentType || '').toLowerCase();
        if (/explore|research|search|scout|web/.test(t)) return 'scout';
        if (/review|plan|architect|critic|judge/.test(t)) return 'suit';
        if (/bot|general|worker|code/.test(t)) return 'dev';
        return null; // caller picks by hash
    }

    function gridToPixels(grid, colors) {
        const bySlot = {};
        grid.forEach((row, y) => {
            for (let x = 0; x < row.length; x++) {
                const ch = row[x];
                if (ch === '.' || ch === ' ') continue;
                (bySlot[ch] = bySlot[ch] || []).push([x, y]);
            }
        });
        return Object.entries(bySlot).map(([slot, coords]) => ({
            color: colors[slot] || '#888888',
            coords,
        }));
    }

    // ── The hand-drawn cast ──────────────────────────────────────────────
    // The presentation view ships hand-drawn production-company characters
    // (sprites.js, global CHARACTERS). When an agent's name or role matches
    // one — researcher, director, producer, … — use the real character art
    // instead of a generated template.
    const CAST_TINTS = {
        series_producer: '#6a5acd',
        producer: '#8d6e63',
        researcher: '#4fc3f7',
        director: '#e94560',
        production_manager: '#ff9800',
    };

    const normKey = s => String(s || '').toLowerCase().replace(/[^a-z]/g, '');

    function castSprite(label) {
        // sprites.js declares `const CHARACTERS` — a lexical global that never
        // lands on window — so probe the bare identifier, not window.CHARACTERS.
        const chars = typeof CHARACTERS !== 'undefined' ? CHARACTERS : null;
        if (!Array.isArray(chars)) return null;
        const key = normKey(label);
        if (!key) return null;
        const ch = chars.find(c => normKey(c.id) === key || normKey(c.name) === key);
        if (!ch) return null;
        // Character grids may start above row 0 (hats, hair) — shift every
        // pixel onto the canvas and report the true row count.
        let minY = Infinity, maxY = -Infinity;
        ch.pixels.forEach(g => g.coords.forEach(([, y]) => {
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
        }));
        const pixels = ch.pixels.map(g => ({
            color: g.color,
            coords: g.coords.map(([x, y]) => [x, y - minY]),
        }));
        return { pixels, tint: CAST_TINTS[ch.id] || '#f5c542',
                 template: 'cast', rows: maxY - minY + 1 };
    }

    // Build a sprite for a dynamically-spawned agent. Deterministic in
    // (id + name), so replays and scrubbing always redraw the same person.
    function makeAgentSprite(id, name, agentType) {
        const cast = castSprite(name) || castSprite(agentType);
        if (cast) return cast;
        const h = hashString(String(id) + '|' + String(name));
        const keys = Object.keys(TEMPLATES);
        const tplKey = templateFor(agentType) || keys[h % keys.length];
        const top = TOPS[h % TOPS.length];
        const colors = {
            s: SKINS[(h >> 3) % SKINS.length],
            h: HAIRS[(h >> 6) % HAIRS.length],
            t: top,
            a: lighten(top, 60),
            w: '#eceff1',
            b: BOTTOMS[(h >> 9) % BOTTOMS.length],
            x: '#3e2723',
            k: '#1a1a1a',
            e: '#ffe082',
            r: '#e94560',
        };
        return { pixels: gridToPixels(TEMPLATES[tplKey], colors), tint: top,
                 template: tplKey, rows: TEMPLATES[tplKey].length };
    }

    // The orchestrator is the SERIES PRODUCER from the hand-drawn cast,
    // wearing the star's gold glow. The robot grid above stays as a
    // fallback for pages that load without sprites.js.
    const CLAUDE_SPRITE = (function () {
        const sp = castSprite('series producer');
        if (sp) return Object.assign(sp, { tint: '#f5c542', template: 'series_producer' });
        return { pixels: gridToPixels(CLAUDE_GRID, CLAUDE_COLORS),
                 tint: '#d97757', template: 'claude', rows: CLAUDE_GRID.length };
    })();

    // Render a sprite's pixel groups into a canvas at the given pixel size.
    function drawSprite(canvas, sprite, px) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = false;
        sprite.pixels.forEach(group => {
            ctx.fillStyle = group.color;
            group.coords.forEach(([x, y]) => {
                ctx.fillRect(x * px, y * px, px, px);
            });
        });
    }

    window.THEATRE_SPRITES = { makeAgentSprite, CLAUDE_SPRITE, drawSprite, hashString };
})();
