// ── Search with HTMX ──────────────────────────────────────────
// HTMX handles most of the library page interactivity via hx-* attributes.
// This file handles filter button toggling and relative timestamp formatting.

document.addEventListener('DOMContentLoaded', () => {
    initFilterButtons();
    formatRelativeTimes();
});

// ── Filter buttons ────────────────────────────────────────────
function initFilterButtons() {
    document.querySelectorAll('.filter-btn[data-group]').forEach((btn) => {
        // Update hidden input BEFORE htmx fires the request
        btn.addEventListener('click', () => {
            const fieldId = btn.dataset.field;
            const value = btn.dataset.value ?? '';
            if (fieldId) {
                const input = document.getElementById(fieldId);
                if (input) input.value = value;
            }
            // Update active state within this group
            const group = btn.dataset.group;
            document.querySelectorAll(`.filter-btn[data-group="${group}"]`).forEach(b => {
                b.classList.remove('active');
            });
            btn.classList.add('active');
        });
    });
}

// ── Relative timestamps ───────────────────────────────────────
function formatRelativeTimes() {
    document.querySelectorAll('time[datetime]').forEach((el) => {
        const iso = el.getAttribute('datetime');
        if (!iso) return;
        const dt = new Date(iso);
        el.textContent = timeAgo(dt);
        el.title = dt.toLocaleString();
    });
}

function timeAgo(dt) {
    const now = Date.now();
    const diff = Math.floor((now - dt.getTime()) / 1000);

    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    if (diff < 86400 * 30) return `${Math.floor(diff / 86400)}d ago`;
    return dt.toLocaleDateString();
}

// ── Tag filter state ──────────────────────────────────────────
const _activeTags = new Set();
let _tagMode = 'or'; // 'or' | 'and'

function filterByTag(tag) {
    if (_activeTags.has(tag)) {
        _activeTags.delete(tag);
    } else {
        _activeTags.add(tag);
    }
    refreshGrid();
    highlightActiveTags();
    updateTagModeBar();
}

function setTagMode(mode) {
    _tagMode = mode;
    document.getElementById('btn-tag-or').classList.toggle('active', mode === 'or');
    document.getElementById('btn-tag-and').classList.toggle('active', mode === 'and');
    refreshGrid();
}

function refreshGrid() {
    const params = new URLSearchParams();
    const q = document.querySelector('input[name="q"]')?.value;
    if (q) params.set('q', q);
    const status = document.getElementById('filter-status')?.value;
    const format = document.getElementById('filter-format')?.value;
    if (status) params.set('status', status);
    if (format) params.set('format', format);
    if (_activeTags.size > 0) {
        params.set('tags', [..._activeTags].join(','));
        params.set('tag_mode', _tagMode);
    }
    htmx.ajax('GET', '/api/bags/grid-partial?' + params.toString(), {
        target: '#bag-grid',
        swap: 'innerHTML',
    });
}

function highlightActiveTags() {
    document.querySelectorAll('.tag--clickable').forEach(btn => {
        btn.classList.toggle('tag--active', _activeTags.has(btn.dataset.tag));
    });
}

function updateTagModeBar() {
    const bar = document.getElementById('tag-mode-bar');
    if (!bar) return;
    if (_activeTags.size >= 2) {
        bar.style.display = '';
        bar.classList.remove('hidden');
    } else {
        bar.style.display = 'none';
    }
}

// Inject active tags into every HTMX grid request (filter buttons, search bar)
document.addEventListener('htmx:configRequest', (e) => {
    if (!e.detail.path.includes('/api/bags/grid-partial')) return;
    if (_activeTags.size > 0) {
        e.detail.parameters['tags'] = [..._activeTags].join(',');
        e.detail.parameters['tag_mode'] = _tagMode;
    }
});

// Re-highlight after every grid swap
document.addEventListener('htmx:afterSettle', highlightActiveTags);

// ── Send bag to NAS ───────────────────────────────────────────
let _nasPopoverBagId = null;
let _nasDefaultPath = null;

async function _getNasDefaultPath() {
    if (_nasDefaultPath !== null) return _nasDefaultPath;
    try {
        const r = await fetch('/nas/config');
        if (r.ok) {
            const data = await r.json();
            _nasDefaultPath = data.upload_path || '/rosbags';
        }
    } catch {}
    return _nasDefaultPath || '/rosbags';
}

async function sendToNas(bagId, anchorEl) {
    const popover = document.getElementById('nas-dest-popover');
    if (!popover) { _doSendToNas(bagId, null); return; }

    _nasPopoverBagId = bagId;
    const defaultPath = await _getNasDefaultPath();
    document.getElementById('nas-dest-input').value = defaultPath;

    // Position popover near the button
    if (anchorEl) {
        const rect = anchorEl.getBoundingClientRect();
        const top = rect.bottom + 6;
        let left = rect.right - 300;
        if (left < 8) left = 8;
        popover.style.top = top + 'px';
        popover.style.left = left + 'px';
    } else {
        popover.style.top = '50%';
        popover.style.left = '50%';
        popover.style.transform = 'translate(-50%,-50%)';
    }
    popover.style.display = 'flex';

    const confirmBtn = document.getElementById('nas-dest-confirm');
    confirmBtn.onclick = () => {
        const path = document.getElementById('nas-dest-input').value.trim() || defaultPath;
        closeNasPopover();
        _doSendToNas(bagId, path);
    };

    document.getElementById('nas-dest-input').onkeydown = (e) => {
        if (e.key === 'Enter') confirmBtn.click();
        if (e.key === 'Escape') closeNasPopover();
    };
    setTimeout(() => document.getElementById('nas-dest-input').select(), 0);
}

function closeNasPopover() {
    const popover = document.getElementById('nas-dest-popover');
    if (popover) popover.style.display = 'none';
    _nasPopoverBagId = null;
}

document.addEventListener('click', (e) => {
    const popover = document.getElementById('nas-dest-popover');
    if (popover && popover.style.display !== 'none' && !popover.contains(e.target)) {
        const btn = e.target.closest('[id^="nas-btn-"]');
        if (!btn) closeNasPopover();
    }
});

async function _doSendToNas(bagId, destPath) {
    const btn = document.getElementById(`nas-btn-${bagId}`);
    const progressEl = document.getElementById(`nas-progress-${bagId}`);
    const barEl = document.getElementById(`nas-bar-${bagId}`);
    const stepEl = document.getElementById(`nas-step-${bagId}`);

    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    if (progressEl) progressEl.style.display = 'block';

    try {
        const r = await fetch(`/nas/bags/${bagId}/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dest_path: destPath }),
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: 'Failed' }));
            if (stepEl) stepEl.textContent = '✗ ' + (err.detail || 'Failed');
            if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
            return;
        }
        const { task_id } = await r.json();

        const es = new EventSource(`/nas/task/${task_id}/stream`);
        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (barEl) barEl.style.width = (data.pct || 0) + '%';
            if (stepEl) stepEl.textContent = data.step || data.state;

            if (data.state === 'SUCCESS') {
                es.close();
                if (barEl) barEl.style.width = '100%';
                if (stepEl) stepEl.textContent = '✓ Sent to NAS';
                if (btn) { btn.disabled = false; btn.textContent = '✓ NAS'; }
            } else if (data.state === 'FAILURE') {
                es.close();
                if (stepEl) stepEl.textContent = '✗ NAS upload failed';
                if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
            }
        };
        es.onerror = () => {
            es.close();
            if (stepEl) stepEl.textContent = '✗ Connection lost';
            if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
        };
    } catch {
        if (stepEl) stepEl.textContent = '✗ Error';
        if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
    }
}

// ── Publish a draft bag ───────────────────────────────────────
async function publishBag(bagId, btn) {
    btn.disabled = true;
    btn.textContent = 'Publishing…';
    try {
        const r = await fetch(`/api/bags/${bagId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ published: true }),
        });
        if (!r.ok) throw new Error(await r.text());
        // Remove the card from drafts view or refresh it in normal view
        htmx.ajax('GET', `/api/bags/${bagId}/card-partial`, {
            target: `[data-bag-id="${bagId}"]`,
            swap: 'outerHTML',
        });
    } catch {
        btn.disabled = false;
        btn.textContent = 'Publish';
    }
}

// ── Copy topic name on click ──────────────────────────────────
document.addEventListener('click', (e) => {
    const topicName = e.target.closest('.topic-item__name');
    if (topicName) {
        navigator.clipboard.writeText(topicName.textContent.trim()).catch(() => {});
        topicName.style.opacity = '0.5';
        setTimeout(() => { topicName.style.opacity = ''; }, 300);
    }
});
