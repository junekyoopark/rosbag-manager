const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const queueList = document.getElementById('queue-list');
const queueSection = document.getElementById('upload-queue');

// ── Drag-and-drop ──────────────────────────────────────────────
dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const files = [...e.dataTransfer.files];
    files.forEach(enqueueFile);
});

fileInput.addEventListener('change', () => {
    [...fileInput.files].forEach(enqueueFile);
    fileInput.value = '';
});

// ── Queue management ──────────────────────────────────────────
let queueId = 0;
const _tagInputs = {};

function enqueueFile(file) {
    queueSection.style.display = 'block';
    const id = ++queueId;
    const item = createQueueItem(id, file.name);
    queueList.appendChild(item);
    _initMetadataForm(id, file.name);
    uploadFile(file, id);
}

function createQueueItem(id, filename) {
    const el = document.createElement('div');
    el.className = 'queue-item';
    el.id = `qi-${id}`;
    el.innerHTML = `
        <div class="queue-item__header">
            <span class="queue-item__name">${escHtml(filename)}</span>
            <span class="queue-item__status" id="qi-status-${id}">Waiting…</span>
        </div>
        <div class="progress-bar" id="qi-bar-wrap-${id}">
            <div class="progress-bar__fill" id="qi-bar-${id}" style="width:0%"></div>
        </div>
        <div class="queue-item__step" id="qi-step-${id}"></div>
        <div id="qi-meta-${id}"></div>
    `;
    return el;
}

function _initMetadataForm(queueItemId, filename) {
    const metaEl = document.getElementById(`qi-meta-${queueItemId}`);
    if (!metaEl) return;

    const defaultName = filename.replace(/\.[^.]+$/, '');
    const teams = (typeof upload_teams !== 'undefined') ? upload_teams : [];
    const userTeam = (typeof upload_user_team !== 'undefined' && upload_user_team) ? upload_user_team : '';
    const teamsHtml = teams.length ? `
        <div style="display:flex;flex-wrap:wrap;gap:6px" id="qi-teams-${queueItemId}">
            ${teams.map(t => `<button type="button" class="tag tag--clickable team-toggle${t === userTeam ? ' tag--active' : ''}" data-team="${escHtml(t)}" onclick="this.classList.toggle('tag--active')">${escHtml(t)}</button>`).join('')}
        </div>` : '';

    metaEl.innerHTML = `
        <div class="publish-form">
            <input class="publish-form__input" type="text" id="qi-name-${queueItemId}"
                   value="${escHtml(defaultName)}" placeholder="Name">
            <input class="publish-form__input" type="text" id="qi-desc-${queueItemId}"
                   placeholder="Description (optional)">
            ${teamsHtml}
            <div class="tags-input chip-input" id="qi-tags-${queueItemId}"
                 onclick="this.querySelector('.chip-input__text').focus()">
                <input class="chip-input__text" type="text" placeholder="Add tag…">
            </div>
            <div class="publish-form__actions" id="qi-actions-${queueItemId}" style="display:none">
                <button class="btn btn--primary btn--sm" id="publish-btn-${queueItemId}">Publish</button>
                <a href="/" class="btn btn--secondary btn--sm">View Library</a>
            </div>
        </div>
    `;

    const tagContainer = document.getElementById(`qi-tags-${queueItemId}`);
    _tagInputs[queueItemId] = makeTagInput(tagContainer);
}

function setStatus(id, text) {
    const el = document.getElementById(`qi-status-${id}`);
    if (el) el.textContent = text;
}

function setBar(id, pct) {
    const el = document.getElementById(`qi-bar-${id}`);
    if (el) el.style.width = pct + '%';
}

function setStep(id, text) {
    const el = document.getElementById(`qi-step-${id}`);
    if (el) el.textContent = text;
}

// ── Upload + auto-convert ─────────────────────────────────────
async function uploadFile(file, queueItemId) {
    const formData = new FormData();
    formData.append('file', file);

    setStatus(queueItemId, 'Uploading…');

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                setBar(queueItemId, pct);
                setStatus(queueItemId, `${pct}% uploaded`);
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                const resp = JSON.parse(xhr.responseText);
                setStatus(queueItemId, 'Converting…');
                setBar(queueItemId, 0);
                // Update name field with server-confirmed name if user hasn't edited it
                const nameEl = document.getElementById(`qi-name-${queueItemId}`);
                if (nameEl && nameEl.value === nameEl.defaultValue) {
                    nameEl.value = resp.name;
                    nameEl.defaultValue = resp.name;
                }
                watchConversionProgress(resp.job_id, queueItemId, resp.id, resp.name);
                resolve(resp);
            } else {
                setStatus(queueItemId, `Error ${xhr.status}`);
                document.getElementById(`qi-${queueItemId}`)?.classList.add('queue-item--error');
                reject(new Error(xhr.responseText));
            }
        });

        xhr.addEventListener('error', () => {
            setStatus(queueItemId, 'Network error');
            document.getElementById(`qi-${queueItemId}`)?.classList.add('queue-item--error');
            reject(new Error('Network error'));
        });

        xhr.open('POST', '/api/bags/upload');
        xhr.send(formData);
    });
}

// ── SSE conversion progress ───────────────────────────────────
function watchConversionProgress(jobId, queueItemId, bagId, bagName) {
    const evtSource = new EventSource(`/api/jobs/${jobId}/stream`);

    evtSource.onmessage = (e) => {
        const data = JSON.parse(e.data);
        setBar(queueItemId, data.pct || 0);
        setStep(queueItemId, data.step || '');

        if (data.state === 'SUCCESS') {
            evtSource.close();
            setStatus(queueItemId, '✓ Converted');
            setBar(queueItemId, 100);
            setStep(queueItemId, '');
            document.getElementById(`qi-${queueItemId}`)?.classList.add('queue-item--done');
            _revealPublishButton(queueItemId, bagId);
        } else if (data.state === 'FAILURE') {
            evtSource.close();
            setStatus(queueItemId, '✗ Failed');
            document.getElementById(`qi-${queueItemId}`)?.classList.add('queue-item--error');
        }
    };

    evtSource.onerror = () => {
        evtSource.close();
        setStatus(queueItemId, 'Connection lost');
    };
}

// ── Reveal publish button after conversion ────────────────────
function _revealPublishButton(queueItemId, bagId) {
    const actionsEl = document.getElementById(`qi-actions-${queueItemId}`);
    if (actionsEl) actionsEl.style.display = '';

    document.getElementById(`publish-btn-${queueItemId}`)?.addEventListener('click', async () => {
        const btn = document.getElementById(`publish-btn-${queueItemId}`);
        btn.disabled = true;
        btn.textContent = 'Saving…';

        const nameVal = document.getElementById(`qi-name-${queueItemId}`)?.value.trim() || '';
        const descVal = document.getElementById(`qi-desc-${queueItemId}`)?.value.trim() || null;
        const tagInput = _tagInputs[queueItemId];
        const tags = tagInput ? tagInput.getValues() : [];
        const teamPills = document.querySelectorAll(`#qi-teams-${queueItemId} .tag--active`);
        const team = [...teamPills].map(b => b.dataset.team);

        try {
            const r = await fetch(`/api/bags/${bagId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: nameVal || undefined, description: descVal, tags, team: team.length ? team : null, published: true }),
            });
            if (!r.ok) throw new Error(await r.text());
            const metaEl = document.getElementById(`qi-meta-${queueItemId}`);
            if (metaEl) metaEl.innerHTML = `<span class="publish-success">✓ Published &middot; <a href="/">View in Library</a></span>`;
            delete _tagInputs[queueItemId];
        } catch {
            btn.disabled = false;
            btn.textContent = 'Publish';
            setStatus(queueItemId, 'Save failed');
        }
    });
}

// ── Reusable chip tag input ───────────────────────────────────
function makeTagInput(container) {
    const input = container.querySelector('.chip-input__text');
    const values = [];

    function addChip(val) {
        val = val.trim();
        if (!val || values.includes(val)) { input.value = ''; return; }
        values.push(val);
        const chip = document.createElement('span');
        chip.className = 'tag-chip';
        chip.dataset.tag = val;
        chip.innerHTML = `${escHtml(val)}<span class="tag-chip__remove">×</span>`;
        chip.querySelector('.tag-chip__remove').addEventListener('click', () => {
            values.splice(values.indexOf(val), 1);
            chip.remove();
        });
        container.insertBefore(chip, input);
        input.value = '';
    }

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            addChip(input.value);
        }
        if (e.key === 'Backspace' && input.value === '' && values.length) {
            const last = values[values.length - 1];
            values.pop();
            container.querySelector(`[data-tag="${CSS.escape(last)}"]`)?.remove();
        }
    });

    input.addEventListener('blur', () => { if (input.value.trim()) addChip(input.value); });

    return { getValues: () => [...values] };
}

function escHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
