/* 彩珠密令：页面只显示题目要用的珠子和线索约定 */

window.__beadcipher_loaded = true;

const COLORS = {
  Y: { name: '黄', css: '#f2c231' },
  G: { name: '绿', css: '#4caf50' },
  R: { name: '红', css: '#e5484d' },
  P: { name: '紫', css: '#9b59d0' },
  B: { name: '蓝', css: '#3b82f6' },
  O: { name: '橙', css: '#f2811d' },
};

const API = window.API_BASE || '/api';
const select = document.getElementById('level');
const nextButton = document.getElementById('next');
const WANT_ID = (() => {
  try {
    const q = new URLSearchParams(location.search);
    return (q.get('p') || q.get('puzzle') || '').trim();
  } catch (e) {
    return '';
  }
})();
let current = null;

async function fetchJson(url) {
  const response = await fetch(url);
  let body = null;
  try {
    body = await response.json();
  } catch (e) {
    body = null;
  }
  if (!response.ok) throw new Error((body && body.detail) || ('HTTP ' + response.status));
  return body;
}

function render(puzzle) {
  current = puzzle;
  document.title = 'BeadMatch · 彩珠密令';
  document.getElementById('puzzle-title').textContent = puzzle.title || '';
  select.value = String(puzzle.level);
  nextButton.disabled = typeof puzzle.pool_size === 'number' && puzzle.pool_size <= 1;

  const row = document.getElementById('beads');
  row.innerHTML = '';
  (puzzle.beads || puzzle.colors || []).forEach((letter) => {
    const info = COLORS[letter] || { name: letter, css: '#888' };
    const item = document.createElement('div');
    item.className = 'bead-item';

    const bead = document.createElement('span');
    bead.className = 'bead';
    bead.style.background = info.css;
    bead.title = info.name + '色';
    bead.setAttribute('aria-label', info.name + '色');

    const label = document.createElement('span');
    label.className = 'bead-name';
    label.textContent = info.name;
    item.append(bead, label);
    row.appendChild(item);
  });

  const clues = document.getElementById('clues');
  clues.innerHTML = '';
  (puzzle.clue_rule || '')
    .split('；')
    .map((text) => text.trim())
    .filter(Boolean)
    .forEach((text) => {
      const item = document.createElement('li');
      item.textContent = /[。？！]$/.test(text) ? text : text + '。';
      clues.appendChild(item);
    });

  document.getElementById('status').textContent = '';
  if (window.plazaSetPuzzle) {
    window.plazaSetPuzzle({ id: puzzle.id, level: puzzle.level });
  }
}

async function loadLevels() {
  const levels = await fetchJson(API + '/levels');
  select.innerHTML = '';
  (levels.levels || []).forEach(({ level, count }) => {
    const option = document.createElement('option');
    option.value = String(level);
    option.textContent = level + ' 级（' + count + ' 道）';
    select.appendChild(option);
  });
  if (!select.options.length) throw new Error('题库是空的');
}

async function loadRandom(level, exclude = '') {
  const tail = exclude ? '&exclude=' + encodeURIComponent(exclude) : '';
  return fetchJson(API + '/random?level=' + encodeURIComponent(level) + tail);
}

async function load() {
  try {
    let puzzle = null;
    if (WANT_ID) {
      try {
        puzzle = await fetchJson(API + '/puzzles/' + encodeURIComponent(WANT_ID));
      } catch (e) {
        puzzle = null;
      }
    }
    await loadLevels();
    if (!puzzle) {
      puzzle = await loadRandom(select.value);
    }
    render(puzzle);
  } catch (e) {
    document.getElementById('status').textContent = '题目读取失败：' + e.message;
  }
}

select.addEventListener('change', async (event) => {
  try {
    render(await loadRandom(event.target.value));
  } catch (e) {
    document.getElementById('status').textContent = '题目读取失败：' + e.message;
  }
});

nextButton.addEventListener('click', async () => {
  try {
    render(await loadRandom(select.value, current ? current.id : ''));
  } catch (e) {
    document.getElementById('status').textContent = '题目读取失败：' + e.message;
  }
});

load();
