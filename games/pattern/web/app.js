/* 找规律（Pattern）前端：拿题 → 画题面（珠子 / 空位）→ 点「完成」亮答案和规律 → 自评
 *
 * 数据约定（跟后端一致，见 games/pattern/core/cards.py 的 payload）：
 *   rows        [[{bead:'R'} | {blank:true} | {blank_group:true}], ...]  一行一组
 *   reveal_rows 同上，但空位填上了答案，每格多一个 mark（'' / 'answer' / 'fix'）
 *   answer_text "蓝、红、红（3 颗）"
 *   fix_text    "第 8 颗：原来是蓝，该改成红"（没有 fix 就是空串）
 *   task        页面上那句任务说明（后端拼好的）
 *
 * **这个游戏不在屏幕上摆珠子** —— 珠子是实物，屏幕上只出题、给答案和解释。
 */

window.__pattern_loaded = true;

// 颜色：编号 → 中文名 / 颜色值（跟后端 core/colors.py 的 "YGRPBO" 对应）
const COLORS = {
  Y: { name: '黄', css: '#f2c231' },
  G: { name: '绿', css: '#4caf50' },
  R: { name: '红', css: '#e5484d' },
  P: { name: '紫', css: '#9b59d0' },
  B: { name: '蓝', css: '#3b82f6' },
  O: { name: '橙', css: '#f2811d' },
};

const $ = (id) => document.getElementById(id);
// 接口基址：单独跑时是 /api，广场里由广场往页面里注入 window.API_BASE
const API = window.API_BASE || '/api';

// 历史页「打开」带过来的题目 id（/games/pattern/?p=<id>，`?puzzle=` 也认）
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const boardEl = $('board');

const state = {
  card: null,        // 当前这道题（后端返回的原样）
  revealed: false,   // 有没有点过「完成」
  solved: false,     // 自评"摆对了"没有
};

// ---------------------------------------------------------------------------
// 声音（Web Audio 合成，不用素材文件）
// ---------------------------------------------------------------------------

let audio = null;
function audioCtx() {
  if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio.state === 'suspended') audio.resume();
  return audio;
}

/** 放珠子 / 点珠子："嗒" */
function playTick(pitch = 1) {
  try {
    const ctx = audioCtx();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.value = (360 + Math.random() * 90) * pitch;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.22, t + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.2);
  } catch (e) { /* 没声音也不影响玩 */ }
}

/** 对了："叮" */
function playDing() {
  try {
    const ctx = audioCtx();
    const t = ctx.currentTime;
    [880, 1320].forEach((f, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.value = f;
      gain.gain.setValueAtTime(0.0001, t + i * 0.04);
      gain.gain.exponentialRampToValueAtTime(0.18, t + i * 0.04 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.04 + 0.5);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t + i * 0.04);
      osc.stop(t + i * 0.04 + 0.55);
    });
  } catch (e) { /* 同上 */ }
}

/** 没对 / 到头："咚" */
function playThud() {
  try {
    const ctx = audioCtx();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(150, t);
    osc.frequency.exponentialRampToValueAtTime(70, t + 0.22);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.3, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.4);
  } catch (e) { /* 没声音也不影响 */ }
}

// ---------------------------------------------------------------------------
// 朗读
// ---------------------------------------------------------------------------

/** 念之前先把 emoji 之类去掉（念出来是噪音） */
function speechText(text) {
  return (text || '')
    .replace(/[^\u4e00-\u9fff，。、？！：；""''（）,.?!0-9A-Za-z\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const clean = speechText(text);
  if (!clean) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(clean);
    u.lang = 'zh-CN';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  } catch (e) { /* 不支持就算了 */ }
}

/** 把题面念成一串颜色名（`红、蓝、红、蓝……`） */
function beadsSpeech() {
  const card = state.card;
  if (!card) return '';
  const rows = card.rows.map((row) => row.map((cell) => {
    if (cell.bead) return COLORS[cell.bead].name;
    return '空';
  }).join('、'));
  return rows.join('，然后');
}

function readWhole() {
  const card = state.card;
  if (!card) return;
  const parts = [card.title, card.story, beadsSpeech(), card.task];
  if (state.revealed) {
    if (card.answer_text) parts.push('答案：' + card.answer_text);
    if (card.fix_text) parts.push(card.fix_text);
    parts.push(card.rule);
  }
  speak(parts.filter(Boolean).join('。'));
}

// ---------------------------------------------------------------------------
// 画题面
// ---------------------------------------------------------------------------

let toastTimer = null;
function toast(text, ms = 2200) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

function setStatus(text) { $('status').textContent = text; }

function beadEl(letter, mark = '') {
  const info = COLORS[letter] || { name: letter, css: '#888' };
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'bead' + (mark === 'answer' ? ' right' : mark === 'fix' ? ' wrong' : '');
  el.dataset.letter = letter;
  el.style.background = info.css;
  el.title = info.name + '色';
  el.setAttribute('aria-label', info.name + '色');
  el.addEventListener('click', () => {
    playTick(1.2);
    toast(info.name + '色');
    speak(info.name + '色');
  });
  return el;
}

/** 画题面：一行一组；`blank` 是空位，`blank_group` 是"整组空着"（几颗得孩子自己想）。 */
function render() {
  const card = state.card;
  if (!card) return;
  const rows = state.revealed ? card.reveal_rows : card.rows;
  const line = card.kind === 'repeat';
  boardEl.innerHTML = '';

  let pos = 0;
  rows.forEach((row, gi) => {
    const groupEl = document.createElement('div');
    groupEl.className = 'group' + (line ? ' line' : '');

    row.forEach((cell) => {
      if (cell.blank_group) {
        const box = document.createElement('div');
        box.className = 'blank group-blank';
        box.textContent = '？这一组';
        groupEl.appendChild(box);
        return;
      }
      const wrap = document.createElement('div');
      wrap.className = 'cell';
      if (cell.bead) {
        wrap.appendChild(beadEl(cell.bead, cell.mark));
      } else {
        const box = document.createElement('div');
        box.className = 'blank';
        box.textContent = '?';
        wrap.appendChild(box);
      }
      pos += 1;
      const num = document.createElement('span');
      num.className = 'num';
      num.textContent = String(pos);
      wrap.appendChild(num);
      groupEl.appendChild(wrap);
    });

    if (!line) {
      const tag = document.createElement('span');
      tag.className = 'group-name';
      tag.textContent = '第 ' + (gi + 1) + ' 组';
      groupEl.appendChild(tag);
    }
    boardEl.appendChild(groupEl);
  });

  $('task').textContent = card.task;
}

// ---------------------------------------------------------------------------
// 拿题
// ---------------------------------------------------------------------------

async function loadLevels() {
  try {
    const r = await fetch(API + '/levels');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const sel = $('level');
    sel.innerHTML = '';
    (data.levels || []).forEach(({ level, count }) => {
      const o = document.createElement('option');
      o.value = String(level);
      o.textContent = `${level} 级（${count} 道）`;
      sel.appendChild(o);
    });
    if (sel.options.length === 0) {
      const o = document.createElement('option');
      o.textContent = '题库是空的';
      sel.appendChild(o);
    }
  } catch (e) {
    const sel = $('level');
    sel.innerHTML = '';
    const o = document.createElement('option');
    o.textContent = '读不到题库';
    sel.appendChild(o);
    toast('读不到题库：' + e.message + '（后端起了吗？）', 5000);
    return false;
  }
  return true;
}

/** 把等级下拉框拨到这道题那一档（题库里没有那一档就不动它） */
function syncLevel(level) {
  const sel = $('level');
  const value = String(level);
  if (Array.from(sel.options).some((o) => o.value === value)) sel.value = value;
}

/** 拿到一道题之后：重置"揭晓/自评"，画题面。 */
function showCard(p, opts = {}) {
  state.card = p;
  state.revealed = false;
  state.solved = false;
  syncLevel(p.level);
  $('result').hidden = true;
  $('show').disabled = false;
  $('puzzle-title').textContent = p.title || '';
  $('puzzle-title').hidden = !p.title;
  $('story').textContent = p.story || '';
  $('story').hidden = !p.story;
  render();
  updateNext();
  setStatus(`等级 ${p.level} · ${p.kind} · id ${p.id}`);
  $('board').scrollIntoView({ block: 'nearest' });
  if (!(opts && opts.silent)) playTick(0.8);
}

function updateNext() {
  // 换一题 = 同一档里再抽一道；那一档只有一道时按钮没意义
  const p = state.card;
  $('next').disabled = !!(p && typeof p.pool_size === 'number' && p.pool_size <= 1);
}

async function fetchCard(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail = '';
    try {
      const data = await r.json();
      detail = (data && data.detail) || '';
    } catch (e) { /* 不是 JSON 就算了 */ }
    throw new Error(`HTTP ${r.status}${detail ? '：' + detail : ''}`);
  }
  return r.json();
}

/** 抽某一档的题（demo 每档一道，抽到的就是它）。 */
async function loadLevel(level, opts = {}) {
  if (!level) return false;
  $('show').disabled = true;
  try {
    const ex = (opts && opts.exclude) ? `&exclude=${encodeURIComponent(opts.exclude)}` : '';
    const p = await fetchCard(`${API}/random?level=${encodeURIComponent(level)}${ex}`);
    showCard(p, opts);
    return true;
  } catch (e) {
    toast('拿题失败：' + e.message, 4000);
    $('show').disabled = false;
    return false;
  }
}

/** 按 id 取题（历史页「打开」跳过来时用）。 */
async function loadById(id, opts = {}) {
  if (!id) return false;
  $('show').disabled = true;
  try {
    const p = await fetchCard(`${API}/puzzles/${encodeURIComponent(id)}`);
    showCard(p, opts);
    return true;
  } catch (e) {
    toast('那道题打不开：' + e.message + '，换成随机一道', 4000);
    $('show').disabled = false;
    return false;
  }
}

// ---------------------------------------------------------------------------
// 完成 → 揭晓 → 自评
// ---------------------------------------------------------------------------

function reveal() {
  const card = state.card;
  if (!card || state.revealed) return;
  state.revealed = true;
  render();

  $('answer').textContent = card.answer_text ? '标准答案：' + card.answer_text : '';
  $('answer').hidden = !card.answer_text;
  const fixEl = $('rule');
  fixEl.textContent = (card.fix_text ? '错的那颗：' + card.fix_text + '。' : '') + card.rule;
  $('result').hidden = false;
  $('show').disabled = true;
  setStatus('对着答案看看：摆对了吗？');
  playTick(0.7);
  readWhole();
  $('result').scrollIntoView({ block: 'nearest' });
}

function judge(ok) {
  if (!state.revealed) return;
  if (ok) {
    state.solved = true;
    playDing();
    speak('对了');
    setStatus('通关！这题摆对了 —— 点「下一题」继续。');
    toast('通关！', 2400);
    $('yes').disabled = true;
  } else {
    playThud();
    speak('没关系，再来一次');
    state.revealed = false;
    state.solved = false;
    $('result').hidden = true;
    $('yes').disabled = false;
    $('show').disabled = false;
    render();
    setStatus('再来一次：把答案挡住，重新摆一遍。');
  }
}

function nextLevel() {
  const cur = state.card ? Number(state.card.level) : 0;
  const sel = $('level');
  const levels = Array.from(sel.options).map((o) => Number(o.value))
      .filter((n) => Number.isFinite(n) && n > 0);
  const nxt = levels.find((n) => n > cur);
  if (!nxt) {
    playThud();
    toast('已经到最后一题了');
    return;
  }
  loadLevel(nxt);
}

/** 换一题：同一档里再抽一道（把现在这道剔掉，别原地打转）。 */
function anotherCard() {
  if (!state.card) return;
  loadLevel(state.card.level, { exclude: state.card.id });
}

function prevLevel() {
  const cur = state.card ? Number(state.card.level) : 0;
  const sel = $('level');
  const levels = Array.from(sel.options).map((o) => Number(o.value))
      .filter((n) => Number.isFinite(n) && n > 0).sort((a, b) => a - b);
  const nxt = levels.filter((n) => n < cur).pop();
  if (!nxt) {
    playThud();
    toast('已经是第一题了');
    return;
  }
  loadLevel(nxt);
}

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

$('show').addEventListener('click', reveal);
$('next').addEventListener('click', anotherCard);
$('yes').addEventListener('click', () => judge(true));
$('no').addEventListener('click', () => judge(false));
$('read').addEventListener('click', readWhole);
$('level').addEventListener('change', (e) => { loadLevel(e.target.value); e.target.blur(); });

// 键盘：空格 读整题 / 回车 完成 / ← → 上一题下一题 / y n 自评
window.addEventListener('keydown', (e) => {
  if (!state.card) return;
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;   // 别抢表单的键

  if (e.key === ' ' || e.code === 'Space') { e.preventDefault(); readWhole(); return; }
  if (e.key === 'Enter') { e.preventDefault(); reveal(); return; }
  if (e.key === 'ArrowLeft') { e.preventDefault(); prevLevel(); return; }
  if (e.key === 'ArrowRight') { e.preventDefault(); nextLevel(); return; }
  if (state.revealed && (e.key === 'y' || e.key === 'Y')) { e.preventDefault(); judge(true); return; }
  if (state.revealed && (e.key === 'n' || e.key === 'N')) { e.preventDefault(); judge(false); return; }
});

// 打开页面：先读等级；历史页点名了 id 就先开那道题，否则从最低一档抽一道
loadLevels().then(async (ok) => {
  if (!ok) return;
  if (WANT_ID && await loadById(WANT_ID, { silent: true })) return;
  const first = $('level').options[0];
  if (first && first.value) loadLevel(first.value, { silent: true });
});
