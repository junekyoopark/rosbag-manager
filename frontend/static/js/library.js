// ── Search with HTMX ──────────────────────────────────────────
// HTMX handles most of the library page interactivity via hx-* attributes.
// This file handles filter button toggling and relative timestamp formatting.

document.addEventListener('DOMContentLoaded', () => {
    initFilterButtons();
    formatRelativeTimes();
    formatRosTimes();
    initSearchTagParsing();
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

// ── ROS timestamps (nanoseconds → browser local time) ─────────
function formatRosTimes() {
    document.querySelectorAll('[data-ros-time]').forEach(el => {
        const ns = el.dataset.rosTime;
        if (!ns) return;
        const dt = new Date(Number(ns) / 1e6);
        el.textContent = dt.toLocaleString(undefined, {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
        });
        el.title = 'Recording start: ' + dt.toLocaleString();
    });
}

// ── Tag filter state ──────────────────────────────────────────
const _activeTags = new Set();
let _tagMode = 'or';

// ── Chip rendering ────────────────────────────────────────────
function _renderChips() {
    const chips = document.getElementById('active-tag-chips');
    const row = document.getElementById('active-tag-row');
    if (!chips) return;
    chips.innerHTML = '';
    for (const tag of _activeTags) {
        const chip = document.createElement('span');
        chip.className = 'tag-filter-chip';
        chip.dataset.tag = tag;
        chip.innerHTML = `${_esc(tag)}<button class="tag-filter-chip__remove"
            onmousedown="event.preventDefault(); removeTagFilter('${_esc(tag)}')" title="Remove">×</button>`;
        chips.appendChild(chip);
    }
    if (row) row.style.display = _activeTags.size > 0 ? 'flex' : 'none';
    const bar = document.getElementById('tag-mode-bar');
    if (bar) bar.style.display = _activeTags.size >= 2 ? 'flex' : 'none';
}

// ── Tag filter actions ────────────────────────────────────────
function _syncTagInputs() {
    const tagsEl = document.getElementById('filter-tags');
    const modeEl = document.getElementById('filter-tag-mode');
    if (tagsEl) tagsEl.value = [..._activeTags].join(',');
    if (modeEl) modeEl.value = _tagMode;
}

function addTagFilter(tag) {
    tag = (tag || '').trim();
    if (!tag || _activeTags.has(tag)) return;
    _activeTags.add(tag);
    const input = document.getElementById('tag-filter-input');
    if (input) input.value = '';
    _syncTagInputs();
    _renderChips();
    refreshGrid();
    highlightActiveTags();
}

function removeTagFilter(tag) {
    _activeTags.delete(tag);
    _syncTagInputs();
    _renderChips();
    refreshGrid();
    highlightActiveTags();
}

function clearTagFilters() {
    _activeTags.clear();
    _syncTagInputs();
    _renderChips();
    refreshGrid();
    highlightActiveTags();
}

function filterByTag(tag) {
    if (_activeTags.has(tag)) removeTagFilter(tag);
    else addTagFilter(tag);
}

function setTagMode(mode) {
    _tagMode = mode;
    _syncTagInputs();
    document.getElementById('btn-tag-or')?.classList.toggle('active', mode === 'or');
    document.getElementById('btn-tag-and')?.classList.toggle('active', mode === 'and');
    refreshGrid();
}

// ── Search bar #tag parsing ───────────────────────────────────
function initSearchTagParsing() {
    const searchInput = document.querySelector('input[name="q"]');
    if (!searchInput) return;
    searchInput.addEventListener('input', () => {
        const val = searchInput.value;
        let changed = false;
        const newVal = val.replace(/#(\S+)\s/g, (match, tag) => {
            addTagFilter(tag);
            changed = true;
            return '';
        });
        if (changed) searchInput.value = newVal.trimStart();
    });
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const val = searchInput.value;
            const tagMatch = val.match(/#(\S+)$/);
            if (tagMatch) {
                e.preventDefault();
                searchInput.value = val.replace(/#\S+$/, '').trim();
                addTagFilter(tagMatch[1]);
            }
        }
    });
}

// ── Multi-team filter ─────────────────────────────────────────
const _activeTeams = new Set();

function toggleTeamFilter(btn) {
    const team = btn.dataset.team;
    if (team === '') {
        _activeTeams.clear();
    } else {
        if (_activeTeams.has(team)) _activeTeams.delete(team);
        else _activeTeams.add(team);
    }
    document.querySelectorAll('.filter-btn[data-team]').forEach(b => {
        if (b.dataset.team === '') b.classList.toggle('active', _activeTeams.size === 0);
        else b.classList.toggle('active', _activeTeams.has(b.dataset.team));
    });
    document.getElementById('filter-team').value = [..._activeTeams].join(',');
    refreshGrid();
}

// ── Grid refresh ──────────────────────────────────────────────
function refreshGrid() {
    const params = new URLSearchParams();
    const q = document.querySelector('input[name="q"]')?.value;
    if (q) params.set('q', q);
    const status = document.getElementById('filter-status')?.value;
    const format = document.getElementById('filter-format')?.value;
    const drafts = document.getElementById('filter-drafts')?.value;
    if (status) params.set('status', status);
    if (format) params.set('format', format);
    if (drafts && drafts !== 'false') params.set('drafts', drafts);
    if (_activeTeams.size > 0) params.set('team', [..._activeTeams].join(','));
    if (_activeTags.size > 0) {
        params.set('tags', [..._activeTags].join(','));
        params.set('tag_mode', _tagMode);
    }
    htmx.ajax('GET', '/api/bags/grid-partial?' + params.toString(), {
        target: '#bag-grid', swap: 'innerHTML',
    });
}

function highlightActiveTags() {
    document.querySelectorAll('.tag--clickable[data-tag]').forEach(btn => {
        btn.classList.toggle('tag--active', _activeTags.has(btn.dataset.tag));
    });
}

// Inject active tags + tag_mode + active teams into all HTMX grid requests
document.addEventListener('htmx:configRequest', (e) => {
    if (!e.detail.path.includes('/api/bags/grid-partial')) return;
    if (_activeTags.size > 0) {
        e.detail.parameters['tags'] = [..._activeTags].join(',');
        e.detail.parameters['tag_mode'] = _tagMode;
    }
    if (_activeTeams.size > 0) {
        e.detail.parameters['team'] = [..._activeTeams].join(',');
    } else {
        delete e.detail.parameters['team'];
    }
});

document.addEventListener('htmx:afterSettle', () => {
    highlightActiveTags();
    document.querySelectorAll('time[datetime]').forEach(el => {
        const dt = new Date(el.getAttribute('datetime'));
        if (!isNaN(dt)) { el.textContent = timeAgo(dt); el.title = dt.toLocaleString(); }
    });
    formatRosTimes();
});

function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Send bag to NAS ───────────────────────────────────────────
let _nasPopoverBagId = null;
let _nasDefaultPath = null;
const _nasActiveSends = new Map();  // bagId → { taskId, es, cancelBtn }

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

        // Add cancel button to progress area
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn--ghost btn--sm';
        cancelBtn.style.cssText = 'margin-top:4px;font-size:11px';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', () => cancelNasSend(bagId));
        if (progressEl) progressEl.appendChild(cancelBtn);

        const es = new EventSource(`/nas/task/${task_id}/stream`);
        _nasActiveSends.set(bagId, { taskId: task_id, es, cancelBtn });

        const _cleanupSend = (finalText, btnText) => {
            es.close();
            const s = _nasActiveSends.get(bagId);
            if (s) { s.cancelBtn?.remove(); _nasActiveSends.delete(bagId); }
            if (stepEl) stepEl.textContent = finalText;
            if (btn) { btn.disabled = false; btn.textContent = btnText; }
        };

        es.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (barEl) barEl.style.width = (data.pct || 0) + '%';
            if (stepEl) stepEl.textContent = data.step || data.state;

            if (data.state === 'SUCCESS') {
                if (barEl) barEl.style.width = '100%';
                _cleanupSend('✓ Sent to NAS', '✓ NAS');
            } else if (data.state === 'FAILURE') {
                _cleanupSend('✗ NAS upload failed', '→ NAS');
            }
        };
        es.onerror = () => _cleanupSend('✗ Connection lost', '→ NAS');
    } catch {
        if (stepEl) stepEl.textContent = '✗ Error';
        if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
    }
}

async function cancelNasSend(bagId) {
    const send = _nasActiveSends.get(bagId);
    if (!send) return;
    if (send.es) send.es.close();
    _nasActiveSends.delete(bagId);
    if (send.cancelBtn) send.cancelBtn.remove();
    try { await fetch(`/nas/task/${send.taskId}`, { method: 'DELETE' }); } catch {}
    const btn = document.getElementById(`nas-btn-${bagId}`);
    if (btn) { btn.disabled = false; btn.textContent = '→ NAS'; }
    const stepEl = document.getElementById(`nas-step-${bagId}`);
    if (stepEl) stepEl.textContent = 'Cancelled';
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
