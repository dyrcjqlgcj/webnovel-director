// webnovel-director Dashboard
const STATE = {};
let currentVolume = 0;

function normalizeStatus(s) {
  s = (s || '').toUpperCase();
  if (['WRITTEN', '已写'].includes(s)) return 'written';
  if (['PASS', '通过'].includes(s)) return 'pass';
  if (['WARN', '警告'].includes(s)) return 'warn';
  if (['FAIL', '失败'].includes(s)) return 'fail';
  if (['NEEDS_WRITING', 'NEEDS WRITING'].includes(s)) return 'queue';
  return 'queue';
}

function statusLabel(s) {
  const m = {written:'已写', pass:'通过', warn:'警告', fail:'失败', queue:'待写'};
  return m[normalizeStatus(s)] || '待写';
}

// Theme persistence
const savedTheme = localStorage.getItem('wd-theme') || 'dark';
document.documentElement.setAttribute('data-theme', savedTheme);

function toggleTheme() {
  const el = document.documentElement;
  const next = el.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  el.setAttribute('data-theme', next);
  localStorage.setItem('wd-theme', next);
}

async function refresh() {
  try {
    const r = await fetch('/api/state');
    const s = await r.json();
    Object.assign(STATE, s);
    render(s);
  } catch(e) { console.error(e); }
}

function render(s) {
  document.getElementById('project-title').textContent = s.title || '未命名项目';
  const totalBookChapters = (s.volumes||[]).reduce((sum, v) => sum + v.chapters, 0) || s.total_chapters_planned;
  let planned, written;
  if (currentVolume > 0) {
    const vol = (s.volumes||[]).find(v => v.start === currentVolume);
    if (vol) {
      planned = vol.chapters;
      written = (s.chapters||[]).filter(c => c.chapter >= vol.start && c.chapter <= vol.end && c.words > 0).length;
    }
  }
  if (!planned) { planned = totalBookChapters; written = s.total_chapters_written; }
  document.getElementById('ch-progress').textContent = written + '/' + planned + (currentVolume > 0 ? '' : ' (全)');
  document.getElementById('ch-words').textContent = (s.total_chars/10000).toFixed(1) + '万';
  const auditStatus = (s.last_audit || {}).status || '-';
  const auditLabels = {PASS:'通过', WARN:'警告', FAIL:'失败', NONE:'未审'};
  document.getElementById('ch-status').textContent = auditLabels[auditStatus] || auditStatus;

  const sel = document.getElementById('vol-selector');
  sel.innerHTML = '<option value="0">全部卷</option>' +
    (s.volumes||[]).map((v,i) =>
      `<option value="${v.start}" ${currentVolume===v.start?'selected':''}>第${v.label}卷 ${v.start}-${v.end}章 ${v.theme}</option>`
    ).join('');

  let chapters = s.chapters || [];
  if (currentVolume > 0) {
    const vol = (s.volumes||[]).find(v => v.start === currentVolume);
    if (vol) chapters = chapters.filter(c => c.chapter >= vol.start && c.chapter <= vol.end);
  }
  const sf = document.getElementById('status-filter').value;
  if (sf) chapters = chapters.filter(c => normalizeStatus(c.status) === sf);

  document.getElementById('s-chapters').textContent = written;
  document.getElementById('s-words').textContent = (s.total_chars/10000).toFixed(1) + '万字';
  const passN = (s.chapters||[]).filter(c => c.review_verdict === 'PASS').length;
  const warnN = (s.chapters||[]).filter(c => c.review_verdict === 'WARN').length;
  const failN = (s.chapters||[]).filter(c => c.review_verdict === 'FAIL').length;
  const totalReviewed = passN + warnN + failN;
  document.getElementById('s-pass').innerHTML = totalReviewed + '<span style="font-size:11px;margin-left:4px"><span style="color:var(--pass)">' + passN + '</span>/<span style="color:var(--warn)">' + warnN + '</span>/<span style="color:var(--fail)">' + failN + '</span></span>';

  const pct = planned > 0 ? Math.round(written / planned * 100) : 0;
  document.getElementById('progress-fill').style.width = pct + '%';

  const tbody = document.querySelector('#chapter-table tbody');
  tbody.innerHTML = chapters.slice(0, 50).map(c => {
    const ns = normalizeStatus(c.status);
    const cls = ns === 'written' ? 'PASS' : ns === 'warn' ? 'WARN' : ns === 'fail' ? 'FAIL' : 'QUEUE';
    const stLabel = statusLabel(c.status);
    const title = c.title || ('第' + String(c.chapter).padStart(3,'0') + '章');
    const w = c.words || 0;
    const wDisplay = w > 0 ? w.toString() : '-';
    const mTime = c.mtime || '-';
    const rvTime = c.reviewed_at || '';
    const rvVerdict = c.review_verdict || '';
    const rvIssues = c.review_issues || [];
    const issuesSummary = rvIssues.slice(0, 2).map(i => i.replace(/^\[.+\]\s*/, '').substring(0, 20)).join(', ') || '';
    const verdictColors = {PASS:'var(--pass)',WARN:'var(--warn)',FAIL:'var(--fail)'};
    const verdictStyle = rvVerdict ? `color:${verdictColors[rvVerdict]||'var(--muted)'};font-weight:600` : '';
    const verdictLabels = {PASS:'通过',WARN:'警告',FAIL:'失败'};
    return `<tr style="cursor:pointer" onclick="showDetail(${c.chapter})">
      <td class="ch">${c.chapter}</td>
      <td>${esc(title)}</td>
      <td style="font-variant-numeric:tabular-nums;text-align:right;padding-right:16px;font-size:12px;color:var(--muted)">${wDisplay}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${mTime}</td>
      <td style="font-size:12px;${verdictStyle}">${rvVerdict ? (verdictLabels[rvVerdict]||rvVerdict) : '-'}</td>
      <td style="font-size:11px;color:var(--muted);white-space:nowrap">${rvTime || '-'}</td>
      <td style="font-size:11px;color:var(--muted);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(rvIssues.join('; '))}">${issuesSummary || '-'}</td>
      <td class="status"><span class="status-badge ${cls}">${stLabel}</span></td>
      <td><button class="btn" style="padding:2px 6px;font-size:11px;width:36px" onclick="event.stopPropagation();doAction('review_ch_${c.chapter}')" title="审查第${c.chapter}章">审</button></td>
    </tr>`;
  }).join('');

  const bl = document.getElementById('blockers-list');
  if ((s.blockers||[]).length > 0) {
    bl.innerHTML = s.blockers.map(b => `<span class="blocker-tag">⚠ ${esc(b)}</span>`).join('');
  } else {
    bl.innerHTML = '<span style="color:var(--pass);font-size:13px">✅ 无阻塞项</span>';
  }
  document.getElementById('refresh-time').textContent = '更新 ' + new Date().toLocaleTimeString();
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function switchVolume() {
  currentVolume = parseInt(document.getElementById('vol-selector').value) || 0;
  render(STATE);
}

function closeModal() { document.getElementById('detail-modal').classList.remove('show'); }

let editingChapter = 0;

function showDetail(chNum) {
  const ch = (STATE.chapters||[]).find(c => c.chapter === chNum);
  if (!ch) return;
  editingChapter = chNum;
  document.getElementById('modal-title').textContent = '第' + ch.chapter + '章 ' + (ch.title || '');
  document.getElementById('modal-meta').textContent =
    '状态: ' + statusLabel(ch.status) + ' | 字数: ' + ((ch.words||0)/1000).toFixed(1) + 'k' +
    (ch.reviewed_at ? ' | 最后修改: ' + ch.reviewed_at : '');
  renderReadOnly(ch);
  document.getElementById('detail-modal').classList.add('show');
}

function renderReadOnly(ch) {
  document.getElementById('modal-goal').style.display = 'block'; document.getElementById('modal-goal-edit').style.display = 'none';
  document.getElementById('modal-premise').style.display = 'block'; document.getElementById('modal-premise-edit').style.display = 'none';
  document.getElementById('modal-forbidden').style.display = 'block'; document.getElementById('modal-forbidden-edit').style.display = 'none';
  document.getElementById('modal-goal').textContent = ch.goal || '未设定';
  document.getElementById('modal-premise').textContent = ch.premise_hit || '未设定';
  document.getElementById('modal-forbidden').textContent = ch.forbidden || '无';
  document.getElementById('modal-edit-btn').style.display = 'inline-block';
  document.getElementById('modal-save-btn').style.display = 'none'; document.getElementById('modal-cancel-btn').style.display = 'none';
  document.getElementById('modal-save-status').textContent = '';
}

function startEdit() {
  const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
  if (!ch) return;
  document.getElementById('modal-goal').style.display = 'none'; document.getElementById('modal-goal-edit').style.display = 'block';
  document.getElementById('modal-goal-edit').value = ch.goal || '';
  document.getElementById('modal-premise').style.display = 'none'; document.getElementById('modal-premise-edit').style.display = 'block';
  document.getElementById('modal-premise-edit').value = ch.premise_hit || '';
  document.getElementById('modal-forbidden').style.display = 'none'; document.getElementById('modal-forbidden-edit').style.display = 'block';
  document.getElementById('modal-forbidden-edit').value = ch.forbidden || '';
  document.getElementById('modal-edit-btn').style.display = 'none';
  document.getElementById('modal-save-btn').style.display = 'inline-block'; document.getElementById('modal-cancel-btn').style.display = 'inline-block';
}

function cancelEdit() {
  const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
  if (ch) renderReadOnly(ch);
}

async function saveEdit() {
  const goal = document.getElementById('modal-goal-edit').value;
  const premise = document.getElementById('modal-premise-edit').value;
  const forbidden = document.getElementById('modal-forbidden-edit').value;
  const statusEl = document.getElementById('modal-save-status');
  statusEl.textContent = '保存中...';
  try {
    const r = await fetch('/api/save_chapter', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({chapter: editingChapter, goal, premise_hit: premise, forbidden})
    });
    const d = await r.json();
    if (d.success) {
      const ch = (STATE.chapters||[]).find(c => c.chapter === editingChapter);
      if (ch) { ch.goal = goal; ch.premise_hit = premise; ch.forbidden = forbidden; }
      renderReadOnly(ch || {});
      refresh();
      statusEl.textContent = '✅ 已保存';
      setTimeout(() => { statusEl.textContent = ''; }, 2000);
    } else {
      statusEl.textContent = '❌ ' + (d.error || '失败');
    }
  } catch(e) { statusEl.textContent = '❌ ' + e.message; }
}

function exportTable() {
  const chapters = STATE.chapters || [];
  const rows = [['章','标题','字数','Goal','Premise Hit','状态']];
  for (const c of chapters.slice(0, 80)) {
    if (currentVolume > 0) {
      const vol = (STATE.volumes||[]).find(v => v.start === currentVolume);
      if (vol && (c.chapter < vol.start || c.chapter > vol.end)) continue;
    }
    rows.push([c.chapter, c.title||'', ((c.words||0)/1000).toFixed(1)+'k', (c.goal||'').substring(0,50), (c.premise_hit||'').substring(0,50), statusLabel(c.status)]);
  }
  const text = rows.map(r => r.join('\t')).join('\n');
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.target;
    const orig = btn.textContent;
    btn.textContent = '✅ 已复制';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

async function doAction(action) {
  const btn = event.target;
  const orig = btn.textContent;
  btn.disabled = true;
  btn.style.width = btn.offsetWidth + 'px';
  btn.innerHTML = '<span class="spinner"></span>';
  const out = document.getElementById('output');
  out.textContent = '执行中...';
  try {
    const r = await fetch('/api/action/' + action);
    const d = await r.json();
    out.textContent = (d.output || d.error || 'Done.');

    if (action.startsWith('review_ch_')) {
      const chNum = action.replace('review_ch_', '');
      const statusMatch = (d.output || '').match(/结论[：:]\s*(PASS|WARN|FAIL)/);
      if (statusMatch) {
        const ch = (STATE.chapters||[]).find(c => c.chapter === parseInt(chNum));
        if (ch) {
          ch.reviewed_at = new Date().toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});
          ch.review_verdict = statusMatch[1];
          const issues = [];
          for (const line of (d.output || '').split('\n')) {
            const m = line.match(/(?:WARN|FAIL)\s+\[(.+?)\]\s*(?:—|:)?\s*(.+)/);
            if (m) issues.push('[' + m[1] + '] ' + m[2].trim());
          }
          ch.review_issues = issues;
        }
        render(STATE);
      }
    }
    if (!action.startsWith('review_ch_') && d.success) setTimeout(refresh, 2000);
  } catch(e) { out.textContent = 'Error: ' + e.message; }
  btn.disabled = false;
  btn.textContent = orig;
  btn.style.width = '';
}

// Auto-refresh every 30 seconds
let refreshCountdown = 30;
setInterval(() => {
  refreshCountdown--;
  if (refreshCountdown <= 0) { refresh(); refreshCountdown = 30; }
  document.getElementById('auto-refresh-label').textContent = refreshCountdown + 's 自动刷新';
}, 1000);

refresh();
