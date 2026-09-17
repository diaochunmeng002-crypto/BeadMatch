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
    el.addEventListener('click', () => place(letter));
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
    if (letter) {
      const el = beadEl(letter, { drop: animate });
      el.addEventListener('click', () => takeBack(i));
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
 *  只有自己按「换一题」时才响。 */
async function newPuzzle(opts = {}) {
  const level = $('level').value;
  if (!level) return;
  $('new').disabled = true;
  try {
    const r = await fetch(`${API}/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const p = await r.json();
    state.puzzle = p;
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

loadLevels().then(() => newPuzzle({ silent: true }));
