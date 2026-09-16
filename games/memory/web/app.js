/* BeadMatch · 记忆 前端：拿规则卡 → 出题人摆珠子 → 倒计时 → 盖住 → 孩子还原 → 出题人判定
 *
 * ⚠️ 这游戏**程序手里没有答案**（排列是出题人当场摆的，见 README §2）：
 *    所以没有"检查对错"的接口，最后一步是出题人自己看，然后点"一样 / 没对"。
 *
 * 数据约定（跟后端一致）：
 *   materials = [{ color:"R", name:"红色", emoji:"🔴", count:3 }]，多的排前面
 *   shape / restore = "row" / "order" 这种记号，shape_cn / restore_cn 是中文
 *   observe / delay = 秒数，reverse = 要不要从右往左，demo = 例子（不是答案）
 */

window.__memory_loaded = true;   // index.html 靠它判断脚本有没有加载成功

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
const materialsEl = $('materials');
const tasksEl = $('tasks');
const demoEl = $('demo');
const countEl = $('count');
const promptEl = $('prompt');

const state = {
  card: null,      // 当前这张规则卡（后端返回的原样）
  phase: 'card',   // card / observe / cover / wait / restore / judge / done
  result: null,    // 上一轮判定：true = 一样，false = 没对
  timer: null,     // 倒计时的 setInterval
  token: 0,        // 作废旧的倒计时回调（换题 / 取消时用）
};

// 每一步那句提示语（restore / done 要看卡片，单独算）
const PROMPT = { observe: '看好啦', cover: '时间到，请盖住', wait: '先等一会儿', judge: '摆得跟刚才一样吗？' };

// 朗读参数：一句一句读，之间静音这么久（毫秒）
const SPEECH_LINE_GAP = 300;
const SPEECH_RATE = 1.0;

// ---------------------------------------------------------------------------
// 声音（Web Audio 合成，不用素材文件）
// ---------------------------------------------------------------------------

let audio = null;
function audioCtx() {
  if (!audio) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio.state === 'suspended') audio.resume();
  return audio;
}

/** 每秒"滴"一声（观察倒计时）；pitch 越大越尖 */
function playTick(pitch = 1) {
  try {
    const ctx = audioCtx();
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = 660 * pitch;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.16, t + 0.006);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + 0.18);
  } catch (e) { /* 没声音也不影响玩 */ }
}

/** "叮"：时间到 / 挑战成功 */
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

/** "咚"：没对 / 取消 */
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
    console.warn('[memory] 这个浏览器不支持 speechSynthesis，没法朗读');
    return;
  }
  try {
    window.speechSynthesis.cancel();
    const voice = pickVoice();
    if (!voice) console.warn('[memory] 没找到中文语音，用系统默认语音读');
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
      u.onerror = (e) => console.warn('[memory] 朗读出错：', e.error || e);
      window.speechSynthesis.speak(u);
    };
    next();
  } catch (e) {
    console.warn('[memory] 朗读失败：', e);
  }
}

function speak(text) { speakLines([text]); }

/** 把这张规则卡念一遍（大人手上在摆珠子，不用低头看屏幕） */
function speakCard() {
  const p = state.card;
  if (!p) return;
  const lines = [];
  if ((p.title || '').trim()) lines.push(p.title.trim());
  lines.push(`准备 ${p.beads} 颗珠子：${(p.materials || []).map((m) => `${m.name} ${m.count} 颗`).join('，')}。`);
  lines.push(...taskLines(p));
  speakLines(lines);
}

// ---------------------------------------------------------------------------
// 小工具
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

function dotEl(letter, className) {
  const el = document.createElement('span');
  el.className = className;
  el.style.background = (COLORS[letter] || {}).css || '#888';
  return el;
}

function pulse(el) {
  el.classList.remove('pulse');
  void el.offsetWidth;          // 强制重排，动画才能重放
  el.classList.add('pulse');
}

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

/** 题目三步：① 摆题 → ② 看几秒 → ③ 摆回来。
 *
 * **按字段算出来，不写进卡片的正文里** —— 否则同一个数字要写两遍（字段一遍、句子里一遍），
 * 改观察时间就会漏一处（3 秒 → 5 秒那次就是这么踩的）。
 * 卡片正文（`note`）只放「这一档额外的嘱咐」（比如 L5 的"别摆成规律"），有就补在三步后面。
 */
function taskLines(p) {
  const shape = p.shape === 'row' ? '排成一排' : `摆成${p.shape_cn || p.shape}`;
  const lines = [`把 ${p.beads} 颗珠子${shape}（顺序随意）`];
  lines.push(`给孩子看 ${p.observe} 秒后盖住${p.delay ? `，再等 ${p.delay} 秒` : ''}`);
  if (p.reverse) lines.push('再让孩子从右往左凭记忆摆回来');
  else if (p.restore === 'layout') lines.push('再让孩子凭记忆摆回每一颗的位置');
  else lines.push('再让孩子凭记忆摆回原来的顺序');
  const note = (p.note || '').trim();
  if (note) lines.push(...note.split('\n').map((s) => s.trim()).filter(Boolean));
  return lines;
}

function renderCard(p) {
  // 材料：珠子 + 颜色名 + ×几颗
  materialsEl.innerHTML = '';
  (p.materials || []).forEach((m) => {
    const row = document.createElement('div');
    row.className = 'material';
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = m.name;
    const times = document.createElement('span');
    times.className = 'times';
    times.textContent = '×' + m.count;
    row.append(dotEl(m.color, 'dot'), name, times);
    materialsEl.appendChild(row);
  });

  tasksEl.innerHTML = '';
  taskLines(p).forEach((text) => {
    const li = document.createElement('li');
    li.textContent = text;
    tasksEl.appendChild(li);
  });

  // 例子：灰灰的，一眼看出"不是要照着摆的"
  const demo = p.demo || [];
  demoEl.innerHTML = '';
  demo.forEach((letter) => demoEl.appendChild(dotEl(letter, 'dot')));
  $('demo-wrap').hidden = demo.length === 0;

  const name = (p.title || '').trim();
  $('card-title').textContent = name;
  $('card-title').hidden = !name;

  setStatus(`${name ? name + ' · ' : ''}等级 ${p.level} · ${p.beads} 颗 / ${p.colors} 色 · id ${p.id}`);
}

/** 按当前这一步，安排按钮 / 提示语 / 倒计时该谁露面 */
function renderPhase() {
  const ph = state.phase;
  const busy = ph === 'observe' || ph === 'wait';      // 观察和空等的几秒里，别乱动

  $('level').disabled = busy;
  $('new').disabled = busy;
  $('read').disabled = busy;

  $('yes').hidden = ph !== 'judge';
  $('no').hidden = ph !== 'judge';

  if (!busy) {                                          // 倒计时收摊
    countEl.hidden = true;
    countEl.textContent = '';
  }

  let text = PROMPT[ph] || '';
  promptEl.className = 'prompt';
  if (ph === 'restore') {
    text = (state.card && state.card.reverse)
      ? '把珠子打乱，让孩子凭记忆从右往左摆回来'
      : '把珠子打乱，让孩子凭记忆摆回刚才的样子';
  } else if (ph === 'done') {
    if (state.result) { text = '挑战成功 ✓'; promptEl.className = 'prompt win'; }
    else { text = '没关系，再来一题试试'; promptEl.className = 'prompt miss'; }
  }
  promptEl.textContent = text;
  promptEl.hidden = !text;
}

function setPhase(name) {
  state.phase = name;
  renderPhase();
}

// ---------------------------------------------------------------------------
// 一局：卡片 → 观察 → 盖住 →（要不要先等）→ 还原 → 判定 → 结束
// ---------------------------------------------------------------------------

function clearTimers() {
  state.token += 1;
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

/** 倒计时：屏幕上显示秒数，每秒一声"滴"，到点交给 onDone */
function countdown(seconds, { onTick, onDone } = {}) {
  const token = state.token;
  const deadline = Date.now() + seconds * 1000;
  let left = seconds;
  countEl.hidden = false;
  countEl.textContent = String(left);
  pulse(countEl);
  if (onTick) onTick(left);
  state.timer = setInterval(() => {
    if (token !== state.token) return;                   // 换题了 / 取消了
    const now = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (now !== left && now > 0) {
      left = now;
      countEl.textContent = String(left);
      pulse(countEl);
      if (onTick) onTick(left);
    }
    if (Date.now() >= deadline) {
      clearTimers();
      countEl.textContent = '0';
      if (onDone) onDone();
    }
  }, 100);
}

/** 摆好了 → 观察 */
function startObserve() {
  const p = state.card;
  if (!p) return;
  clearTimers();
  setPhase('observe');
  speak('开始');
  countdown(p.observe, {
    onTick: (n) => playTick(1 + (p.observe - n) * 0.06),
    onDone: () => {
      playDing();
      toCover();
      speak('时间到，请盖住');
    },
  });
}

function toCover() { setPhase('cover'); }

/** 盖住了。卡里写了 delay 就先空等一会儿，再让孩子摆 */
function afterCover() {
  const p = state.card;
  if (!p.delay) { toRestore(); return; }
  setPhase('wait');
  countdown(p.delay, {
    onTick: () => playTick(0.75),
    onDone: () => { playDing(); toRestore(); },
  });
}

function toRestore() { setPhase('restore'); }

function toJudge() { setPhase('judge'); }

/** 判定：出题人自己看（程序不知道原来摆的是什么） */
function judge(ok) {
  state.result = ok;
  if (ok) {
    playDing();
    toast('挑战成功');
    speak('挑战成功');
  } else {
    playThud();
    toast('没关系，再来一次');
    speak('没关系，再来一次');
  }
  setPhase('done');
}

function backToCard() {
  clearTimers();
  setPhase('card');
}

function cancelRound() {
  if (state.phase === 'card') return;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  state.result = null;
  backToCard();
  playThud();
  toast('这一轮取消了');
}

// ---------------------------------------------------------------------------
// 拿卡
// ---------------------------------------------------------------------------

async function loadLevels() {
  try {
    const r = await fetch('/api/memory/levels');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    const sel = $('level');
    sel.innerHTML = '';
    (data.levels || []).forEach(({ level, count }) => {
      const o = document.createElement('option');
      o.value = String(level);
      o.textContent = `${level} 级（${count} 张）`;
      sel.appendChild(o);
    });
    if (sel.options.length === 0) {
      const o = document.createElement('option');
      o.textContent = '卡片库是空的';
      sel.appendChild(o);
    }
  } catch (e) {
    const sel = $('level');
    sel.innerHTML = '';
    const o = document.createElement('option');
    o.textContent = '读不到卡片库';
    sel.appendChild(o);
    toast('读不到卡片库：' + e.message + '（后端起了吗？）', 5000);
  }
}

async function newCard() {
  const level = $('level').value;
  if (!level) return;
  clearTimers();
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  $('new').disabled = true;
  try {
    const r = await fetch(`/api/memory/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const p = await r.json();
    state.card = p;
    state.result = null;
    renderCard(p);
    setPhase('card');
    playTick(0.9);
  } catch (e) {
    toast('拿卡失败：' + e.message);
  } finally {
    $('new').disabled = false;
  }
}

function nextCard() { backToCard(); newCard(); }

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

/** 空格 = 当前这一步的"继续" */
function onGo() {
  switch (state.phase) {
    case 'card': startObserve(); break;
    case 'cover': afterCover(); break;
    case 'restore': toJudge(); break;
    case 'done': nextCard(); break;
    default: break;      // 观察 / 空等 / 判定不吃这一下
  }
}

$('yes').addEventListener('click', () => { $('yes').blur(); judge(true); });
$('no').addEventListener('click', () => { $('no').blur(); judge(false); });
$('new').addEventListener('click', newCard);
$('read').addEventListener('click', speakCard);
$('level').addEventListener('change', (e) => { newCard(); e.target.blur(); });

window.addEventListener('keydown', (e) => {
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;   // 别抢表单的键

  if (e.key === 'Escape') {
    if (state.phase !== 'card') { e.preventDefault(); cancelRound(); }
    return;
  }
  if (e.key === ' ' || e.code === 'Space') {
    e.preventDefault();        // 顺带压掉"空格又点了一次刚按过的按钮"
    onGo();
    return;
  }
  if (state.phase === 'judge') {           // 判定得自己按，别让空格替人做主
    if (e.key === 'y' || e.key === 'Y') { e.preventDefault(); judge(true); return; }
    if (e.key === 'n' || e.key === 'N') { e.preventDefault(); judge(false); return; }
    return;
  }
  if (state.phase === 'card' && (e.key === 'r' || e.key === 'R')) {
    e.preventDefault();
    speakCard();
  }
});

loadLevels().then(newCard);
