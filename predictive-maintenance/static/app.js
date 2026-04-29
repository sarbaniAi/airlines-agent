/* ============================================================
   Air India Predictive Maintenance Command Center
   Frontend Application
   ============================================================ */

const API = '';
let selectedAircraft = null;
let fleetData = [];
let analysisResult = null;

// ─── Initialize ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    loadFleet();
    loadAlerts();
    setInterval(loadAlerts, 30000);
    setupChat();
});

function updateClock() {
    const now = new Date();
    const el = document.getElementById('clock');
    if (el) {
        el.textContent = now.toUTCString().slice(17, 25) + ' UTC';
    }
}

// ─── Fleet Loading ───────────────────────────────────────────
async function loadFleet() {
    try {
        const res = await fetch(`${API}/api/fleet`);
        const data = await res.json();
        fleetData = data.fleet;
        renderFleetGrid(fleetData);
    } catch (e) {
        console.error('Failed to load fleet:', e);
    }
}

function renderFleetGrid(fleet) {
    const grid = document.getElementById('fleet-grid');
    grid.innerHTML = '';
    fleet.forEach(ac => {
        const card = document.createElement('div');
        card.className = `aircraft-card status-${ac.health_status}`;
        if (selectedAircraft === ac.aircraft_reg) card.classList.add('selected');
        card.onclick = () => selectAircraft(ac.aircraft_reg);

        const healthColor = getHealthColor(ac.overall_health);
        const healthPct = Math.max(0, Math.min(100, ac.overall_health));
        const circumference = 2 * Math.PI * 26;
        const offset = circumference - (healthPct / 100) * circumference;

        card.innerHTML = `
            <div class="ac-header">
                <div>
                    <div class="ac-reg">${ac.aircraft_reg}</div>
                    <div class="ac-type">${ac.aircraft_type.split(' ')[0]} ${ac.aircraft_type.split(' ').slice(1).join(' ')}</div>
                </div>
                <span class="ac-badge ${ac.health_status}">${ac.health_status.replace('_',' ')}</span>
            </div>
            <div class="health-gauge">
                <svg width="64" height="64" viewBox="0 0 64 64">
                    <circle cx="32" cy="32" r="26" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="4"/>
                    <circle cx="32" cy="32" r="26" fill="none" stroke="${healthColor}" stroke-width="4"
                        stroke-dasharray="${circumference}" stroke-dashoffset="${offset}"
                        stroke-linecap="round" style="transition: stroke-dashoffset 1s ease"/>
                </svg>
                <span class="health-gauge-text" style="color:${healthColor}">${Math.round(ac.overall_health)}</span>
            </div>
            <div class="ac-details">
                <span>${ac.base_station}</span>
                <span>${(ac.total_flight_hours/1000).toFixed(1)}K FH</span>
                ${ac.critical_alerts > 0 ? `<span style="color:var(--critical-red)">${ac.critical_alerts} alert${ac.critical_alerts>1?'s':''}</span>` : `<span style="color:var(--green)">OK</span>`}
            </div>
        `;
        grid.appendChild(card);
    });
}

function getHealthColor(score) {
    if (score >= 75) return '#22c55e';
    if (score >= 50) return '#f59e0b';
    if (score >= 25) return '#f97316';
    return '#ef4444';
}

// ─── Aircraft Selection & Detail ─────────────────────────────
async function selectAircraft(reg) {
    selectedAircraft = reg;
    renderFleetGrid(fleetData);

    const panel = document.getElementById('detail-panel');
    const analysisPanel = document.getElementById('analysis-panel');
    panel.classList.add('active');
    analysisPanel.classList.remove('active');

    panel.innerHTML = `<div style="text-align:center;padding:40px"><div class="spinner"></div><p style="margin-top:12px;color:var(--text-muted)">Loading ${reg}...</p></div>`;

    try {
        const res = await fetch(`${API}/api/aircraft/${reg}`);
        const data = await res.json();
        renderAircraftDetail(data);
    } catch (e) {
        panel.innerHTML = `<p style="color:var(--red)">Error loading aircraft data: ${e.message}</p>`;
    }
}

function renderAircraftDetail(data) {
    const panel = document.getElementById('detail-panel');
    const ac = data.aircraft;
    const alerts = data.alerts || [];
    const components = data.components || [];
    const sensors = data.sensors || [];
    const flights = data.upcoming_flights || [];

    const hasCritical = alerts.some(a => a.severity === 'CRITICAL');

    let alertsHTML = '';
    if (alerts.length > 0) {
        alertsHTML = `<div class="card" style="border-color:${hasCritical ? 'var(--critical-red)' : 'var(--amber)'}">
            <h3 style="color:${hasCritical ? 'var(--critical-red)' : 'var(--amber)'}">Active Alerts (${alerts.length})</h3>
            ${alerts.map(a => `
                <div class="result-item">
                    <span class="result-label">
                        <span class="severity-badge severity-${a.severity}">${a.severity}</span>
                        ${a.sensor_type} / ${a.engine_position}
                    </span>
                    <span class="result-value" style="font-size:11px;max-width:50%;text-align:right;white-space:normal">${(a.description||'').slice(0,120)}...</span>
                </div>
            `).join('')}
        </div>`;
    }

    let sensorsHTML = sensors.map(s => {
        const val = parseFloat(s.value);
        const min = parseFloat(s.normal_min);
        const max = parseFloat(s.normal_max);
        const score = parseFloat(s.anomaly_score);
        const isAnomaly = val > max || val < min || score > 0.5;
        const cls = isAnomaly ? (score > 0.8 ? 'danger' : 'warning') : 'normal';
        return `<div class="result-item">
            <span class="result-label">${s.sensor_type} (${s.engine_position})</span>
            <span class="result-value ${cls}">${val.toFixed(1)} ${s.unit} <span style="font-size:10px;color:var(--text-muted)">[${min}-${max}]</span></span>
        </div>`;
    }).join('');

    let componentsHTML = '';
    if (components.length > 0) {
        componentsHTML = `<div class="component-grid">
            ${components.map(c => {
                const h = parseFloat(c.health_score);
                const color = getHealthColor(h);
                const circ = 2 * Math.PI * 16;
                const off = circ - (h/100) * circ;
                return `<div class="component-item">
                    <div class="component-health-ring">
                        <svg width="40" height="40" viewBox="0 0 40 40">
                            <circle cx="20" cy="20" r="16" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="3"/>
                            <circle cx="20" cy="20" r="16" fill="none" stroke="${color}" stroke-width="3"
                                stroke-dasharray="${circ}" stroke-dashoffset="${off}" stroke-linecap="round"/>
                        </svg>
                        <span class="component-health-value" style="color:${color}">${Math.round(h)}</span>
                    </div>
                    <div class="component-info">
                        <div class="component-name">${c.component_type}</div>
                        <div class="component-status">${c.status} | ${c.current_hours}/${c.expected_life_hours} hrs</div>
                    </div>
                </div>`;
            }).join('')}
        </div>`;
    }

    let flightsHTML = flights.slice(0, 5).map(f => {
        const dep = new Date(f.departure);
        return `<div class="result-item">
            <span class="result-label">${f.flight_number} ${f.origin} &rarr; ${f.destination}</span>
            <span class="result-value" style="font-size:12px">${dep.toUTCString().slice(0,22)}</span>
        </div>`;
    }).join('') || '<p style="color:var(--text-muted);font-size:13px">No upcoming flights</p>';

    // Build chart containers for key sensors of the selected aircraft
    const chartSensors = ['ENGINE_VIBRATION_N2', 'OIL_TEMP', 'EGT', 'HYDRAULIC_PRESSURE'];
    let chartsHTML = chartSensors.map(st => `
        <div class="chart-container">
            <div class="chart-title">
                <span>${st.replace(/_/g,' ')}</span>
                <span class="value" id="chart-val-${st}">--</span>
            </div>
            <canvas class="chart-canvas" id="chart-${st}" width="600" height="120"></canvas>
        </div>
    `).join('');

    panel.innerHTML = `
        <button class="back-btn" onclick="deselectAircraft()">&#8592; Back to Fleet</button>
        <div class="detail-header">
            <div>
                <h2 style="font-family:var(--font-mono)">${ac.aircraft_reg}
                    <span style="font-size:14px;font-weight:400;color:var(--text-secondary);margin-left:8px">${ac.aircraft_type}</span>
                </h2>
                <p style="font-size:13px;color:var(--text-muted);margin-top:4px">
                    Engine: ${ac.engine_type} | Base: ${ac.base_station} | ${ac.total_flight_hours.toLocaleString()} FH / ${ac.total_cycles.toLocaleString()} FC
                </p>
            </div>
            <button class="btn btn-primary" onclick="runAnalysis('${ac.aircraft_reg}')">
                Run Predictive Analysis
            </button>
        </div>
        ${alertsHTML}
        <div class="detail-grid" style="margin-top:16px">
            <div>
                <h3 style="margin-bottom:12px;font-size:14px">Sensor Trends (7-Day)</h3>
                ${chartsHTML}
            </div>
            <div>
                <div class="card" style="margin-bottom:12px">
                    <h3 style="margin-bottom:8px;font-size:14px">Latest Sensor Readings</h3>
                    ${sensorsHTML || '<p style="color:var(--text-muted)">No sensor data</p>'}
                </div>
                <div class="card" style="margin-bottom:12px">
                    <h3 style="margin-bottom:8px;font-size:14px">Upcoming Flights</h3>
                    ${flightsHTML}
                </div>
            </div>
        </div>
        <div style="margin-top:16px">
            <h3 style="margin-bottom:12px;font-size:14px">Component Health</h3>
            ${componentsHTML || '<p style="color:var(--text-muted)">No component data</p>'}
        </div>
    `;

    // Load charts
    chartSensors.forEach(st => loadSensorChart(ac.aircraft_reg, st));
}

function deselectAircraft() {
    selectedAircraft = null;
    document.getElementById('detail-panel').classList.remove('active');
    document.getElementById('analysis-panel').classList.remove('active');
    renderFleetGrid(fleetData);
}

// ─── Sensor Charts (Canvas) ─────────────────────────────────
async function loadSensorChart(reg, sensorType) {
    try {
        const res = await fetch(`${API}/api/sensor-history/${reg}/${sensorType}`);
        const data = await res.json();
        if (data.series && data.series.length > 0) {
            data.series.forEach(s => drawChart(sensorType, s));
        }
    } catch (e) {
        console.error(`Failed to load chart for ${sensorType}:`, e);
    }
}

function drawChart(sensorType, series) {
    const canvas = document.getElementById(`chart-${sensorType}`);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const W = rect.width;
    const H = rect.height;

    const points = series.data_points;
    if (!points || points.length === 0) return;

    const values = points.map(p => p.value);
    const scores = points.map(p => p.anomaly_score);
    const normalMin = series.normal_min;
    const normalMax = series.normal_max;

    const allVals = [...values, normalMin, normalMax];
    const dataMin = Math.min(...allVals) * 0.95;
    const dataMax = Math.max(...allVals) * 1.05;
    const range = dataMax - dataMin || 1;

    const padL = 8, padR = 8, padT = 10, padB = 20;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    function xPos(i) { return padL + (i / (points.length - 1 || 1)) * chartW; }
    function yPos(v) { return padT + chartH - ((v - dataMin) / range) * chartH; }

    // Clear
    ctx.clearRect(0, 0, W, H);

    // Normal range band
    const yMin = yPos(normalMin);
    const yMax = yPos(normalMax);
    ctx.fillStyle = 'rgba(34, 197, 94, 0.06)';
    ctx.fillRect(padL, yMax, chartW, yMin - yMax);

    // Normal range lines
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    [normalMin, normalMax].forEach(v => {
        ctx.beginPath();
        ctx.moveTo(padL, yPos(v));
        ctx.lineTo(padL + chartW, yPos(v));
        ctx.stroke();
    });
    ctx.setLineDash([]);

    // Draw data line
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.lineWidth = 2;
    points.forEach((p, i) => {
        const x = xPos(i);
        const y = yPos(p.value);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Gradient fill under line
    const gradient = ctx.createLinearGradient(0, padT, 0, padT + chartH);
    const lastScore = scores[scores.length - 1] || 0;
    if (lastScore > 0.7) {
        gradient.addColorStop(0, 'rgba(239, 68, 68, 0.2)');
        gradient.addColorStop(1, 'rgba(239, 68, 68, 0)');
    } else if (lastScore > 0.4) {
        gradient.addColorStop(0, 'rgba(245, 158, 11, 0.15)');
        gradient.addColorStop(1, 'rgba(245, 158, 11, 0)');
    } else {
        gradient.addColorStop(0, 'rgba(34, 197, 94, 0.1)');
        gradient.addColorStop(1, 'rgba(34, 197, 94, 0)');
    }
    ctx.lineTo(xPos(points.length - 1), padT + chartH);
    ctx.lineTo(xPos(0), padT + chartH);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Anomaly points (red dots)
    points.forEach((p, i) => {
        if (p.anomaly_score > 0.5 || p.value > normalMax || p.value < normalMin) {
            const x = xPos(i);
            const y = yPos(p.value);
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fillStyle = p.anomaly_score > 0.8 ? '#ef4444' : '#f59e0b';
            ctx.fill();
            // Glow
            ctx.beginPath();
            ctx.arc(x, y, 6, 0, Math.PI * 2);
            ctx.fillStyle = p.anomaly_score > 0.8 ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.15)';
            ctx.fill();
        }
    });

    // Latest value dot
    const lastI = points.length - 1;
    const lx = xPos(lastI);
    const ly = yPos(values[lastI]);
    ctx.beginPath();
    ctx.arc(lx, ly, 4, 0, Math.PI * 2);
    ctx.fillStyle = lastScore > 0.7 ? '#ef4444' : lastScore > 0.4 ? '#f59e0b' : '#22c55e';
    ctx.fill();

    // X-axis labels (first and last date)
    ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'left';
    const firstDate = new Date(points[0].timestamp);
    ctx.fillText(formatDate(firstDate), padL, H - 4);
    ctx.textAlign = 'right';
    const lastDate = new Date(points[lastI].timestamp);
    ctx.fillText(formatDate(lastDate), W - padR, H - 4);

    // Normal range labels
    ctx.fillStyle = 'rgba(34, 197, 94, 0.5)';
    ctx.font = '9px Inter, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`${normalMax}`, W - padR, yMax - 2);
    ctx.fillText(`${normalMin}`, W - padR, yMin + 10);

    // Update current value display
    const valEl = document.getElementById(`chart-val-${sensorType}`);
    if (valEl) {
        const lastVal = values[lastI];
        const isOver = lastVal > normalMax || lastVal < normalMin;
        valEl.textContent = `${lastVal.toFixed(1)} ${series.unit}`;
        valEl.className = `value ${lastScore > 0.7 ? 'danger' : lastScore > 0.4 ? 'warning' : 'normal'}`;
        if (series.engine_position) {
            valEl.textContent += ` (${series.engine_position})`;
        }
    }
}

function formatDate(d) {
    return `${d.getUTCDate()}/${d.getUTCMonth()+1} ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`;
}

// ─── Alerts ──────────────────────────────────────────────────
async function loadAlerts() {
    try {
        const res = await fetch(`${API}/api/alerts`);
        const data = await res.json();
        renderAlertBanner(data.alerts);
    } catch (e) {
        console.error('Failed to load alerts:', e);
    }
}

function renderAlertBanner(alerts) {
    const banner = document.getElementById('alert-banner');
    const criticalAlerts = alerts.filter(a => a.severity === 'CRITICAL' || a.severity === 'HIGH');
    if (criticalAlerts.length === 0) {
        banner.classList.remove('active');
        return;
    }
    banner.classList.add('active');
    const scroll = document.getElementById('alert-scroll');
    const items = criticalAlerts.map(a =>
        `<span class="alert-item">
            <span class="severity-badge severity-${a.severity}">${a.severity}</span>
            <strong>${a.aircraft_reg}</strong> ${a.sensor_type} (${a.engine_position}) &mdash; ${(a.description||'').slice(0, 100)}...
        </span>`
    ).join('');
    scroll.innerHTML = items + items; // Duplicate for seamless scroll
}

// ─── Analysis ────────────────────────────────────────────────
async function runAnalysis(reg) {
    const panel = document.getElementById('analysis-panel');
    panel.classList.add('active');

    // Scroll to analysis
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Show agent progress
    const agents = [
        { id: 'anomaly', name: 'Anomaly Detection', icon: '\u{1F50D}' },
        { id: 'workorder', name: 'Work Order', icon: '\u{1F4CB}' },
        { id: 'parts', name: 'Parts & Inventory', icon: '\u{1F4E6}' },
        { id: 'schedule', name: 'Schedule Alignment', icon: '\u{1F4C5}' },
    ];

    panel.innerHTML = `
        <div class="section-header">
            <h2>Predictive Maintenance Analysis: ${reg}</h2>
        </div>
        <div class="agent-progress">
            ${agents.map(a => `
                <div class="agent-step" id="agent-${a.id}">
                    <div class="agent-icon">${a.icon}</div>
                    <div class="agent-name">${a.name}</div>
                    <div class="agent-status" id="agent-status-${a.id}">Pending</div>
                    <div class="agent-time" id="agent-time-${a.id}"></div>
                </div>
            `).join('')}
        </div>
        <div id="analysis-results"></div>
    `;

    // Animate agents sequentially
    const startTime = Date.now();
    animateAgent('anomaly', 'running');

    try {
        const res = await fetch(`${API}/api/analyze/${reg}`, { method: 'POST' });
        const result = await res.json();
        analysisResult = result;

        const timings = result.agent_timings || {};

        // Complete all agents with timings
        animateAgent('anomaly', 'complete', timings.anomaly_detection);
        animateAgent('workorder', 'complete', timings.work_order);
        animateAgent('parts', 'complete', timings.parts_and_schedule);
        animateAgent('schedule', 'complete', timings.parts_and_schedule);

        renderAnalysisResults(result);
    } catch (e) {
        document.getElementById('analysis-results').innerHTML =
            `<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">Analysis failed: ${e.message}</p></div>`;
    }
}

function animateAgent(id, status, time) {
    const el = document.getElementById(`agent-${id}`);
    const statusEl = document.getElementById(`agent-status-${id}`);
    const timeEl = document.getElementById(`agent-time-${id}`);
    if (!el) return;
    el.className = `agent-step ${status}`;
    statusEl.className = `agent-status ${status}`;
    statusEl.textContent = status === 'running' ? 'Running...' : status === 'complete' ? 'Complete' : 'Pending';
    if (time !== undefined && timeEl) {
        timeEl.textContent = `${time.toFixed(2)}s`;
    }
}

function renderAnalysisResults(result) {
    const container = document.getElementById('analysis-results');
    if (result.status === 'HEALTHY') {
        container.innerHTML = `
            <div class="savings-highlight" style="border-color:var(--green)">
                <div class="savings-label">Status</div>
                <div class="savings-amount" style="font-size:24px">All Systems Nominal</div>
                <p style="color:var(--text-secondary);font-size:14px">${result.message}</p>
            </div>`;
        return;
    }

    if (result.status === 'ERROR') {
        container.innerHTML = `<div class="card" style="border-color:var(--red)"><p style="color:var(--red)">Error: ${result.error}</p></div>`;
        return;
    }

    const wo = result.work_order_result || {};
    const parts = result.parts_result || {};
    const schedule = result.schedule_result || {};
    const rec = schedule.recommendation || {};
    const savings = result.estimated_savings_usd || rec.estimated_savings_usd || 125000;

    // Savings banner
    let html = `
        <div class="savings-highlight">
            <div class="savings-label">Estimated AOG Cost Avoided</div>
            <div class="savings-amount">$${Number(savings).toLocaleString()}</div>
            <p style="color:var(--text-secondary);font-size:13px">Proactive maintenance prevents ${Math.ceil(savings/100000)} day(s) of Aircraft on Ground</p>
        </div>
    `;

    // Results grid
    html += '<div class="results-grid">';

    // Work Orders
    html += `<div class="result-card">
        <h3>Work Orders (${wo.total_work_orders || 0})</h3>
        ${(wo.work_orders || []).map(w => `
            <div style="padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;margin-bottom:8px">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px">
                    <span style="font-family:var(--font-mono);font-size:12px;color:var(--ai-gold)">${w.work_order_id}</span>
                    <span class="severity-badge severity-${w.priority === 'AOG_PREVENTION' ? 'CRITICAL' : w.priority}">${w.priority}</span>
                </div>
                <div style="font-size:13px;font-weight:600;margin-bottom:4px">${w.component} (${w.engine_position})</div>
                <div class="result-item"><span class="result-label">Type</span><span class="result-value">${w.action_type}</span></div>
                <div class="result-item"><span class="result-label">Duration</span><span class="result-value">${w.estimated_duration_hours}h</span></div>
                <div class="result-item"><span class="result-label">Cost</span><span class="result-value">$${Number(w.estimated_cost_usd).toLocaleString()}</span></div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:6px">Skills: ${(w.required_skills||[]).join(', ')}</div>
            </div>
        `).join('')}
        <div class="result-item" style="font-weight:600;margin-top:8px">
            <span>Total Estimated Cost</span>
            <span class="result-value" style="color:var(--ai-gold)">$${Number(wo.total_estimated_cost_usd || 0).toLocaleString()}</span>
        </div>
    </div>`;

    // Parts & Logistics
    html += `<div class="result-card">
        <h3>Parts & Logistics</h3>
        <div class="result-item">
            <span class="result-label">Status</span>
            <span class="result-value" style="color:${parts.overall_status === 'ALL_AVAILABLE' ? 'var(--green)' : 'var(--amber)'}">${(parts.overall_status || '').replace(/_/g, ' ')}</span>
        </div>
        <p style="font-size:13px;color:var(--text-secondary);margin:8px 0">${parts.message || ''}</p>
        ${(parts.transfers_needed || []).map(t => `
            <div style="padding:8px;background:rgba(245,158,11,0.08);border-radius:8px;margin:6px 0">
                <div class="transfer-tag">${t.from_station} &rarr; ${t.to_station}</div>
                <div style="font-size:12px;margin-top:4px">${t.description || t.part_number}</div>
                <div class="result-item"><span class="result-label">Flight Time</span><span class="result-value">${t.flight_time_hours}h</span></div>
                <div class="result-item"><span class="result-label">Total Time</span><span class="result-value">${t.total_transfer_time_hours}h</span></div>
            </div>
        `).join('')}
        ${(parts.parts_report || []).filter(p => p.available_at_base).slice(0, 5).map(p => `
            <div class="result-item">
                <span class="result-label" style="font-size:11px">${p.description || p.part_number}</span>
                <span style="color:var(--green);font-size:11px">In Stock at ${parts.base_station}</span>
            </div>
        `).join('')}
    </div>`;

    // Schedule
    html += `<div class="result-card">
        <h3>Schedule Recommendation</h3>
        ${rec.summary ? `<p style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">${rec.summary}</p>` : ''}
        ${rec.maintenance_start ? `
            <div class="result-item"><span class="result-label">Start</span><span class="result-value">${new Date(rec.maintenance_start).toUTCString().slice(0,22)}</span></div>
            <div class="result-item"><span class="result-label">Location</span><span class="result-value">${rec.location || ''}</span></div>
            <div class="result-item"><span class="result-label">Hangar</span><span class="result-value">${rec.hangar || ''} (${rec.hangar_type || ''})</span></div>
            <div class="result-item"><span class="result-label">Flights Impacted</span><span class="result-value" style="color:${rec.flights_impacted === 0 ? 'var(--green)' : 'var(--amber)'}">${rec.flights_impacted === 0 ? 'None' : rec.flights_impacted}</span></div>
        ` : '<p style="color:var(--text-muted)">No schedule data</p>'}
        ${(rec.timeline || []).length > 0 ? `
            <div style="margin-top:12px">
                <h4 style="font-size:12px;color:var(--text-muted);margin-bottom:8px">EXECUTION TIMELINE</h4>
                <div class="timeline">
                    ${rec.timeline.map(t => `
                        <div class="timeline-item">
                            <div class="timeline-time">${t.time ? new Date(t.time).toUTCString().slice(0,22) : ''} (${t.duration_hours}h)</div>
                            <div class="timeline-action">${t.action}</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    </div>`;

    // Flight Impact
    const fi = schedule.flight_impact || {};
    html += `<div class="result-card">
        <h3>Operational Impact</h3>
        <div class="result-item"><span class="result-label">Flights Impacted</span><span class="result-value">${fi.flights_impacted || 0}</span></div>
        <div class="result-item"><span class="result-label">Revenue Impact</span><span class="result-value">$${Number(fi.revenue_impact_usd || 0).toLocaleString()}</span></div>
        <div class="result-item"><span class="result-label">Passengers Affected</span><span class="result-value">${fi.passengers_affected || 0}</span></div>
        <p style="font-size:13px;color:var(--text-secondary);margin-top:8px">${fi.description || 'No impact analysis available.'}</p>
    </div>`;

    html += '</div>'; // Close results-grid

    // Action Plan
    if (result.action_plan) {
        html += `
            <div style="margin-top:20px">
                <h3 style="margin-bottom:12px;font-size:14px">AI Maintenance Action Plan</h3>
                <div class="action-plan">${escapeHtml(result.action_plan)}</div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/## (.*)/g, '<h3 style="color:var(--ai-gold);margin:12px 0 6px">$1</h3>')
        .replace(/# (.*)/g, '<h2 style="color:var(--ai-gold);margin:16px 0 8px">$1</h2>')
        .replace(/- (.*)/g, '<div style="padding-left:12px;margin:2px 0">&bull; $1</div>');
}

// ─── Chat ────────────────────────────────────────────────────
function setupChat() {
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');
    if (!input || !sendBtn) return;

    sendBtn.onclick = () => sendChat();
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });

    // Welcome message
    addChatMessage('assistant', 'Welcome to the Air India Maintenance Command Center. I can answer questions about fleet health, maintenance outlook, sensor trends, and more. Try asking:\n\n- "What\'s the maintenance outlook for VT-ALJ?"\n- "Which aircraft need immediate attention?"\n- "Show me fleet health summary"');
}

async function sendChat() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    addChatMessage('user', msg);
    const loadingId = addChatMessage('assistant', 'Analyzing...', true);

    try {
        const res = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg }),
        });
        const data = await res.json();
        removeChatMessage(loadingId);
        addChatMessage('assistant', data.response);
    } catch (e) {
        removeChatMessage(loadingId);
        addChatMessage('assistant', `Error: ${e.message}`);
    }
}

let chatMsgId = 0;
function addChatMessage(role, text, isLoading = false) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    const id = `chat-msg-${++chatMsgId}`;
    div.id = id;
    div.className = `chat-message ${role}${isLoading ? ' loading' : ''}`;
    div.textContent = text;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return id;
}

function removeChatMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}
