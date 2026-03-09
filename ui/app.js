// Creative Office Dashboard — Main Application Logic

class CreativeOfficeDashboard {
    constructor() {
        this.sessions        = [];
        this.currentData     = null;
        this.scoreChart      = null;
        this.liveInterval    = null;
        this.selectedIdeaIdx = null;

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadSessions();
        this.startLivePolling();
    }

    // -----------------------------------------------------------------------
    // Events
    // -----------------------------------------------------------------------

    bindEvents() {
        document.getElementById('refreshBtn').addEventListener('click', () => this.refreshData());
        document.getElementById('sessionSelect').addEventListener('change', e => this.loadSession(e.target.value));
        document.getElementById('closeModal').addEventListener('click', () => this.closeModal());
        document.getElementById('ideaModal').addEventListener('click', e => {
            if (e.target.id === 'ideaModal') this.closeModal();
        });

        // Seed launcher
        document.getElementById('newSessionBtn').addEventListener('click', () => this.openSeedModal());
        document.getElementById('closeSeedModal').addEventListener('click', () => this.closeSeedModal());
        document.getElementById('seedModal').addEventListener('click', e => {
            if (e.target.id === 'seedModal') this.closeSeedModal();
        });
        document.getElementById('seedForm').addEventListener('submit', e => {
            e.preventDefault();
            this.submitSeed();
        });

        // Auto-refresh toggle for Live tab
        document.getElementById('autoRefresh').addEventListener('change', e => {
            if (e.target.checked) this.startLivePolling();
            else this.stopLivePolling();
        });

        // Tabs
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', e => this.switchTab(e.target.dataset.tab));
        });
    }

    // -----------------------------------------------------------------------
    // Session loading
    // -----------------------------------------------------------------------

    async loadSessions() {
        try {
            const res = await fetch('/api/sessions');
            if (!res.ok) throw new Error();
            this.sessions = await res.json();
            this.populateSessionSelect();
        } catch {
            this.loadSampleData();
        }
    }

    populateSessionSelect() {
        const select = document.getElementById('sessionSelect');
        select.innerHTML = '<option value="">Select Session...</option>';
        this.sessions.forEach(s => {
            const opt = document.createElement('option');
            opt.value       = s.id;
            opt.textContent = `${s.name}${s.date ? ' — ' + s.date : ''}`;
            select.appendChild(opt);
        });
    }

    async loadSession(sessionId) {
        if (!sessionId) { this.currentData = null; this.clearDisplay(); return; }
        try {
            const res = await fetch(`/api/sessions/${sessionId}`);
            if (!res.ok) throw new Error();
            this.currentData = await res.json();
            this.render();
        } catch {
            this.loadSampleData();
        }
    }

    refreshData() {
        const select = document.getElementById('sessionSelect');
        select.value ? this.loadSession(select.value) : this.loadSessions();
    }

    // -----------------------------------------------------------------------
    // Tabs
    // -----------------------------------------------------------------------

    switchTab(tabName) {
        document.querySelectorAll('.tab-button').forEach(b => {
            b.classList.remove('active', 'border-blue-500');
            b.classList.add('border-transparent');
        });
        const active = document.querySelector(`[data-tab="${tabName}"]`);
        active.classList.add('active', 'border-blue-500');
        active.classList.remove('border-transparent');

        document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
        document.getElementById(`${tabName}-tab`).classList.remove('hidden');
    }

    // -----------------------------------------------------------------------
    // Rendering
    // -----------------------------------------------------------------------

    render() {
        if (!this.currentData) return;
        this.renderStats();
        this.renderTimeline();
        this.renderIdeas();
        this.renderScores();
        this.renderChart();
    }

    renderStats() {
        const s = this.currentData.stats;
        document.getElementById('generatorCount').textContent = s.ideasGenerated;
        document.getElementById('criticCount').textContent    = s.ideasKilled;
        document.getElementById('builderCount').textContent   = s.specsBuilt;
        document.getElementById('mutantCount').textContent    = s.hybridsCreated;
        document.getElementById('editorCount').textContent    = s.roundsCompleted;
        document.getElementById('totalRounds').textContent    = s.roundsCompleted;
        document.getElementById('totalIdeas').textContent     = s.ideasGenerated;

        const rate = s.ideasGenerated > 0
            ? ((s.ideasSurvived / s.ideasGenerated) * 100).toFixed(1)
            : '0.0';
        document.getElementById('survivalRate').textContent = `${rate}%`;
        document.getElementById('avgScore').textContent     = (s.avgCompositeScore || 0).toFixed(2);
    }

    renderTimeline() {
        const container = document.getElementById('timelineContainer');
        container.innerHTML = '';

        this.currentData.rounds.forEach((round, rIdx) => {
            // Round header
            const roundHeader = document.createElement('div');
            roundHeader.className = 'text-xs font-semibold text-slate-500 uppercase tracking-widest mt-4 mb-2';
            roundHeader.textContent = `Round ${round.round || rIdx + 1}`;
            container.appendChild(roundHeader);

            round.interactions.forEach((interaction, iIdx) => {
                const item = document.createElement('div');
                item.className = 'timeline-item';
                item.style.color = this.getAgentColor(interaction.agent);

                item.innerHTML = `
                    <div class="agent-card ${interaction.agent} bg-slate-800 rounded-lg p-4">
                        <div class="flex items-center justify-between mb-2">
                            <span class="agent-badge ${interaction.agent}">${interaction.agent}</span>
                        </div>
                        <p class="text-sm text-slate-300 line-clamp-3">${this.escapeHtml(interaction.summary)}</p>
                        <button onclick="dashboard.showInteractionDetail(${rIdx}, ${iIdx})"
                                class="text-xs text-blue-400 hover:text-blue-300 mt-2">
                            View full output →
                        </button>
                    </div>`;
                container.appendChild(item);
            });
        });
    }

    renderIdeas() {
        const container = document.getElementById('ideasList');
        container.innerHTML = '';

        this.currentData.ideas.forEach((idea, idx) => {
            const card = document.createElement('div');
            card.className = 'idea-card rounded-lg p-4 cursor-pointer';
            card.onclick = () => this.selectIdea(idx);

            const statusColor = this.getStatusColor(idea.status);
            card.innerHTML = `
                <div class="flex items-start justify-between mb-2">
                    <div class="flex-1">
                        <h3 class="text-white font-semibold">${this.escapeHtml(idea.name)}</h3>
                        <p class="text-xs text-slate-400 mt-1">${idea.domains.join(' × ')}</p>
                    </div>
                    <div class="flex items-center gap-2 flex-shrink-0 ml-2">
                        <span class="px-2 py-1 rounded text-xs font-medium"
                              style="background:${statusColor}20;color:${statusColor}">
                            ${idea.status}
                        </span>
                        <button onclick="event.stopPropagation();dashboard.showIdeaDetail(${idx})"
                                class="text-xs text-blue-400 hover:text-blue-300 px-2 py-1 border border-blue-400/30 rounded">
                            Details
                        </button>
                    </div>
                </div>
                <p class="text-sm text-slate-300 line-clamp-2">${this.escapeHtml(idea.pitch)}</p>
                ${idea.composite ? `
                    <div class="mt-2 flex items-center gap-2">
                        <span class="text-xs text-slate-400">Score:</span>
                        <span class="text-sm font-bold" style="color:${this.getScoreColor(idea.composite)}">
                            ${idea.composite.toFixed(2)}
                        </span>
                    </div>` : ''}`;
            container.appendChild(card);
        });
    }

    renderScores() {
        const tbody = document.getElementById('scoresTable');
        tbody.innerHTML = '';

        const sorted = [...this.currentData.ideas]
            .filter(i => i.scores)
            .sort((a, b) => b.composite - a.composite);

        sorted.forEach(idea => {
            const row = document.createElement('tr');
            row.className = 'border-b border-slate-700 hover:bg-slate-700/30';

            const scoreCells = ['novelty','timing','desire','buildability','strangeness','survivability']
                .map(k => {
                    const v = idea.scores[k];
                    const color = this.getAgentColorFromMetric(k);
                    return `<td class="py-3 px-4 text-center">
                        <div class="flex items-center gap-2">
                            <div class="score-bar w-16">
                                <div class="score-fill" style="width:${v*10}%;background:${color}"></div>
                            </div>
                            <span class="text-xs text-slate-300">${v.toFixed(1)}</span>
                        </div>
                    </td>`;
                }).join('');

            row.innerHTML = `
                <td class="py-3 px-4 text-white font-medium">${this.escapeHtml(idea.name)}</td>
                ${scoreCells}
                <td class="py-3 px-4 text-center">
                    <span class="text-lg font-bold" style="color:${this.getScoreColor(idea.composite)}">
                        ${idea.composite.toFixed(2)}
                    </span>
                </td>`;
            tbody.appendChild(row);
        });
    }

    renderChart() {
        const ctx = document.getElementById('scoreChart').getContext('2d');
        if (this.scoreChart) { this.scoreChart.destroy(); }

        const scored = this.currentData.ideas.filter(i => i.composite);
        const ranges = { '9–10': 0, '8–9': 0, '7–8': 0, '6–7': 0, '5–6': 0, '<5': 0 };
        scored.forEach(i => {
            if (i.composite >= 9)      ranges['9–10']++;
            else if (i.composite >= 8) ranges['8–9']++;
            else if (i.composite >= 7) ranges['7–8']++;
            else if (i.composite >= 6) ranges['6–7']++;
            else if (i.composite >= 5) ranges['5–6']++;
            else                       ranges['<5']++;
        });

        this.scoreChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: Object.keys(ranges),
                datasets: [{
                    label: 'Ideas',
                    data:  Object.values(ranges),
                    backgroundColor: [
                        'rgba(16,185,129,0.7)', 'rgba(59,130,246,0.7)',
                        'rgba(139,92,246,0.7)', 'rgba(245,158,11,0.7)',
                        'rgba(239,68,68,0.7)',  'rgba(107,114,128,0.7)',
                    ],
                    borderRadius: 6,
                    borderWidth: 0,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.1)' } },
                    x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                },
            },
        });
    }

    // -----------------------------------------------------------------------
    // Idea journey panel (right panel in Ideas tab)
    // -----------------------------------------------------------------------

    selectIdea(index) {
        this.selectedIdeaIdx = index;
        const idea    = this.currentData.ideas[index];
        const panel   = document.getElementById('ideaJourney');
        const statusColor = this.getStatusColor(idea.status);

        panel.innerHTML = `
            <div class="space-y-4">
                <div>
                    <h3 class="text-white font-semibold mb-1">${this.escapeHtml(idea.name)}</h3>
                    <span class="px-2 py-1 rounded text-xs font-medium"
                          style="background:${statusColor}20;color:${statusColor}">
                        ${idea.status}
                    </span>
                </div>

                <div>
                    <p class="text-xs text-slate-400 mb-1">Domains</p>
                    <div class="flex flex-wrap gap-1">
                        ${idea.domains.map(d => `
                            <span class="px-2 py-1 bg-slate-700 rounded text-xs text-white">${d}</span>
                        `).join('')}
                    </div>
                </div>

                ${idea.composite ? `
                    <div>
                        <p class="text-xs text-slate-400 mb-1">Composite Score</p>
                        <span class="text-3xl font-bold" style="color:${this.getScoreColor(idea.composite)}">
                            ${idea.composite.toFixed(2)}
                        </span>
                    </div>
                    <div class="space-y-2">
                        ${Object.entries(idea.scores).map(([k, v]) => `
                            <div>
                                <div class="flex justify-between text-xs mb-1">
                                    <span class="text-slate-400 capitalize">${k}</span>
                                    <span class="text-white">${v.toFixed(1)}</span>
                                </div>
                                <div class="score-bar">
                                    <div class="score-fill" style="width:${v*10}%;background:${this.getAgentColorFromMetric(k)}"></div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                ` : ''}

                <div>
                    <p class="text-xs text-slate-400 mb-2">Journey</p>
                    <div class="space-y-2">
                        ${(idea.journey || []).map((step, i) => `
                            <div class="flex items-start gap-2 text-sm">
                                <div class="w-5 h-5 rounded-full flex-shrink-0 flex items-center justify-center text-xs"
                                     style="background:${this.getAgentColor(step.agent)}20;color:${this.getAgentColor(step.agent)}">
                                    ${i + 1}
                                </div>
                                <div>
                                    <span class="text-white font-medium capitalize">${step.agent}</span>
                                    <p class="text-slate-400 text-xs">${step.action}</p>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>

                <button onclick="dashboard.showIdeaDetail(${index})"
                        class="w-full py-2 bg-blue-600/20 hover:bg-blue-600/40 border border-blue-500/30 rounded text-blue-400 text-sm transition-colors">
                    Full Details
                </button>
            </div>`;
    }

    // -----------------------------------------------------------------------
    // Modals
    // -----------------------------------------------------------------------

    showIdeaDetail(index) {
        const idea = this.currentData.ideas[index];
        document.getElementById('modalIdeaName').textContent = idea.name;

        document.getElementById('modalContent').innerHTML = `
            <div class="space-y-5">
                <div>
                    <h4 class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Pitch</h4>
                    <p class="text-white leading-relaxed">${this.escapeHtml(idea.pitch)}</p>
                </div>
                ${idea.timing ? `
                    <div>
                        <h4 class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Timing</h4>
                        <p class="text-white">${this.escapeHtml(idea.timing)}</p>
                    </div>` : ''}
                <div>
                    <h4 class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-2">Domains</h4>
                    <div class="flex flex-wrap gap-2">
                        ${idea.domains.map(d => `<span class="px-3 py-1 bg-slate-700 rounded-full text-xs text-white">${d}</span>`).join('')}
                    </div>
                </div>
                ${idea.scores ? `
                    <div>
                        <h4 class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">Scores</h4>
                        <div class="grid grid-cols-2 gap-3">
                            ${Object.entries(idea.scores).map(([k, v]) => `
                                <div>
                                    <div class="flex justify-between text-xs mb-1">
                                        <span class="text-slate-400 capitalize">${k}</span>
                                        <span class="text-white font-medium">${v.toFixed(1)}</span>
                                    </div>
                                    <div class="score-bar">
                                        <div class="score-fill" style="width:${v*10}%;background:${this.getAgentColorFromMetric(k)}"></div>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                        <div class="mt-4 pt-4 border-t border-slate-700 flex justify-between items-center">
                            <span class="text-slate-400">Composite Score</span>
                            <span class="text-2xl font-bold" style="color:${this.getScoreColor(idea.composite)}">
                                ${idea.composite.toFixed(2)}
                            </span>
                        </div>
                    </div>` : ''}
                ${idea.journey ? `
                    <div>
                        <h4 class="text-xs font-medium text-slate-400 uppercase tracking-wider mb-3">Journey</h4>
                        <div class="space-y-2">
                            ${idea.journey.map((step, i) => `
                                <div class="flex items-start gap-3 text-sm">
                                    <div class="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
                                         style="background:${this.getAgentColor(step.agent)}20;color:${this.getAgentColor(step.agent)}">
                                        ${i + 1}
                                    </div>
                                    <div>
                                        <span class="text-white font-medium capitalize">${step.agent}</span>
                                        <p class="text-slate-400 text-xs">${step.action}</p>
                                    </div>
                                </div>`).join('')}
                        </div>
                    </div>` : ''}
            </div>`;

        document.getElementById('ideaModal').classList.remove('hidden');
    }

    showInteractionDetail(roundIndex, interactionIndex) {
        const interaction = this.currentData.rounds[roundIndex].interactions[interactionIndex];
        const agentColor  = this.getAgentColor(interaction.agent);

        document.getElementById('modalIdeaName').innerHTML = `
            <span class="agent-badge ${interaction.agent} mr-2">${interaction.agent}</span>
            Round ${roundIndex + 1} Output`;

        // Format content: replace markdown headers and bold
        const formatted = this.escapeHtml(interaction.content)
            .replace(/^(#{1,3}) (.+)$/gm, '<span class="text-slate-300 font-semibold">$2</span>')
            .replace(/\*\*([^\*]+)\*\*/g, '<strong class="text-white">$1</strong>')
            .replace(/\n/g, '<br>');

        document.getElementById('modalContent').innerHTML = `
            <div class="font-mono text-sm text-slate-300 leading-relaxed whitespace-pre-wrap"
                 style="border-left: 3px solid ${agentColor}; padding-left: 1rem;">
                ${formatted}
            </div>`;

        document.getElementById('ideaModal').classList.remove('hidden');
    }

    closeModal() {
        document.getElementById('ideaModal').classList.add('hidden');
    }

    // -----------------------------------------------------------------------
    // Seed launcher
    // -----------------------------------------------------------------------

    openSeedModal() {
        document.getElementById('seedModal').classList.remove('hidden');
        document.getElementById('seedForm').reset();
        document.getElementById('seedStatus').textContent = '';
    }

    closeSeedModal() {
        document.getElementById('seedModal').classList.add('hidden');
    }

    async submitSeed() {
        const form   = document.getElementById('seedForm');
        const status = document.getElementById('seedStatus');
        const btn    = document.getElementById('seedSubmitBtn');

        const payload = {
            title:          document.getElementById('seedTitle').value.trim(),
            domain:         document.getElementById('seedDomain').value.trim(),
            temporal_frame: document.getElementById('seedTemporal').value.trim(),
            constraints:    document.getElementById('seedConstraints').value.trim(),
            provocation:    document.getElementById('seedProvocation').value.trim(),
            anti_targets:   document.getElementById('seedAntiTargets').value.trim(),
        };

        if (!payload.title) {
            status.textContent = 'Title is required.';
            status.className   = 'text-red-400 text-sm mt-2';
            return;
        }

        btn.disabled       = true;
        btn.textContent    = 'Saving...';
        status.textContent = '';

        try {
            const res  = await fetch('/api/seeds', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            });
            const data = await res.json();

            if (data.success) {
                status.textContent = `✓ Seed saved as ${data.filename}. Run: python run.py seeds/pending/${data.filename}`;
                status.className   = 'text-green-400 text-sm mt-2';
                btn.textContent    = 'Seed Launched';
            } else {
                throw new Error(data.error || 'Unknown error');
            }
        } catch (err) {
            status.textContent = `Error: ${err.message}`;
            status.className   = 'text-red-400 text-sm mt-2';
            btn.disabled       = false;
            btn.textContent    = 'Launch Session';
        }
    }

    // -----------------------------------------------------------------------
    // Live monitor
    // -----------------------------------------------------------------------

    startLivePolling() {
        if (this.liveInterval) return;
        this.liveInterval = setInterval(() => this.fetchLiveStatus(), 5000);
        this.fetchLiveStatus();
    }

    stopLivePolling() {
        if (this.liveInterval) {
            clearInterval(this.liveInterval);
            this.liveInterval = null;
        }
    }

    async fetchLiveStatus() {
        try {
            const res  = await fetch('/api/live');
            const data = await res.json();
            this.renderLiveStatus(data);
        } catch {
            // server not running or no room file — ignore silently
        }
    }

    renderLiveStatus(data) {
        const indicator = document.getElementById('liveIndicator');
        const statusTxt = document.getElementById('liveStatus');
        const roundLbl  = document.getElementById('liveRoundLabel');
        const output    = document.getElementById('liveOutput');
        const pipeline  = document.getElementById('liveAgentPipeline');

        if (data.running) {
            indicator.className = 'w-3 h-3 rounded-full bg-green-400 pulse-dot';
            const age = data.last_modified_seconds;
            statusTxt.textContent = `Session active — ${data.session_name || 'running'} — updated ${age}s ago`;
            statusTxt.className   = 'text-green-400';
        } else {
            indicator.className   = 'w-3 h-3 rounded-full bg-slate-600';
            statusTxt.textContent = 'No active session';
            statusTxt.className   = 'text-slate-400';
        }

        roundLbl.textContent = data.current_round
            ? `Round ${data.current_round}`
            : '—';

        // Agent pipeline
        const agentNames = ['generator', 'critic', 'builder', 'mutant', 'editor'];
        pipeline.innerHTML = agentNames.map((agent, i) => {
            const isLast   = agent === data.last_completed_agent;
            const isNext   = agent === data.next_agent && data.running;
            const isPast   = data.running && !isNext && !isLast &&
                agentNames.indexOf(agent) < agentNames.indexOf(data.last_completed_agent);

            let dotClass  = 'live-agent-dot';
            let labelClass = 'text-slate-500';
            let icon       = '';

            if (isPast || isLast) {
                dotClass  += ' done';
                labelClass = 'text-slate-400';
                icon       = '✓';
            }
            if (isNext) {
                dotClass  += ' active';
                labelClass = `font-semibold`;
            }

            const color = this.getAgentColor(agent);
            const arrow = i < 4 ? `<div class="live-arrow">→</div>` : '';

            return `
                <div class="flex items-center gap-1">
                    <div class="text-center">
                        <div class="${dotClass}" style="--agent-color:${color}">
                            ${icon || (isNext ? '●' : '○')}
                        </div>
                        <p class="text-xs ${labelClass} mt-1" style="${isNext ? `color:${color}` : ''}">${agent}</p>
                    </div>
                    ${arrow}
                </div>`;
        }).join('');

        output.textContent = data.recent_output || '— waiting for output —';
        // Auto-scroll to bottom
        output.scrollTop = output.scrollHeight;
    }

    // -----------------------------------------------------------------------
    // Helpers
    // -----------------------------------------------------------------------

    clearDisplay() {
        ['generatorCount','criticCount','builderCount','mutantCount','editorCount',
         'totalRounds','totalIdeas'].forEach(id => document.getElementById(id).textContent = '0');
        document.getElementById('survivalRate').textContent = '0%';
        document.getElementById('avgScore').textContent     = '0';
        document.getElementById('timelineContainer').innerHTML = '';
        document.getElementById('ideasList').innerHTML = '';
        document.getElementById('scoresTable').innerHTML = '';
        document.getElementById('ideaJourney').innerHTML = `
            <div class="text-center py-8 text-slate-400">Select an idea to see its journey</div>`;
        if (this.scoreChart) { this.scoreChart.destroy(); this.scoreChart = null; }
    }

    escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    getAgentColor(agent) {
        return { generator:'#8b5cf6', critic:'#ef4444', builder:'#3b82f6',
                 mutant:'#10b981', editor:'#f59e0b' }[agent] || '#94a3b8';
    }

    getAgentColorFromMetric(metric) {
        return { novelty:'#8b5cf6', timing:'#3b82f6', desire:'#10b981',
                 buildability:'#f59e0b', strangeness:'#ec4899', survivability:'#6366f1' }[metric] || '#94a3b8';
    }

    getStatusColor(status) {
        return { generated:'#8b5cf6', killed:'#ef4444', built:'#3b82f6',
                 mutated:'#10b981', selected:'#f59e0b' }[status] || '#94a3b8';
    }

    getScoreColor(score) {
        if (score >= 8) return '#10b981';
        if (score >= 7) return '#3b82f6';
        if (score >= 6) return '#f59e0b';
        if (score >= 5) return '#ef4444';
        return '#64748b';
    }

    // -----------------------------------------------------------------------
    // Sample data fallback
    // -----------------------------------------------------------------------

    loadSampleData() {
        this.currentData = {
            stats: {
                ideasGenerated: 45, ideasKilled: 28, ideasSurvived: 17,
                specsBuilt: 12,     hybridsCreated: 8, roundsCompleted: 5,
                avgCompositeScore: 7.2,
            },
            rounds: [
                { round: 1, interactions: [
                    { agent: 'generator', summary: 'Generated 10 new ideas combining quantum computing with traditional industries', content: 'Full generator output for round 1...' },
                    { agent: 'critic',    summary: 'Killed 6 ideas due to market saturation or technical infeasibility', content: 'Full critic output for round 1...' },
                    { agent: 'builder',   summary: 'Created detailed specs for 4 promising ideas', content: 'Full builder output...' },
                    { agent: 'mutant',    summary: 'Created 3 hybrid ideas from surviving concepts', content: 'Full mutant output...' },
                    { agent: 'editor',    summary: 'Selected top 2 ideas for this round', content: 'Full editor output...' },
                ]},
                { round: 2, interactions: [
                    { agent: 'generator', summary: 'Generated 9 new ideas focusing on biotech interfaces', content: 'Round 2 generator...' },
                    { agent: 'critic',    summary: 'Killed 5 ideas, flagged 2 for market research', content: 'Round 2 critic...' },
                    { agent: 'builder',   summary: 'Built technical specifications for 3 ideas', content: 'Round 2 builder...' },
                    { agent: 'mutant',    summary: 'Combined 2 ideas into promising hybrid', content: 'Round 2 mutant...' },
                    { agent: 'editor',    summary: 'Ranked all ideas, noted improvement in quality', content: 'Round 2 editor...' },
                ]},
            ],
            ideas: [
                {
                    name: 'NeuroLink Markets', pitch: 'Brain-computer interface for high-frequency trading decisions',
                    timing: 'BCI latency dropped below 10ms threshold in 2029',
                    domains: ['Neuroscience', 'Finance', 'AI'], status: 'selected',
                    scores: { novelty:9.2, timing:8.5, desire:7.8, buildability:6.5, strangeness:9.0, survivability:7.2 },
                    composite: 8.1,
                    journey: [
                        { agent:'generator', action:'Created initial concept' },
                        { agent:'critic',    action:'Flagged regulatory concerns' },
                        { agent:'builder',   action:'Designed compliance layer' },
                        { agent:'editor',    action:'Selected as top idea (composite: 8.1)' },
                    ],
                },
                {
                    name: 'QuantumGrief', pitch: 'Quantum encryption for digital legacy and posthumous message delivery',
                    timing: 'Quantum computers broke traditional encryption in 2031',
                    domains: ['Quantum Computing', 'Cryptography'], status: 'built',
                    scores: { novelty:8.8, timing:9.0, desire:8.2, buildability:7.5, strangeness:8.5, survivability:8.0 },
                    composite: 8.3,
                    journey: [
                        { agent:'generator', action:'Generated concept' },
                        { agent:'critic',    action:'Validated market need' },
                        { agent:'builder',   action:'Created full spec' },
                    ],
                },
                {
                    name: 'MyceliumNet', pitch: 'Fungal network-inspired decentralized internet infrastructure',
                    timing: 'Climate collapse made traditional infrastructure unreliable',
                    domains: ['Biology', 'Networking'], status: 'killed',
                    scores: { novelty:8.5, timing:7.0, desire:6.5, buildability:5.0, strangeness:9.5, survivability:4.5 },
                    composite: 6.8,
                    journey: [
                        { agent:'generator', action:'Created idea' },
                        { agent:'critic',    action:'Killed — impractical implementation' },
                    ],
                },
            ],
        };
        this.render();
        const select = document.getElementById('sessionSelect');
        select.innerHTML = '<option value="demo" selected>Demo Session — sample data</option>';
    }
}

const dashboard = new CreativeOfficeDashboard();
