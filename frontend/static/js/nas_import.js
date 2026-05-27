// ── NAS Import browser ────────────────────────────────────────
let _nasPath = '/';
let _nasSelected = new Set();   // set of paths
let _nasFileMap  = new Map();   // path → {name, size}
let _nasImportTagValues = [];
let _nasActiveStreams = [];     // {es, poll, taskId} for cleanup

// ── Open / close ──────────────────────────────────────────────
async function openNasImport() {
    document.getElementById('nas-import-modal').classList.remove('hidden');
    _nasSelected.clear();
    _nasFileMap.clear();
    _nasImportTagValues = [];
    _nasRenderSelectionBar();
    _nasRenderImportChips();
    _nasShowPhase('browse');

    let startPath = '/';
    try {
        const r = await fetch('/nas/import-path');
        if (r.ok) startPath = (await r.json()).path || '/';
    } catch {}
    _nasLoadDir(startPath);
}

function closeNasImport() {
    document.getElementById('nas-import-modal').classList.add('hidden');

    // Move still-active rows to the persistent activity panel instead of killing their streams
    const queueEl = document.getElementById('nas-queue-list');
    const activityList = document.getElementById('nas-activity-list');
    if (queueEl && activityList) {
        [...queueEl.querySelectorAll('.nas-queue-item:not([data-done])')].forEach(row => {
            activityList.appendChild(row);
        });
    }

    // Discard only fully-finished streams (es=null && poll=null)
    _nasActiveStreams = _nasActiveStreams.filter(s => s.es !== null || s.poll !== null);
    _nasActivityUpdate();
}

function _nasShowPhase(phase) {
    document.getElementById('nas-browse-phase').style.display  = phase === 'browse'  ? '' : 'none';
    document.getElementById('nas-queue-phase').style.display   = phase === 'queue'   ? '' : 'none';
}

// ── Directory loading ─────────────────────────────────────────
async function _nasLoadDir(path) {
    _nasPath = path;
    const list = document.getElementById('nas-file-list');
    list.innerHTML = '<div class="nas-loading">Loading…</div>';
    _nasRenderBreadcrumb(path);

    try {
        const r = await fetch('/nas/browse?path=' + encodeURIComponent(path));
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: 'Error' }));
            list.innerHTML = _nasErrorHtml(err.detail || 'Failed to load NAS folder');
            return;
        }
        const data = await r.json();
        _nasRenderList(data.items);
    } catch {
        list.innerHTML = _nasErrorHtml('Connection failed');
    }
}

function _nasRenderBreadcrumb(path) {
    const bc = document.getElementById('nas-breadcrumb');
    const parts = path.replace(/\/+$/, '').split('/').filter(Boolean);
    let html = `<span class="nas-bc-item" onclick="_nasLoadDir('/')">/</span>`;
    let cum = '';
    for (const part of parts) {
        cum += '/' + part;
        const p = cum;
        html += `<span class="nas-bc-sep">›</span>
                 <span class="nas-bc-item" onclick="_nasLoadDir('${_nasEsc(p)}')">${_nasEsc(part)}</span>`;
    }
    bc.innerHTML = html;
}

function _nasRenderList(items) {
    const list = document.getElementById('nas-file-list');
    if (!items.length) {
        list.innerHTML = '<div class="nas-empty">No bag files or folders here.</div>';
        return;
    }

    // Track files in this listing
    items.forEach(it => { if (!it.is_dir) _nasFileMap.set(it.path, it); });

    list.innerHTML = items.map(item => {
        if (item.is_dir) {
            return `<div class="nas-item nas-item--dir" data-path="${_nasEsc(item.path)}">
                        <span class="nas-item__icon">📁</span>
                        <span class="nas-item__name">${_nasEsc(item.name)}</span>
                    </div>`;
        }
        const checked = _nasSelected.has(item.path) ? 'checked' : '';
        return `<div class="nas-item nas-item--file" data-path="${_nasEsc(item.path)}">
                    <input class="nas-check" type="checkbox" ${checked}
                           data-path="${_nasEsc(item.path)}" data-name="${_nasEsc(item.name)}"
                           data-size="${item.size || 0}">
                    <span class="nas-item__icon">🎬</span>
                    <span class="nas-item__name">${_nasEsc(item.name)}</span>
                    <span class="nas-item__size">${_nasFormatSize(item.size)}</span>
                </div>`;
    }).join('');

    list.querySelectorAll('.nas-item--dir').forEach(el => {
        el.addEventListener('click', () => _nasLoadDir(el.dataset.path));
    });
    list.querySelectorAll('.nas-item--file').forEach(el => {
        el.addEventListener('click', e => {
            if (e.target.type === 'checkbox') return; // handled separately
            const cb = el.querySelector('.nas-check');
            if (cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); }
        });
    });
    list.querySelectorAll('.nas-check').forEach(cb => {
        cb.addEventListener('change', () => {
            if (cb.checked) _nasSelected.add(cb.dataset.path);
            else            _nasSelected.delete(cb.dataset.path);
            _nasRenderSelectionBar();
        });
    });
}

// ── Selection bar ─────────────────────────────────────────────
function _nasRenderSelectionBar() {
    const bar  = document.getElementById('nas-selection-bar');
    const cntEl = document.getElementById('nas-selection-count');
    const btn  = document.getElementById('nas-import-confirm-btn');
    const n = _nasSelected.size;
    if (n === 0) {
        bar.style.display = 'none';
        return;
    }
    bar.style.display = '';
    cntEl.textContent = `${n} bag${n > 1 ? 's' : ''} selected`;
    btn.textContent   = `Import ${n} bag${n > 1 ? 's' : ''}`;
}

// ── Tag chips ─────────────────────────────────────────────────
function _nasRenderImportChips() {
    const container = document.getElementById('nas-import-tag-chips');
    if (!container) return;
    const input = document.getElementById('nas-import-tag-input');
    container.querySelectorAll('.tag-chip').forEach(c => c.remove());
    for (const t of _nasImportTagValues) {
        const chip = document.createElement('span');
        chip.className = 'tag-chip';
        chip.innerHTML = `${_nasEsc(t)}<span class="tag-chip__remove" data-tag="${_nasEsc(t)}">×</span>`;
        chip.querySelector('.tag-chip__remove').addEventListener('click', () => {
            _nasImportTagValues = _nasImportTagValues.filter(x => x !== t);
            _nasRenderImportChips();
        });
        container.insertBefore(chip, input);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const ti = document.getElementById('nas-import-tag-input');
    if (!ti) return;
    ti.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const val = ti.value.trim();
            if (val && !_nasImportTagValues.includes(val)) {
                _nasImportTagValues.push(val);
                _nasRenderImportChips();
            }
            ti.value = '';
        }
        if (e.key === 'Backspace' && ti.value === '' && _nasImportTagValues.length) {
            _nasImportTagValues.pop();
            _nasRenderImportChips();
        }
    });
});

// ── Confirm import ────────────────────────────────────────────
let _nasTotalImports = 0;
let _nasPublishedCount = 0;

async function confirmNasImport() {
    if (_nasSelected.size === 0) return;

    const teamBtns = document.querySelectorAll('#nas-import-team-group .tag--active');
    const team = [...teamBtns].map(b => b.dataset.team);
    const paths = [..._nasSelected];

    _nasTotalImports = paths.length;
    _nasPublishedCount = 0;

    _nasShowPhase('queue');
    const queueEl = document.getElementById('nas-queue-list');
    queueEl.innerHTML = '';

    await Promise.all(paths.map(path => _nasStartOneImport(path, team, queueEl)));
}

async function _nasStartOneImport(path, team, queueEl) {
    const info = _nasFileMap.get(path) || { name: path.split('/').pop() };
    const defaultName = info.name.replace(/\.[^.]+$/, '');

    const rowId = 'nas-qi-' + Math.random().toString(36).slice(2);
    const row = document.createElement('div');
    row.className = 'nas-queue-item';
    row.id = rowId;

    const hasTeams = typeof _nasTeams !== 'undefined' && _nasTeams.length > 0;
    row.innerHTML = `
        <div class="nas-qi__filename">
            <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"
                 viewBox="0 0 24 24" style="flex-shrink:0;opacity:0.5">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                <polyline points="13 2 13 9 20 9"/>
            </svg>
            ${_nasEsc(info.name)}
        </div>
        <div class="nas-qi__body">
            <div class="nas-qi__row2">
                <div class="nas-qi__field">
                    <label class="nas-qi__label">Name</label>
                    <input class="modal__input" type="text"
                           id="${rowId}-name" value="${_nasEsc(defaultName)}" placeholder="Name"
                           style="font-size:12px;padding:5px 8px">
                </div>
                <div class="nas-qi__field">
                    <label class="nas-qi__label">Description</label>
                    <input class="modal__input" type="text"
                           id="${rowId}-desc" placeholder="Optional…"
                           style="font-size:12px;padding:5px 8px">
                </div>
            </div>
            ${hasTeams ? `<div class="nas-qi__field">
                <label class="nas-qi__label">Team</label>
                <div class="nas-qi__team-group" id="${rowId}-team"></div>
            </div>` : ''}
            <div class="nas-qi__field">
                <label class="nas-qi__label">Tags</label>
                <div class="nas-qi__tags-input" id="${rowId}-tags-container"
                     onclick="document.getElementById('${rowId}-tag-input').focus()">
                    <input type="text" id="${rowId}-tag-input" placeholder="Add tag…">
                </div>
            </div>
            <div class="nas-qi__progress-section">
                <div class="nas-qi__progress-row">
                    <div class="progress-bar nas-qi__bar">
                        <div class="progress-bar__fill" id="${rowId}-bar" style="width:2%"></div>
                    </div>
                    <span class="nas-qi__status" id="${rowId}-status">Starting…</span>
                </div>
                <div class="nas-qi__actions" id="${rowId}-actions"></div>
            </div>
        </div>`;
    queueEl.appendChild(row);
    // Scroll to bottom so the newest card (including its progress bar) is fully visible
    queueEl.scrollTop = queueEl.scrollHeight;

    // ── Team toggles ──────────────────────────────────────────
    const teamGroupEl = document.getElementById(`${rowId}-team`);
    if (hasTeams && teamGroupEl) {
        for (const t of _nasTeams) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'tag tag--clickable team-toggle' + (team.includes(t) ? ' tag--active' : '');
            btn.dataset.team = t;
            btn.textContent = t;
            btn.addEventListener('click', () => btn.classList.toggle('tag--active'));
            teamGroupEl.appendChild(btn);
        }
    }

    // ── Per-row tag chips ─────────────────────────────────────
    let rowTags = [..._nasImportTagValues];
    function _renderRowTags() {
        const container = document.getElementById(`${rowId}-tags-container`);
        const input = document.getElementById(`${rowId}-tag-input`);
        if (!container || !input) return;
        container.querySelectorAll('.tag-chip').forEach(c => c.remove());
        for (const t of rowTags) {
            const chip = document.createElement('span');
            chip.className = 'tag-chip';
            chip.dataset.tag = t;
            chip.innerHTML = `${_nasEsc(t)}<span class="tag-chip__remove">×</span>`;
            chip.querySelector('.tag-chip__remove').addEventListener('click', () => {
                rowTags = rowTags.filter(x => x !== t);
                _renderRowTags();
            });
            container.insertBefore(chip, input);
        }
    }
    _renderRowTags();
    const tagInput = document.getElementById(`${rowId}-tag-input`);
    if (tagInput) {
        tagInput.addEventListener('keydown', e => {
            if ((e.key === 'Enter' || e.key === ',') && !e.isComposing) {
                e.preventDefault();
                const val = tagInput.value.trim();
                if (val && !rowTags.includes(val)) { rowTags.push(val); _renderRowTags(); }
                tagInput.value = '';
            }
            if (e.key === 'Backspace' && tagInput.value === '' && rowTags.length) {
                rowTags.pop(); _renderRowTags();
            }
        });
    }

    // ── Progress helper ───────────────────────────────────────
    const setStatus = (pct, text) => {
        const b = document.getElementById(`${rowId}-bar`);
        const s = document.getElementById(`${rowId}-status`);
        if (b) b.style.width = Math.max(pct, 2) + '%';
        if (s) s.textContent = text;
    };

    try {
        const r = await fetch('/nas/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, name: defaultName, tags: _nasImportTagValues, team }),
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: 'Failed' }));
            setStatus(0, '✗ ' + (err.detail || 'Failed'));
            _nasMarkRowDone(rowId);
            return;
        }
        const { task_id, bag_id } = await r.json();
        _nasPersistAdd(task_id, bag_id, info.name);

        const actionsEl = document.getElementById(`${rowId}-actions`);
        const cancelBtn = document.createElement('button');
        cancelBtn.id = `${rowId}-cancel`;
        cancelBtn.className = 'btn btn--ghost btn--sm';
        cancelBtn.style.fontSize = '11px';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', () => _nasCancelOneImport(task_id, rowId, setStatus));
        if (actionsEl) actionsEl.appendChild(cancelBtn);

        _nasWatchImport(task_id, bag_id, rowId, setStatus);
    } catch {
        setStatus(0, '✗ Request error');
        _nasMarkRowDone(rowId);
    }
}

function _nasWatchImportResume(taskId, bagId, rowId, setStatus, actionsEl, cancelBtn) {
    const es = new EventSource(`/nas/task/${taskId}/stream`);
    const stream = { es, poll: null, taskId };
    _nasActiveStreams.push(stream);
    es.onmessage = e => {
        const data = JSON.parse(e.data);
        setStatus(data.pct || 0, data.step || data.state);
        if (data.state === 'SUCCESS') {
            es.close(); stream.es = null;
            cancelBtn?.remove();
            setStatus(90, 'Converting…');
            if (typeof refreshGrid === 'function') refreshGrid();
            stream.poll = setInterval(async () => {
                try {
                    const r = await fetch(`/api/bags/${bagId}`);
                    if (!r.ok) return;
                    const bag = await r.json();
                    if (bag.status === 'ready') {
                        clearInterval(stream.poll); stream.poll = null;
                        setStatus(100, '✓ Ready');
                        _nasPersistRemove(taskId);
                        _nasAddPublishBtn(rowId, bagId);
                        if (typeof refreshGrid === 'function') refreshGrid();
                    } else if (bag.status === 'error') {
                        clearInterval(stream.poll); stream.poll = null;
                        setStatus(0, '✗ Conversion failed');
                        _nasPersistRemove(taskId);
                        _nasMarkRowDone(rowId);
                    }
                } catch {}
            }, 3000);
        } else if (data.state === 'FAILURE') {
            es.close(); stream.es = null;
            cancelBtn?.remove();
            _nasPersistRemove(taskId);
            setStatus(0, '✗ Import failed');
            _nasMarkRowDone(rowId);
        }
    };
    es.onerror = () => {
        es.close(); stream.es = null;
        cancelBtn?.remove();
        setStatus(0, '✗ Connection lost');
        _nasMarkRowDone(rowId);
    };
}

function _nasWatchImport(taskId, bagId, rowId, setStatus) {
    const es = new EventSource(`/nas/task/${taskId}/stream`);
    const stream = { es, poll: null, taskId };
    _nasActiveStreams.push(stream);

    es.onmessage = e => {
        const data = JSON.parse(e.data);
        setStatus(data.pct || 0, data.step || data.state);

        if (data.state === 'SUCCESS') {
            es.close();
            stream.es = null;
            document.getElementById(`${rowId}-cancel`)?.remove();
            setStatus(100, 'Converting…');
            if (typeof refreshGrid === 'function') refreshGrid();
            // Poll for conversion completion
            stream.poll = setInterval(async () => {
                try {
                    const r = await fetch(`/api/bags/${bagId}`);
                    if (!r.ok) return;
                    const bag = await r.json();
                    if (bag.status === 'ready') {
                        clearInterval(stream.poll);
                        stream.poll = null;
                        setStatus(100, '✓ Ready');
                        _nasPersistRemove(taskId);
                        _nasAddPublishBtn(rowId, bagId);
                        if (typeof refreshGrid === 'function') refreshGrid();
                    } else if (bag.status === 'error') {
                        clearInterval(stream.poll);
                        stream.poll = null;
                        setStatus(0, '✗ Conversion failed');
                        _nasPersistRemove(taskId);
                        _nasMarkRowDone(rowId);
                    }
                } catch {}
            }, 3000);
        } else if (data.state === 'FAILURE') {
            es.close();
            stream.es = null;
            document.getElementById(`${rowId}-cancel`)?.remove();
            setStatus(0, '✗ Import failed');
            _nasPersistRemove(taskId);
            _nasMarkRowDone(rowId);
        }
    };
    es.onerror = () => {
        es.close();
        stream.es = null;
        document.getElementById(`${rowId}-cancel`)?.remove();
        setStatus(0, '✗ Connection lost');
        _nasMarkRowDone(rowId);
    };
}

function _nasAddPublishBtn(rowId, bagId) {
    const row = document.getElementById(rowId);
    if (!row) return;
    const btn = document.createElement('button');
    btn.className = 'btn btn--primary btn--sm';
    btn.style.fontSize = '11px';
    btn.textContent = 'Publish';
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.textContent = 'Publishing…';
        const name = document.getElementById(`${rowId}-name`)?.value.trim();
        const desc = document.getElementById(`${rowId}-desc`)?.value.trim() || null;
        const tagContainer = document.getElementById(`${rowId}-tags-container`);
        const tagInputEl = document.getElementById(`${rowId}-tag-input`);
        const tags = tagContainer
            ? [...tagContainer.querySelectorAll('.tag-chip[data-tag]')].map(c => c.dataset.tag)
            : [];
        const pendingTag = tagInputEl?.value.trim();
        if (pendingTag && !tags.includes(pendingTag)) tags.push(pendingTag);
        const teamGroup = document.getElementById(`${rowId}-team`);
        const team = teamGroup
            ? [...teamGroup.querySelectorAll('.tag--active')].map(b => b.dataset.team)
            : [];
        try {
            const r = await fetch(`/api/bags/${bagId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, description: desc, tags, team, published: true }),
            });
            if (!r.ok) throw new Error();
            btn.textContent = '✓ Published';
            if (typeof refreshGrid === 'function') refreshGrid();
            _nasPublishedCount++;
            _nasCheckAllDone();
            _nasMarkRowDone(rowId);
        } catch {
            btn.disabled = false;
            btn.textContent = 'Publish';
        }
    });
    const actionsEl = document.getElementById(`${rowId}-actions`);
    if (actionsEl) actionsEl.appendChild(btn);
    else row.appendChild(btn);
}

function _nasCheckAllDone() {
    if (_nasPublishedCount < _nasTotalImports) return;
    const footer = document.querySelector('#nas-queue-phase .modal__footer');
    if (!footer) return;
    const closeBtn = footer.querySelector('.btn--secondary');
    if (closeBtn) {
        closeBtn.textContent = 'Done';
        closeBtn.classList.replace('btn--secondary', 'btn--primary');
    }
}

// ── Cancel one NAS import ─────────────────────────────────────
async function _nasCancelOneImport(taskId, rowId, setStatus) {
    const stream = _nasActiveStreams.find(s => s.taskId === taskId);
    if (stream) {
        if (stream.es) stream.es.close();
        if (stream.poll) clearInterval(stream.poll);
        _nasActiveStreams = _nasActiveStreams.filter(s => s !== stream);
    }
    try { await fetch(`/nas/task/${taskId}`, { method: 'DELETE' }); } catch {}
    setStatus(0, 'Cancelled');
    document.getElementById(`${rowId}-cancel`)?.remove();
    _nasPersistRemove(taskId);
    _nasMarkRowDone(rowId);
}

// ── Helpers ───────────────────────────────────────────────────
function _nasFormatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
    return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

function _nasEsc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function _nasErrorHtml(msg) {
    const suffix = (typeof _nasUserIsAdmin !== 'undefined' && _nasUserIsAdmin)
        ? ` — <a href="/nas" style="color:inherit;text-decoration:underline">Configure NAS →</a>`
        : ' — contact your administrator to configure NAS.';
    return `<div class="nas-error">${_nasEsc(msg)}${suffix}</div>`;
}

// ── Activity panel ────────────────────────────────────────────
function _nasMarkRowDone(rowId) {
    const row = document.getElementById(rowId);
    if (row) row.dataset.done = '1';
    _nasActivityUpdate();
}

function _nasActivityUpdate() {
    const panel = document.getElementById('nas-activity-panel');
    const list  = document.getElementById('nas-activity-list');
    if (!panel || !list) return;
    const total  = list.querySelectorAll('.nas-queue-item').length;
    const active = list.querySelectorAll('.nas-queue-item:not([data-done])').length;
    if (total === 0) { panel.style.display = 'none'; return; }
    panel.style.display = '';
    const countEl = document.getElementById('nas-activity-count');
    if (countEl) countEl.textContent = active > 0 ? `${active} running` : 'All done';
    const closeBtn = document.getElementById('nas-activity-close');
    if (closeBtn) closeBtn.style.display = active === 0 ? '' : 'none';
}

function toggleNasActivityPanel() {
    const body   = document.getElementById('nas-activity-body');
    const toggle = document.getElementById('nas-activity-toggle');
    if (!body) return;
    const isHidden = body.style.display === 'none';
    body.style.display = isHidden ? '' : 'none';
    if (toggle) toggle.textContent = isHidden ? '−' : '+';
}

function closeNasActivityPanel() {
    const panel = document.getElementById('nas-activity-panel');
    const list  = document.getElementById('nas-activity-list');
    if (list) list.innerHTML = '';
    if (panel) panel.style.display = 'none';
    _nasPersistClear();
}

// ── Persist active tasks across page refresh ──────────────────
const _NAS_PERSIST_KEY = 'nas_active_imports';
const _NAS_PERSIST_TTL = 2 * 60 * 60 * 1000;  // 2 hours

function _nasPersistAdd(taskId, bagId, name) {
    try {
        const items = _nasPersistLoad();
        items.push({ taskId, bagId, name, ts: Date.now() });
        localStorage.setItem(_NAS_PERSIST_KEY, JSON.stringify(items));
    } catch {}
}

function _nasPersistRemove(taskId) {
    try {
        const items = _nasPersistLoad().filter(i => i.taskId !== taskId);
        localStorage.setItem(_NAS_PERSIST_KEY, JSON.stringify(items));
    } catch {}
}

function _nasPersistClear() {
    try { localStorage.removeItem(_NAS_PERSIST_KEY); } catch {}
}

function _nasPersistLoad() {
    try {
        const raw = localStorage.getItem(_NAS_PERSIST_KEY);
        if (!raw) return [];
        return JSON.parse(raw).filter(i => Date.now() - i.ts < _NAS_PERSIST_TTL);
    } catch { return []; }
}

// Resume watching any tasks that were active before page refresh
document.addEventListener('DOMContentLoaded', async () => {
    const pending = _nasPersistLoad();
    if (!pending.length) return;
    const activityList = document.getElementById('nas-activity-list');
    if (!activityList) return;

    for (const { taskId, bagId, name } of pending) {
        let bag = null;
        try {
            const r = await fetch(`/api/bags/${bagId}`);
            if (r.ok) bag = await r.json();
        } catch {}
        const bagStatus = bag?.status ?? null;

        const rowId = 'nas-resume-' + taskId.slice(0, 8);
        const row = document.createElement('div');
        row.className = 'nas-queue-item';
        row.id = rowId;

        const hasTeams = typeof _nasTeams !== 'undefined' && _nasTeams.length > 0;
        const bagName = bag?.name || name.replace(/\.[^.]+$/, '');
        const bagDesc = bag?.description || '';
        const bagTags = bag?.tags || [];
        const bagTeam = bag?.team || [];

        row.innerHTML = `
            <div class="nas-qi__filename">
                <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"
                     viewBox="0 0 24 24" style="flex-shrink:0;opacity:0.5">
                    <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/>
                    <polyline points="13 2 13 9 20 9"/>
                </svg>
                ${_nasEsc(name)}
                <span style="margin-left:auto;font-style:italic;color:var(--text-muted)">resumed</span>
            </div>
            <div class="nas-qi__body">
                <div class="nas-qi__progress-section">
                    <div class="nas-qi__progress-row">
                        <div class="progress-bar nas-qi__bar">
                            <div class="progress-bar__fill" id="${rowId}-bar" style="width:2%"></div>
                        </div>
                        <span class="nas-qi__status" id="${rowId}-status">Connecting…</span>
                    </div>
                    <div class="nas-qi__actions" id="${rowId}-actions"></div>
                </div>
                <div id="${rowId}-fields" style="display:none;margin-top:8px;display:none">
                    <div class="nas-qi__row2">
                        <div class="nas-qi__field">
                            <label class="nas-qi__label">Name</label>
                            <input class="modal__input" type="text"
                                   id="${rowId}-name" value="${_nasEsc(bagName)}" placeholder="Name"
                                   style="font-size:12px;padding:5px 8px">
                        </div>
                        <div class="nas-qi__field">
                            <label class="nas-qi__label">Description</label>
                            <input class="modal__input" type="text"
                                   id="${rowId}-desc" value="${_nasEsc(bagDesc)}" placeholder="Optional…"
                                   style="font-size:12px;padding:5px 8px">
                        </div>
                    </div>
                    ${hasTeams ? `<div class="nas-qi__field" style="margin-top:6px">
                        <label class="nas-qi__label">Team</label>
                        <div class="nas-qi__team-group" id="${rowId}-team"></div>
                    </div>` : ''}
                    <div class="nas-qi__field" style="margin-top:6px">
                        <label class="nas-qi__label">Tags</label>
                        <div class="nas-qi__tags-input" id="${rowId}-tags-container"
                             onclick="document.getElementById('${rowId}-tag-input').focus()">
                            <input type="text" id="${rowId}-tag-input" placeholder="Add tag…">
                        </div>
                    </div>
                </div>
            </div>`;
        activityList.appendChild(row);

        // Team toggles (pre-select existing team)
        const teamGroupEl = document.getElementById(`${rowId}-team`);
        if (hasTeams && teamGroupEl) {
            for (const t of _nasTeams) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'tag tag--clickable team-toggle' + (bagTeam.includes(t) ? ' tag--active' : '');
                btn.dataset.team = t;
                btn.textContent = t;
                btn.addEventListener('click', () => btn.classList.toggle('tag--active'));
                teamGroupEl.appendChild(btn);
            }
        }

        // Tag chips (pre-filled with existing tags)
        let rowTags = [...bagTags];
        const _renderResumeTags = () => {
            const container = document.getElementById(`${rowId}-tags-container`);
            const input = document.getElementById(`${rowId}-tag-input`);
            if (!container || !input) return;
            container.querySelectorAll('.tag-chip').forEach(c => c.remove());
            for (const t of rowTags) {
                const chip = document.createElement('span');
                chip.className = 'tag-chip';
                chip.dataset.tag = t;
                chip.innerHTML = `${_nasEsc(t)}<span class="tag-chip__remove">×</span>`;
                chip.querySelector('.tag-chip__remove').addEventListener('click', () => {
                    rowTags = rowTags.filter(x => x !== t);
                    _renderResumeTags();
                });
                container.insertBefore(chip, input);
            }
        };
        _renderResumeTags();
        const resumeTagInput = document.getElementById(`${rowId}-tag-input`);
        if (resumeTagInput) {
            resumeTagInput.addEventListener('keydown', e => {
                if ((e.key === 'Enter' || e.key === ',') && !e.isComposing) {
                    e.preventDefault();
                    const val = resumeTagInput.value.trim();
                    if (val && !rowTags.includes(val)) { rowTags.push(val); _renderResumeTags(); }
                    resumeTagInput.value = '';
                }
                if (e.key === 'Backspace' && resumeTagInput.value === '' && rowTags.length) {
                    rowTags.pop(); _renderResumeTags();
                }
            });
        }

        const setStatus = (pct, text) => {
            const b = document.getElementById(`${rowId}-bar`);
            const s = document.getElementById(`${rowId}-status`);
            if (b) b.style.width = Math.max(pct, 2) + '%';
            if (s) s.textContent = text;
        };

        const actionsEl = document.getElementById(`${rowId}-actions`);

        // Edit button — reveals the editable fields
        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn--secondary btn--sm';
        editBtn.style.fontSize = '11px';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => {
            const fields = document.getElementById(`${rowId}-fields`);
            if (!fields) return;
            const visible = fields.style.display !== 'none';
            fields.style.display = visible ? 'none' : '';
            editBtn.textContent = visible ? 'Edit' : 'Done';
        });
        if (actionsEl) actionsEl.appendChild(editBtn);

        // Cancel button
        const cancelBtn = document.createElement('button');
        cancelBtn.id = `${rowId}-cancel`;
        cancelBtn.className = 'btn btn--ghost btn--sm';
        cancelBtn.style.fontSize = '11px';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', async () => {
            actionsEl.innerHTML = '';
            try { await fetch(`/nas/task/${taskId}`, { method: 'DELETE' }); } catch {}
            setStatus(0, 'Cancelled');
            _nasPersistRemove(taskId);
            _nasMarkRowDone(rowId);
        });
        if (actionsEl) actionsEl.appendChild(cancelBtn);

        _nasActivityUpdate();

        if (bagStatus === 'ready') {
            setStatus(100, '✓ Ready');
            cancelBtn.remove();
            _nasPersistRemove(taskId);
            _nasAddPublishBtn(rowId, bagId);
            if (typeof refreshGrid === 'function') refreshGrid();
        } else if (bagStatus === 'error') {
            setStatus(0, '✗ Failed');
            cancelBtn.remove();
            editBtn.remove();
            _nasPersistRemove(taskId);
            _nasMarkRowDone(rowId);
        } else if (bagStatus === 'converting') {
            setStatus(90, 'Converting…');
            cancelBtn.remove();
            const poll = setInterval(async () => {
                try {
                    const r = await fetch(`/api/bags/${bagId}`);
                    if (!r.ok) return;
                    const b = await r.json();
                    if (b.status === 'ready') {
                        clearInterval(poll);
                        setStatus(100, '✓ Ready');
                        _nasPersistRemove(taskId);
                        _nasAddPublishBtn(rowId, bagId);
                        if (typeof refreshGrid === 'function') refreshGrid();
                    } else if (b.status === 'error') {
                        clearInterval(poll);
                        setStatus(0, '✗ Conversion failed');
                        _nasPersistRemove(taskId);
                        editBtn.remove();
                        _nasMarkRowDone(rowId);
                    }
                } catch {}
            }, 3000);
        } else {
            // Still downloading — watch SSE
            _nasWatchImportResume(taskId, bagId, rowId, setStatus, actionsEl, cancelBtn);
        }
    }
});
