// The one piece of motion on the site: the tap, in three beats.
//
//   verify   the phone confirms its owner (fingerprint line, then its check)
//   tap      the signed code arrives whole, then crosses to the reader:
//            leader IN -> photo, and the reader's indigo "beep"
//   recorded leader photo -> OUT, the register slides down one row, the
//            count's last digit rolls 6 -> 7, the live dot blinks once
//
// Pacing: slow where the person acts (verify), fast where the system
// responds (tap, record). The tap leader is the quickest beat on screen
// because the real exchange is about 0.1 s.
//
// The markup is the finished state. The inline script in <head> adds
// .motion before first paint, and styles.css shows the rewound state until
// this script marks the stage .played. One Web Animations timeline drives
// it, so Replay can cancel it cleanly. With reduced motion the same beats
// play as opacity fades only: no movement, no clip, no roll.

(function () {
  window.suaamsHero = true; // tells the <head> fallback this script arrived

  // Optional images (the reader photo before it's uploaded, screenshots)
  // remove themselves when missing, so the frame behind them shows instead
  // of a broken-image icon.
  document.querySelectorAll('img[data-optional]').forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) { img.remove(); return; }
    img.addEventListener('error', function () { img.remove(); });
  });

  var stage = document.getElementById('stage');
  if (!stage) return;
  var root = document.documentElement;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var replay = document.getElementById('replay');

  // If the 3 s fallback already showed the finished stage, leave it; Replay
  // can still play it.
  var autoplay = !root.classList.contains('motion-done');

  var EASE_OUT = 'cubic-bezier(.16, 1, .3, 1)';
  var EASE_MOVE = 'cubic-bezier(.77, 0, .175, 1)';

  var q = function (sel) { return stage.querySelector(sel); };
  var el = {
    verify: q('.verify'),
    ok: q('.verify .ok'),
    payload: q('.token .payload'),
    sig: q('.token .sig'),
    leaderIn: q('.stage-col:first-child .leader'),
    ring: q('.photo-ring'),
    leaderOut: q('.stage-col:last-child .leader'),
    log: q('.log'),
    newRow: q('.log li:first-child'),
    oldRow: q('.log li:last-child'),
    digit: q('.roll-strip'),
    dot: q('.live')
  };
  var running = [];

  // [element, keyframes, start ms, duration ms, easing]
  function fullTimeline() {
    var shut = 'inset(0 100% 0 0)', open = 'inset(0 0 0 0)';
    return [
      // verify
      [el.verify, [{ opacity: 0, transform: 'scale(.96)' }, { opacity: 1, transform: 'none' }], 120, 220, EASE_OUT],
      [el.ok, [{ opacity: 0, transform: 'scale(.9)' }, { opacity: 1, transform: 'none' }], 380, 160, EASE_OUT],
      // the code arrives whole: payload, then signature 60 ms behind
      [el.payload, [{ clipPath: shut }, { clipPath: open }], 540, 220, EASE_OUT],
      [el.sig, [{ clipPath: shut }, { clipPath: open }], 600, 220, EASE_OUT],
      // tap: the fastest beat
      [el.leaderIn, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], 860, 180, EASE_MOVE],
      [el.ring, [{ opacity: 0 }, { opacity: 1, offset: .3 }, { opacity: 0 }], 960, 300, 'ease'],
      // recorded
      [el.leaderOut, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], 1040, 180, EASE_MOVE],
      [el.log, [{ transform: 'translateY(-36px)' }, { transform: 'none' }], 1220, 240, EASE_OUT],
      [el.newRow, [{ opacity: 0 }, { opacity: 1 }], 1220, 200, EASE_OUT],
      [el.oldRow, [{ opacity: 1 }, { opacity: 0 }], 1220, 160, EASE_OUT],
      [el.digit, [{ transform: 'translateY(0)' }, { transform: 'translateY(-50%)' }], 1240, 220, EASE_OUT],
      [el.dot, [{ opacity: .3 }, { opacity: 1 }], 1220, 200, 'ease']
    ];
  }

  // Reduced motion: the same order, as fades, with nothing travelling.
  function gentleTimeline() {
    var open = 'inset(0 0 0 0)';
    return [
      [el.verify, [{ opacity: 0 }, { opacity: 1 }], 0, 200, 'ease'],
      [el.ok, [{ opacity: 0 }, { opacity: 1 }], 0, 200, 'ease'],
      [el.payload, [{ clipPath: open, opacity: 0 }, { clipPath: open, opacity: 1 }], 150, 200, 'ease'],
      [el.sig, [{ clipPath: open, opacity: 0 }, { clipPath: open, opacity: 1 }], 150, 200, 'ease'],
      [el.leaderIn, [{ transform: 'none', opacity: 0 }, { transform: 'none', opacity: 1 }], 300, 200, 'ease'],
      [el.leaderOut, [{ transform: 'none', opacity: 0 }, { transform: 'none', opacity: 1 }], 300, 200, 'ease'],
      [el.log, [{ transform: 'none' }, { transform: 'none' }], 450, 0, 'linear'],
      [el.newRow, [{ opacity: 0 }, { opacity: 1 }], 450, 200, 'ease'],
      [el.digit, [{ transform: 'translateY(-50%)' }, { transform: 'translateY(-50%)' }], 450, 0, 'linear'],
      [el.dot, [{ opacity: .3 }, { opacity: 1 }], 450, 200, 'ease']
    ];
  }

  function cancelAll() {
    running.forEach(function (a) { a.cancel(); });
    running = [];
  }

  function play() {
    cancelAll();
    root.classList.remove('motion-done');
    stage.classList.remove('played'); // CSS rewinds the stage
    var beats = reduce.matches ? gentleTimeline() : fullTimeline();
    running = beats.filter(function (b) { return b[0]; }).map(function (b) {
      return b[0].animate(b[1], { delay: b[2], duration: b[3], easing: b[4], fill: 'both' });
    });
    Promise.all(running.map(function (a) { return a.finished; })).then(function () {
      // Hand the end state back to CSS, then drop the animations.
      stage.classList.add('played');
      cancelAll();
    }, function () { /* cancelled by a replay: the new run takes over */ });
  }

  // Replay: a short fade to the rewound state rather than a blank frame.
  function replayTap() {
    if (!stage.classList.contains('played') || reduce.matches) { play(); return; }
    var dyn = [el.verify, el.payload, el.sig, el.leaderIn, el.leaderOut, el.newRow];
    var fades = dyn.filter(Boolean).map(function (d) {
      return d.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 150, easing: 'ease', fill: 'forwards' });
    });
    fades[0].finished.then(function () {
      play();
      fades.forEach(function (f) { f.cancel(); });
    });
  }

  if (replay) {
    replay.hidden = false;
    replay.addEventListener('click', replayTap);
  }

  if (!autoplay || !('IntersectionObserver' in window)) {
    // No autoplay: show the finished stage (Replay still works).
    stage.classList.add('played');
    return;
  }
  // Play when the parts that move are in view, not just the stage box.
  // Wide (three columns in one row): 35% of the stage shows all of it.
  // 1000px and narrower the photo comes first and the stage is taller than
  // the screen, so "35% of the stage" was mostly photo and the tap played
  // below the fold. There, wait for the count (the last moving part) to be
  // fully in view, clear of the bottom edge: the IN column is above it, so
  // verify, the code and the register are all on screen together.
  var stacked = window.matchMedia('(max-width: 1000px)').matches;
  var target = stacked ? stage.querySelector('.count') : stage;
  var io = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) { io.disconnect(); play(); }
  }, stacked
    ? { threshold: 1, rootMargin: '0px 0px -10% 0px' }
    : { threshold: 0.35 });
  io.observe(target);
})();
