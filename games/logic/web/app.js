/* BeadMatch · 推理 前端：拿题 → 显示题目 → 排珠子 → 自动检查（声音 + 朗读）
 *
 * 数据约定（跟后端一致）：
 *   participants / answer = ["R","B",...]，颜色首字母
 *   clues   = [{ text: "🔴 红色在第一个。", notation: "R@1" }]
 *   check   = POST /api/logic/check {id, order} → { ok, broken: [...] }
 */

window.__logic_loaded = true;   // index.html 靠它判断脚本有没有加载成功

// 颜色：字母 → 中文名 / 颜色值（跟后端 COLOR_LETTERS = "YGRPBO" 对应）
const COLORS = {
  Y: { name: '黄', css: '#f2c231' },
  G: { name: '绿', css: '#4caf50' },
  R: { name: '红', css: '#e5484d' },
  P: { name: '紫', css: '#9b59d0' },
  B: { name: '蓝', css: '#3b82f6' },
  O: { name: '橙', css: '#f2811d' },
};

const $ = (id) => document.getElementById(id);
// 接口基址：单独跑时是 /api/logic，广场里由广场往页面里注入 window.API_BASE
const API = window.API_BASE || '/api/logic';

// 历史页「打开」带过来的题目 id（/games/logic/?p=<id>，`?puzzle=` 也认）：
// 有就开**那一道题**，没有就照旧随机抽一道。认不出来会退回随机，不至于开个空白页。
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const poolEl = $('pool');
const cluesEl = $('clues');
const slotsEl = $('slots');

const state = {
  puzzle: null,      // 当前这道题（后端返回的原样）
  pick: [],          // 从左到右排好的珠子（null = 空位）
  selected: null,    // 当前选中的线索（键盘操作靠它）
  checked: 0,        // 0 = 还没检查；1 = 对；-1 = 错
};

// 朗读参数：一条一条读，条目之间静音这么久（毫秒）
const SPEECH_LINE_GAP = 300;
const SPEECH_RATE = 1.0;      // 1.0 = 系统默认，越大越快

// ---------------------------------------------------------------------------
// 声音（Web Audio 合成，不用素材文件）
// ---------------------------------------------------------------------------

let audio = null;
function audioCtx() {
  if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio.state === 'suspended') audio.resume();
  return audio;
}

/** 放珠子："嗒" */
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

/** 排对了："叮" */
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

/** 到头了 / 排错了："咚" —— 比放珠声更低更闷 */
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

/** 朗读用的文本：去掉 emoji（读出来是噪音），留下汉字和标点 */
function speechText(text) {
  return (text || '')
    .replace(/[^\u4e00-\u9fff，。、？！：；""''（）,.?!0-9A-Za-z\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function pickVoice() {
  try {
    const voices = window.speechSynthesis.getVoices() || [];
    return voices.find((v) => /^zh/i.test(v.lang)) || null;
  } catch (e) {
    return null;
  }
}

/** 一条一条读（Web Speech 不支持 SSML，停顿只能靠"分多次 + 定时"） */
function speakLines(lines) {
  const texts = lines.map(speechText).filter(Boolean);
  if (!texts.length) return;
  if (!('speechSynthesis' in window)) {
    console.warn('[logic] 这个浏览器不支持 speechSynthesis，没法朗读');
    return;
  }
  try {
    window.speechSynthesis.cancel();
    const voice = pickVoice();
    if (!voice) console.warn('[logic] 没找到中文语音，用系统默认语音读');
    let i = 0;
    const next = () => {
      if (i >= texts.length) return;
      const text = texts[i];
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'zh-CN';
      u.rate = SPEECH_RATE;
      if (voice) u.voice = voice;
      i += 1;
      u.onend = () => { if (i < texts.length) setTimeout(next, SPEECH_LINE_GAP); };
      u.onerror = (e) => console.warn('[logic] 朗读出错：', e.error || e);
      window.speechSynthesis.speak(u);
    };
    next();
  } catch (e) {
    console.warn('[logic] 朗读失败：', e);
  }
}

function speak(text) { speakLines([text]); }

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

function beadEl(letter, { drop = false, clickable = true } = {}) {
  const info = COLORS[letter] || { name: letter, css: '#888' };
  const el = document.createElement('button');
  el.className = 'bead' + (drop ? ' drop' : '');
  el.type = 'button';
  el.dataset.letter = letter;
  el.style.background = info.css;
  el.title = info.name + '色';
  if (!clickable) el.disabled = true;
  return el;
}

function renderPool() {
  poolEl.innerHTML = '';
  (state.puzzle.participants || []).forEach((letter) => {
    const el = beadEl(letter);
    const info = COLORS[letter] || { name: letter };
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = info.name;
    el.appendChild(tag);
    if (leftInPool(letter) <= 0) el.classList.add('used');
    el.addEventListener('click', () => { if (!swallowDragClick()) place(letter); });
    makeDraggable(el, { kind: 'pool', letter });
    poolEl.appendChild(el);
  });
}

/** 这种颜色还能放几颗（同色有两颗时，放一颗不算用完） */
function leftInPool(letter) {
  const need = (state.puzzle.participants || []).filter((x) => x === letter).length;
  const used = state.pick.filter((x) => x === letter).length;
  return need - used;
}

function renderClues() {
  cluesEl.innerHTML = '';
  (state.puzzle.clues || []).forEach((clue, i) => {
    const li = document.createElement('li');
    li.dataset.index = String(i);
    li.dataset.notations = (clue.notations || []).join(' ');
    li.textContent = clue.text;
    li.addEventListener('click', () => selectClue(i));
    cluesEl.appendChild(li);
  });
}

function renderSlots(animate = true) {
  slotsEl.innerHTML = '';
  slotsEl.classList.remove('ok', 'bad');
  state.pick.forEach((letter, i) => {
    const box = document.createElement('div');
    box.className = 'slotbox' + (letter ? ' filled' : '');
    box.dataset.index = String(i);
    if (letter) {
      const el = beadEl(letter, { drop: animate });
      el.addEventListener('click', () => { if (!swallowDragClick()) takeBack(i); });
      makeDraggable(el, { kind: 'slot', index: i });
      box.appendChild(el);
    }
    const num = document.createElement('span');
    num.className = 'num';
    num.textContent = String(i + 1);
    box.appendChild(num);
    slotsEl.appendChild(box);
  });
}

function renderAll(animate = true) {
  renderPool();
  renderClues();
  renderSlots(animate);
}

let toastTimer = null;
function toast(text, ms = 2000) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

function setStatus(text) { $('status').textContent = text; }

// ---------------------------------------------------------------------------
// 排珠子
// ---------------------------------------------------------------------------

/** 把一颗珠子放进最左边的空位 */
function place(letter) {
  if (!state.puzzle || leftInPool(letter) <= 0) return;
  const at = state.pick.indexOf(null);
  if (at < 0) return;
  state.pick[at] = letter;
  clearMarks();
  renderAll(true);
  playTick();
  speak(COLORS[letter] ? COLORS[letter].name + '色' : letter);
  maybeCheck();
}

/** 把某个位置上的珠子拿回来 */
function takeBack(index) {
  if (index < 0 || index >= state.pick.length || !state.pick[index]) return;
  state.pick[index] = null;
  clearMarks();
  renderAll(false);
  playThud();
  setStatus('拿回来了。');
}

function clearMarks() {
  state.checked = 0;
  cluesEl.querySelectorAll('li').forEach((li) => li.classList.remove('broken', 'done'));
  slotsEl.classList.remove('ok', 'bad');
}

// ---------------------------------------------------------------------------
// 拖拽：按住一颗珠子就能拖 —— 从参与者拖进任意一个槽 / 槽与槽互拖换位 / 拖回参与者就拿回来
//
// 用 Pointer Events（不是 HTML5 的 dragstart）：手指、鼠标、笔走同一条路，平板上也能拖。
// **点击那套照旧**：手指没挪过 `DRAG_SLOP` 就当"点了一下"，后面那个 click 照常走
// place() / takeBack()；真拖过之后紧跟着的那一下 click 要吞掉，不然会多放一颗。
// ---------------------------------------------------------------------------

const DRAG_SLOP = 6;          // 挪过这么多像素才算"拖"（手指抖一下不算）

const drag = {
  from: null,                 // 从哪儿拎起来的：null / {kind:'pool', letter} / {kind:'slot', index}
  ghost: null,                // 跟着手走的那颗（克隆一份，原件留在原地淡着）
  source: null,               // 原件（松手后把淡化去掉）
  target: null,               // 当前高亮的落点
  moved: false,               // 这一把是"拖"还是"点"
  swallowClick: false,        // 拖完那一下 click 要吞掉
  startX: 0,
  startY: 0,
  grabX: 0,                   // 抓在珠子上的哪个位置（免得影子跳一下）
  grabY: 0,
};

/** 拖完跟着来的那次 click 要吞掉吗（吞一次就复位，免得多吃一次真点击） */
function swallowDragClick() {
  if (!drag.swallowClick) return false;
  drag.swallowClick = false;
  return true;
}

/** 给一颗珠子装上"能拖"的手：`from` 说明它是从哪儿拎起来的 */
function makeDraggable(el, from) {
  el.addEventListener('pointerdown', (e) => {
    if (!state.puzzle || e.button !== 0) return;        // 只认左键 / 单指
    drag.from = from;
    drag.moved = false;
    drag.swallowClick = false;                          // 新手势开始，清掉上一把的残留
    drag.startX = e.clientX;
    drag.startY = e.clientY;
    try { el.setPointerCapture(e.pointerId); } catch (err) { /* 合成事件没有真手指：忽略 */ }
  });

  el.addEventListener('pointermove', (e) => {
    if (!drag.from) return;
    if (!drag.moved) {
      if (Math.abs(e.clientX - drag.startX) + Math.abs(e.clientY - drag.startY) < DRAG_SLOP) return;
      drag.moved = true;
      startGhost(el, e);
    }
    moveGhost(e.clientX, e.clientY);
    showDropSpot(e.clientX, e.clientY);
  });

  const finish = (e) => {
    if (!drag.from) return;
    const wasDrag = drag.moved;
    if (wasDrag) dropAt(e.clientX, e.clientY);
    endGhost();
    showDropSpot(null, null);
    drag.from = null;
    drag.moved = false;
    drag.swallowClick = wasDrag;                        // 拖过的那一下别再当点击
  };
  el.addEventListener('pointerup', finish);
  el.addEventListener('pointercancel', finish);
}

/** 起一个跟手的"影子"，原件留在原地淡掉 */
function startGhost(el, e) {
  const rect = el.getBoundingClientRect();
  const ghost = el.cloneNode(true);
  ghost.classList.add('ghost');
  ghost.style.width = `${rect.width}px`;
  ghost.style.height = `${rect.height}px`;
  document.body.appendChild(ghost);
  drag.ghost = ghost;
  drag.source = el;
  drag.grabX = e.clientX - rect.left;
  drag.grabY = e.clientY - rect.top;
  el.classList.add('dragging');
  moveGhost(e.clientX, e.clientY);
}

function moveGhost(x, y) {
  if (!drag.ghost) return;
  drag.ghost.style.left = `${x - drag.grabX}px`;
  drag.ghost.style.top = `${y - drag.grabY}px`;
}

function endGhost() {
  if (drag.ghost) drag.ghost.remove();
  if (drag.source) drag.source.classList.remove('dragging');
  drag.ghost = null;
  drag.source = null;
}

/** 手指底下是什么落点：第几个槽 / 参与者 / 别的地方（返回 null） */
function dropSpot(x, y) {
  if (x === null || y === null) return null;
  const el = document.elementFromPoint(x, y);
  if (!el || !el.closest) return null;
  const box = el.closest('.slotbox');
  if (box) return { kind: 'slot', el: box, index: Number(box.dataset.index) };
  const pool = el.closest('#pool');
  if (pool) return { kind: 'pool', el: pool };
  return null;
}

/** 拖的时候把落点点亮（换了落点就换高亮） */
function showDropSpot(x, y) {
  const spot = dropSpot(x, y);
  if (drag.target && (!spot || drag.target.el !== spot.el)) {
    drag.target.el.classList.remove('drop-target');
    drag.target = null;
  }
  if (spot && !drag.target) {
    spot.el.classList.add('drop-target');
    drag.target = spot;
  }
}

/** 松手：落到槽里就放 / 换位，落到参与者就拿回来，落到别处（线索、页头……）当没拖 */
function dropAt(x, y) {
  const spot = dropSpot(x, y);
  const from = drag.from;
  if (!spot || !from) return;
  if (spot.kind === 'pool') {
    if (from.kind === 'slot') takeBack(from.index);
    return;
  }
  if (from.kind === 'pool') placeAt(from.letter, spot.index);
  else moveSlot(from.index, spot.index);
}

/** 把一颗（从参与者拖来的）珠子放到第 index 个槽：那格原来有珠子的话，它退回参与者 */
function placeAt(letter, index) {
  if (!state.puzzle || index < 0 || index >= state.pick.length) return;
  if (state.pick[index] === letter) return;             // 拖回原位：什么都不做
  if (leftInPool(letter) <= 0) return;                  // 这种颜色已经摆满了
  state.pick[index] = letter;
  clearMarks();
  renderAll(true);
  playTick();
  speak(COLORS[letter] ? COLORS[letter].name + '色' : letter);
  maybeCheck();
}

/** 槽与槽：把 from 那颗挪到 to；to 里有珠子就换位（空位就是单纯搬过去） */
function moveSlot(from, to) {
  if (from === to) return;
  if (from < 0 || to < 0 || from >= state.pick.length || to >= state.pick.length) return;
  const tmp = state.pick[to];
  state.pick[to] = state.pick[from];
  state.pick[from] = tmp;
  clearMarks();
  renderAll(true);
  playTick();
  maybeCheck();
}

/** 摆满了就自动检查 */
function maybeCheck() {
  if (state.pick.includes(null)) {
    setStatus(`还差 ${state.pick.filter((x) => !x).length} 颗。`);
    return;
  }
  check();
}

async function check({ silent = false } = {}) {
  if (!state.puzzle || state.pick.includes(null)) return;
  try {
    const r = await fetch(API + '/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: state.puzzle.id, order: state.pick }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const broken = new Set((data.broken || []).map((c) => c.notation));

    cluesEl.querySelectorAll('li').forEach((li) => {
      const mine = (li.dataset.notations || '').split(' ').filter(Boolean);
      li.classList.remove('broken', 'done');
      if (data.ok) li.classList.add('done');
      else if (mine.some((n) => broken.has(n))) li.classList.add('broken');
    });
    slotsEl.classList.toggle('ok', !!data.ok);
    slotsEl.classList.toggle('bad', !data.ok);
    state.checked = data.ok ? 1 : -1;

    if (data.ok) {
      playDing();
      toast('排对了！');
      if (!silent) speak('排对了');
      setStatus('✔ 全对。');
    } else {
      playThud();
      toast(`还差一点：有 ${(data.broken || []).length} 条线索没满足（标红的那些）`, 2600);
      if (!silent) speak('还差一点');
      setStatus(`✘ 有 ${(data.broken || []).length} 条线索没满足。`);
    }
  } catch (e) {
    toast('检查失败：' + e.message);
  }
}

/** 看答案：直接摆成答案的样子 */
function showAnswer() {
  if (!state.puzzle) return;
  state.pick = (state.puzzle.answer || []).slice();
  clearMarks();
  renderAll(true);
  check({ silent: true });
  toast('这是答案：' + state.pick.map((l) => (COLORS[l] || {}).name || l).join(' → '), 3200);
}

// ---------------------------------------------------------------------------
// 线索的选中与朗读（键盘操作靠它）
// ---------------------------------------------------------------------------

function selectClue(index, read = true) {
  const items = cluesEl.querySelectorAll('li');
  if (!items.length) return;
  const i = Math.max(0, Math.min(items.length - 1, index));
  state.selected = i;
  items.forEach((li, k) => li.classList.toggle('selected', k === i));
  const li = items[i];
  li.classList.add('reading');
  setTimeout(() => li.classList.remove('reading'), 320);
  toast(`第 ${i + 1} 条：${li.textContent}`);
  if (read) speak(li.textContent);
  playTick(1.2);
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
  }
}

/** 拿一道新题。``opts.silent`` 用在**刚打开页面**那一次 —— 点链接跳过来不该"嗒"一声，
 *  只有自己按「换一题」时才响。
 *
 *  ``opts.id`` 给了就**按 id 取那一道题**（历史页「打开」跳过来时用），否则按当前等级随机抽。
 *  拿成了返回 true、没拿成返回 false —— 调用方靠它决定要不要再兜一道随机题。 */
async function newPuzzle(opts = {}) {
  const id = ((opts && opts.id) || '').trim();
  const level = $('level').value;
  if (!level && !id) return false;
  $('new').disabled = true;
  try {
    const r = await fetch(id ? `${API}/puzzles/${encodeURIComponent(id)}`
                             : `${API}/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const p = await r.json();
    if (id) syncLevel(p.level);   // 下拉框跟着这道题走，免得"题是 20 级的、框里写着 1 级"
    state.puzzle = p;
    // 告诉广场"现在是哪一道"（收藏星标用；单独跑时没有这个函数）
    if (window.plazaSetPuzzle) window.plazaSetPuzzle({ id: p.id, level: p.level });
    state.pick = new Array((p.participants || []).length).fill(null);
    state.selected = null;
    state.checked = 0;
    renderAll(true);

    // 题目的名字：有就显示，没有就把这一行藏起来
    const name = (p.title || '').trim();
    const titleEl = $('puzzle-title');
    titleEl.textContent = name;
    titleEl.hidden = !name;

    setStatus(`${name ? name + ' · ' : ''}等级 ${p.level} · ${(p.clues || []).length} 条线索 · id ${p.id}`);
    if (!(opts && opts.silent)) playTick(0.8);
    return true;
  } catch (e) {
    toast((id ? '那道题打不开：' : '拿题失败：') + e.message);
    return false;
  } finally {
    $('new').disabled = false;
  }
}

/** 把等级下拉框拨到这道题那一档（题库里没有这一档就不动它） */
function syncLevel(level) {
  const sel = $('level');
  const value = String(level);
  if (Array.from(sel.options).some((o) => o.value === value)) sel.value = value;
}

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

$('new').addEventListener('click', newPuzzle);
$('answer').addEventListener('click', showAnswer);
$('level').addEventListener('change', (e) => { newPuzzle(); e.target.blur(); });

// 键盘：↑ ↓（或 ← →）换线索（到头"咚"一声），空格重读选中的线索（没选就读整道题）
window.addEventListener('keydown', (e) => {
  if (!state.puzzle) return;
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;   // 别抢表单的键

  if (e.key === ' ' || e.code === 'Space') {
    e.preventDefault();
    if (state.selected === null) {
      const name = (state.puzzle.title || '').trim();
      speakLines([
        ...(name ? [name] : []),
        ...(state.puzzle.clues || []).map((c) => c.text),
      ]);
      toast('读题…');
    } else {
      selectClue(state.selected);
    }
    return;
  }
  // 线索是一列，所以上下最顺手；左右也留着（跟串珠那套一致）
  const up = e.key === 'ArrowUp' || e.key === 'ArrowLeft';
  const down = e.key === 'ArrowDown' || e.key === 'ArrowRight';
  if (up || down) {
    e.preventDefault();
    const step = up ? -1 : 1;
    const count = (state.puzzle.clues || []).length;
    if (state.selected === null) { selectClue(0); return; }
    const next = state.selected + step;
    if (next < 0 || next >= count) { playThud(); return; }   // 上面/下面没有了
    selectClue(next);
  }
});

// 历史页点「打开」过来的（?p=<id>）就先开那一道题；没带 id、或那道题打不开，就随机抽一道
loadLevels().then(async () => {
  if (WANT_ID && await newPuzzle({ id: WANT_ID, silent: true })) return;
  newPuzzle({ silent: true });
});
