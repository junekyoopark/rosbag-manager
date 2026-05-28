// ── Robot SFTP Import ─────────────────────────────────────────────
let _robotId = null;
let _robotName = '';
let _sftpPath = null;
let _selectedFile = null;  // {path, name, size}
let _pollTimer = null;

function openRobotImport(robotId, robotName) {
    _robotId = robotId;
    _robotName = robotName;
    _selectedFile = null;
    _sftpPath = null;

    document.getElementById('import-modal-title').textContent = 'Import from ' + robotName;
    document.getElementById('ssh-user').value = '';
    document.getElementById('ssh-pass').value = '';
    document.getElementById('sftp-browser').style.display = 'none';
    document.getElementById('sftp-error').style.display = 'none';
    document.getElementById('sftp-selected-name').textContent = '';
    showImportPhase('browse');
    document.getElementById('robot-import-modal').classList.remove('hidden');
    setTimeout(() => document.getElementById('ssh-user').focus(), 80);
}

function closeRobotImport() {
    document.getElementById('robot-import-modal').classList.add('hidden');
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

function showImportPhase(phase) {
    document.getElementById('import-browse-phase').style.display   = phase === 'browse'   ? '' : 'none';
    document.getElementById('import-options-phase').style.display  = phase === 'options'  ? '' : 'none';
    document.getElementById('import-progress-phase').style.display = phase === 'progress' ? '' : 'none';
}

function showBrowsePhase() {
    _selectedFile = null;
    showImportPhase('browse');
}

// ── SFTP connect & browse ─────────────────────────────────────────

async function connectSftp() {
    const user = document.getElementById('ssh-user').value.trim();
    const pass = document.getElementById('ssh-pass').value;
    if (!user) { _sftpError('Enter a username.'); return; }

    _sftpError('');
    document.querySelector('#import-browse-phase .btn--secondary').textContent = 'Connecting…';
    document.querySelector('#import-browse-phase .btn--secondary').disabled = true;

    await _sftpLoad('.');
    document.querySelector('#import-browse-phase .btn--secondary').textContent = 'Connect';
    document.querySelector('#import-browse-phase .btn--secondary').disabled = false;
}

async function _sftpLoad(path) {
    const user = document.getElementById('ssh-user').value.trim();
    const pass = document.getElementById('ssh-pass').value;

    try {
        const resp = await fetch('/robots/' + _robotId + '/sftp/browse', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user, password: pass, path: path}),
        });
        const data = await resp.json();
        if (data.error) { _sftpError(data.error); return; }
        _sftpPath = data.path;
        _renderFileList(data.path, data.items);
        document.getElementById('sftp-browser').style.display = '';
        document.getElementById('sftp-error').style.display = 'none';
    } catch (e) {
        _sftpError('Connection failed: ' + e.message);
    }
}

function _renderFileList(path, items) {
    document.getElementById('sftp-path').textContent = path;
    const list = document.getElementById('sftp-list');

    let html = '';
    // Up directory
    const parent = path.includes('/') ? path.replace(/\/[^/]+\/?$/, '') || '/' : '/';
    if (path !== '/' && path !== '') {
        html += `<div class="file-item file-item--up" onclick="_sftpLoad('${_esc(parent)}')">
            <span class="file-item__icon">↩</span>
            <span class="file-item__name">.. (up)</span>
        </div>`;
    }

    for (const item of items) {
        const icon = item.is_dir ? '📁' : '📄';
        const size = item.is_dir ? '' : _fmtSize(item.size);
        const cls = (!item.is_dir && _selectedFile && _selectedFile.path === item.path) ? ' selected' : '';
        if (item.is_dir) {
            html += `<div class="file-item${cls}" onclick="_sftpLoad('${_esc(item.path)}')">
                <span class="file-item__icon">${icon}</span>
                <span class="file-item__name">${_esc(item.name)}</span>
                <span class="file-item__size">${size}</span>
            </div>`;
        } else {
            html += `<div class="file-item${cls}" onclick="_selectFile(${JSON.stringify(item)})">
                <span class="file-item__icon">${icon}</span>
                <span class="file-item__name">${_esc(item.name)}</span>
                <span class="file-item__size">${size}</span>
            </div>`;
        }
    }
    if (!items.length && path !== '/') {
        html = '<div style="padding:12px;font-size:13px;color:var(--text-muted)">No bag files here.</div>';
    }
    list.innerHTML = html;
}

function _selectFile(item) {
    _selectedFile = item;
    document.getElementById('sftp-selected-name').textContent = item.name + ' selected';
    // Re-render to highlight
    const items = Array.from(document.querySelectorAll('#sftp-list .file-item:not(.file-item--up)'));
    items.forEach(el => {
        const nameEl = el.querySelector('.file-item__name');
        if (nameEl && nameEl.textContent === item.name) el.classList.add('selected');
        else el.classList.remove('selected');
    });

    // Move to options phase
    document.getElementById('import-file-label').textContent = item.path;
    document.getElementById('import-name').value = item.name.replace(/\.[^.]+$/, '');
    showImportPhase('options');
}

function _sftpError(msg) {
    const el = document.getElementById('sftp-error');
    if (msg) { el.textContent = msg; el.style.display = ''; }
    else { el.style.display = 'none'; }
}

// ── Import ────────────────────────────────────────────────────────

async function startImport() {
    if (!_selectedFile) return;
    const user = document.getElementById('ssh-user').value.trim();
    const pass = document.getElementById('ssh-pass').value;
    const name = document.getElementById('import-name').value.trim();

    showImportPhase('progress');
    _setProgress(1, 'Queuing transfer…');
    document.getElementById('import-progress-done').style.display = 'none';

    try {
        const resp = await fetch('/robots/' + _robotId + '/sftp/import', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                username: user,
                password: pass,
                path: _selectedFile.path,
                name: name || null,
            }),
        });
        const data = await resp.json();
        if (data.error) {
            _setProgress(0, 'Error: ' + data.error);
            return;
        }
        _pollProgress(data.task_id);
    } catch (e) {
        _setProgress(0, 'Failed: ' + e.message);
    }
}

function _pollProgress(taskId) {
    if (_pollTimer) clearInterval(_pollTimer);
    _pollTimer = setInterval(async () => {
        try {
            const r = await fetch('/api/jobs/' + taskId + '/status');
            if (!r.ok) return;
            const d = await r.json();
            if (d.state === 'PROGRESS') {
                _setProgress(d.meta?.pct ?? 0, d.meta?.step ?? 'Transferring…');
            } else if (d.state === 'SUCCESS') {
                _setProgress(100, 'Done');
                clearInterval(_pollTimer); _pollTimer = null;
                document.getElementById('import-progress-done').style.display = '';
            } else if (d.state === 'FAILURE') {
                _setProgress(0, 'Failed: ' + (d.error || 'unknown error'));
                clearInterval(_pollTimer); _pollTimer = null;
            }
        } catch {}
    }, 1000);
}

function _setProgress(pct, msg) {
    document.getElementById('import-progress-msg').textContent = msg;
    document.getElementById('import-progress-bar').style.width = pct + '%';
}

// ── Helpers ───────────────────────────────────────────────────────

function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _fmtSize(bytes) {
    if (!bytes) return '';
    const units = ['B','KB','MB','GB','TB'];
    let n = bytes, i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return n.toFixed(1) + ' ' + units[i];
}
