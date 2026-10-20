/* 数学实验室前端：拿演示 → 参与者 + 编号题目 → 看答案（性质 + 示例摆法 + 为什么）
 *
 * 数据约定（见 games/mathlab/core/demos.py 的 payload）：
 *   thing / unit             这些珠子假装是什么（小球 / 气球 / 豆腐…）、量词
 *   materials                参与者：[{'bead': 'R', 'count': 7}]
 *   steps                    题目：编号步骤（最后一步就是那句"问"）
 *   answer                    答案 = 一条性质（不是唯一结果）
 *   why                       为什么（一句给孩子听的话）
 *   example                   [{'label': '摆成一排', 'groups': ['RRRRRRR'], 'wide': true}]
 *
 * **屏幕不摆珠子** —— 珠子是实物；这里只出题、说清怎么玩、给答案和示例。
 */

window.__mathlab_loaded = true;

const COLORS = {
  Y: { name: '黄', css: '#f2c231' },
  G: { name: '绿', css: '#4caf50' },
  R: { name: '红', css: '#e5484d' },
  P: { name: '紫', css: '#9b59d0' },
  B: { name: '蓝', css: '#3b82f6' },
  O: { name: '橙', css: '#f2811d' },
};

const $ = (id) => document.getElementById(id);
const API = window.API_BASE || '/api';

// 历史页「打开」带过来的演示 id（/games/mathlab/?p=<id>）
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const state = {
  demo: null,        // 当前这个演示（后端返回的原样）
  levels: [],        // 每档几个演示（下拉框用，跟别的游戏一样只列难度）
  revealed: false,
};

// ---------------------------------------------------------------------------
// 声音 / 朗读
// ---------------------------------------------------------------------------

let audio = null;
function audioCtx() {
  if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio.state === 'suspended') audio.resume();
  return audio;
}

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
  } catch (e) { /* 没声音也不影响 */ }
}

/** 念之前把 markdown 记号之类的去掉（数据里偶尔会写「**」） */
function speechText(text) {
  return (text || '')
    .replace(/\*\*/g, '')
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

function readWhole() {
  const d = state.demo;
  if (!d) return;
  const parts = [d.title, materialsText(d), ...d.steps];
  if (state.revealed) parts.push('答案：' + d.answer, d.why);
  speak(parts.filter(Boolean).join('。'));
}

/** "红色小球，7 颗" 这种说法（念出来 / 画参与者都用得上） */
function materialsText(d) {
  return (d.materials || []).map((row) => {
    const info = COLORS[row.bead] || { name: row.bead };
    return info.name + '色' + (d.thing || '珠子') + '，' + row.count + ' ' + (d.unit || '颗');
  }).join('；');
}

// ---------------------------------------------------------------------------
// 画
// ---------------------------------------------------------------------------

let toastTimer = null;
function toast(text, ms = 2200) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

function bead(letter) {
  const info = COLORS[letter] || { name: letter, css: '#888' };
  const el = document.createElement('span');
  el.className = 'bead';
  el.style.background = info.css;
  el.title = info.name + '色';
  return el;
}

/** 示例摆法：一行一个摆法（label + 几组珠子 + 一共几颗）。 */
function renderExample(rows) {
  const box = $('example');
  box.innerHTML = '';
  (rows || []).forEach((row) => {
    const line = document.createElement('div');
    line.className = 'row';
    const name = document.createElement('span');
    name.className = 'row-label';
    name.textContent = row.label || '';
    line.appendChild(name);

    const groups = document.createElement('span');
    groups.className = 'groups';
    let total = 0;
    (row.groups || []).forEach((g) => {
      const group = document.createElement('span');
      group.className = 'group' + ((row.groups || []).length === 1 ? ' plain' : '')
                    + (row.wide ? ' wide' : '');
      for (const ch of g) {
        group.appendChild(bead(ch));
        total += 1;
      }
      groups.appendChild(group);
    });
    line.appendChild(groups);

    const count = document.createElement('span');
    count.className = 'count';
    // 有 note 就用 note（"红 6 / 蓝 6" 这种比较说明），没有就报"一共 N 颗"
    const unit = (state.demo && state.demo.unit) || '颗';
    count.textContent = row.note || ('一共 ' + total + ' ' + unit);
    line.appendChild(count);
    box.appendChild(line);
  });
}

/** 参与者：一排珠子 + 一句"红色小球 · 7 颗" */
function renderMaterials(d) {
  const box = $('materials');
  box.innerHTML = '';
  (d.materials || []).forEach((row) => {
    const info = COLORS[row.bead] || { name: row.bead };
    const line = document.createElement('div');
    line.className = 'material';
    const beads = document.createElement('span');
    beads.className = 'beads';
    for (let i = 0; i < row.count; i += 1) beads.appendChild(bead(row.bead));
    line.appendChild(beads);
    const cap = document.createElement('span');
    cap.className = 'cap';
    cap.textContent = info.name + '色' + (d.thing || '珠子') + ' · ' + row.count + ' ' + (d.unit || '颗');
    line.appendChild(cap);
    box.appendChild(line);
  });
}

/** 题目：编号步骤 */
function renderSteps(d) {
  const list = $('steps');
  list.innerHTML = '';
  (d.steps || []).forEach((text) => {
    const li = document.createElement('li');
    li.textContent = text;
    list.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// 拿演示
// ---------------------------------------------------------------------------

/** 下拉框：`1 级（4 个演示）` —— 跟别的游戏一个写法 */
function fillSelect() {
  const sel = $('level');
  sel.innerHTML = '';
  state.levels.forEach((row) => {
    const o = document.createElement('option');
    o.value = String(row.level);
    o.textContent = row.level + ' 级（' + row.count + ' 道）';
    sel.appendChild(o);
  });
}

function show(d) {
  state.demo = d;
  // 告诉广场"现在是哪一个"（收藏星标用；单独跑时没有这个函数）
  if (window.plazaSetPuzzle) window.plazaSetPuzzle({ id: d.id, level: d.level });
  state.revealed = false;
  $('level').value = String(d.level);
  $('demo-title').textContent = d.title || '';
  $('demo-title').hidden = !d.title;
  renderMaterials(d);
  renderSteps(d);
  $('result').hidden = true;
  $('show').disabled = false;
  // 这一档只有一个演示时，「换一题」没意义
  $('next').disabled = typeof d.pool_size === 'number' && d.pool_size <= 1;
  playTick(0.8);
}

async function fetchJson(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail = '';
    try {
      const data = await r.json();
      detail = (data && data.detail) || '';
    } catch (e) { /* 不是 JSON 就算了 */ }
    throw new Error('HTTP ' + r.status + (detail ? '：' + detail : ''));
  }
  return r.json();
}

async function loadLevels() {
  try {
    const data = await fetchJson(API + '/levels');
    state.levels = data.levels || [];
    fillSelect();
    return state.levels.length > 0;
  } catch (e) {
    $('level').innerHTML = '<option>读不到题库</option>';
    toast('读不到题库：' + e.message + '（后端起了吗？）', 5000);
    return false;
  }
}

/** 抽某一档里的演示（「换一题」会把现在这个剔掉，别原地打转）。 */
async function loadLevel(level, opts = {}) {
  if (!level) return false;
  try {
    const ex = (opts && opts.exclude) ? '&exclude=' + encodeURIComponent(opts.exclude) : '';
    show(await fetchJson(API + '/random?level=' + encodeURIComponent(level) + ex));
    return true;
  } catch (e) {
    toast('拿不到这个演示：' + e.message, 4000);
    return false;
  }
}

/** 历史页「打开」带 id 过来时用。 */
async function loadById(id) {
  try {
    show(await fetchJson(API + '/puzzles/' + encodeURIComponent(id)));
    return true;
  } catch (e) {
    toast('这个演示打不开：' + e.message + '，换一个', 4000);
    return false;
  }
}

/** 换一题：同一档里再抽一个（现在这个剔掉）。 */
function another() {
  if (!state.demo) return;
  loadLevel(state.demo.level, { exclude: state.demo.id });
}

// ---------------------------------------------------------------------------
// 看答案
// ---------------------------------------------------------------------------

function reveal() {
  const d = state.demo;
  if (!d || state.revealed) return;
  state.revealed = true;
  $('answer').textContent = d.answer || '';
  renderExample(d.example);
  $('why').textContent = d.why || '';
  $('result').hidden = false;
  $('show').disabled = true;
  playTick(0.7);
  $('result').scrollIntoView({ block: 'nearest' });
}

/** ← →：上一档 / 下一档（跟别的游戏一样）。 */
function step(delta) {
  if (!state.demo || !state.levels.length) return;
  const levels = state.levels.map((row) => row.level);
  const at = levels.indexOf(Number(state.demo.level));
  const next = at + delta;
  if (at < 0 || next < 0 || next >= levels.length) {
    playTick(0.6);
    toast(delta > 0 ? '已经是最后一档了' : '已经是第一档了');
    return;
  }
  loadLevel(levels[next]);
}

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

$('show').addEventListener('click', reveal);
$('read').addEventListener('click', readWhole);
$('next').addEventListener('click', another);
$('level').addEventListener('change', (e) => { loadLevel(e.target.value); e.target.blur(); });

window.addEventListener('keydown', (e) => {
  if (!state.demo) return;
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (e.key === ' ' || e.code === 'Space') { e.preventDefault(); readWhole(); return; }
  if (e.key === 'Enter') { e.preventDefault(); reveal(); return; }
  if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); return; }
  if (e.key === 'ArrowRight') { e.preventDefault(); step(1); return; }
});

// 打开页面：先读等级；历史页点名了 id 就先开那个，否则从第一档抽一个
loadLevels().then(async (ok) => {
  if (!ok) return;
  if (WANT_ID && await loadById(WANT_ID)) return;
  loadLevel(state.levels[0].level);
});
