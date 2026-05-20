// ============================================================================
// GLOBAL STATE
// ============================================================================

let currentResults = null;
let currentPage = 1;
const rowsPerPage = 50;
let filteredPredictions = [];

// ============================================================================
// FILE UPLOAD HANDLING
// ============================================================================

const dragDropBox = document.getElementById('dragDropBox');
const fileInput = document.getElementById('fileInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const fileNameDisplay = document.getElementById('fileName');

// Click to browse
dragDropBox.addEventListener('click', () => fileInput.click());

// Drag and drop
dragDropBox.addEventListener('dragover', (e) => {
    e.preventDefault();
    dragDropBox.classList.add('active');
});

dragDropBox.addEventListener('dragleave', () => {
    dragDropBox.classList.remove('active');
});

dragDropBox.addEventListener('drop', (e) => {
    e.preventDefault();
    dragDropBox.classList.remove('active');
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        onFileSelected();
    }
});

fileInput.addEventListener('change', onFileSelected);

function onFileSelected() {
    const file = fileInput.files[0];
    if (!file) return;
    const lower = file.name.toLowerCase();
    if (!lower.endsWith('.csv') && !lower.endsWith('.txt')) {
        fileNameDisplay.textContent = '❌ Invalid file type. Use .csv or .txt';
        fileNameDisplay.style.color = 'var(--danger)';
        fileNameDisplay.style.display = 'block';
        analyzeBtn.style.display = 'none';
        if (window.toast) window.toast('Invalid file type. Use .csv or .txt', 'error');
        return;
    }
    fileNameDisplay.textContent = `✓ Selected: ${file.name}`;
    fileNameDisplay.style.color = 'var(--success)';
    fileNameDisplay.style.display = 'block';
    analyzeBtn.style.display = 'block';
}

// ============================================================================
// ANALYSIS & PREDICTION
// ============================================================================

analyzeBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) {
        if (window.toast) window.toast('Please select a file first', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    showLoadingSpinner(true);

    try {
        const response = await fetch('/api/predict', { method: 'POST', body: formData });
        const data = await response.json();

        if (!response.ok) {
            showLoadingSpinner(false);
            if (window.toast) window.toast(data.error || 'Prediction failed', 'error');
            return;
        }

        currentResults = data;
        filteredPredictions = [...data.predictions];
        currentPage = 1;

        displayResults(data);
        showLoadingSpinner(false);
        if (window.toast) {
            const msg = data.attacks > 0
                ? `${data.attacks} attacks detected out of ${data.total} rows`
                : `No attacks detected (${data.total} rows scanned)`;
            window.toast(msg, data.attacks > 0 ? 'error' : 'success');
        }
    } catch (error) {
        console.error('Error:', error);
        if (window.toast) window.toast('Error processing file: ' + error.message, 'error');
        showLoadingSpinner(false);
    }
});

// ============================================================================
// DISPLAY RESULTS
// ============================================================================

function displayResults(results) {
    // Show results section
    document.getElementById('resultsSection').style.display = 'block';
    
    // Update summary cards
    document.getElementById('totalRecords').textContent = results.total;
    document.getElementById('normalCount').textContent = results.normal;
    document.getElementById('attackCount').textContent = results.attacks;
    document.getElementById('avgConfidence').textContent = results.avg_confidence.toFixed(1) + '%';
    
    // Update severity counts
    const severityMap = { 'High': 'highCount', 'Medium': 'mediumCount', 'Low': 'lowCount' };
    document.getElementById('highCount').textContent = results.severity_counts['High'] || 0;
    document.getElementById('mediumCount').textContent = results.severity_counts['Medium'] || 0;
    document.getElementById('lowCount').textContent = results.severity_counts['Low'] || 0;
    
    // Display alert
    const alertBox = document.getElementById('alertBox');
    if (results.attacks > 0) {
        alertBox.className = 'card alert-box danger';
        alertBox.innerHTML = `
            <strong>⚠️ ${results.attacks} attacks detected out of ${results.total} records (${results.attack_rate}%)</strong>
            <p>Review flagged connections above immediately</p>
        `;
    } else {
        alertBox.className = 'card alert-box success';
        alertBox.innerHTML = '<strong>✅ No attacks detected in this batch</strong>';
    }
    
    // Draw charts
    drawAttackChart(results);
    drawCategoryChart(results);
    
    // Display predictions table
    displayPredictionsTable(results.predictions);
}

// ============================================================================
// CHARTS
// ============================================================================

let attackChart = null;
let categoryChart = null;

function drawAttackChart(results) {
    const ctx = document.getElementById('attackChart').getContext('2d');
    
    if (attackChart) {
        attackChart.destroy();
    }
    
    attackChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Normal', 'Attack'],
            datasets: [{
                data: [results.normal, results.attacks],
                backgroundColor: ['#22c55e', '#ef4444'],
                borderColor: '#0f172a',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e2e8f0',
                        padding: 16,
                        font: { size: 13, weight: '500' }
                    }
                }
            }
        }
    });
}

function drawCategoryChart(results) {
    const ctx = document.getElementById('categoryChart').getContext('2d');
    
    if (categoryChart) {
        categoryChart.destroy();
    }
    
    const categories = Object.keys(results.category_counts);
    const counts = Object.values(results.category_counts);
    
    const colorMap = {
        'Normal': '#22c55e',
        'DoS': '#ef4444',
        'Probe': '#f97316',
        'R2L': '#a855f7',
        'U2R': '#ec4899'
    };
    
    const colors = categories.map(cat => colorMap[cat] || '#94a3b8');
    
    categoryChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: categories,
            datasets: [{
                label: 'Count',
                data: counts,
                backgroundColor: colors,
                borderColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(56,189,248,0.1)' }
                },
                y: {
                    ticks: { color: '#94a3b8' },
                    grid: { display: false }
                }
            }
        }
    });
}

// ============================================================================
// PREDICTIONS TABLE
// ============================================================================

function displayPredictionsTable(predictions) {
    updateTable();
    setupEventListeners();
}

function updateTable() {
    const tbody = document.getElementById('predictionsBody');
    tbody.innerHTML = '';
    
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    const pagePredictions = filteredPredictions.slice(start, end);
    
    pagePredictions.forEach((pred) => {
        const tr = document.createElement('tr');
        
        const rowClass = pred.prediction === 'Attack' ? 'attack-row' : 'normal-row';
        tr.className = rowClass;
        
        tr.innerHTML = `
            <td>${pred.row}</td>
            <td><strong>${pred.prediction}</strong></td>
            <td>${pred.confidence}%</td>
            <td>${pred.category}</td>
            <td><span style="padding: 4px 8px; border-radius: 4px; background-color: ${getSeverityColor(pred.severity)}; color: #000; font-weight: 600; font-size: 0.85em;">${pred.severity}</span></td>
        `;
        
        tbody.appendChild(tr);
    });
    
    updatePagination();
}

function getSeverityColor(severity) {
    const colorMap = {
        'High': '#ef4444',
        'Medium': '#f97316',
        'Low': '#eab308',
        'Safe': '#22c55e'
    };
    return colorMap[severity] || '#94a3b8';
}

function updatePagination() {
    const totalPages = Math.ceil(filteredPredictions.length / rowsPerPage);
    const paginationDiv = document.getElementById('pagination');
    paginationDiv.innerHTML = '';
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            updateTable();
            window.scrollTo(0, 0);
        }
    });
    paginationDiv.appendChild(prevBtn);
    
    // Page info
    const pageInfo = document.createElement('span');
    pageInfo.style.alignSelf = 'center';
    pageInfo.style.color = '#94a3b8';
    pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
    paginationDiv.appendChild(pageInfo);
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            updateTable();
            window.scrollTo(0, 0);
        }
    });
    paginationDiv.appendChild(nextBtn);
}

// ============================================================================
// SEARCH & FILTER
// ============================================================================

let _eventsBound = false;
function setupEventListeners() {
    if (_eventsBound) return;
    _eventsBound = true;
    const searchBox = document.getElementById('searchBox');
    const attacksOnlyFilter = document.getElementById('attacksOnlyFilter');

    if (searchBox) {
        const debounced = (window.debounce || ((fn) => fn))(applyFilters, 150);
        searchBox.addEventListener('input', debounced);
    }
    if (attacksOnlyFilter) {
        attacksOnlyFilter.addEventListener('change', applyFilters);
    }

    window.addEventListener('resize', () => {
        if (attackChart) attackChart.resize();
        if (categoryChart) categoryChart.resize();
    });
}

function applyFilters() {
    const searchTerm = document.getElementById('searchBox').value.toLowerCase();
    const attacksOnly = document.getElementById('attacksOnlyFilter').checked;
    
    filteredPredictions = currentResults.predictions.filter(pred => {
        const matchesSearch = !searchTerm || 
            pred.prediction.toLowerCase().includes(searchTerm) ||
            pred.category.toLowerCase().includes(searchTerm);
        
        const matchesFilter = !attacksOnly || pred.prediction === 'Attack';
        
        return matchesSearch && matchesFilter;
    });
    
    currentPage = 1;
    updateTable();
}

// ============================================================================
// DOWNLOAD RESULTS
// ============================================================================

document.getElementById('downloadBtn').addEventListener('click', () => {
    if (!currentResults) return;
    
    let csv = '#,Prediction,Confidence,Category,Severity\n';
    currentResults.predictions.forEach(pred => {
        csv += `${pred.row},${pred.prediction},${pred.confidence}%,${pred.category},${pred.severity}\n`;
    });
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'ids_predictions.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
});

// ============================================================================
// LOADING SPINNER
// ============================================================================

function showLoadingSpinner(show) {
    const spinner = document.getElementById('loadingSpinner');
    if (show) {
        spinner.style.display = 'flex';
    } else {
        spinner.style.display = 'none';
    }
}