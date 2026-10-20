/* BeadMatch · 计算 前端：拿卡 → 摆出材料 → 孩子说答案 → 大人按「看答案」自己对
 *
 * 数据约定（跟后端一致）：
 *   participants = [{ color:"B", name:"蓝色", emoji:"🔵", count:3 }]，多的排前面
 *   rule         = "数一数：一共有几颗珠子？"（原样，就是给孩子听的那句话）
 *   answer       = 原样（"5" / "蓝" / "equal"）；answer_value = 规范化后的（5 / "B" / "equal"）
 *
 * 页面上只出题（材料 + 题目）和对答案，判定由人做。
 * 后端其实还有 POST /api/calc/check（交一个答案自动判对错），页面没用它 ——
 * 哪天想让孩子在屏幕上答题，接回来就行。
 */

window.__calc_loaded = true;   // index.html 靠它判断脚本有没有加载成功

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
// 接口基址：单独跑时是 /api/calc，广场里由广场往页面里注入 window.API_BASE
const API = window.API_BASE || '/api/calc';

// 历史页「打开」带过来的题目 id（/games/calc/?p=<id>，`?puzzle=` 也认）：
// 有就开**那一道题**，没有就照旧随机抽一道。认不出来会退回随机，不至于开个空白页。
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const materialsEl = $('materials');
const ruleEl = $('rule');
const promptEl = $('prompt');

const state = {
  card: null,      // 当前这张卡（后端返回的原样）
};

// 朗读参数
const SPEECH_LINE_GAP = 300;   // 一句一句读，之间静音这么久（毫秒）
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

/** 换题："嗒" */
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

/** 看答案："叮" */
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
    console.warn('[calc] 这个浏览器不支持 speechSynthesis，没法朗读');
    return;
  }
  try {
    window.speechSynthesis.cancel();
    const voice = pickVoice();
    if (!voice) console.warn('[calc] 没找到中文语音，用系统默认语音读');
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
      u.onerror = (e) => console.warn('[calc] 朗读出错：', e.error || e);
      window.speechSynthesis.speak(u);
    };
    next();
  } catch (e) {
    console.warn('[calc] 朗读失败：', e);
  }
}

function speak(text) { speakLines([text]); }

/** 把这张卡念一遍：先报材料，再念规则（大人手上在摆珠子，不用低头看屏幕） */
function speakCard() {
  const p = state.card;
  if (!p) return;
  const lines = [];
  if ((p.title || '').trim()) lines.push(p.title.trim());
  lines.push(`准备 ${p.beads} 颗珠子：${(p.participants || []).map((m) => `${m.name} ${m.count} 颗`).join('，')}。`);
  if ((p.rule || '').trim()) lines.push(p.rule.trim());
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

function setPrompt(text) {
  promptEl.textContent = text || '';
  promptEl.hidden = !text;
}

/** 答案给人看的样子：5 → "5"；"B" → "蓝色"；"equal" → "一样多" */
function answerText(card) {
  const v = card.answer_value;
  if (v === 'equal') return '一样多';
  if (typeof v === 'number') return String(v);
  const info = COLORS[v];
  return info ? info.name + '色' : String(v);
}

// ---------------------------------------------------------------------------
// 渲染
// ---------------------------------------------------------------------------

function renderCard(p) {
  // 材料：把珠子**画出来**（几颗就画几个圆点，孩子能直接点数）+ 颜色名 + 几颗
  materialsEl.innerHTML = '';
  const rows = p.participants || [];
  // 圆点列统一宽度：一行画 5 颗也放得下，这样"颜色名 / 几颗"能上下对齐
  const dotCol = Math.max(1, ...rows.map((m) => m.count)) * 28;
  rows.forEach((m) => {
    const row = document.createElement('div');
    row.className = 'material';
    const dots = document.createElement('span');
    dots.className = 'dots';
    dots.style.minWidth = dotCol + 'px';
    for (let i = 0; i < m.count; i += 1) {
      const dot = document.createElement('span');
      dot.className = 'dot';
      dot.style.background = (COLORS[m.color] || {}).css || '#888';
      dots.appendChild(dot);
    }
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = m.name;
    const qty = document.createElement('span');
    qty.className = 'qty';                 // 别叫 .count —— 以后加倒计时会跟它撞
    qty.textContent = m.count + ' 颗';
    row.append(dots, name, qty);
    materialsEl.appendChild(row);
  });

  ruleEl.textContent = p.rule || '';
  setPrompt('');                        // 答案先藏着，换一题就收起来

  const name = (p.title || '').trim();
  $('card-title').textContent = name;
  $('card-title').hidden = !name;

  setStatus(`${name ? name + ' · ' : ''}等级 ${p.level} · ${p.task_cn} · ${p.beads} 颗 / ${p.colors} 色 · id ${p.id}`);
}

/** 看答案：大人直接对（页面上不判对错） */
function peekAnswer() {
  const p = state.card;
  if (!p) return;
  const shown = answerText(p);
  setPrompt('答案是 ' + shown);
  toast('答案是 ' + shown, 3000);
  playDing();
  speak('答案是' + shown);
}

// ---------------------------------------------------------------------------
// 拿卡
// ---------------------------------------------------------------------------

async function loadLevels() {
  try {
    const r = await fetch(API + '/levels');
    if (!r.ok) throw new Error(await errText(r));
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

/** 拿一张新卡。``opts.silent`` 用在**刚打开页面**那一次 —— 点链接跳过来不该"嗒"一声，
 *  只有自己按「换一题」/空格时才响。
 *
 *  ``opts.id`` 给了就**按 id 取那一道题**（历史页「打开」跳过来时用），否则按当前等级随机抽。
 *  拿成了返回 true、没拿成返回 false —— 调用方靠它决定要不要再兜一道随机题。 */
async function newCard(opts = {}) {
  const id = ((opts && opts.id) || '').trim();
  const level = $('level').value;
  if (!level && !id) return false;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  $('new').disabled = true;
  try {
    const r = await fetch(id ? `${API}/puzzles/${encodeURIComponent(id)}`
                             : `${API}/random?level=${encodeURIComponent(level)}`);
    if (!r.ok) throw new Error(await errText(r));
    const p = await r.json();
    if (id) syncLevel(p.level);   // 下拉框跟着这张卡走，免得"卡是 20 级的、框里写着 1 级"
    state.card = p;
    // 告诉广场"现在是哪一道"（收藏星标用；单独跑时没有这个函数）
    if (window.plazaSetPuzzle) window.plazaSetPuzzle({ id: p.id, level: p.level });
    renderCard(p);
    if (!(opts && opts.silent)) playTick(0.9);
    return true;
  } catch (e) {
    toast((id ? '那张卡打不开：' : '拿卡失败：') + e.message);
    return false;
  } finally {
    $('new').disabled = false;
  }
}

/** 把等级下拉框拨到这张卡那一档（题库里没有这一档就不动它） */
function syncLevel(level) {
  const sel = $('level');
  const value = String(level);
  if (Array.from(sel.options).some((o) => o.value === value)) sel.value = value;
}

/** 后端报错时，把它自己的说明也带出来 —— 不然只看到 "HTTP 500"，查不出原因。
 *
 * 最常见的 500 是"后端还是旧进程"（代码改过之后没重启），所以顺手提一句。
 */
async function errText(r) {
  let detail = '';
  try {
    const data = await r.json();
    detail = (data && data.detail) || '';
  } catch (e) { /* 不是 JSON 就算了 */ }
  const tail = detail ? '：' + detail : '';
  if (r.status === 500) {
    return `HTTP 500${tail}（后端像是旧进程，重启一下：python -m games.calc.api）`;
  }
  return `HTTP ${r.status}${tail}`;
}

// ---------------------------------------------------------------------------
// 绑定
// ---------------------------------------------------------------------------

$('peek').addEventListener('click', () => { $('peek').blur(); peekAnswer(); });
$('read').addEventListener('click', () => { $('read').blur(); speakCard(); });
$('new').addEventListener('click', newCard);
$('level').addEventListener('change', (e) => { newCard(); e.target.blur(); });

window.addEventListener('keydown', (e) => {
  const tag = (e.target && e.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;   // 别抢表单的键

  if (e.key === ' ' || e.code === 'Space') { e.preventDefault(); newCard(); return; }
  if (e.key === 'r' || e.key === 'R') { e.preventDefault(); speakCard(); return; }
  if (e.key === 'a' || e.key === 'A') { e.preventDefault(); peekAnswer(); }
});

// 历史页点「打开」过来的（?p=<id>）就先开那一张卡；没带 id、或那张卡打不开，就随机抽一张
loadLevels().then(async () => {
  if (WANT_ID && await newCard({ id: WANT_ID, silent: true })) return;
  newCard({ silent: true });
});
