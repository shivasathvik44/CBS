// Pulls real metrics from /api/insights (no hardcoded values).

let featureChart = null;

document.addEventListener('DOMContentLoaded', () => { loadInsights(); });

async function loadInsights() {
    const errBox = document.getElementById('insightsError');
    try {
        const response = await fetch('/api/insights');
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));

        displayMetrics(data);
        displayPerformanceNote(data);
        displayConfusionMatrix(data);
        displayModelParameters(data);
        drawFeatureChart(data.top_features || []);
        renderPerClass(data.per_class || {});
        renderCV(data.cv);
        renderCandidates(data.candidate_scores);
    } catch (err) {
        console.error('insights load failed', err);
        if (errBox) errBox.style.display = 'block';
        if (window.toast) window.toast('Could not load insights — retrain the model?', 'error');
    }
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function displayMetrics(data) {
    setText('accuracyValue', (data.accuracy ?? 0).toFixed(2) + '%');
    setText('precisionValue', (data.precision ?? 0).toFixed(2) + '%');
    setText('recallValue', (data.recall ?? 0).toFixed(2) + '%');
    setText('f1Value', (data.f1 ?? 0).toFixed(2) + '%');
    setText('rocAucValue', (data.roc_auc ?? 0).toFixed(2) + '%');
}

function displayPerformanceNote(data) {
    const performanceText = document.getElementById('performanceText');
    if (!performanceText) return;
    const floor = data.precision_floor ? (data.precision_floor * 100).toFixed(0) + '%' : '85%';
    performanceText.innerHTML = `
        <strong>Model Evaluation Summary</strong><br><br>
        <strong>Precision ${(data.precision ?? 0).toFixed(2)}%:</strong> When the model flags an attack,
        it is correct ${(data.precision ?? 0).toFixed(2)}% of the time.<br><br>
        <strong>Recall ${(data.recall ?? 0).toFixed(2)}%:</strong> The model catches ${(data.recall ?? 0).toFixed(2)}%
        of actual attacks. The decision threshold (${(data.threshold ?? 0.5).toFixed(4)}) is tuned to maximise
        recall while keeping precision above the ${floor} floor — false negatives are more costly than false alarms
        in intrusion detection.<br><br>
        <strong>ROC-AUC ${(data.roc_auc ?? 0).toFixed(2)}%:</strong> Strong separation between normal and attack
        patterns across all thresholds.
    `;
}

function displayConfusionMatrix(data) {
    const cm = data.confusion_matrix || {};
    setText('tnValue', fmtInt(cm.tn));
    setText('fpValue', fmtInt(cm.fp));
    setText('fnValue', fmtInt(cm.fn));
    setText('tpValue', fmtInt(cm.tp));
}

function fmtInt(n) {
    if (n === undefined || n === null) return '—';
    return Number(n).toLocaleString();
}

function displayModelParameters(data) {
    const p = data.model_params || {};
    setText('paramAlgorithm', p.algorithm || '—');
    setText('paramTrees', p.n_estimators ?? p.voting ?? '—');
    setText('paramClassWeight', p.class_weight || '—');
    setText('paramThreshold', (data.threshold ?? 0.5).toFixed(4));
    setText('paramMaxDepth', p.max_depth ?? '—');
    setText('paramRandomState', p.random_state ?? '—');
}

function drawFeatureChart(topFeatures) {
    const canvas = document.getElementById('featureChart');
    if (!canvas || !topFeatures.length) return;
    const ctx = canvas.getContext('2d');
    if (featureChart) featureChart.destroy();

    const labels = topFeatures.map(f => f.name);
    const importances = topFeatures.map(f => f.importance);
    const gradient = ctx.createLinearGradient(0, 0, 500, 0);
    gradient.addColorStop(0, '#38bdf8');
    gradient.addColorStop(1, '#6366f1');

    featureChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Importance',
                data: importances,
                backgroundColor: gradient,
                borderColor: '#38bdf8',
                borderWidth: 1,
            }],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(56,189,248,0.1)' }, max: Math.max(...importances) * 1.2 },
                y: { ticks: { color: '#94a3b8' }, grid: { display: false } },
            },
        },
    });
    window.addEventListener('resize', () => featureChart && featureChart.resize());
}

function renderPerClass(perClass) {
    const tbody = document.getElementById('perClassBody');
    if (!tbody) return;
    tbody.innerHTML = '';
    const names = Object.keys(perClass);
    if (!names.length) {
        document.getElementById('perClassCard')?.style.setProperty('display', 'none');
        return;
    }
    names.forEach(name => {
        const m = perClass[name];
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${name}</strong></td>
            <td>${m.precision.toFixed(2)}%</td>
            <td>${m.recall.toFixed(2)}%</td>
            <td>${m.f1.toFixed(2)}%</td>
            <td>${m.support.toLocaleString()}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderCV(cv) {
    if (!cv) return;
    const target = document.getElementById('cvBlock');
    if (!target) return;
    const rows = Object.entries(cv).map(([k, v]) =>
        `<div class="param-item">
            <div class="param-key">${k.replace(/_/g, ' ')}</div>
            <div class="param-value">${(v.mean * 100).toFixed(2)}% ± ${(v.std * 100).toFixed(2)}%</div>
         </div>`
    ).join('');
    target.innerHTML = rows;
}

function renderCandidates(scores) {
    if (!scores) return;
    const target = document.getElementById('candidateBlock');
    if (!target) return;
    const best = Math.max(...Object.values(scores));
    const rows = Object.entries(scores).map(([k, v]) => {
        const isBest = v === best;
        return `<div class="param-item">
            <div class="param-key">${k.replace(/_/g, ' ')}${isBest ? ' ★' : ''}</div>
            <div class="param-value">${(v * 100).toFixed(2)}%</div>
         </div>`;
    }).join('');
    target.innerHTML = rows;
}
