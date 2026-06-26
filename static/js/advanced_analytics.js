let radarChartInstance = null;
let scatterChartInstance = null;

async function loadDimensionIds(prefix) {
    const typeSelect = document.getElementById(`${prefix}-type`);
    const idSelect = document.getElementById(`${prefix}-id`);
    
    try {
        const res = await fetch(`/api/analytics/list-dimensions?dimension_type=${typeSelect.value}`);
        const data = await res.json();
        
        idSelect.innerHTML = '';
        if (data.length === 0) {
            idSelect.innerHTML = `<option value="">N/A</option>`;
        } else {
            data.forEach(item => {
                const opt = document.createElement('option');
                opt.value = item;
                opt.textContent = item;
                idSelect.appendChild(opt);
            });
        }
        
        // Auto-select defaults to save time
        if(typeSelect.value === 'NETWORK' && data.includes('JORDAN')) {
            idSelect.value = 'JORDAN';
        } else if(typeSelect.value === 'GOVERNORATE' && data.includes('عمان')) {
            idSelect.value = 'عمان';
        }
    } catch (e) {
        console.error("Failed to load dimension IDs", e);
    }
}

async function runComparison() {
    const dim1Type = document.getElementById('dim1-type').value;
    const dim1Id = document.getElementById('dim1-id').value;
    const dim2Type = document.getElementById('dim2-type').value;
    const dim2Id = document.getElementById('dim2-id').value;
    
    if(!dim1Id || !dim2Id) return alert('Please select valid dimensions.');

    try {
        // Fetch Comparison Data
        const res = await fetch(`/api/analytics/compare?dim1_type=${dim1Type}&dim1_id=${dim1Id}&dim2_type=${dim2Type}&dim2_id=${dim2Id}`);
        const data = await res.json();
        
        // Render Z-Scores
        const zCont = document.getElementById('zscore-container');
        const zTbody = document.getElementById('zscore-tbody');
        
        function formatZ(z) {
            return z > 0 ? `<span class="text-success fw-bold">+${z}</span>` : 
                   (z < 0 ? `<span class="text-danger fw-bold">${z}</span>` : `<span>0</span>`);
        }
        
        zTbody.innerHTML = `
            <tr>
                <td class="fw-bold">${data.dim1.name}</td>
                <td>${formatZ(data.dim1.z_scores.governance)}</td>
                <td>${formatZ(data.dim1.z_scores.attendance)}</td>
            </tr>
            <tr>
                <td class="fw-bold">${data.dim2.name}</td>
                <td>${formatZ(data.dim2.z_scores.governance)}</td>
                <td>${formatZ(data.dim2.z_scores.attendance)}</td>
            </tr>
        `;
        zCont.classList.remove('d-none');
        
        renderRadarChart(data.dim1, data.dim2);
        
        // Fetch Predictive Data & Scatter Data for Dim1
        fetchPredictiveInsights(dim1Type, dim1Id);
        fetchScatterData(dim1Type, dim1Id);
    } catch (e) {
        console.error(e);
        alert('Failed to run analysis. Check console.');
    }
}

async function fetchPredictiveInsights(dimType, dimId) {
    const container = document.getElementById('predictive-metrics');
    try {
        const res = await fetch(`/api/analytics/predictive?dimension_type=${dimType}&dimension_id=${dimId}`);
        if(!res.ok) throw new Error('Data not found');
        const data = await res.json();
        
        const ar = window.KINJO_LANG === 'ar' || true; // Force AR based on user context
        
        const trendIcon = data.attendance_trend_slope > 0 ? 'bi-arrow-up-right-circle-fill text-success' : 'bi-arrow-down-right-circle-fill text-danger';
        const trendDir = data.attendance_trend_slope > 0 ? (ar ? 'إيجابي' : 'Positive') : (ar ? 'سلبي' : 'Negative');
        
        const corrVal = (data.staffing_quality_correlation || 0).toFixed(2);
        const corrText = corrVal > 0.5 ? (ar ? 'ارتباط قوي' : 'Strongly Correlated') : (ar ? 'ارتباط ضعيف' : 'Weakly Correlated');

        container.innerHTML = `
            <div class="col-md-4 mb-3">
                <div class="bg-white bg-opacity-10 p-3 rounded h-100 border border-light border-opacity-25">
                    <h6 class="text-white-50 text-uppercase fw-bold mb-2">${ar ? 'معامل الارتباط (طاقم/حوادث)' : 'Staff/Incident Correlation'}</h6>
                    <h2 class="fw-bold mb-0">${corrVal}</h2>
                    <small>${corrText}</small>
                </div>
            </div>
            <div class="col-md-4 mb-3">
                <div class="bg-white bg-opacity-10 p-3 rounded h-100 border border-light border-opacity-25">
                    <h6 class="text-white-50 text-uppercase fw-bold mb-2">${ar ? 'مسار الغياب التنبؤي' : 'Predictive Absence Trend'}</h6>
                    <h2 class="fw-bold mb-0"><i class="bi ${trendIcon}"></i> ${Math.abs(data.attendance_trend_slope).toFixed(2)}</h2>
                    <small>${trendDir}</small>
                </div>
            </div>
            <div class="col-md-4 mb-3">
                <div class="bg-white bg-opacity-10 p-3 rounded h-100 border border-light border-opacity-25">
                    <h6 class="text-white-50 text-uppercase fw-bold mb-2">${ar ? 'مؤشر الخطر المتوقع' : 'Predicted Risk Index'}</h6>
                    <h2 class="fw-bold mb-0 text-warning">${data.risk_score ? data.risk_score.toFixed(1) : 'N/A'}</h2>
                    <small>${ar ? 'بناءً على الانحدار الخطي' : 'Based on linear regression'}</small>
                </div>
            </div>
        `;
    } catch (e) {
        container.innerHTML = `<div class="col-12"><p class="text-warning">No predictive data available for this dimension.</p></div>`;
    }
}

async function fetchScatterData(dimType, dimId) {
    try {
        const res = await fetch(`/api/analytics/scatter?dim_type=${dimType}&dim_id=${dimId}`);
        if (!res.ok) throw new Error('Data not found');
        const data = await res.json();
        renderScatterChart(data);
    } catch (e) {
        console.error("Failed to load scatter data", e);
    }
}

function renderScatterChart(points) {
    const ctx = document.getElementById('scatterChart').getContext('2d');
    
    if (scatterChartInstance) {
        scatterChartInstance.destroy();
    }
    
    const ar = window.KINJO_LANG === 'ar' || true;
    
    scatterChartInstance = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: ar ? 'توزيع الأداء' : 'Performance Distribution',
                data: points,
                backgroundColor: 'rgba(239, 68, 68, 0.6)', // Red for visibility
                borderColor: 'rgba(239, 68, 68, 1)',
                pointRadius: 6,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    title: { display: true, text: ar ? 'علامة الحوكمة (%)' : 'Governance Score (%)' },
                    min: 0,
                    max: 100
                },
                y: {
                    title: { display: true, text: ar ? 'نسبة الحضور (%)' : 'Attendance Rate (%)' },
                    min: 0,
                    max: 100
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return `${ctx.raw.name}: (${ctx.raw.x.toFixed(1)}%, ${ctx.raw.y.toFixed(1)}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderRadarChart(dim1, dim2) {
    const ctx = document.getElementById('radarChart').getContext('2d');
    
    if (radarChartInstance) {
        radarChartInstance.destroy();
    }
    
    const ar = window.KINJO_LANG === 'ar' || true;
    const labels = ar ? 
        ['الحضور', 'الحوكمة', 'الالتحاق', 'السلامة', 'السعة'] : 
        ['Attendance', 'Governance', 'Enrollment', 'Safety', 'Capacity'];

    radarChartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: dim1.name,
                    data: [dim1.attendance, dim1.governance, dim1.enrollment, dim1.safety, dim1.capacity],
                    backgroundColor: 'rgba(79, 70, 229, 0.2)', // Indigo
                    borderColor: 'rgba(79, 70, 229, 1)',
                    pointBackgroundColor: 'rgba(79, 70, 229, 1)',
                    borderWidth: 2
                },
                {
                    label: dim2.name,
                    data: [dim2.attendance, dim2.governance, dim2.enrollment, dim2.safety, dim2.capacity],
                    backgroundColor: 'rgba(14, 165, 233, 0.2)', // Sky blue
                    borderColor: 'rgba(14, 165, 233, 1)',
                    pointBackgroundColor: 'rgba(14, 165, 233, 1)',
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                r: {
                    angleLines: { color: 'rgba(0, 0, 0, 0.1)' },
                    grid: { color: 'rgba(0, 0, 0, 0.1)' },
                    pointLabels: {
                        font: { size: 14, family: "'Inter', sans-serif", weight: 'bold' },
                        color: '#334155'
                    },
                    suggestedMin: 0,
                    suggestedMax: 100
                }
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { font: { size: 14, family: "'Inter', sans-serif" } }
                }
            }
        }
    });
}

// Init
document.addEventListener("DOMContentLoaded", () => {
    loadDimensionIds('dim1');
    loadDimensionIds('dim2');
});
