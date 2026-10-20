/* 竞技串珠（BeadSort）前端：拿题 → 画柱子 → 点柱子读颜色 → 演示解法（飞球 + 声音 + 朗读）
 *
 * 数据约定（跟后端一致）：
 *   matrix[柱子][位置]，位置 0 = 最顶端那一格，0 表示空位
 *   solution = "3-7 1-2"（柱子编号从 1 起）
 */

window.__beadsort_loaded = true;   // index.html 靠它判断脚本有没有加载成功

// 颜色：编号 → 字母 / 中文名 / 颜色值（跟后端 COLOR_LETTERS = "YGRPBO" 对应）
const COLORS = {
  1: { letter: 'Y', name: '黄', css: '#f2c231' },
  2: { letter: 'G', name: '绿', css: '#4caf50' },
  3: { letter: 'R', name: '红', css: '#e5484d' },
  4: { letter: 'P', name: '紫', css: '#9b59d0' },
  5: { letter: 'B', name: '蓝', css: '#3b82f6' },
  6: { letter: 'O', name: '橙', css: '#f2811d' },
};

const $ = (id) => document.getElementById(id);
// 接口基址：单独跑时是 /api，广场里由广场往页面里注入 window.API_BASE
const API = window.API_BASE || '/api';

// 历史页「打开」带过来的题目 id（/games/beadsort/?p=<id>，`?puzzle=` 也认）：
// 有就开**那一道题**，没有就照旧随机抽一道。认不出来会退回随机，不至于开个空白页。
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const board = $('board');

const state = {
  matrix: null,          // 当前摆在场上的局面
  base: null,            // 这道题的初始局面（回放的起点）
  meta: null,
  cursor: 0,             // 回放到第几步：0 = 题目初始局面
  playing: false,        // 演示中
  busy: false,           // 这颗球正在飞
  timer: null,
  run: 0,                // 自动播放的批次号：停下来就作废，防止旧的一轮还在跑
  selected: null,        // 当前选中的柱子（键盘操作靠它）
  half: null,            // 最近读到的那一段：'low'（下五）/ 'high'（上五）—— 空格重读用
};

// ---------------------------------------------------------------------------
// 小工具：跟后端 free_solver 里那套规则一一对应
// ---------------------------------------------------------------------------

const topIndex = (tube) => tube.findIndex((v) => v !== 0);      // 顶珠下标；空柱 -1
const hasRoom = (tube) => tube[0] === 0;                        // 顶端还有空位
const ballCount = (tube) => tube.filter((v) => v !== 0).length;

/** 走一步：源柱顶珠 → 目标柱的空位（返回新矩阵，不改原矩阵） */
function applyMove(matrix, from, to) {
  const next = matrix.map((t) => t.slice());
  const k = topIndex(next[from]);
  if (k < 0 || !hasRoom(next[to])) throw new Error('这一步不合法');
  const ball = next[from][k];
  next[from][k] = 0;
  let e = 0;
  while (e < next[to].length && next[to][e] === 0) e += 1;
  next[to][e - 1] = ball;
  return next;
}

/** "3-7 1-2" → [[2,6],[0,1]] */
function parseMoves(text) {
  return (text || '').trim().split(/\s+/).filter(Boolean).map((tok) => {
    const [a, b] = tok.split('-').map(Number);
    return [a - 1, b - 1];
  });
}

// ---------------------------------------------------------------------------
// 声音（Web Audio 合成，不用素材文件）
// ---------------------------------------------------------------------------

let audio = null;
function audioCtx() {
  if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio.state === 'suspended') audio.resume();
  return audio;
}

/** 落珠："嗒" */
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

/** 解开一根柱子："叮" */
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

/** 到头了："咚" —— 比落珠声更低更闷，一听就知道是"没有了" */
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

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  } catch (e) { /* 不支持就算了 */ }
}

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

function render(animateIn = true) {
  const m = state.matrix;
  const capacity = m[0].length;
  board.innerHTML = '';
  m.forEach((tube, t) => {
    const el = document.createElement('div');
    el.className = 'tube';
    el.dataset.tube = String(t);
    if (t === state.selected) el.classList.add('selected');
    el.addEventListener('click', () => readTube(t, 'low'));   // 点柱子 = 听「下五」
    for (let p = 0; p < capacity; p++) {
      const slot = document.createElement('div');
      slot.className = 'slot';
      const v = tube[p];
      if (v) {
        const ball = document.createElement('div');
        ball.className = 'ball' + (animateIn ? ' drop' : '');
        ball.style.background = COLORS[v].css;
        // 从下往上依次落下：最底下的那颗先到
        ball.style.setProperty('--i', String(capacity - 1 - p));
        slot.appendChild(ball);
      }
      el.appendChild(slot);
    }
    board.appendChild(el);
  });
}

/** 一根柱子的珠子，按「由下到上」排成颜色名（内部是"顶在前"，所以先反过来）。 */
function namesBottomUp(tube) {
  return tube.filter((v) => v !== 0).reverse().map((v) => COLORS[v].name);
}

/** 中文数字（1~10 够用了 —— 柱容量就是 10；再大就退回阿拉伯数字） */
const CN_NUM = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十'];
const cn = (n) => CN_NUM[n] || String(n);

/** 一根柱子按「由下到上」分成两段：**下五**（最下面 5 颗）+ **上面剩下的那些**。
 *
 *  上面那段的颗数是**动态的**：10 颗 = 下五 + 上五、9 颗 = 下五 + 上四、7 颗 = 下五 + 上二
 *  —— 一开始写死"最上面 5 颗"，9 颗时第 5 颗会被念两遍（2026-10-16 反馈修掉）。
 *  不够 5 颗就只有"下"这一段（有几颗就叫下几）；空柱两段都是空的。
 *  返回 `{ label, names }`：label 里的数字是**这一段实际有几颗**。
 */
function halfOf(tube, half) {
  const names = namesBottomUp(tube);
  const low = names.slice(0, 5);
  const high = names.slice(5);
  if (!low.length) return { label: '空柱子', names: [] };
  if (half === 'high' && high.length) return { label: '上' + cn(high.length), names: high };
  return { label: '下' + cn(low.length), names: low };
}

/** 选中一根柱子（只高亮 + 记下它是谁）—— 说话交给 readHalf，别在这儿出声。 */
function selectTube(t) {
  state.selected = t;
  board.querySelectorAll('.tube').forEach((el) => {
    el.classList.toggle('selected', Number(el.dataset.tube) === t);
  });
}

/** 读第 t 根柱子的一段：报「第 X 根 + 下五/上四 + 颜色（由下到上）」，把它点亮。
 *  语音里**不报「第几根」**（2026-10-16 反馈：听着啰嗦），屏幕上那行还写着。 */
function readHalf(t, half) {
  const { label, names } = halfOf(state.matrix[t], half);
  const shown = names.join('、');
  state.half = half;
  const el = board.querySelector(`.tube[data-tube="${t}"]`);
  if (el) {
    el.classList.add('reading');
    setTimeout(() => el.classList.remove('reading'), 320);
  }

  if (!shown) {
    toast(`第 ${t + 1} 根：空柱子`);
    speak('空柱子');
  } else {
    // 话就两节：下五/上四 / 颜色 —— 不报"第几根"，也不念"最上面 5 颗"这种长句子
    toast(`第 ${t + 1} 根 ${label}（由下到上）：${shown}`);
    speak(`${label}，${shown}`);
  }
  playTick(1.2);
}

/** 读第 t 根柱子的某一段：`half` = 'low'（下五）/ 'high'（上面那段）。
 *  没指定哪根就用当前选中的，一根都没选过就从第一根开始。 */
function readTube(t, half) {
  if (t === null || t === undefined) t = state.selected;
  if (t === null || t === undefined) t = 0;
  selectTube(t);
  readHalf(t, half);
}

let toastTimer = null;
function toast(text, ms = 1800) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

function setStatus(text) { $('status').textContent = text; }

// ---------------------------------------------------------------------------
// 飞球（FLIP：让一颗球从源柱顶飞到目标柱的空位）
// ---------------------------------------------------------------------------

function animateBall(from, to) {
  const src = board.querySelector(`.tube[data-tube="${from}"]`);
  const dst = board.querySelector(`.tube[data-tube="${to}"]`);
  const ballEl = src && src.querySelector('.ball');       // 源柱顶上的那颗（DOM 从上到下）
  if (!ballEl || !dst) return Promise.resolve();

  const capacity = state.matrix[0].length;
  const landing = dst.querySelectorAll('.slot')[capacity - 1 - ballCount(state.matrix[to])];
  const a = ballEl.getBoundingClientRect();
  const b = landing.getBoundingClientRect();

  const ghost = ballEl.cloneNode(true);
  ghost.classList.remove('drop');
  ghost.classList.add('ghost');
  ghost.style.position = 'fixed';
  ghost.style.left = `${a.left}px`;
  ghost.style.top = `${a.top}px`;
  ghost.style.width = `${a.width}px`;
  ghost.style.height = `${a.height}px`;
  document.body.appendChild(ghost);
  ballEl.style.visibility = 'hidden';

  const dx = b.left - a.left;
  const dy = b.top - a.top;
  const anim = ghost.animate([
    { transform: 'translate(0, 0) scale(1)' },
    { transform: `translate(${dx * 0.6}px, ${dy * 0.6 - 26}px) scale(1.1)`, offset: 0.55 },
    { transform: `translate(${dx}px, ${dy}px) scale(1)` },
  ], { duration: 330, easing: 'cubic-bezier(.35, 0, .25, 1)' });

  return anim.finished.then(() => {
    ghost.remove();
    ballEl.style.visibility = '';
  }).catch(() => { ghost.remove(); ballEl.style.visibility = ''; });
}

// ---------------------------------------------------------------------------
// 回放：局面 = 从题目开局重放 moves[0..cursor)
//
// 上一步不去"撤销"，而是重放到 cursor-1 —— 走多少步都只有这一个来源，
// 所以前进、后退、回到题目、自动播放永远不会互相错位。
// ---------------------------------------------------------------------------

function movesOf() {
  return state.meta ? parseMoves(state.meta.solution) : [];
}

/** 重放到第 n 步的局面（n = 0 就是题目初始局面） */
function matrixAt(n) {
  const moves = movesOf();
  let m = state.base.map((t) => t.slice());
  for (let i = 0; i < n; i++) m = applyMove(m, moves[i][0], moves[i][1]);
  return m;
}

/** 把画面切到第 n 步（不动画，动画由调用方控制） */
function showAt(n) {
  state.cursor = n;
  state.matrix = matrixAt(n);
  render(false);
  updateTransport();
}

function updateTransport() {
  const total = movesOf().length;
  const c = state.cursor;
  $('counter').textContent = `第 ${c} / ${total} 步`;
  $('reset').disabled = c === 0;
  $('prev').disabled = c === 0;
  $('next').disabled = c >= total;
  $('demo').textContent = state.playing ? '暂停' : '演示解法';
  $('demo').disabled = !state.playing && c >= total;
}

/** 等正在飞的这颗球落地（动画 330ms），免得点击被吞掉 */
async function waitIdle() {
  while (state.busy) await new Promise((r) => setTimeout(r, 30));
}

/** 可被打断的等待：stopPlay 会立刻叫醒它，别让播放循环卡在睡眠里 */
let sleepWake = null;
function pause(ms) {
  return new Promise((resolve) => {
    sleepWake = () => { sleepWake = null; resolve(); };
    state.timer = setTimeout(() => { if (sleepWake) sleepWake(); }, ms);
  });
}

/** 走一步：飞球 + 落珠声。调用前请自行置 state.busy。 */
async function stepForward() {
  const moves = movesOf();
  if (state.cursor >= moves.length) return false;
  const [from, to] = moves[state.cursor];
  state.matrix = matrixAt(state.cursor);
  render(false);
  await animateBall(from, to);
  state.cursor += 1;
  state.matrix = matrixAt(state.cursor);
  render(false);
  playTick();
  updateTransport();
  return true;
}

/** 退一步：把刚搬过去的那颗球飞回来 */
async function stepBack() {
  const moves = movesOf();
  if (state.cursor <= 0) return false;
  const [from, to] = moves[state.cursor - 1];
  state.matrix = matrixAt(state.cursor);
  render(false);
  await animateBall(to, from);
  state.cursor -= 1;
  state.matrix = matrixAt(state.cursor);
  render(false);
  playTick(0.8);
  updateTransport();
  return true;
}

function stopPlay() {
  state.playing = false;
  state.run += 1;                       // 还在跑的那一轮看到批次号变了就退出
  if (state.timer) { clearTimeout(state.timer); state.timer = null; }
  if (sleepWake) sleepWake();           // 叫醒正卡在 pause() 里的那一轮
  updateTransport();
}

/** 手动接管：先停下自动播放，再走这一步 */
async function doStep(dir) {
  if (!state.meta) return;
  stopPlay();
  await waitIdle();
  state.busy = true;
  try {
    if (dir > 0) await stepForward(); else await stepBack();
  } catch (e) {
    toast('走不动了：' + e.message);
  } finally {
    state.busy = false;
  }
}

async function resetBoard() {
  if (!state.meta) return;
  stopPlay();
  await waitIdle();
  showAt(0);
  toast('回到题目');
  playTick(0.8);
}

async function playSolution() {
  if (!state.meta) return;
  const moves = movesOf();
  if (!moves.length) { toast('这道题没有解法信息'); return; }
  if (state.playing) { stopPlay(); return; }          // 再点一次 = 暂停
  if (state.cursor >= moves.length) return;

  await waitIdle();
  const myRun = state.run + 1;
  state.run = myRun;
  state.playing = true;
  updateTransport();
  try {
    while (state.playing && state.run === myRun && state.cursor < moves.length) {
      state.busy = true;
      await stepForward();
      state.busy = false;
      if (!state.playing || state.cursor >= moves.length) break;
      await pause(90);
    }
  } catch (e) {
    toast('演示出错了：' + e.message);
  } finally {
    const done = state.cursor >= moves.length;
    state.playing = false;
    state.busy = false;
    updateTransport();
    if (done) {
      playDing();
      toast('解开了！');
      speak('解开了');
      setStatus(`演示完成：共 ${moves.length} 步（等级 ${state.meta.level}）`);
    }
  }
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
  stopPlay();                     // 演示中也能换题：先停，不锁按钮
  await waitIdle();
  $('new').disabled = true;
  try {
    const r = await fetch(id ? `${API}/puzzles/${encodeURIComponent(id)}`
                             : `${API}/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const p = await r.json();
    if (id) syncLevel(p.level);   // 下拉框跟着这道题走，免得"题是 20 级的、框里写着 1 级"
    state.meta = p;
    // 告诉广场"现在是哪一道"（收藏星标用；单独跑时没有这个函数）
    if (window.plazaSetPuzzle) window.plazaSetPuzzle({ id: p.id, level: p.level });
    state.base = p.matrix.map((t) => t.slice());
    state.cursor = 0;
    state.selected = null;
    state.half = null;
    state.matrix = matrixAt(0);
    render(true);
    updateTransport();
    setStatus(`等级 ${p.level} · ${p.moves} 步 · id ${p.id}`);
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
$('demo').addEventListener('click', playSolution);
$('reset').addEventListener('click', resetBoard);
$('prev').addEventListener('click', () => doStep(-1));
$('next').addEventListener('click', () => doStep(1));
$('level').addEventListener('change', (e) => { newPuzzle(); e.target.blur(); });

// 键盘：
//   ← →        换柱子（到头"咚"一声）—— 给读屏用的，别占
//   ↑          读「上五」（最上面 5 颗）—— 一次只读五个，整根 10 颗一口气读太快
//   ↓          读「下五」（最下面 5 颗），跟点柱子、← → 一样
//   空格       重读刚才读到的那一段
//   Home       回到题目
//   PageUp     上一步
//   PageDown   下一步
//   End        演示解法 / 暂停
window.addEventListener('keydown', (e) => {
  if (!state.matrix) return;
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;   // 别抢表单的键

  if (e.key === 'Home') { e.preventDefault(); resetBoard(); return; }
  if (e.key === 'PageUp') { e.preventDefault(); doStep(-1); return; }
  if (e.key === 'PageDown') { e.preventDefault(); doStep(1); return; }
  if (e.key === 'End') { e.preventDefault(); playSolution(); return; }

    if (e.key === ' ' || e.code === 'Space') {
    e.preventDefault();
    if (state.selected !== null) readHalf(state.selected, state.half || 'low');
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    readTube(null, 'high');   // 读「上五」
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    readTube(null, 'low');    // 读「下五」—— 跟点柱子、← → 一个动作
    return;
  }
  if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault();
    const step = e.key === 'ArrowLeft' ? -1 : 1;
    if (state.selected === null) {
      readTube(0, 'low');     // 还没选过柱子：从第一根开始，读它的「下五」
      return;
    }
    const next = state.selected + step;
    if (next < 0 || next >= state.matrix.length) {
      playThud();          // 左边/右边没有了
      return;
    }
    readTube(next, 'low');    // 换根柱子就读它的「下五」
  }
});

updateTransport();          // 还没拿到题：先让回放条是灰的
// 历史页点「打开」过来的（?p=<id>）就先开那一道题；没带 id、或那道题打不开，就随机抽一道
loadLevels().then(async () => {
  if (WANT_ID && await newPuzzle({ id: WANT_ID, silent: true })) return;
  newPuzzle({ silent: true });
});
