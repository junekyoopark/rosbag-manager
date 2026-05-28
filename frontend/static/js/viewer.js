// Viewer page: embed the Rerun web viewer and wire up the topic sidebar.
// Keeps viewer instance alive across bag navigation (soft page swaps).

let _viewer = null;

document.addEventListener('DOMContentLoaded', async () => {
    if (typeof rrdUrl === 'undefined' || !rrdUrl) {
        document.getElementById('rerun-container').innerHTML =
            '<div class="viewer-not-ready"><p>No recording available.</p></div>';
        return;
    }

    try {
        const { WebViewer } = await import('/static/vendor/rerun/index.js');
        _viewer = new WebViewer();
        await _viewer.start(rrdUrl, document.getElementById('rerun-container'), {
            width: '100%',
            height: '100%',
            hide_welcome_screen: true,
        });
    } catch (err) {
        console.error('Failed to start Rerun viewer:', err);
        document.getElementById('rerun-container').innerHTML =
            `<div class="viewer-not-ready"><p>Failed to load viewer: ${err.message}</p></div>`;
    }

    setupTopicClicks();
});

function setupTopicClicks() {
    document.querySelectorAll('.topic-item').forEach((item) => {
        item.addEventListener('click', () => {
            const name = item.querySelector('.topic-item__name')?.textContent?.trim();
            if (name) {
                navigator.clipboard.writeText(name).catch(() => {});
                item.style.background = 'var(--bg-elevated)';
                setTimeout(() => { item.style.background = ''; }, 300);
            }
        });
    });
}

// Load a bag via fetch and update page in-place (soft navigation)
async function softNavigateToBag(bagId) {
    try {
        const resp = await fetch(`/bags/${bagId}/data`);
        if (!resp.ok) throw new Error('Failed to fetch bag data');
        const data = await resp.json();

        if (data.status !== 'ready' || !data.rrd_url) {
            alert('Bag not ready yet');
            return;
        }

        const rrdUrl = window.location.origin + '/rrd/' + data.rrd_url;

        // Update UI with new bag data
        document.querySelector('.viewer-bar__title').textContent = data.name;
        document.getElementById('_bagId').value = data.id;
        document.getElementById('vedit-name').value = data.name;
        document.getElementById('vedit-desc').value = data.description || '';

        // Update tags
        const container = document.getElementById('vedit-tags-container');
        if (container) {
            container.innerHTML = '';
            const input = document.querySelector('#vedit-tag-input');
            if (input) container.appendChild(input);
            _veditTags = data.tags || [];
            for (const tag of _veditTags) {
                const chip = document.createElement('span');
                chip.className = 'tag-chip';
                chip.dataset.tag = tag;
                chip.style.cssText = 'display:inline-flex;align-items:center;gap:3px;background:var(--bg-elevated);border:1px solid var(--border);border-radius:999px;padding:2px 8px;font-size:11px';
                chip.innerHTML = `${tag}<span class="tag-chip__remove" style="cursor:pointer;margin-left:2px">×</span>`;
                chip.querySelector('.tag-chip__remove').addEventListener('click', () => {
                    _veditTags = _veditTags.filter(t => t !== tag);
                    chip.remove();
                });
                container.insertBefore(chip, input);
            }
        }

        // Update browser URL without full page reload
        history.pushState({ bagId }, data.name, `/bags/${data.id}`);

        // Switch Rerun viewer to new RRD file
        if (_viewer && data.rrd_url) {
            await _viewer.open(rrdUrl);
        }
    } catch (err) {
        console.error('Failed to switch bag:', err);
        alert('Could not load bag');
    }
}

// Handle browser back button
window.addEventListener('popstate', (e) => {
    if (e.state?.bagId) {
        softNavigateToBag(e.state.bagId);
    }
});

// Intercept bag card clicks from library pages if viewer is already loaded
document.addEventListener('click', (e) => {
    if (_viewer) {
        const bagLink = e.target.closest('a[href*="/bags/"][href*!="/api/"]');
        if (bagLink && !bagLink.closest('[onclick]')) {
            const bagId = bagLink.href.match(/\/bags\/([^/]+)/)?.[1];
            if (bagId) {
                e.preventDefault();
                softNavigateToBag(bagId);
            }
        }
    }
});
