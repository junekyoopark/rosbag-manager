const dropzone = document.getElementById('dropzone');
const fileInput = document.getElementById('file-input');
const nameInput = document.getElementById('name-input');
const descInput = document.getElementById('desc-input');
const queueList = document.getElementById('queue-list');
const queueSection = document.getElementById('upload-queue');
const submitBtn = document.getElementById('submit-btn');

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

submitBtn.addEventListener('click', () => fileInput.click());

// ── Tags input ─────────────────────────────────────────────────
const tagsContainer = document.getElementById('tags-container');
const tagInput = document.getElementById('tag-input');
let tagValues = [];

tagInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ',') {
        e.preventDefault();
        addTag(tagInput.value.trim());
    }
    if (e.key === 'Backspace' && tagInput.value === '' && tagValues.length > 0) {
        removeTag(tagValues[tagValues.length - 1]);
    }
});

function addTag(val) {
    if (!val || tagValues.includes(val)) return;
    tagValues.push(val);
    const chip = document.createElement('span');
    chip.className = 'tag-chip';
    chip.dataset.tag = val;
    chip.innerHTML = `${val}<span class="tag-chip__remove" data-tag="${val}">×</span>`;
    chip.querySelector('.tag-chip__remove').addEventListener('click', () => removeTag(val));
    tagsContainer.insertBefore(chip, tagInput);
    tagInput.value = '';
}

function removeTag(val) {
    tagValues = tagValues.filter(t => t !== val);
    const chip = tagsContainer.querySelector(`[data-tag="${CSS.escape(val)}"]`);
    if (chip) chip.remove();
}

// ── Queue management ──────────────────────────────────────────
let queueId = 0;

function enqueueFile(file) {
    queueSection.style.display = 'block';
    const id = ++queueId;
    const item = createQueueItem(id, file.name);
    queueList.appendChild(item);
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
    `;
    return el;
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
    const stepEl = document.getElementById(`qi-step-${id}`);
    if (stepEl && typeof text === 'string') stepEl.textContent = text;
}

// ── Upload + auto-convert ─────────────────────────────────────
async function uploadFile(file, queueItemId) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', nameInput.value.trim() || file.name.replace(/\.[^.]+$/, ''));
    if (descInput.value.trim()) formData.append('description', descInput.value.trim());
    if (tagValues.length) formData.append('tags', tagValues.join(','));

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
            document.getElementById(`qi-${queueItemId}`)?.classList.add('queue-item--done');
            showPublishForm(queueItemId, bagId, bagName);
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

// ── Publish form ──────────────────────────────────────────────
function showPublishForm(queueItemId, bagId, bagName) {
    const stepEl = document.getElementById(`qi-step-${queueItemId}`);
    if (!stepEl) return;
    stepEl.innerHTML = `
        <div class="publish-form">
            <input class="publish-form__input" type="text" data-field="name"
                   value="${escHtml(bagName)}" placeholder="Name">
            <input class="publish-form__input" type="text" data-field="desc"
                   placeholder="Description (optional)">
            <div class="tags-input chip-input" id="publish-tags-${queueItemId}"
                 onclick="this.querySelector('.chip-input__text').focus()">
                <input class="chip-input__text" type="text" placeholder="Add tag…">
            </div>
            <div class="publish-form__actions">
                <button class="btn btn--primary btn--sm" id="publish-btn-${queueItemId}">Publish</button>
                <a href="/" class="btn btn--secondary btn--sm">View Library</a>
            </div>
        </div>
    `;

    const tagContainer = document.getElementById(`publish-tags-${queueItemId}`);
    const tagInput = makeTagInput(tagContainer);

    document.getElementById(`publish-btn-${queueItemId}`)?.addEventListener('click', async () => {
        const btn = document.getElementById(`publish-btn-${queueItemId}`);
        btn.disabled = true;
        btn.textContent = 'Saving…';

        const nameVal = stepEl.querySelector('[data-field="name"]').value.trim() || bagName;
        const descVal = stepEl.querySelector('[data-field="desc"]').value.trim() || null;
        const tags = tagInput.getValues();

        try {
            const r = await fetch(`/api/bags/${bagId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: nameVal, description: descVal, tags, published: true }),
            });
            if (!r.ok) throw new Error(await r.text());
            stepEl.innerHTML = `<span class="publish-success">✓ Published &middot; <a href="/">View in Library</a></span>`;
        } catch {
            btn.disabled = false;
            btn.textContent = 'Publish';
            setStatus(queueItemId, 'Save failed');
        }
    });
}

function escHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
