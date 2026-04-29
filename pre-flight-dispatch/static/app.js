/**
 * Air India Pre-Flight Readiness & Dispatch Agent
 * Frontend Application
 */

(function () {
    "use strict";

    // ================================================================
    // State
    // ================================================================
    let selectedFlightId = null;
    let dispatchResult = null;
    let ws = null;
    let timerInterval = null;
    let timerStart = 0;

    // DOM references
    const flightSelector = document.getElementById("flightSelector");
    const runCheckBtn = document.getElementById("runCheckBtn");
    const flightInfoCard = document.getElementById("flightInfoCard");
    const decisionPanel = document.getElementById("decisionPanel");
    const chatPanel = document.getElementById("chatPanel");
    const chatInput = document.getElementById("chatInput");
    const chatSendBtn = document.getElementById("chatSendBtn");
    const chatMessages = document.getElementById("chatMessages");
    const execTimer = document.getElementById("execTimer");
    const timerValue = document.getElementById("timerValue");
    const currentTimeEl = document.getElementById("currentTime");

    // ================================================================
    // Clock
    // ================================================================
    function updateClock() {
        const now = new Date();
        currentTimeEl.textContent = now.toLocaleString("en-IN", {
            weekday: "short",
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ================================================================
    // Load flights
    // ================================================================
    async function loadFlights() {
        try {
            const res = await fetch("/api/flights");
            if (!res.ok) throw new Error("Failed to load flights");
            const flights = await res.json();

            flightSelector.innerHTML = '<option value="">-- Choose a flight --</option>';
            flights.forEach((f) => {
                const dep = new Date(f.scheduled_departure).toLocaleTimeString("en-IN", {
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                });
                const opt = document.createElement("option");
                opt.value = f.flight_id;
                opt.textContent = `${f.flight_number} | ${f.origin} -> ${f.destination} | ${f.aircraft_type} (${f.aircraft_reg}) | ${dep} | ${f.status}`;
                if (f.status === "DEPARTED") opt.disabled = true;
                flightSelector.appendChild(opt);
            });
        } catch (err) {
            console.error("Error loading flights:", err);
            const statusEl = document.getElementById("systemStatus");
            statusEl.innerHTML = '<span class="status-dot red"></span><span>DB Offline</span>';
        }
    }

    // ================================================================
    // Flight selection
    // ================================================================
    flightSelector.addEventListener("change", async function () {
        selectedFlightId = this.value;
        runCheckBtn.disabled = !selectedFlightId;
        resetAgents();
        decisionPanel.style.display = "none";
        chatPanel.style.display = "none";

        if (!selectedFlightId) {
            flightInfoCard.style.display = "none";
            return;
        }

        try {
            const res = await fetch(`/api/flight/${selectedFlightId}`);
            if (!res.ok) throw new Error("Flight not found");
            const data = await res.json();
            renderFlightInfo(data.flight);
            flightInfoCard.style.display = "block";
        } catch (err) {
            console.error("Error loading flight details:", err);
        }
    });

    function renderFlightInfo(f) {
        document.getElementById("originCode").textContent = f.origin;
        document.getElementById("destCode").textContent = f.destination;
        document.getElementById("flightNum").textContent = f.flight_number;

        const statusBadge = document.getElementById("flightStatus");
        statusBadge.textContent = f.status;
        statusBadge.className = "flight-status-badge " + f.status;

        const acType = f.model_variant
            ? `${f.aircraft_type} ${f.model_variant}`
            : f.aircraft_type;
        document.getElementById("aircraftInfo").textContent = acType;
        document.getElementById("aircraftReg").textContent = f.aircraft_reg;

        document.getElementById("captainName").textContent = f.captain_name || "--";
        document.getElementById("captainMeta").textContent = f.captain_rank || "--";

        document.getElementById("foName").textContent = f.fo_name || "--";
        document.getElementById("foMeta").textContent = f.fo_rank || "--";

        const dep = new Date(f.scheduled_departure);
        const arr = new Date(f.scheduled_arrival);
        document.getElementById("departureTime").textContent = dep.toLocaleTimeString("en-IN", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        }) + " UTC";
        document.getElementById("arrivalTime").textContent =
            "Arr: " +
            arr.toLocaleTimeString("en-IN", {
                hour: "2-digit",
                minute: "2-digit",
                hour12: false,
            }) + " UTC";

        document.getElementById("paxCount").textContent = f.pax_count;
    }

    // ================================================================
    // Reset agents to idle
    // ================================================================
    function resetAgents() {
        const agents = [
            "aircraft_health",
            "crew_legality",
            "weather_slots",
            "regulatory_compliance",
        ];
        agents.forEach((a) => {
            const card = document.getElementById(`agent-${a}`);
            card.dataset.status = "idle";
            card.dataset.result = "";
            const badge = document.getElementById(`badge-${a}`);
            badge.textContent = "IDLE";
            badge.className = "agent-status-badge";
            document.getElementById(`spinner-${a}`).className = "agent-spinner";
            document.getElementById(`findings-${a}`).innerHTML =
                '<p class="idle-text">Awaiting dispatch...</p>';
        });
    }

    // ================================================================
    // Run dispatch check (WebSocket with HTTP fallback)
    // ================================================================
    runCheckBtn.addEventListener("click", function () {
        if (!selectedFlightId) return;
        startDispatchCheck();
    });

    function startDispatchCheck() {
        // Reset state
        resetAgents();
        decisionPanel.style.display = "none";
        chatPanel.style.display = "none";
        dispatchResult = null;

        // Update button
        runCheckBtn.disabled = true;
        runCheckBtn.classList.add("running");
        runCheckBtn.innerHTML =
            '<svg class="spin-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4m10-10h-4M6 12H2m15.07-5.07l-2.83 2.83M9.76 14.24l-2.83 2.83m0-10.14l2.83 2.83m4.48 4.48l2.83 2.83"/></svg> Running...';

        // Start timer
        timerStart = Date.now();
        execTimer.style.display = "flex";
        timerInterval = setInterval(() => {
            const elapsed = ((Date.now() - timerStart) / 1000).toFixed(1);
            timerValue.textContent = elapsed + "s";
        }, 100);

        // Try WebSocket first, fall back to HTTP
        tryWebSocket();
    }

    function tryWebSocket() {
        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${proto}//${window.location.host}/ws/dispatch/${selectedFlightId}`;

        try {
            ws = new WebSocket(wsUrl);

            ws.onopen = function () {
                ws.send(JSON.stringify({ action: "start" }));
            };

            ws.onmessage = function (event) {
                const msg = JSON.parse(event.data);
                handleWsMessage(msg);
            };

            ws.onerror = function () {
                console.warn("WebSocket failed, falling back to HTTP");
                ws.close();
                fallbackHttp();
            };

            ws.onclose = function () {};

        } catch (e) {
            fallbackHttp();
        }
    }

    function handleWsMessage(msg) {
        if (msg.type === "agent_progress") {
            updateAgentCard(msg.agent, msg.status, msg.data);
        } else if (msg.type === "dispatch_complete") {
            onDispatchComplete(msg.data);
        } else if (msg.type === "chat_response") {
            appendChatMessage("assistant", msg.response);
        } else if (msg.type === "error") {
            onDispatchError(msg.message);
        }
    }

    async function fallbackHttp() {
        // Set all agents to running
        ["aircraft_health", "crew_legality", "weather_slots", "regulatory_compliance"].forEach(
            (a) => updateAgentCard(a, "RUNNING", {})
        );

        try {
            const res = await fetch("/api/dispatch-check", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ flight_id: selectedFlightId }),
            });

            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();

            // Update agent cards from result
            if (data.agent_results) {
                Object.entries(data.agent_results).forEach(([name, result]) => {
                    updateAgentCard(name, "COMPLETE", result);
                });
            }

            onDispatchComplete(data);
        } catch (err) {
            onDispatchError(err.message);
        }
    }

    // ================================================================
    // Update agent card UI
    // ================================================================
    function updateAgentCard(agentName, status, data) {
        if (agentName === "orchestrator") return; // Skip orchestrator updates for cards

        const card = document.getElementById(`agent-${agentName}`);
        if (!card) return;

        const badge = document.getElementById(`badge-${agentName}`);
        const spinner = document.getElementById(`spinner-${agentName}`);
        const findings = document.getElementById(`findings-${agentName}`);

        if (status === "RUNNING") {
            card.dataset.status = "running";
            badge.textContent = "RUNNING";
            badge.className = "agent-status-badge running";
            spinner.className = "agent-spinner active";
            findings.innerHTML = '<p style="color: var(--ai-gold);">Analyzing...</p>';
        } else if (status === "COMPLETE" || status === "ERROR") {
            card.dataset.status = "complete";
            const agentStatus = data.status || "RED";
            card.dataset.result = agentStatus;
            badge.textContent = agentStatus;
            badge.className = `agent-status-badge ${agentStatus}`;
            spinner.className = "agent-spinner";

            // Render findings
            const findingsList = data.findings || [];
            if (findingsList.length === 0) {
                findings.innerHTML = '<p class="finding-item ok">All checks passed</p>';
            } else {
                findings.innerHTML = findingsList
                    .map((f) => {
                        let cls = "finding-item";
                        const fl = f.toLowerCase();
                        if (
                            fl.includes("expired") ||
                            fl.includes("exceeds") ||
                            fl.includes("missing") ||
                            fl.includes("red") ||
                            fl.includes("critical")
                        ) {
                            cls += " critical";
                        } else if (
                            fl.includes("approaching") ||
                            fl.includes("expiring") ||
                            fl.includes("amber") ||
                            fl.includes("reduced") ||
                            fl.includes("snow") ||
                            fl.includes("low") ||
                            fl.includes("elevated")
                        ) {
                            cls += " warning";
                        } else if (fl.includes("valid") || fl.includes("serviceable") || fl.includes("nominal")) {
                            cls += " ok";
                        }
                        return `<div class="${cls}">${escapeHtml(f)}</div>`;
                    })
                    .join("");
            }
        }
    }

    // ================================================================
    // Dispatch complete
    // ================================================================
    function onDispatchComplete(data) {
        // Stop timer
        clearInterval(timerInterval);
        const elapsed = ((Date.now() - timerStart) / 1000).toFixed(1);
        timerValue.textContent = elapsed + "s";

        // Reset button
        runCheckBtn.disabled = false;
        runCheckBtn.classList.remove("running");
        runCheckBtn.innerHTML =
            '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Dispatch Check';

        dispatchResult = data;

        // Show decision
        renderDecision(data.decision || {});
        decisionPanel.style.display = "block";

        // Show chat
        chatPanel.style.display = "block";
        chatInput.disabled = false;
        chatSendBtn.disabled = false;
        chatMessages.innerHTML = "";

        // Footer
        document.getElementById("footerExecTime").textContent =
            `Last check: ${data.execution_time_seconds || elapsed}s`;
    }

    function onDispatchError(message) {
        clearInterval(timerInterval);
        runCheckBtn.disabled = false;
        runCheckBtn.classList.remove("running");
        runCheckBtn.innerHTML =
            '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Dispatch Check';

        alert("Dispatch check failed: " + message);
    }

    // ================================================================
    // Render decision
    // ================================================================
    function renderDecision(d) {
        const badge = document.getElementById("decisionBadge");
        const decision = (d.decision || "UNKNOWN").toUpperCase();

        badge.className = "decision-badge " + decision;

        let icon = "";
        if (decision === "GO") icon = "\u2713";
        else if (decision === "NO-GO") icon = "\u2717";
        else if (decision === "CONDITIONAL") icon = "\u26A0";
        else icon = "?";

        document.getElementById("decisionIcon").textContent = icon;
        document.getElementById("decisionText").textContent = decision;

        // Confidence
        const conf = d.confidence != null ? Math.round(d.confidence * 100) : "--";
        document.getElementById("decisionConfidence").innerHTML =
            `Confidence: <strong>${conf}%</strong>`;

        // Risk
        const riskEl = document.getElementById("decisionRisk");
        const risk = (d.risk_level || "UNKNOWN").toUpperCase();
        riskEl.textContent = risk + " RISK";
        riskEl.className = "decision-risk " + risk;

        // Summary
        document.getElementById("decisionSummary").textContent = d.summary || "";

        // Reasoning
        document.getElementById("decisionReasoning").textContent = d.reasoning || "";

        // Actions
        const actionsEl = document.getElementById("decisionActions");
        const actions = d.actions || [];
        if (actions.length > 0) {
            actionsEl.innerHTML =
                "<h4>Required Actions</h4>" +
                actions.map((a) => `<div class="action-item">${escapeHtml(a)}</div>`).join("");
        } else {
            actionsEl.innerHTML = "";
        }

        // Alternatives
        const altEl = document.getElementById("decisionAlternatives");
        const alts = d.alternatives || [];
        if (alts.length > 0) {
            altEl.innerHTML =
                "<h4>Alternatives</h4>" +
                alts.map((a) => `<div class="alt-item">${escapeHtml(a)}</div>`).join("");
        } else {
            altEl.innerHTML = "";
        }

        // Animate
        const card = document.getElementById("decisionCard");
        card.classList.remove("reveal");
        void card.offsetWidth; // force reflow
        card.classList.add("reveal");
    }

    // ================================================================
    // Chat
    // ================================================================
    chatSendBtn.addEventListener("click", sendChat);
    chatInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });

    async function sendChat() {
        const msg = chatInput.value.trim();
        if (!msg || !selectedFlightId) return;

        appendChatMessage("user", msg);
        chatInput.value = "";
        chatInput.disabled = true;
        chatSendBtn.disabled = true;

        // Try WebSocket first
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: "chat", message: msg }));
            // Re-enable after a short delay (response comes via WS)
            setTimeout(() => {
                chatInput.disabled = false;
                chatSendBtn.disabled = false;
                chatInput.focus();
            }, 500);
            return;
        }

        // HTTP fallback
        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    flight_id: selectedFlightId,
                    message: msg,
                }),
            });
            if (!res.ok) throw new Error("Chat request failed");
            const data = await res.json();
            appendChatMessage("assistant", data.response);
        } catch (err) {
            appendChatMessage("assistant", "Sorry, I could not process your question. " + err.message);
        } finally {
            chatInput.disabled = false;
            chatSendBtn.disabled = false;
            chatInput.focus();
        }
    }

    function appendChatMessage(role, text) {
        const div = document.createElement("div");
        div.className = `chat-msg ${role}`;
        div.textContent = text;
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Chat toggle
    document.getElementById("chatToggle").addEventListener("click", function () {
        const msgs = chatMessages;
        const input = document.querySelector(".chat-input-row");
        if (msgs.style.display === "none") {
            msgs.style.display = "flex";
            input.style.display = "flex";
            this.innerHTML = "&#x2212;";
        } else {
            msgs.style.display = "none";
            input.style.display = "none";
            this.innerHTML = "&#x002B;";
        }
    });

    // ================================================================
    // Utilities
    // ================================================================
    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // ================================================================
    // Init
    // ================================================================
    loadFlights();
})();
