// The one piece of motion on the first screen: the tap, in three beats.
//
//   1  confirm   the phone shows the ID card's Check in button; the
//                reader shows the class and "TAP your phone"
//   2  tap       the phone listens for the reader; the reader beeps (one
//                indigo flash) and shows WAIT, "Checking..."
//   3  marked    "Attendance verified" on the phone; DONE, the student's
//                name and "marked present" on the reader
//
// Pacing: slow where the person acts (beat 1), quicker where the system
// answers (beat 2). It plays once, when the beats list is fully in view,
// and Replay plays it again.
//
// The markup is the finished state (data-beat="3"). The inline script in
// <head> adds .motion before first paint, and styles.css shows beat 1
// until this script marks the .tap .armed. All this script changes is
// data-beat; styles.css draws each beat. With reduced motion the screens
// still change, as fades, and nothing travels.

(function () {
  window.suaamsHero = true; // tells the <head> fallback this script arrived

  // Optional images (the screenshots, the reader photo once it exists)
  // remove themselves when missing, so the frame behind them shows instead
  // of a broken-image icon.
  document.querySelectorAll('img[data-optional]').forEach(function (img) {
    if (img.complete && img.naturalWidth === 0) { img.remove(); return; }
    img.addEventListener('error', function () { img.remove(); });
  });

  var tap = document.getElementById('tap');
  if (!tap) return;
  var root = document.documentElement;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var replay = document.getElementById('replay');
  var ring = tap.querySelector('.tap-ring');

  // How long beats 1 and 2 stay up (ms). Beat 3 is the end state.
  var CONFIRM = 1600;
  var TAP = 1300;
  var timers = [];

  function show(beat) { tap.dataset.beat = String(beat); }

  function play() {
    timers.forEach(clearTimeout);
    timers = [];
    root.classList.remove('motion-done');
    tap.classList.add('armed');
    show(1);
    timers.push(setTimeout(function () {
      show(2);
      if (ring && ring.animate) {
        ring.animate([{ opacity: 0 }, { opacity: 1, offset: .3 }, { opacity: 0 }],
          { duration: reduce.matches ? 400 : 300, easing: 'ease' });
      }
    }, CONFIRM));
    timers.push(setTimeout(function () { show(3); }, CONFIRM + TAP));
  }

  if (replay) {
    replay.hidden = false;
    replay.addEventListener('click', play);
  }

  // If the 3 s fallback already showed the finished tap, leave it; Replay
  // can still play it.
  if (root.classList.contains('motion-done') || !('IntersectionObserver' in window)) {
    tap.classList.add('armed');
    return;
  }
  // Hold beat 1 now (same as the CSS rewind), then play when the beats
  // list is on screen: the phone and reader sit above it (phones) or
  // beside it (desktop), so all three are in view together. 0.9, not 1:
  // subpixel heights can leave "fully visible" half a pixel short forever.
  tap.classList.add('armed');
  show(1);
  var io = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) { io.disconnect(); play(); }
  }, { threshold: 0.9, rootMargin: '0px 0px -8% 0px' });
  io.observe(tap.querySelector('.beats'));
})();
