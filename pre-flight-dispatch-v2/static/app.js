/**
 * Air India Pre-Flight Dispatch Agent V2
 * Frontend Application — Simple, direct JS with data-agent attribute matching.
 */

(function () {
    "use strict";

    // ── DOM refs ──────────────────────────────────────────────
    var flightSelect = document.getElementById("flightSelect");
    var btnDispatch  = document.getElementById("btnDispatch");
    var flightInfoPanel = document.getElementById("flightInfoPanel");
    var flightInfoGrid  = document.getElementById("flightInfoGrid");
    var decisionBody    = document.getElementById("decisionBody");
    var actionsPanel    = document.getElementById("actionsPanel");
    var actionsList     = document.getElementById("actionsList");
    var alternativesPanel = document.getElementById("alternativesPanel");
    var alternativesList  = document.getElementById("alternativesList");
    var chatMessages = document.getElementById("chatMessages");
    var chatInput    = document.getElementById("chatInput");
    var btnChatSend  = document.getElementById("btnChatSend");

    // Eval
    var evalTime       = document.getElementById("evalTime");
    var evalConfidence  = document.getElementById("evalConfidence");
    var evalRisk        = document.getElementById("evalRisk");
    var evalRules       = document.getElementById("evalRules");
    var evalAgents      = document.getElementById("evalAgents");

    // State
    var selectedFlightId = null;
    var isRunning = false;

    // ── CLOCK ─────────────────────────────────────────────────
    function updateClock() {
        var el = document.getElementById("currentTime");
        if (el) el.textContent = new Date().toLocaleTimeString("en-IN", { hour12: false });
    }
    setInterval(updateClock, 1000);
    updateClock();

    // ── LOAD FLIGHTS ──────────────────────────────────────────
    function loadFlights() {
        fetch("/api/flights")
            .then(function (r) { return r.json(); })
            .then(function (flights) {
                flightSelect.innerHTML = '<option value="">-- Select Flight --</option>';
                flights.forEach(function (f) {
                    var opt = document.createElement("option");
                    opt.value = f.flight_id;
                    opt.textContent = f.flight_number + " | " + f.origin + " → " + f.destination + " | " + (f.aircraft_type || f.aircraft_reg) + " | " + f.scheduled_departure;
                    flightSelect.appendChild(opt);
                });
            })
            .catch(function (err) {
                console.error("Failed to load flights:", err);
            });
    }
    loadFlights();

    // ── FLIGHT SELECT ─────────────────────────────────────────
    flightSelect.addEventListener("change", function () {
        selectedFlightId = this.value || null;
        btnDispatch.disabled = !selectedFlightId || isRunning;
        if (selectedFlightId) {
            loadFlightInfo(selectedFlightId);
        } else {
            flightInfoPanel.style.display = "none";
        }
        resetAll();
    });

    function loadFlightInfo(fid) {
        fetch("/api/flight/" + encodeURIComponent(fid))
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var f = data.flight || {};
                var fields = [
                    ["Flight", f.flight_number || fid],
                    ["Route", (f.origin || "?") + " → " + (f.destination || "?")],
                    ["Aircraft", f.aircraft_reg + " (" + (f.aircraft_type || "") + ")"],
                    ["Captain", f.captain_name || "N/A"],
                    ["First Officer", f.fo_name || "N/A"],
                    ["PAX", f.pax_count || "N/A"],
                    ["Departure", f.scheduled_departure || "N/A"],
                    ["Status", f.status || "N/A"]
                ];
                flightInfoGrid.innerHTML = "";
                fields.forEach(function (pair) {
                    var div = document.createElement("div");
                    div.className = "fi-item";
                    div.innerHTML = '<span class="fi-label">' + pair[0] + '</span><span class="fi-value">' + pair[1] + '</span>';
                    flightInfoGrid.appendChild(div);
                });
                flightInfoPanel.style.display = "block";
            })
            .catch(function () {
                flightInfoPanel.style.display = "none";
            });
    }

    // ── RESET ALL ─────────────────────────────────────────────
    function resetAll() {
        // Reset agent cards
        var cards = document.querySelectorAll(".agent-card");
        cards.forEach(function (card) {
            card.className = "panel agent-card";
            var badge = card.querySelector(".agent-badge");
            if (badge) { badge.className = "agent-badge idle"; badge.textContent = "IDLE"; }
            var time = card.querySelector(".agent-time");
            if (time) time.textContent = "";
            var body = card.querySelector(".agent-card-body");
            if (body) body.className = "agent-card-body";
            var findings = card.querySelector(".agent-findings");
            if (findings) findings.innerHTML = "";
            var refs = card.querySelector(".agent-refs");
            if (refs) { refs.className = "agent-refs"; refs.innerHTML = ""; }
        });

        // Reset flow nodes
        var flowNodes = document.querySelectorAll(".flow-node");
        flowNodes.forEach(function (node) {
            node.className = "flow-node";
            var badge = node.querySelector(".flow-node-badge");
            if (badge) { badge.textContent = ""; badge.style.color = ""; badge.style.background = ""; }
        });
        var connectors = document.querySelectorAll(".flow-connector");
        connectors.forEach(function (c) { c.className = "flow-connector"; });

        // Reset decision
        decisionBody.innerHTML = '<div class="decision-placeholder"><p>Select a flight and run dispatch check to see the decision.</p></div>';
        actionsPanel.style.display = "none";
        actionsList.innerHTML = "";
        alternativesPanel.style.display = "none";
        alternativesList.innerHTML = "";

        // Reset rules
        var rules = document.querySelectorAll(".rule-item");
        rules.forEach(function (r) { r.classList.remove("triggered"); });

        // Reset eval
        evalTime.textContent = "--";
        evalConfidence.textContent = "--";
        evalRisk.textContent = "--";
        evalRules.textContent = "--";
        evalAgents.textContent = "--";

        // Reset chat
        chatMessages.innerHTML = '<div class="chat-placeholder">Ask follow-up questions about the dispatch decision.</div>';
        chatInput.disabled = true;
        btnChatSend.disabled = true;
    }

    // ── FLOW ANIMATION (sequential, simulated) ────────────────
    var flowOrder = [
        "supervisor", "aircraft_health", "crew_legality",
        "weather_notam", "regulatory_compliance", "genie_analytics",
        "llm_synthesis", "guardrails", "decision"
    ];

    function animateFlowStart() {
        // Sequentially activate flow nodes with delay
        flowOrder.forEach(function (key, i) {
            setTimeout(function () {
                if (!isRunning) return;
                var node = document.querySelector('.flow-node[data-flow="' + key + '"]');
                if (node) {
                    node.className = "flow-node active";
                    var badge = node.querySelector(".flow-node-badge");
                    if (badge) { badge.textContent = "..."; badge.style.color = "#3b82f6"; badge.style.background = "rgba(59,130,246,0.15)"; }
                }
                // Light up connector before this node
                if (i > 0) {
                    var allConnectors = document.querySelectorAll(".flow-connector");
                    if (allConnectors[i - 1]) allConnectors[i - 1].classList.add("lit");
                }
            }, i * 300);
        });
    }

    function finalizeFlow(data) {
        var agentResults = data.agent_results || {};
        var decision = data.decision || {};

        // Supervisor — always done
        setFlowDone("supervisor", "green", "OK");

        // Agent nodes
        var agentKeys = ["aircraft_health", "crew_legality", "weather_notam", "regulatory_compliance"];
        agentKeys.forEach(function (key) {
            var result = agentResults[key];
            if (result) {
                var st = (result.status || "GREEN").toUpperCase();
                var cls = st === "RED" ? "red" : st === "AMBER" ? "amber" : "green";
                setFlowDone(key, cls, st);
            } else {
                setFlowDone(key, "skip", "N/A");
            }
        });

        // Genie
        if (data.genie_analytics) {
            setFlowDone("genie_analytics", "green", "OK");
        } else {
            setFlowDone("genie_analytics", "skip", "Skipped");
        }

        // LLM Synthesis
        setFlowDone("llm_synthesis", "green", "Done");

        // Guardrails
        var triggered = (decision.triggered_rules || []).length;
        if (triggered > 0) {
            setFlowDone("guardrails", "red", triggered + " rules");
        } else {
            setFlowDone("guardrails", "green", "Clear");
        }

        // Decision
        var dec = (decision.decision || "").toUpperCase();
        if (dec === "GO") setFlowDone("decision", "green", "GO");
        else if (dec === "NO-GO") setFlowDone("decision", "red", "NO-GO");
        else setFlowDone("decision", "amber", dec || "?");
    }

    function setFlowDone(key, color, label) {
        var node = document.querySelector('.flow-node[data-flow="' + key + '"]');
        if (!node) return;
        node.className = "flow-node done-" + color;
        var badge = node.querySelector(".flow-node-badge");
        if (badge) {
            badge.textContent = label;
            var colorMap = { green: "#22c55e", amber: "#f59e0b", red: "#E31837", skip: "#8892a8" };
            var bgMap = { green: "rgba(34,197,94,0.15)", amber: "rgba(245,158,11,0.15)", red: "rgba(227,24,55,0.15)", skip: "rgba(255,255,255,0.06)" };
            badge.style.color = colorMap[color] || "#8892a8";
            badge.style.background = bgMap[color] || "transparent";
        }
    }

    // ── RUN DISPATCH CHECK ────────────────────────────────────
    btnDispatch.addEventListener("click", function () {
        if (!selectedFlightId || isRunning) return;
        isRunning = true;
        btnDispatch.classList.add("running");
        btnDispatch.textContent = "Running...";
        btnDispatch.disabled = true;

        resetAll();

        // Set all agent cards to RUNNING
        var agentKeys = ["aircraft_health", "crew_legality", "weather_notam", "regulatory_compliance", "genie_analytics"];
        agentKeys.forEach(function (key, i) {
            setTimeout(function () {
                setAgentRunning(key);
            }, i * 200);
        });

        // Animate flow pipeline
        animateFlowStart();

        // Call API
        fetch("/api/dispatch-check", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ flight_id: selectedFlightId })
        })
        .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        })
        .then(function (data) {
            isRunning = false;
            btnDispatch.classList.remove("running");
            btnDispatch.textContent = "Run Dispatch Check";
            btnDispatch.disabled = false;

            // Update agent cards
            updateAgentCards(data);

            // Update flow pipeline with real data
            finalizeFlow(data);

            // Update decision panel
            updateDecision(data);

            // Update safety rules
            updateTriggeredRules(data);

            // Update eval scores
            updateEval(data);

            // Enable chat
            chatInput.disabled = false;
            btnChatSend.disabled = false;
            chatMessages.innerHTML = '<div class="chat-placeholder">Dispatch complete. Ask follow-up questions.</div>';
        })
        .catch(function (err) {
            isRunning = false;
            btnDispatch.classList.remove("running");
            btnDispatch.textContent = "Run Dispatch Check";
            btnDispatch.disabled = false;
            console.error("Dispatch check failed:", err);
            decisionBody.innerHTML = '<div class="decision-placeholder" style="color:var(--red);">Dispatch check failed: ' + err.message + '</div>';
        });
    });

    // ── SET AGENT RUNNING ─────────────────────────────────────
    function setAgentRunning(key) {
        var card = document.querySelector('.agent-card[data-agent="' + key + '"]');
        if (!card) return;
        card.className = "panel agent-card status-running";
        var badge = card.querySelector(".agent-badge");
        if (badge) { badge.className = "agent-badge running"; badge.textContent = "RUNNING"; }
    }

    // ── UPDATE AGENT CARDS ────────────────────────────────────
    function updateAgentCards(data) {
        var agentResults = data.agent_results || {};

        // Loop through each key in agent_results and find matching card
        Object.keys(agentResults).forEach(function (key) {
            var result = agentResults[key];
            if (!result) return;

            var card = document.querySelector('.agent-card[data-agent="' + key + '"]');
            if (!card) {
                console.warn("No card found for agent key:", key);
                return;
            }

            var status = (result.status || "GREEN").toUpperCase();
            var statusLower = status.toLowerCase();

            // Update card border color class
            card.className = "panel agent-card status-" + (statusLower === "red" ? "red" : statusLower === "amber" ? "amber" : "green");

            // Update badge
            var badge = card.querySelector(".agent-badge");
            if (badge) {
                badge.className = "agent-badge " + statusLower;
                badge.textContent = status;
            }

            // Show body
            var body = card.querySelector(".agent-card-body");
            if (body) body.className = "agent-card-body visible";

            // Findings
            var findingsEl = card.querySelector(".agent-findings");
            if (findingsEl) {
                findingsEl.innerHTML = "";
                var findings = result.findings || [];
                findings.forEach(function (f) {
                    var div = document.createElement("div");
                    div.className = "finding";
                    var dotColor = statusLower === "red" ? "red" : statusLower === "amber" ? "amber" : "green";
                    div.innerHTML = '<span class="finding-dot ' + dotColor + '"></span><span>' + escHtml(f) + '</span>';
                    findingsEl.appendChild(div);
                });
            }

            // Recommendations as refs
            var refsEl = card.querySelector(".agent-refs");
            if (refsEl) {
                var refs = result.recommendations || result.regulatory_references || result.sop_references || [];
                if (refs.length > 0) {
                    refsEl.className = "agent-refs visible";
                    refsEl.innerHTML = '<div class="agent-refs-title">References / Recommendations</div>';
                    refs.forEach(function (r) {
                        var div = document.createElement("div");
                        div.className = "ref-item";
                        div.textContent = r;
                        refsEl.appendChild(div);
                    });
                }
            }
        });

        // Handle genie_analytics specially (may be null)
        var genieCard = document.querySelector('.agent-card[data-agent="genie_analytics"]');
        if (genieCard) {
            if (data.genie_analytics) {
                var gr = data.genie_analytics;
                var gStatus = (gr.status || "GREEN").toUpperCase();
                var gLower = gStatus.toLowerCase();
                genieCard.className = "panel agent-card status-" + (gLower === "red" ? "red" : gLower === "amber" ? "amber" : "green");
                var gBadge = genieCard.querySelector(".agent-badge");
                if (gBadge) { gBadge.className = "agent-badge " + gLower; gBadge.textContent = gStatus; }
            } else if (!agentResults.genie_analytics) {
                genieCard.className = "panel agent-card";
                var gBadge2 = genieCard.querySelector(".agent-badge");
                if (gBadge2) { gBadge2.className = "agent-badge skipped"; gBadge2.textContent = "SKIPPED"; }
            }
        }

        // Execution time on agent cards
        var execTime = data.execution_time_seconds;
        if (execTime) {
            var perAgent = (execTime / 4).toFixed(1); // rough estimate
            var agentKeys = ["aircraft_health", "crew_legality", "weather_notam", "regulatory_compliance"];
            agentKeys.forEach(function (key) {
                var card = document.querySelector('.agent-card[data-agent="' + key + '"] .agent-time');
                if (card) card.textContent = perAgent + "s";
            });
        }
    }

    // ── UPDATE DECISION ───────────────────────────────────────
    function updateDecision(data) {
        var d = data.decision || {};
        var dec = (d.decision || "").toUpperCase();
        var badgeClass = dec === "GO" ? "go" : dec === "NO-GO" ? "no-go" : "conditional";

        var html = '';
        html += '<div style="text-align:center;margin-bottom:12px;">';
        html += '<div class="decision-badge ' + badgeClass + '">' + escHtml(dec || "UNKNOWN") + '</div>';
        html += '</div>';

        html += '<div class="decision-meta">';
        html += '<div class="decision-meta-item"><span class="decision-meta-label">Confidence</span><span class="decision-meta-value">' + ((d.confidence || 0) * 100).toFixed(0) + '%</span></div>';
        html += '<div class="decision-meta-item"><span class="decision-meta-label">Risk Level</span><span class="decision-meta-value">' + escHtml(d.risk_level || "N/A") + '</span></div>';
        html += '<div class="decision-meta-item"><span class="decision-meta-label">Time</span><span class="decision-meta-value">' + (data.execution_time_seconds || 0).toFixed(1) + 's</span></div>';
        html += '</div>';

        if (d.summary) {
            html += '<div class="decision-summary">' + escHtml(d.summary) + '</div>';
        }

        if (d.reasoning) {
            html += '<button class="reasoning-toggle" onclick="toggleReasoning()">Show Full Reasoning</button>';
            html += '<div class="reasoning-content" id="reasoningContent">' + escHtml(d.reasoning) + '</div>';
        }

        decisionBody.innerHTML = html;

        // Actions
        if (d.actions && d.actions.length > 0) {
            actionsPanel.style.display = "block";
            actionsList.innerHTML = "";
            d.actions.forEach(function (a) {
                var li = document.createElement("li");
                li.textContent = a;
                actionsList.appendChild(li);
            });
        }

        // Alternatives
        if (d.alternatives && d.alternatives.length > 0) {
            alternativesPanel.style.display = "block";
            alternativesList.innerHTML = "";
            d.alternatives.forEach(function (a) {
                var li = document.createElement("li");
                li.textContent = a;
                alternativesList.appendChild(li);
            });
        }
    }

    // Global toggle function referenced from inline onclick
    window.toggleReasoning = function () {
        var el = document.getElementById("reasoningContent");
        if (!el) return;
        el.classList.toggle("visible");
        var btn = el.previousElementSibling;
        if (btn) btn.textContent = el.classList.contains("visible") ? "Hide Reasoning" : "Show Full Reasoning";
    };

    // ── UPDATE TRIGGERED RULES ────────────────────────────────
    function updateTriggeredRules(data) {
        var d = data.decision || {};
        var triggered = d.triggered_rules || [];

        // Clear all
        var ruleItems = document.querySelectorAll(".rule-item");
        ruleItems.forEach(function (r) { r.classList.remove("triggered"); });

        triggered.forEach(function (rule) {
            var ruleId = rule.id || rule.rule_id || "";
            if (!ruleId) return;
            var el = document.querySelector('.rule-item[data-rule="' + ruleId + '"]');
            if (el) {
                el.classList.add("triggered");
            }
        });
    }

    // ── UPDATE EVAL SCORES ────────────────────────────────────
    function updateEval(data) {
        var d = data.decision || {};
        evalTime.textContent = (data.execution_time_seconds || 0).toFixed(2) + "s";
        evalConfidence.textContent = ((d.confidence || 0) * 100).toFixed(0) + "%";
        evalRisk.textContent = d.risk_level || "N/A";
        evalRules.textContent = (d.triggered_rules || []).length + " / 18";

        var agentCount = Object.keys(data.agent_results || {}).length;
        evalAgents.textContent = agentCount + " / 4";
    }

    // ── CHAT ──────────────────────────────────────────────────
    function sendChat() {
        var msg = chatInput.value.trim();
        if (!msg || !selectedFlightId) return;

        // Clear placeholder
        var placeholder = chatMessages.querySelector(".chat-placeholder");
        if (placeholder) placeholder.remove();

        // Show user message
        appendChatMsg("user", msg);
        chatInput.value = "";

        // Show typing indicator
        var crewKeywords = ["replacement", "crew", "captain", "first officer", "swap"];
        var isCrewQuery = crewKeywords.some(function (kw) { return msg.toLowerCase().indexOf(kw) >= 0; });
        if (isCrewQuery) {
            appendChatMsg("system", "Querying crew database...");
        } else {
            appendChatMsg("system", "Thinking...");
        }

        fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ flight_id: selectedFlightId, message: msg })
        })
        .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
        })
        .then(function (data) {
            // Remove thinking/system messages
            var systemMsgs = chatMessages.querySelectorAll(".chat-msg.system");
            systemMsgs.forEach(function (m) { m.remove(); });

            appendChatMsg("assistant", data.response || "No response.");
        })
        .catch(function (err) {
            var systemMsgs = chatMessages.querySelectorAll(".chat-msg.system");
            systemMsgs.forEach(function (m) { m.remove(); });
            appendChatMsg("assistant", "Error: " + err.message);
        });
    }

    function appendChatMsg(role, text) {
        var div = document.createElement("div");
        div.className = "chat-msg " + role;
        if (role === "assistant") {
            div.innerHTML = markdownToHtml(text);
        } else {
            div.textContent = text;
        }
        chatMessages.appendChild(div);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function markdownToHtml(md) {
        if (!md) return "";
        var html = escHtml(md);
        // Bold: **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Italic: *text* (but not inside **)
        html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
        // Bullet lists: lines starting with - or •
        html = html.replace(/^[\-\•]\s+(.+)$/gm, '<li>$1</li>');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
        // Numbered lists: lines starting with 1. 2. etc
        html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
        // Headers: lines starting with # or ##
        html = html.replace(/^###\s+(.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^##\s+(.+)$/gm, '<h3>$1</h3>');
        // Line breaks
        html = html.replace(/\n/g, '<br>');
        // Clean up double <br> inside lists
        html = html.replace(/<br><li>/g, '<li>');
        html = html.replace(/<\/li><br>/g, '</li>');
        html = html.replace(/<br><\/ul>/g, '</ul>');
        html = html.replace(/<ul><br>/g, '<ul>');
        return html;
    }

    btnChatSend.addEventListener("click", sendChat);
    chatInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") sendChat();
    });

    // ── HELPERS ───────────────────────────────────────────────
    function escHtml(str) {
        if (!str) return "";
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }

    // ═══════════════════════════════════════════════════════════
    // PHASE 1: DISPATCH ACTIONS
    // ═══════════════════════════════════════════════════════════

    // After chat shows crew replacement, inject action buttons
    var _origAppendChat = appendChatMsg;
    appendChatMsg = function(role, text) {
        _origAppendChat(role, text);
        if (role === "assistant" && selectedFlightId) {
            // Detect crew names in the response and add action buttons
            var crewPattern = /((?:FO|SFO|Capt\.?)\s+[A-Z][a-z]+\s+[A-Z][a-z]+)/g;
            var names = text.match(crewPattern);
            if (names && names.length > 0) {
                var actionsDiv = document.createElement("div");
                actionsDiv.className = "chat-actions";
                var uniqueNames = [];
                names.forEach(function(n) { if (uniqueNames.indexOf(n) < 0) uniqueNames.push(n); });
                uniqueNames.forEach(function(name) {
                    var rank = name.startsWith("Capt") ? "CAPTAIN" : name.startsWith("SFO") ? "SENIOR_FIRST_OFFICER" : "FIRST_OFFICER";
                    var row = document.createElement("div");
                    row.className = "crew-action-row";
                    row.innerHTML =
                        '<span class="crew-action-name">' + escHtml(name) + '</span>' +
                        '<button class="btn-action btn-assign" onclick="window.assignCrew(\'' + escHtml(name) + '\',\'' + rank + '\')">Assign</button>' +
                        '<button class="btn-action btn-notify" onclick="window.notifyCrew(\'' + escHtml(name) + '\')">Notify</button>';
                    actionsDiv.appendChild(row);
                });

                // Add Generate Release button
                var releaseBtn = document.createElement("button");
                releaseBtn.className = "btn-action btn-release";
                releaseBtn.textContent = "Generate Dispatch Release";
                releaseBtn.onclick = function() { window.generateRelease(); };
                actionsDiv.appendChild(releaseBtn);

                chatMessages.appendChild(actionsDiv);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }
    };

    // Determine who is being replaced from the dispatch result
    function _getReplacingCrew(rank) {
        var cached = dispatch_cache_local || {};
        var fi = cached.flight_info || {};
        if (rank === "CAPTAIN") return fi.captain_name || "Captain";
        return fi.fo_name || "First Officer";
    }

    var dispatch_cache_local = null;
    // Store dispatch result locally for action reference
    var _origUpdateDecision = updateDecision;
    updateDecision = function(data) {
        dispatch_cache_local = data;
        _origUpdateDecision(data);
    };

    // ── ASSIGN CREW ──────────────────────────────────────────
    window.assignCrew = function(crewName, rank) {
        if (!selectedFlightId) return;
        var replacing = _getReplacingCrew(rank);

        fetch("/api/assign-crew", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({flight_id: selectedFlightId, crew_name: crewName, crew_rank: rank, replacing: replacing})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            showToast("success", "Crew Assigned: " + crewName + " replaces " + replacing);
            appendChatMsg("system", "✅ " + data.message + " — Status: " + data.dispatch_status);
            updateStatusBadge(data.dispatch_status);
            // Disable the assign button
            var btns = document.querySelectorAll(".btn-assign");
            btns.forEach(function(b) {
                if (b.textContent === "Assign" && b.onclick.toString().indexOf(crewName) >= 0) {
                    b.textContent = "Assigned ✓"; b.disabled = true; b.className += " done";
                }
            });
        })
        .catch(function(err) { showToast("error", "Failed to assign: " + err.message); });
    };

    // ── NOTIFY CREW ──────────────────────────────────────────
    window.notifyCrew = function(crewName) {
        if (!selectedFlightId) return;

        fetch("/api/notify-crew", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({flight_id: selectedFlightId, crew_name: crewName})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            showToast("sms", "SMS sent to " + crewName + " at " + data.notification.phone);
            appendChatMsg("system", "📱 " + data.message);
            updateStatusBadge(data.dispatch_status);
        })
        .catch(function(err) { showToast("error", "Failed to notify: " + err.message); });
    };

    // ── GENERATE RELEASE ─────────────────────────────────────
    window.generateRelease = function() {
        if (!selectedFlightId) return;

        fetch("/api/generate-release", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({flight_id: selectedFlightId})
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            showToast("success", "Dispatch Release " + data.release.document_id + " generated");
            updateStatusBadge(data.dispatch_status);

            // Show the release document in a modal-like chat card
            var rel = data.release;
            var releaseHtml =
                '<div class="release-doc">' +
                '<div class="release-header">AMENDED DISPATCH RELEASE</div>' +
                '<div class="release-id">' + escHtml(rel.document_id) + '</div>' +
                '<table class="release-table">' +
                '<tr><td>Flight</td><td>' + escHtml(rel.flight_number) + '</td></tr>' +
                '<tr><td>Route</td><td>' + escHtml(rel.route) + '</td></tr>' +
                '<tr><td>Aircraft</td><td>' + escHtml(rel.aircraft) + ' (' + escHtml(rel.aircraft_type) + ')</td></tr>' +
                '<tr><td>Captain</td><td>' + escHtml(rel.captain) + '</td></tr>' +
                '<tr><td>First Officer</td><td>' + escHtml(rel.first_officer) + '</td></tr>' +
                '<tr><td>PAX</td><td>' + rel.pax + '</td></tr>' +
                '<tr><td>Departure</td><td>' + escHtml(rel.departure) + '</td></tr>' +
                '<tr><td>Decision</td><td><strong style="color:#22c55e">' + escHtml(rel.amended_decision) + '</strong> (was ' + escHtml(rel.original_decision) + ')</td></tr>' +
                '</table>';
            if (rel.amendments && rel.amendments.length) {
                releaseHtml += '<div class="release-section">Amendments</div><ul>';
                rel.amendments.forEach(function(a) { releaseHtml += '<li>' + escHtml(a) + '</li>'; });
                releaseHtml += '</ul>';
            }
            releaseHtml += '<div class="release-footer">' + escHtml(rel.dgca_compliance) + '<br>' + escHtml(rel.authorization) + '</div>';
            releaseHtml += '</div>';

            var div = document.createElement("div");
            div.className = "chat-msg assistant";
            div.innerHTML = releaseHtml;
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        })
        .catch(function(err) { showToast("error", "Failed to generate release: " + err.message); });
    };

    // ── STATUS BADGE UPDATE ──────────────────────────────────
    function updateStatusBadge(newStatus) {
        var badge = document.querySelector(".decision-badge");
        if (!badge) return;
        badge.textContent = newStatus;
        badge.className = "decision-badge " + (newStatus === "GO" ? "go" : newStatus === "NO-GO" ? "no-go" : "conditional");

        // Also update the flow decision node
        if (newStatus === "GO") {
            setFlowDone("decision", "green", "GO ✓");
        } else if (newStatus === "CONDITIONAL") {
            setFlowDone("decision", "amber", "CONDITIONAL");
        }
    }

    // ── TOAST NOTIFICATIONS ──────────────────────────────────
    function showToast(type, message) {
        var toast = document.createElement("div");
        toast.className = "toast toast-" + type;
        var icon = type === "success" ? "✅" : type === "sms" ? "📱" : type === "error" ? "❌" : "ℹ️";
        toast.innerHTML = '<span class="toast-icon">' + icon + '</span><span class="toast-text">' + escHtml(message) + '</span>';
        document.body.appendChild(toast);

        // Animate in
        setTimeout(function() { toast.classList.add("show"); }, 10);
        // Remove after 4 seconds
        setTimeout(function() {
            toast.classList.remove("show");
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    }

})();
