let radarChartInstance = null;
let scatterChartInstance = null;
let genderChartInstance = null;
let ageChartInstance = null;
let densityChartInstance = null;

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
        
        // Fetch Predictive Data, Scatter Data, and Demographics for Dim1
        fetchPredictiveInsights(dim1Type, dim1Id);
        fetchScatterData(dim1Type, dim1Id);
        fetchDemographics(dim1Type, dim1Id);
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

async function fetchDemographics(dimType, dimId) {
    try {
        const res = await fetch(`/api/analytics/demographics?dim_type=${dimType}&dim_id=${dimId}`);
        if (!res.ok) throw new Error('Demographics not found');
        const data = await res.json();
        
        document.getElementById('demo-total-children').innerText = data.total_children;
        document.getElementById('demo-total-kgs').innerText = data.total_kgs;
        
        renderGenderChart(data.gender);
        renderAgeChart(data.age_bands);
        renderDensityChart(data.density_histogram);
    } catch (e) {
        console.error("Failed to load demographics", e);
    }
}

function renderGenderChart(genderData) {
    const ctx = document.getElementById('genderChart').getContext('2d');
    if (genderChartInstance) genderChartInstance.destroy();
    
    const ar = window.KINJO_LANG === 'ar' || true;
    
    genderChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: [ar ? 'ذكور' : 'Male', ar ? 'إناث' : 'Female'],
            datasets: [{
                data: [genderData.MALE || 0, genderData.FEMALE || 0],
                backgroundColor: ['#3b82f6', '#ec4899'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });
}

function renderAgeChart(ageData) {
    const ctx = document.getElementById('ageChart').getContext('2d');
    if (ageChartInstance) ageChartInstance.destroy();
    
    const ar = window.KINJO_LANG === 'ar' || true;
    
    // Maintain strict ordering matching Jordan Reporting Rules
    const labels = [
        "1 day to 3 months",
        "3 to 6 months",
        "6 to 9 months",
        "9 to 12 months",
        "12 to 15 months",
        "15 to 18 months",
        "18 to 21 months",
        "21 to 24 months",
        "24 to 27 months",
        "27 to 30 months",
        "30 to 33 months",
        "33 to 36 months",
        "36 to 39 months",
        "39 to 42 months",
        "42 to 45 months",
        "45 to 48 months",
        "48 to 51 months",
        "51 to 54 months",
        "54 to 57 months"
    ];
    const arLabels = [
        "يوم إلى 3 أشهر",
        "3 إلى 6 أشهر",
        "6 إلى 9 أشهر",
        "9 إلى 12 شهر",
        "12 إلى 15 شهر",
        "15 إلى 18 شهر",
        "18 إلى 21 شهر",
        "21 إلى 24 شهر",
        "24 إلى 27 شهر",
        "27 إلى 30 شهر",
        "30 إلى 33 شهر",
        "33 إلى 36 شهر",
        "36 إلى 39 شهر",
        "39 إلى 42 شهر",
        "42 إلى 45 شهر",
        "45 إلى 48 شهر",
        "48 إلى 51 شهر",
        "51 إلى 54 شهر",
        "54 إلى 57 شهر"
    ];
    
    const values = labels.map(l => ageData[l] || 0);

    ageChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ar ? arLabels : labels,
            datasets: [{
                label: ar ? 'عدد الأطفال' : 'Children Count',
                data: values,
                backgroundColor: '#10b981',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

function renderDensityChart(densityData) {
    const ctx = document.getElementById('densityChart').getContext('2d');
    if (densityChartInstance) densityChartInstance.destroy();
    
    const ar = window.KINJO_LANG === 'ar' || true;
    
    const labels = ["<20", "20-50", "50-100", "100+"];
    const values = labels.map(l => densityData[l] || 0);

    densityChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: ar ? 'عدد الحضانات' : 'Kindergarten Count',
                data: values,
                backgroundColor: '#8b5cf6',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
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
                    data: [dim1.attendance_rate || 0, dim1.final_governance_score || 0, dim1.enrollment_rate || 0, 100 - (dim1.incident_rate_per_100 || 0), dim1.ratio_compliance_rate || 0],
                    backgroundColor: 'rgba(79, 70, 229, 0.2)', // Indigo
                    borderColor: 'rgba(79, 70, 229, 1)',
                    pointBackgroundColor: 'rgba(79, 70, 229, 1)',
                    borderWidth: 2
                },
                {
                    label: dim2.name,
                    data: [dim2.attendance_rate || 0, dim2.final_governance_score || 0, dim2.enrollment_rate || 0, 100 - (dim2.incident_rate_per_100 || 0), dim2.ratio_compliance_rate || 0],
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

// Government Report Logic
async function generateGovReport() {
    const dimType = document.getElementById('dim1-type').value;
    let dimId = document.getElementById('dim1-id').value;
    
    // For network level, we use JORDAN as dimId
    if (dimType === 'NETWORK') {
        dimId = 'JORDAN';
    }

    if (!dimId) {
        alert('Please select a target level first.');
        return;
    }

    try {
        const res = await fetch(`/api/analytics/government-report?dim_type=${dimType}&dim_id=${dimId}`);
        if (!res.ok) throw new Error('Failed to generate report');
        
        const report = await res.json();
        
        document.getElementById('rep-domain').innerText = dimId === 'JORDAN' ? 'الأردن (الشبكة الوطنية)' : dimId.replace('_', ' ');
        document.getElementById('rep-summary').innerText = report.summary;
        document.getElementById('rep-correlations').innerText = report.correlations || 'لا توجد ارتباطات حرجة مسجلة.';
        document.getElementById('rep-judgement').innerText = report.judgement;
        
        const suggUl = document.getElementById('rep-suggestions');
        suggUl.innerHTML = '';
        if (report.suggestions && report.suggestions.length > 0) {
            report.suggestions.forEach(s => {
                const li = document.createElement('li');
                li.innerText = s;
                li.className = 'mb-2';
                suggUl.appendChild(li);
            });
        }
        
        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('govReportModal'));
        modal.show();
        
    } catch (e) {
        console.error(e);
        alert('Error generating report');
    }
}

function printReport() {
    const printContent = document.getElementById('printableReportArea').innerHTML;
    const originalContent = document.body.innerHTML;
    
    document.body.innerHTML = printContent;
    window.print();
    document.body.innerHTML = originalContent;
    window.location.reload(); // Reload to restore JS events
}
