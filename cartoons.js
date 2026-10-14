/**
 * CareLink Cartoon Crew - big animated background characters (original artwork, inline SVG).
 *   - Marmalade (orange tabby cat) chases Pip (grey mouse) across the bottom of the screen;
 *     Pip always makes it back to his mouse hole.
 *   - Pip peeks out of the hole (click the hole) with a status update.
 *   - Biscuit (puppy) naps in the corner, wakes up and barks the news after every data refresh
 *     (or when clicked).
 * The scene sits BEHIND the dashboard content. It respects prefers-reduced-motion and can be
 * hidden with the toggle button (remembered per browser).
 */
(function () {
  'use strict';

  const STORAGE_KEY = 'carelink-cartoons-hidden';
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function storageGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function storageSet(key, value) { try { localStorage.setItem(key, value); } catch { /* unavailable */ } }

  // ---------------------------------------------------------------- Artwork
  const CAT_SVG = `
    <svg viewBox="0 0 260 170" aria-hidden="true">
      <ellipse cx="130" cy="162" rx="100" ry="6" fill="#0f172a" opacity=".08"/>
      <path class="toon-cat-tail" d="M58 92 Q18 84 20 44 Q22 22 36 26 Q30 48 40 66 Q50 80 66 84 Z" fill="#f59e0b"/>
      <path d="M26 34 Q30 26 36 26 Q32 34 33 40 Z" fill="#c2410c"/>
      <g class="toon-leg toon-leg-a"><rect x="66" y="108" width="16" height="44" rx="8" fill="#d97706"/><ellipse cx="76" cy="152" rx="13" ry="7" fill="#fde68a"/></g>
      <g class="toon-leg toon-leg-b"><rect x="160" y="108" width="16" height="44" rx="8" fill="#d97706"/><ellipse cx="170" cy="152" rx="13" ry="7" fill="#fde68a"/></g>
      <ellipse cx="120" cy="98" rx="70" ry="34" fill="#f59e0b"/>
      <ellipse cx="128" cy="113" rx="46" ry="15" fill="#fde68a"/>
      <path d="M88 67 q7 13 0 26 M110 64 q7 14 0 27 M132 66 q7 13 0 25" stroke="#c2410c" stroke-width="6" stroke-linecap="round" fill="none"/>
      <g class="toon-leg toon-leg-b"><rect x="82" y="110" width="16" height="44" rx="8" fill="#f59e0b"/><ellipse cx="92" cy="154" rx="13" ry="7" fill="#fff7ed"/></g>
      <g class="toon-leg toon-leg-a"><rect x="174" y="106" width="16" height="46" rx="8" fill="#f59e0b"/><ellipse cx="185" cy="152" rx="13" ry="7" fill="#fff7ed"/></g>
      <path d="M176 46 L182 8 L204 34 Z" fill="#f59e0b"/><path d="M182 38 L185 18 L197 32 Z" fill="#fda4af"/>
      <path d="M214 34 L234 6 L238 42 Z" fill="#f59e0b"/><path d="M220 34 L232 16 L233 38 Z" fill="#fda4af"/>
      <circle cx="206" cy="66" r="38" fill="#f59e0b"/>
      <path d="M196 31 v12 M206 29 v14 M216 31 v12" stroke="#c2410c" stroke-width="4" stroke-linecap="round"/>
      <ellipse cx="222" cy="83" rx="21" ry="14" fill="#fff7ed"/>
      <ellipse cx="199" cy="60" rx="8.5" ry="10.5" fill="#fff"/><ellipse cx="226" cy="58" rx="8.5" ry="10.5" fill="#fff"/>
      <ellipse cx="203" cy="61" rx="4.2" ry="6.5" fill="#166534"/><ellipse cx="230" cy="59" rx="4.2" ry="6.5" fill="#166534"/>
      <circle cx="204.5" cy="58" r="1.6" fill="#fff"/><circle cx="231.5" cy="56" r="1.6" fill="#fff"/>
      <path d="M188 47 l14 5 M238 45 l-13 5" stroke="#7c2d12" stroke-width="3" stroke-linecap="round"/>
      <path d="M225 74 h8 l-4 5 z" fill="#e11d48"/>
      <path d="M229 79 q-4 7 -11 4 M229 79 q4 7 11 3" stroke="#7c2d12" stroke-width="2.2" fill="none" stroke-linecap="round"/>
      <path d="M240 80 l18 -4 M240 85 l18 2 M206 82 l-18 -3 M206 87 l-18 3" stroke="#78350f" stroke-width="1.6" stroke-linecap="round"/>
    </svg>`;

  const MOUSE_SVG = `
    <svg viewBox="0 0 124 92" aria-hidden="true">
      <ellipse cx="60" cy="86" rx="44" ry="4" fill="#0f172a" opacity=".08"/>
      <path class="toon-mouse-tail" d="M24 62 Q4 62 6 42 Q8 28 20 32" stroke="#a8a29e" stroke-width="4" fill="none" stroke-linecap="round"/>
      <g class="toon-leg toon-leg-a"><ellipse cx="40" cy="80" rx="9" ry="5" fill="#6b7280"/></g>
      <ellipse cx="50" cy="60" rx="30" ry="20" fill="#9ca3af"/>
      <ellipse cx="56" cy="66" rx="18" ry="10" fill="#e5e7eb"/>
      <g class="toon-leg toon-leg-b"><ellipse cx="66" cy="80" rx="9" ry="5" fill="#6b7280"/></g>
      <circle cx="66" cy="23" r="16" fill="#9ca3af"/><circle cx="66" cy="23" r="10" fill="#fbcfe8"/>
      <ellipse cx="82" cy="45" rx="22" ry="18" fill="#9ca3af"/>
      <ellipse cx="101" cy="49" rx="9" ry="6.5" fill="#9ca3af"/>
      <circle cx="109" cy="47.5" r="4" fill="#f472b6"/>
      <circle cx="85" cy="22" r="14" fill="#9ca3af"/><circle cx="85" cy="22" r="8.5" fill="#fbcfe8"/>
      <ellipse cx="91" cy="41" rx="4.2" ry="5.2" fill="#111827"/><circle cx="92.6" cy="39.2" r="1.5" fill="#fff"/>
      <path d="M97 55 q4 3 8 0" stroke="#374151" stroke-width="1.6" fill="none" stroke-linecap="round"/>
      <path d="M104 50 l15 -4 M104 53 l15 2" stroke="#4b5563" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M86 62 L114 70 L86 78 Z" fill="#facc15"/>
      <circle cx="94" cy="69" r="2.4" fill="#eab308"/><circle cx="101" cy="72" r="1.7" fill="#eab308"/><circle cx="92" cy="74.5" r="1.4" fill="#eab308"/>
    </svg>`;

  const PUPPY_SVG = `
    <svg viewBox="0 0 230 136" aria-hidden="true">
      <ellipse cx="118" cy="128" rx="104" ry="7" fill="#0f172a" opacity=".08"/>
      <path class="toon-pup-tail" d="M30 92 Q8 76 16 58" stroke="#fef3c7" stroke-width="12" stroke-linecap="round" fill="none"/>
      <g class="toon-pup-body">
        <ellipse cx="98" cy="96" rx="74" ry="30" fill="#fef3c7"/>
        <ellipse cx="80" cy="86" rx="24" ry="14" fill="#b45309" opacity=".85"/>
        <ellipse cx="124" cy="104" rx="12" ry="8" fill="#b45309" opacity=".6"/>
      </g>
      <ellipse cx="60" cy="122" rx="20" ry="8" fill="#fde68a"/>
      <ellipse cx="156" cy="122" rx="22" ry="8" fill="#fde68a"/>
      <ellipse cx="180" cy="120" rx="22" ry="9" fill="#fef3c7"/>
      <path d="M150 104 Q164 116 184 117" stroke="#e11d48" stroke-width="6" fill="none" stroke-linecap="round"/>
      <circle cx="168" cy="116" r="5" fill="#facc15"/>
      <circle cx="178" cy="90" r="33" fill="#fef3c7"/>
      <ellipse cx="190" cy="82" rx="11" ry="10" fill="#b45309" opacity=".8"/>
      <path d="M156 70 Q134 82 142 116 Q160 112 164 82 Z" fill="#92400e"/>
      <g class="toon-pup-eyes-closed"><path d="M168 86 q5 4 10 0 M184 84 q5 4 10 0" stroke="#451a03" stroke-width="2.6" fill="none" stroke-linecap="round"/></g>
      <g class="toon-pup-eyes-open"><circle cx="173" cy="84" r="4.5" fill="#1f2937"/><circle cx="189" cy="82" r="4.5" fill="#1f2937"/><circle cx="174.5" cy="82.5" r="1.4" fill="#fff"/><circle cx="190.5" cy="80.5" r="1.4" fill="#fff"/></g>
      <ellipse cx="207" cy="96" rx="7.5" ry="5.5" fill="#1f2937"/>
      <path d="M206 102 q-4 6 -11 4" stroke="#451a03" stroke-width="2.2" fill="none" stroke-linecap="round"/>
      <path class="toon-pup-tongue" d="M198 105 q3 9 8 2 z" fill="#fb7185"/>
    </svg>`;

  const HOLE_SVG = `
    <svg viewBox="0 0 140 112" aria-hidden="true">
      <path d="M8 112 L8 62 Q8 8 70 8 Q132 8 132 62 L132 112 Z" fill="#78350f" opacity=".35"/>
      <path d="M18 112 L18 64 Q18 18 70 18 Q122 18 122 64 L122 112 Z" fill="#1f2937"/>
      <path d="M30 112 L30 70 Q30 32 70 30" stroke="#374151" stroke-width="3" fill="none" opacity=".6"/>
    </svg>`;

  // ---------------------------------------------------------------- Lines
  const IDLE_LINES = [
    'Squeak! All quiet in the care office.',
    'I check Log My Care every 10 minutes. Cheese break after.',
    'Every review done is a resident looked after.',
    'Marmalade has not caught me yet. Not even once.',
  ];

  function statusLines(stats) {
    if (!stats) return IDLE_LINES;
    const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
    const lines = [];
    if (stats.incidents_needs_review) lines.push(`${plural(stats.incidents_needs_review, 'incident')} waiting for review.`);
    if (stats.support_plans_overdue) lines.push(`${plural(stats.support_plans_overdue, 'support plan')} overdue for review.`);
    if (stats.goals_overdue) lines.push(`${plural(stats.goals_overdue, 'goal review')} overdue.`);
    if (stats.future_plans_overdue) lines.push(`${plural(stats.future_plans_overdue, 'future plan')} past the review date.`);
    if (!lines.length) lines.push('Everything is up to date. Time for cheese!');
    return lines.concat(IDLE_LINES);
  }

  function boardTotal(stats) {
    if (!stats) return 0;
    return (stats.incidents_needs_review || 0) + (stats.incidents_open || 0) + (stats.support_plans_overdue || 0) +
           (stats.goals_overdue || 0) + (stats.future_plans_overdue || 0);
  }

  // ---------------------------------------------------------------- Build scene
  const scene = document.createElement('div');
  scene.className = 'toon-scene' + (reduceMotion ? ' reduce-motion' : '');
  scene.setAttribute('aria-hidden', 'true');
  scene.innerHTML = `
    <div class="toon-hole" id="toon-hole" title="Knock knock - click for Pip">
      ${HOLE_SVG}
      <div class="toon-peek">${MOUSE_SVG}</div>
      <div class="toon-bubble toon-bubble-hole" id="toon-hole-bubble"></div>
    </div>
    <div class="toon-puppy" id="toon-puppy" title="Biscuit is napping - click to wake him">
      <div class="toon-zzz"><span>z</span><span>z</span><span>Z</span></div>
      ${PUPPY_SVG}
      <div class="toon-bubble toon-bubble-puppy" id="toon-puppy-bubble"></div>
    </div>
    <div class="toon-runner toon-mouse" id="toon-mouse">${MOUSE_SVG}</div>
    <div class="toon-runner toon-cat" id="toon-cat">
      ${CAT_SVG}
      <div class="toon-bubble toon-bubble-cat" id="toon-cat-bubble"></div>
    </div>
  `;
  document.body.prepend(scene);

  const toggle = document.createElement('button');
  toggle.className = 'toon-toggle';
  toggle.type = 'button';
  document.body.appendChild(toggle);

  const hole = scene.querySelector('#toon-hole');
  const holeBubble = scene.querySelector('#toon-hole-bubble');
  const puppy = scene.querySelector('#toon-puppy');
  const puppyBubble = scene.querySelector('#toon-puppy-bubble');
  const mouse = scene.querySelector('#toon-mouse');
  const cat = scene.querySelector('#toon-cat');
  const catBubble = scene.querySelector('#toon-cat-bubble');

  let latestStats = null;
  let lineIndex = 0;
  let chasing = false;
  const timers = {};

  // ---------------------------------------------------------------- Behaviour
  function bubble(el, text, ms) {
    el.textContent = text;
    el.classList.add('show');
    clearTimeout(timers[el.id]);
    timers[el.id] = setTimeout(() => el.classList.remove('show'), ms);
  }

  function restart(el, cls) {
    el.classList.remove(cls);
    void el.offsetWidth; // reflow so the animation plays again
    el.classList.add(cls);
  }

  function peekPip(text) {
    restart(hole, 'peeking');
    setTimeout(() => bubble(holeBubble, text, 3800), 450);
  }

  function nextLine() {
    const lines = statusLines(latestStats);
    return lines[lineIndex++ % lines.length];
  }

  function wakeBiscuit(text) {
    puppy.classList.add('awake');
    bubble(puppyBubble, text, 4200);
    clearTimeout(timers.puppyWake);
    timers.puppyWake = setTimeout(() => puppy.classList.remove('awake'), 4600);
  }

  function chase() {
    if (chasing || reduceMotion || scene.classList.contains('hidden')) return;
    chasing = true;
    cat.classList.remove('leaving');
    restart(mouse, 'running');
    restart(cat, 'running');
    // Pip reaches the hole; Marmalade skids to a stop and complains, then wanders off
    setTimeout(() => peekPip('Too slow, Marmalade!'), 4300);
    setTimeout(() => bubble(catBubble, 'Hmph. Next time, Pip!', 2400), 4700);
    setTimeout(() => { cat.classList.add('leaving'); }, 7200);
    setTimeout(() => {
      mouse.classList.remove('running');
      cat.classList.remove('running', 'leaving');
      chasing = false;
    }, 9800);
  }

  function setHidden(hidden) {
    scene.classList.toggle('hidden', hidden);
    toggle.textContent = hidden ? 'Show cartoons' : 'Hide cartoons';
    toggle.setAttribute('aria-pressed', String(!hidden));
    storageSet(STORAGE_KEY, hidden ? '1' : '0');
  }

  hole.addEventListener('click', () => peekPip(nextLine()));
  puppy.addEventListener('click', () => wakeBiscuit(`Woof! ${nextLine()}`));
  toggle.addEventListener('click', () => setHidden(!scene.classList.contains('hidden')));

  // app.js fires this every time new dashboard data is rendered
  window.addEventListener('dashboard:updated', (e) => {
    const first = latestStats === null;
    latestStats = e.detail && e.detail.stats;
    if (scene.classList.contains('hidden')) return;
    if (first) {
      setTimeout(() => peekPip(statusLines(latestStats)[0]), 1500);
    } else {
      const total = boardTotal(latestStats);
      wakeBiscuit(total ? `Woof! Fresh data: ${total} item${total === 1 ? '' : 's'} on the board.` : 'Woof! Fresh data. All clear!');
    }
  });

  setHidden(storageGet(STORAGE_KEY) === '1');

  // First chase shortly after load, then every 35-60 seconds
  setTimeout(chase, 5000);
  (function scheduleChase() {
    setTimeout(() => { chase(); scheduleChase(); }, 35000 + Math.random() * 25000);
  })();
})();
