// Viewer page: embed the Rerun web viewer and wire up the topic sidebar.
// rrdUrl and rerunVersion are injected as globals by viewer.html.

document.addEventListener('DOMContentLoaded', async () => {
    if (typeof rrdUrl === 'undefined' || !rrdUrl) {
        document.getElementById('rerun-container').innerHTML =
            '<div class="viewer-not-ready"><p>No recording available.</p></div>';
        return;
    }

    try {
        const { WebViewer } = await import('/static/vendor/rerun/index.js');
        const viewer = new WebViewer();
        await viewer.start(rrdUrl, document.getElementById('rerun-container'), {
            width: '100%',
            height: '100%',
            hide_welcome_screen: true,
        });
    } catch (err) {
        console.error('Failed to start Rerun viewer:', err);
        document.getElementById('rerun-container').innerHTML =
            `<div class="viewer-not-ready"><p>Failed to load viewer: ${err.message}</p></div>`;
    }

    // ── Topic copy-on-click ──────────────────────────────────
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
});
