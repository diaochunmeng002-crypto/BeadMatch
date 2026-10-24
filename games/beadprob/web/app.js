/* 彩珠机会屋：屏幕只出题、给答案和解释，选择和比较过程在线下用实物完成。 */

window.__beadprob_loaded = true;

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
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();

const state = {
  puzzle: null,
  revealed: false,
};

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
    const utterance = new SpeechSynthesisUtterance(clean);
    utterance.lang = 'zh-CN';
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  } catch (e) { /* 不支持就算了 */ }
}

let toastTimer = null;
function toast(text, ms = 2200) {
  const el = $('toast');
  el.textContent = text;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), ms);
}

function setStatus(text) { $('status').textContent = text; }

function bagSentence(bag) {
  const parts = (bag.counts || []).map((row) => row.name + '珠 ' + row.count + ' 颗');
  return bag.label + '里有' + parts.join('，');
}

function readWhole() {
  const puzzle = state.puzzle;
  if (!puzzle) return;
  const parts = [puzzle.title, puzzle.story, ...(puzzle.bags || []).map(bagSentence)];
  if ((puzzle.prior || []).length) {
    parts.push('已经摸到：' + puzzle.prior.map((row) => row.name + '珠').join('、'));
  }
  if ((puzzle.removed || []).length) {
    parts.push('已经拿出、不放回：' + puzzle.removed.map((row) => row.name + '珠').join('、'));
  }
  parts.push(puzzle.question, puzzle.action);
  if (state.revealed) {
    if (puzzle.kind !== 'race') parts.push('答案：' + puzzle.answer_text);
    parts.push(puzzle.explain);
  }
  speak(parts.filter(Boolean).join('。'));
}

function beadEl(letter) {
  const info = COLORS[letter] || { name: letter, css: '#888' };
  const bead = document.createElement('span');
  bead.className = 'bead';
  bead.style.background = info.css;
  bead.title = info.name + '色';
  bead.setAttribute('aria-label', info.name + '色');
  return bead;
}

function renderBag(bag) {
  const el = document.createElement('section');
  el.className = 'bag';

  const top = document.createElement('div');
  top.className = 'bag-top';
  const name = document.createElement('span');
  name.className = 'bag-name';
  name.textContent = bag.label;
  const total = document.createElement('span');
  total.className = 'bag-total';
  total.textContent = '共 ' + bag.total + ' 颗';
  top.append(name, total);

  const beads = document.createElement('div');
  beads.className = 'bag-beads';
  const sortedCounts = (bag.counts || []).slice()
    .sort((a, b) => a.count - b.count || a.name.localeCompare(b.name, 'zh-CN'));
  sortedCounts.forEach((row) => {
    const colorRow = document.createElement('div');
    colorRow.className = 'color-row';
    const label = document.createElement('span');
    label.className = 'color-name';
    label.textContent = row.name + ' ' + row.count + ' 颗';
    const rowBeads = document.createElement('span');
    rowBeads.className = 'row-beads';
    for (let i = 0; i < row.count; i += 1) rowBeads.appendChild(beadEl(row.bead));
    colorRow.append(label, rowBeads);
    beads.appendChild(colorRow);
  });

  el.append(top, beads);
  return el;
}

function renderSequence(puzzle) {
  const rows = (puzzle.removed || []).length ? puzzle.removed : (puzzle.prior || []);
  const box = $('sequence');
  const beads = $('sequence-beads');
  beads.innerHTML = '';
  if (!rows.length) {
    box.hidden = true;
    return;
  }
  $('sequence-label').textContent = (puzzle.removed || []).length
    ? '已经拿出（不放回）' : '刚才依次摸到';
  rows.forEach((row) => beads.appendChild(beadEl(row.bead)));
  box.hidden = false;
}

function showAnswer() {
  const puzzle = state.puzzle;
  if (!puzzle || state.revealed) return;
  state.revealed = true;
  const race = puzzle.kind === 'race';
  $('result-title').textContent = race ? '规律' : '答案';
  $('answer').hidden = race;
  $('answer').textContent = race ? '' : '答案：' + puzzle.answer_text;
  $('explain').textContent = puzzle.explain;
  $('result').hidden = false;
  $('show').disabled = true;
  setStatus(race ? '先实际玩几轮，再对照这里的规律。'
                 : '先在线下说出自己的答案，再对照这里的解释。');
  $('result').scrollIntoView({ block: 'nearest' });
  readWhole();
}

function render(puzzle) {
  state.puzzle = puzzle;
  state.revealed = false;
  $('puzzle-title').textContent = puzzle.title || '';
  $('story').textContent = puzzle.story || '';
  $('story').hidden = !puzzle.story;
  $('question').textContent = puzzle.question || '';
  $('action').textContent = puzzle.action || '';
  $('show').textContent = puzzle.kind === 'race' ? '看规律' : '看答案';
  $('level').value = String(puzzle.level);
  $('result').hidden = true;
  $('show').disabled = false;
  document.title = 'BeadMatch · 彩珠机会屋';

  const bags = $('bags');
  bags.innerHTML = '';
  (puzzle.bags || []).forEach((bag) => bags.appendChild(renderBag(bag)));
  renderSequence(puzzle);

  const revealWord = puzzle.kind === 'race' ? '看规律' : '看答案';
  setStatus('等级 ' + puzzle.level + ' · ' + (puzzle.level_name || '')
            + (puzzle.kind === 'race'
              ? ' · 先在线下比赛几轮，再点「' + revealWord + '」。'
              : ' · 先在线下操作，再点「' + revealWord + '」。'));
  if (window.plazaSetPuzzle) {
    window.plazaSetPuzzle({ id: puzzle.id, level: puzzle.level });
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  let body = null;
  try {
    body = await response.json();
  } catch (e) {
    body = null;
  }
  if (!response.ok) {
    throw new Error((body && body.detail) || ('HTTP ' + response.status));
  }
  return body;
}

async function loadLevels() {
  const data = await fetchJson(API + '/levels');
  const select = $('level');
  select.innerHTML = '';
  (data.levels || []).forEach(({ level, count, name }) => {
    const option = document.createElement('option');
    option.value = String(level);
    option.textContent = level + ' 级 · ' + (name || '') + '（' + count + ' 道）';
    select.appendChild(option);
  });
  if (!select.options.length) throw new Error('题库是空的');
}

async function loadLevel(level, opts = {}) {
  $('show').disabled = true;
  try {
    const exclude = opts.exclude
      ? '&exclude=' + encodeURIComponent(opts.exclude) : '';
    const puzzle = await fetchJson(API + '/random?level=' + encodeURIComponent(level) + exclude);
    render(puzzle);
  } catch (e) {
    $('show').disabled = false;
    setStatus('题目读取失败：' + e.message);
    toast('题目读取失败，请确认后端已经启动。', 4000);
  }
}

function anotherQuestion() {
  if (!state.puzzle) return;
  loadLevel(state.puzzle.level, { exclude: state.puzzle.id });
}

async function load() {
  try {
    await loadLevels();
    if (WANT_ID) {
      try {
        render(await fetchJson(API + '/puzzles/' + encodeURIComponent(WANT_ID)));
        return;
      } catch (e) {
        toast('那道题打不开，换成随机一道。', 3200);
      }
    }
    await loadLevel($('level').options[0].value);
  } catch (e) {
    setStatus('题库读取失败：' + e.message);
    toast('题库读取失败，请确认后端已经启动。', 4000);
  }
}

$('read').addEventListener('click', readWhole);
$('show').addEventListener('click', showAnswer);
$('next').addEventListener('click', anotherQuestion);
$('level').addEventListener('change', (event) => {
  loadLevel(event.target.value);
  event.target.blur();
});

window.addEventListener('keydown', (event) => {
  if (!state.puzzle) return;
  const tag = (event.target && event.target.tagName) || '';
  if (tag === 'SELECT' || tag === 'INPUT' || tag === 'TEXTAREA') return;
  if (event.key === ' ' || event.code === 'Space') {
    event.preventDefault();
    readWhole();
    return;
  }
  if (event.key === 'Enter') {
    event.preventDefault();
    showAnswer();
    return;
  }
  if (event.key === 'ArrowRight') {
    event.preventDefault();
    anotherQuestion();
  }
});

load();
