let historyChart = null;

document.addEventListener('DOMContentLoaded', loadHistory);

async function loadHistory() {
    const tbody = document.getElementById('historyBody');
    const empty = document.getElementById('historyEmpty');
    const errBox = document.getElementById('historyError');

    try {
        const res = await fetch('/api/history?limit=50');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const runs = data.runs || [];

        if (!runs.length) {
            empty.style.display = 'block';
            return;
        }

        // Table (newest first as returned by API)
        tbody.innerHTML = '';
        runs.forEach((r, i) => {
            const tr = document.createElement('tr');
            tr.className = r.attacks > 0 ? 'attack-row' : 'normal-row';
            tr.innerHTML = `
                <td>${runs.length - i}</td>
                <td>${formatTimestamp(r.timestamp)}</td>
                <td>${escapeHtml(r.filename || '—')}</td>
                <td>${r.total}</td>
                <td><strong>${r.attacks}</strong></td>
                <td>${r.attack_rate.toFixed(2)}%</td>
                <td>${r.avg_confidence.toFixed(1)}%</td>
            `;
            tbody.appendChild(tr);
        });

        drawHistoryChart(runs);
    } catch (err) {
        console.error('history load failed', err);
        errBox.style.display = 'block';
        if (window.toast) window.toast('Could not load history', 'error');
    }
}

function drawHistoryChart(runs) {
    // chronological order for the time-series chart (API gives newest first)
    const ordered = [...runs].reverse();
    const labels = ordered.map(r => formatTimestamp(r.timestamp, true));
    const rates = ordered.map(r => r.attack_rate);

    const canvas = document.getElementById('historyChart');
    const ctx = canvas.getContext('2d');
    if (historyChart) historyChart.destroy();

    historyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Attack rate (%)',
                data: rates,
                borderColor: '#38bdf8',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                tension: 0.3,
                fill: true,
                pointRadius: 4,
                pointBackgroundColor: '#6366f1',
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { labels: { color: '#94a3b8' } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(56,189,248,0.1)' } },
                y: {
                    ticks: { color: '#94a3b8', callback: v => v + '%' },
                    grid: { color: 'rgba(56,189,248,0.1)' },
                    beginAtZero: true,
                    suggestedMax: 100,
                },
            },
        },
    });

    window.addEventListener('resize', () => historyChart && historyChart.resize(), { once: false });
}

function formatTimestamp(iso, short = false) {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return iso;
        if (short) return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        return d.toLocaleString();
    } catch (_) {
        return iso;
    }
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}
