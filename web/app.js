/* BeadMatch 前端：拿题 → 画柱子 → 点柱子读颜色 → 演示解法（飞球 + 声音 + 朗读）
 *
 * 数据约定（跟后端一致）：
 *   matrix[柱子][位置]，位置 0 = 最顶端那一格，0 表示空位
 *   solution = "3-7 1-2"（柱子编号从 1 起）
 */

window.__beadmatch_loaded = true;   // index.html 靠它判断脚本有没有加载成功

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
const board = $('board');

const state = {
  matrix: null,
  meta: null,
  playing: false,
};

const settings = { sfx: true, speech: false };

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
  if (!settings.sfx) return;
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
  if (!settings.sfx) return;
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

// ---------------------------------------------------------------------------
// 朗读
// ---------------------------------------------------------------------------

function speak(text) {
  if (!settings.speech || !('speechSynthesis' in window)) return;
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
    el.addEventListener('click', () => readTube(t));
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

/** 点一根柱子：从上到下把颜色读出来 */
function readTube(t) {
  const tube = state.matrix[t];
  const names = tube.filter((v) => v !== 0).map((v) => COLORS[v].name);
  const text = names.length ? names.join('、') : '空柱子';
  toast(`第 ${t + 1} 根：${text}`);
  speak(`第${t + 1}根，${text}`);
  playTick(1.2);
  const el = board.querySelector(`.tube[data-tube="${t}"]`);
  if (el) {
    el.classList.add('reading');
    setTimeout(() => el.classList.remove('reading'), 320);
  }
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
// 演示解法
// ---------------------------------------------------------------------------

async function playSolution() {
  if (state.playing || !state.meta) return;
  const moves = parseMoves(state.meta.solution);
  if (!moves.length) { toast('这道题没有解法信息'); return; }

  state.playing = true;
  $('demo').disabled = true;
  $('new').disabled = true;

  try {
    for (let i = 0; i < moves.length; i++) {
      const [from, to] = moves[i];
      const before = state.matrix.map((t) => t.slice());
      await animateBall(from, to);
      state.matrix = applyMove(before, from, to);
      render(false);
      playTick();
      setStatus(`演示中… 第 ${i + 1} / ${moves.length} 步`);
      await new Promise((r) => setTimeout(r, 90));
    }
    playDing();
    toast('解开了！');
    speak('解开了');
    setStatus(`演示完成：共 ${moves.length} 步（等级 ${state.meta.level}）`);
  } catch (e) {
    toast('演示出错了：' + e.message);
  } finally {
    state.playing = false;
    $('demo').disabled = false;
    $('new').disabled = false;
  }
}

// ---------------------------------------------------------------------------
// 拿题
// ---------------------------------------------------------------------------

async function loadLevels() {
  try {
    const r = await fetch('/api/levels');
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

async function newPuzzle() {
  if (state.playing) return;
  const level = $('level').value;
  if (!level) return;
  $('new').disabled = true;
  try {
    const r = await fetch(`/api/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const p = await r.json();
    state.meta = p;
    state.matrix = p.matrix.map((t) => t.slice());
    render(true);
    setStatus(`等级 ${p.level} · ${p.moves} 步 · id ${p.id}`);
    playTick(0.8);
  } catch (e) {
    toast('拿题失败：' + e.message);
  } finally {
    $('new').disabled = false;
  }
}

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

$('new').addEventListener('click', newPuzzle);
$('demo').addEventListener('click', playSolution);
$('level').addEventListener('change', newPuzzle);
$('sfx').addEventListener('change', (e) => { settings.sfx = e.target.checked; });
$('speech').addEventListener('change', (e) => {
  settings.speech = e.target.checked;
  if (settings.speech) speak('朗读已打开');
});

loadLevels().then(newPuzzle);
