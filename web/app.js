const AppConfig = { apiEndpoint: '/api/review', healthEndpoint: '/health' };

// --- Globals ---
let currentRawData = null;
let verifiedItems = {}; // { "missing_0": true, "discrepancy_1": true }
let currentTab = 'summary';

document.addEventListener('DOMContentLoaded', () => {
    // 1. Health check
    const checkHealth = async () => {
        const dot = document.getElementById('backendStatusDot');
        const text = document.getElementById('backendStatusText');
        try {
            if ((await fetch(AppConfig.healthEndpoint)).ok) {
                dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 relative shadow-[0_0_8px_#10b981]';
                text.textContent = '系统在线'; text.className = 'text-xs font-bold text-emerald-600';
            } else throw new Error();
        } catch (e) {
            dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500'; text.textContent = '服务离线'; text.className = 'text-xs font-bold text-rose-600';
        }
    };
    checkHealth(); setInterval(checkHealth, 30000);

    // 2. Drag/drop setup
    const setupDrop = (dropId, inpId, lblId) => {
        const drop = document.getElementById(dropId), inp = document.getElementById(inpId), lbl = document.getElementById(lblId);
        inp.addEventListener('change', (e) => {
            if(e.target.files.length) { lbl.textContent = e.target.files[0].name; lbl.classList.add('text-indigo-600'); drop.classList.add('border-indigo-300', 'bg-indigo-50/50'); }
        });
        drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('drag-active'); });
        ['dragleave', 'drop'].forEach(evt => drop.addEventListener(evt, e => { e.preventDefault(); drop.classList.remove('drag-active'); }));
        drop.addEventListener('drop', e => { if (e.dataTransfer.files.length) { inp.files = e.dataTransfer.files; inp.dispatchEvent(new Event('change')); } });
    };
    setupDrop('dropzoneProcurement', 'procurementFile', 'procurementFileName');
    setupDrop('dropzoneContract', 'contractFile', 'contractFileName');

    // 3. Export buttons
    document.getElementById('exportMdBtn').addEventListener('click', exportMarkdown);
    document.getElementById('exportJsonBtn').addEventListener('click', exportJSON);
    document.getElementById('exportVerifiedBtn').addEventListener('click', exportVerifiedJSON);

    // 4. Form submit
    document.getElementById('reviewForm').addEventListener('submit', handleSubmit);
});

// --- Advanced Config ---
const toggleAdvanced = () => {
    const config = document.getElementById('advancedConfig');
    const arrow = document.getElementById('advancedArrow');
    const isOpen = !config.classList.contains('hidden');
    if (isOpen) {
        config.classList.add('hidden');
        arrow.style.transform = 'rotate(0deg)';
    } else {
        config.classList.remove('hidden');
        arrow.style.transform = 'rotate(90deg)';
    }
};

const updateTempDisplay = () => {
    const val = document.getElementById('temperatureSlider').value;
    document.getElementById('tempDisplay').textContent = val;
    document.getElementById('tempValueLabel').textContent = val;
};

// --- Progress bar ---
let progressInterval;
const startProgress = () => {
    const bar = document.getElementById('progressBar');
    const pct = document.getElementById('loadingPercent');
    let current = 0;

    document.getElementById('step2').classList.add('opacity-40');
    document.getElementById('step2Dot').className = 'absolute -left-[31px] w-4 h-4 rounded-full bg-gray-300 ring-4 ring-white';
    document.getElementById('step3').classList.add('opacity-40');
    document.getElementById('step3Dot').className = 'absolute -left-[31px] w-4 h-4 rounded-full bg-gray-300 ring-4 ring-white';

    bar.style.width = '0%';
    progressInterval = setInterval(() => {
        if (current < 98) current += Math.random() * 2;
        bar.style.width = `${Math.min(current, 100)}%`;
        pct.textContent = `${Math.floor(current)}%`;

        if(current > 30) {
            document.getElementById('step2').classList.remove('opacity-40');
            document.getElementById('step2Dot').classList.replace('bg-gray-300', 'bg-indigo-500');
        }
        if(current > 70) {
            document.getElementById('step3').classList.remove('opacity-40');
            document.getElementById('step3Dot').classList.replace('bg-gray-300', 'bg-indigo-500');
        }
    }, 400);
};

const setUI = (state, msg = '') => {
    ['idleState', 'loadingState', 'reportContent', 'errorState'].forEach(id => document.getElementById(id).classList.add('hidden'));
    const btn = document.getElementById('submitBtn');
    if(state === 'loading') {
        verifiedItems = {};
        document.getElementById('loadingState').classList.remove('hidden');
        btn.disabled = true; btn.textContent = '分析中...';
        startProgress();
    } else if(state === 'success') {
        clearInterval(progressInterval);
        document.getElementById('loadingPercent').textContent = '100%';
        document.getElementById('progressBar').style.width = '100%';
        setTimeout(() => {
            document.getElementById('loadingState').classList.add('hidden');
            document.getElementById('reportContent').classList.remove('hidden');
            document.getElementById('reportContent').classList.add('flex');
            btn.disabled = false; btn.textContent = '重新提交';
        }, 500);
    } else if(state === 'error') {
        clearInterval(progressInterval);
        document.getElementById('errorState').classList.remove('hidden');
        document.getElementById('errorText').textContent = msg;
        btn.disabled = false; btn.textContent = '重试';
    }
};

// --- Form Submit ---
const handleSubmit = async (e) => {
    e.preventDefault();
    const f1 = document.getElementById("procurementFile").files[0],
          f2 = document.getElementById("contractFile").files[0];
    if (!f1 || !f2) return alert("请先上传文件");

    setUI('loading');
    const fd = new FormData();
    fd.append("procurement_file", f1);
    fd.append("contract_file", f2);
    fd.append("provider", document.getElementById("provider").value);

    const apiKey = document.getElementById('apiKeyInput').value;
    const model = document.getElementById('modelInput').value;
    const temperature = document.getElementById('temperatureSlider').value;

    if (apiKey) fd.append('api_key', apiKey);
    if (model) fd.append('model', model);
    fd.append('temperature', temperature);

    try {
        const res = await fetch(AppConfig.apiEndpoint, { method: "POST", body: fd });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || `Error: ${res.status}`);
        renderReport(data);
        setUI('success');
    } catch (err) { setUI('error', err.message); }
};

// --- Tab Switching ---
const switchTab = (tabName) => {
    currentTab = tabName;
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    document.querySelectorAll('.tab-panel').forEach(panel => {
        if (panel.dataset.panel === tabName) {
            panel.classList.remove('hidden');
        } else {
            panel.classList.add('hidden');
        }
    });
};

// --- Render Report ---
const renderReport = (data) => {
    currentRawData = data;
    const report = data.review_report || {};

    const missingItems = report.missing_items || [];
    const discrepancies = report.discrepancies || [];
    const consistentItems = report.consistent_items || [];

    // Update stats
    document.getElementById('statMissing').textContent = missingItems.length;
    document.getElementById('statDiscrepancy').textContent = discrepancies.length;
    document.getElementById('statConsistent').textContent = consistentItems.length;

    // Update tab counts
    document.getElementById('missingTabCount').textContent = missingItems.length;
    document.getElementById('discrepancyTabCount').textContent = discrepancies.length;
    document.getElementById('consistentTabCount').textContent = consistentItems.length;

    // Render each section
    renderSummary(report.review_summary);
    renderMissingItems(missingItems);
    renderDiscrepancies(discrepancies);
    renderConsistentItems(consistentItems);
    renderFullReport(data.report_markdown || '');

    // Default to summary tab
    switchTab('summary');
};

// --- Summary ---
const renderSummary = (summaryText) => {
    document.getElementById('summaryText').textContent = summaryText || '暂无总结信息';
};

// --- Missing Items ---
const renderMissingItems = (items) => {
    const container = document.getElementById('missingItemsContainer');
    const empty = document.getElementById('missingEmpty');
    container.innerHTML = '';

    if (items.length === 0) {
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    const riskColors = { high: 'text-rose-600 bg-rose-100', medium: 'text-amber-600 bg-amber-100', low: 'text-yellow-600 bg-yellow-100' };

    items.forEach((item, idx) => {
        const key = `missing_${idx}`;
        const riskClass = riskColors[item.risk_level] || 'text-gray-500 bg-gray-100';
        const isChecked = verifiedItems[key] || false;

        const div = document.createElement('div');
        div.className = 'result-card bg-rose-50 border-l-4 border-rose-500 rounded-xl p-5 shadow-sm';
        div.innerHTML = `
            <div class="flex items-center gap-2 mb-3 flex-wrap">
                <span class="text-xs px-2 py-0.5 rounded font-medium bg-gray-200 text-gray-600">${escapeHtml(item.dimension || '')}</span>
                <span class="text-xs font-bold text-gray-500">${escapeHtml(item.sub_dimension || '')}</span>
                ${item.risk_level ? `<span class="text-xs font-bold px-2 py-0.5 rounded ${riskClass}">${item.risk_level.toUpperCase()}</span>` : ''}
            </div>
            <div class="bg-white rounded-lg p-3 border border-rose-100 mb-2">
                <p class="text-xs font-bold text-rose-500 mb-1">采购要求原文</p>
                <p class="text-sm text-gray-700">${escapeHtml(item.procurement_quote || '-')}</p>
            </div>
            <div class="bg-indigo-50/50 rounded-lg p-3 border border-indigo-100/50 mb-3">
                <p class="text-xs font-bold text-indigo-500 mb-1">AI 分析</p>
                <p class="text-sm text-gray-800">${escapeHtml(item.analysis || '-')}</p>
            </div>
            <label class="flex items-center gap-2 text-xs text-gray-500 cursor-pointer select-none">
                <input type="checkbox" class="verify-checkbox w-4 h-4 rounded accent-emerald-500" data-key="${key}" ${isChecked ? 'checked' : ''} onchange="toggleVerified('${key}', this.checked)">
                已核验
            </label>
        `;
        container.appendChild(div);
    });
};

// --- Discrepancy Items ---
const renderDiscrepancies = (items) => {
    const container = document.getElementById('discrepancyItemsContainer');
    const empty = document.getElementById('discrepancyEmpty');
    container.innerHTML = '';

    if (items.length === 0) {
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    const riskColors = { high: 'text-rose-600 bg-rose-100', medium: 'text-amber-600 bg-amber-100', low: 'text-yellow-600 bg-yellow-100' };

    items.forEach((item, idx) => {
        const key = `discrepancy_${idx}`;
        const riskClass = riskColors[item.risk_level] || 'text-gray-500 bg-gray-100';
        const isChecked = verifiedItems[key] || false;

        const div = document.createElement('div');
        div.className = 'result-card bg-amber-50 border-l-4 border-amber-500 rounded-xl p-5 shadow-sm';
        div.innerHTML = `
            <div class="flex items-center gap-2 mb-3 flex-wrap">
                <span class="text-xs px-2 py-0.5 rounded font-medium bg-gray-200 text-gray-600">${escapeHtml(item.dimension || '')}</span>
                <span class="text-xs font-bold text-gray-500">${escapeHtml(item.sub_dimension || '')}</span>
                ${item.risk_level ? `<span class="text-xs font-bold px-2 py-0.5 rounded ${riskClass}">${item.risk_level.toUpperCase()}</span>` : ''}
            </div>
            <div class="grid grid-cols-2 gap-3 mb-3">
                <div class="bg-white rounded-lg p-3 border border-gray-100">
                    <p class="text-xs font-bold text-blue-500 mb-1">采购要求</p>
                    <p class="text-sm text-gray-700">${escapeHtml(item.procurement_quote || '-')}</p>
                </div>
                <div class="bg-white rounded-lg p-3 border border-gray-100">
                    <p class="text-xs font-bold text-indigo-500 mb-1">合同草案</p>
                    <p class="text-sm text-gray-700">${escapeHtml(item.contract_quote || '-')}</p>
                </div>
            </div>
            <div class="bg-indigo-50/50 rounded-lg p-3 border border-indigo-100/50 mb-2">
                <p class="text-xs font-bold text-indigo-500 mb-1">AI 分析</p>
                <p class="text-sm text-gray-800">${escapeHtml(item.analysis || '-')}</p>
            </div>
            <label class="flex items-center gap-2 text-xs text-gray-500 cursor-pointer select-none">
                <input type="checkbox" class="verify-checkbox w-4 h-4 rounded accent-emerald-500" data-key="${key}" ${isChecked ? 'checked' : ''} onchange="toggleVerified('${key}', this.checked)">
                已核验
            </label>
        `;
        container.appendChild(div);
    });
};

// --- Consistent Items ---
const renderConsistentItems = (items) => {
    const container = document.getElementById('consistentItemsContainer');
    const empty = document.getElementById('consistentEmpty');
    container.innerHTML = '';

    if (items.length === 0) {
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    items.forEach((item, idx) => {
        const key = `consistent_${idx}`;
        const isChecked = verifiedItems[key] || false;

        const div = document.createElement('div');
        div.className = 'result-card bg-emerald-50/50 border border-emerald-100 rounded-lg p-3';
        div.innerHTML = `
            <div class="flex items-center gap-2 mb-2 flex-wrap">
                <span class="text-xs px-2 py-0.5 rounded font-medium bg-emerald-100 text-emerald-700">${escapeHtml(item.dimension || '')}</span>
                <span class="text-xs font-bold text-gray-500">${escapeHtml(item.sub_dimension || '')}</span>
            </div>
            <div class="grid grid-cols-2 gap-3 text-xs">
                <div class="bg-white rounded p-2 border border-emerald-50">
                    <span class="font-bold text-emerald-600">采购要求: </span>${escapeHtml(item.procurement_quote || '-')}
                </div>
                <div class="bg-white rounded p-2 border border-emerald-50">
                    <span class="font-bold text-emerald-600">合同草案: </span>${escapeHtml(item.contract_quote || '-')}
                </div>
            </div>
            <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none mt-2">
                <input type="checkbox" class="verify-checkbox w-3.5 h-3.5 rounded accent-emerald-500" data-key="${key}" ${isChecked ? 'checked' : ''} onchange="toggleVerified('${key}', this.checked)">
                已核验
            </label>
        `;
        container.appendChild(div);
    });
};

// --- Full Report ---
const renderFullReport = (markdown) => {
    const container = document.getElementById('fullReportContent');
    let html = '';
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        html = marked.parse(markdown);
    } else if (typeof marked !== 'undefined') {
        html = marked(markdown);
    }
    if (typeof DOMPurify !== 'undefined') {
        container.innerHTML = DOMPurify.sanitize(html);
    } else if (html) {
        container.innerHTML = html;
    } else {
        container.textContent = markdown || '暂无完整报告';
    }
};

// --- Verified Checkbox ---
const toggleVerified = (key, checked) => {
    if (checked) {
        verifiedItems[key] = true;
    } else {
        delete verifiedItems[key];
    }
};

// --- Export Functions ---
const downloadBlob = (content, filename, mimeType) => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([content], { type: mimeType }));
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
};

const exportMarkdown = () => {
    if(!currentRawData || !currentRawData.report_markdown) return alert("无 Markdown 数据");
    downloadBlob(currentRawData.report_markdown, "智能审核报告.md", "text/markdown");
};

const exportJSON = () => {
    if(!currentRawData) return alert("无报告数据");
    const payload = JSON.parse(JSON.stringify(currentRawData));
    downloadBlob(JSON.stringify(payload, null, 2), "智能审核报告.json", "application/json");
};

const exportVerifiedJSON = () => {
    if(!currentRawData) return alert("无报告数据");
    const verifiedKeys = Object.keys(verifiedItems);
    if (verifiedKeys.length === 0) return alert("尚未勾选任何\"已核验\"项");

    const payload = JSON.parse(JSON.stringify(currentRawData));
    const report = payload.review_report || {};

    const annotate = (list, prefix) => {
        if (!Array.isArray(list)) return;
        list.forEach((item, i) => {
            item._verified = !!verifiedItems[`${prefix}_${i}`];
        });
    };

    annotate(report.missing_items, 'missing');
    annotate(report.discrepancies, 'discrepancy');
    annotate(report.consistent_items, 'consistent');

    const verifiedCount = verifiedKeys.length;
    const totalCount = (report.missing_items || []).length + (report.discrepancies || []).length + (report.consistent_items || []).length;

    payload._export_info = {
        exported_at: new Date().toISOString(),
        verified_count: verifiedCount,
        total_review_items: totalCount,
        verification_ratio: totalCount > 0 ? (verifiedCount / totalCount).toFixed(2) : '0'
    };

    downloadBlob(JSON.stringify(payload, null, 2), "合同审核核验结果.json", "application/json");
};

// --- Utility ---
const escapeHtml = (str) => {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
};
