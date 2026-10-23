// The one piece of motion on the site: the tap, played once on load.
//
// The finished state is the page's default markup, so with no script, a
// failed load or reduced motion, visitors see the complete stage. This
// script only rewinds it and plays it forward:
//   1. the 32-character code fills in, payload then signature;
//   2. the indigo leaders draw into and out of the photo (CSS);
//   3. the newest line lands on the register as the count ticks 186 -> 187.
// "Replay the tap" runs it again (handy when presenting the page).

(function () {
  // Optional images (the reader photo before it's uploaded, screenshots)
  // remove themselves when missing, so the frame behind them shows instead
  // of a broken-image icon. Replaces the old inline onerror handlers.
  document.querySelectorAll('img[data-optional]').forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) { img.remove(); return; }
    img.addEventListener('error', function () { img.remove(); });
  });

  var stage = document.getElementById('stage');
  if (!stage) return;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

  var token = stage.querySelector('.token');
  var parts = [token.querySelector('.payload'), token.querySelector('.sig')];
  var full = parts.map(function (el) { return el.textContent; });
  var count = stage.querySelector('.count-now');
  var finalCount = parseInt(count.textContent, 10);
  var replay = document.getElementById('replay');
  var timers = [];

  function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
  function clear() { timers.forEach(clearTimeout); timers = []; }

  function finish() {
    clear();
    parts.forEach(function (el, i) { el.textContent = full[i]; });
    token.classList.remove('is-typing');
    count.textContent = finalCount;
    stage.classList.remove('is-ready');
    stage.classList.add('is-played');
  }

  function play() {
    if (reduce.matches) { finish(); return; }
    clear();
    // Rewind: empty code, leaders retracted, newest line and count held back.
    stage.classList.remove('is-played');
    stage.classList.add('is-ready');
    parts.forEach(function (el) { el.textContent = ''; });
    count.textContent = finalCount - 1;
    token.classList.add('is-typing');
    var cursor = document.createElement('span');
    cursor.className = 'cursor';
    cursor.setAttribute('aria-hidden', 'true');

    // 32 characters at 22 ms each: about 0.7 s for the whole code.
    var i = 0, step = 22, total = full[0].length + full[1].length;
    for (var n = 1; n <= total; n++) {
      later(function () {
        i++;
        var a = Math.min(i, full[0].length);
        parts[0].textContent = full[0].slice(0, a);
        parts[1].textContent = full[1].slice(0, Math.max(0, i - full[0].length));
        (i < full[0].length ? parts[0] : parts[1]).after(cursor);
      }, 250 + n * step);
    }
    var done = 250 + total * step;
    later(function () {
      cursor.remove();
      token.classList.remove('is-typing');
      // Force the rewound state to paint before the transition starts.
      void stage.offsetWidth;
      stage.classList.add('is-played');
    }, done + 80);
    // The count ticks as the new log line lands (its CSS delay is .55 s).
    later(function () {
      count.textContent = finalCount;
      stage.classList.remove('is-ready');
    }, done + 80 + 650);
  }

  if (replay) {
    replay.hidden = false;
    replay.addEventListener('click', play);
  }
  reduce.addEventListener && reduce.addEventListener('change', finish);
  // Play when the stage first comes into view, not on load: on a phone the
  // stage starts below the first screen, and a load-time play would finish
  // before anyone scrolled to it. Until then it shows its finished state.
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) { io.disconnect(); play(); }
    }, { threshold: 0.35 });
    io.observe(stage);
  } else {
    play();
  }
})();
