// The hall: 200 dots, one per student. Before the section is seen they sit
// scattered and grey (a hall arriving); when it comes into view they snap
// into the 20 x 10 register in reading order, turning "present" green as
// each lands, while the count beside them ticks up to 200. About 2 s, once.
//
// The finished grid is the markup. This script scatters it with paused Web
// Animations (so the scatter shows before the trigger), then plays them.
// Reduced motion, no IntersectionObserver or no script: the grid just shows.

(function () {
  window.suaamsHall = true; // tells the <head> fallback this script arrived

  var section = document.querySelector('.hall');
  var grid = document.getElementById('hall');
  if (!section || !grid) return;
  var dots = Array.prototype.slice.call(grid.children);
  var counter = section.querySelector('.hall-n');
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

  if (reduce.matches || !('IntersectionObserver' in window) || !grid.animate) {
    section.classList.add('ready', 'played');
    return;
  }

  var EASE_OUT = 'cubic-bezier(.16, 1, .3, 1)';
  var STEP = 7;      // ms between one student and the next: 200 dots in 1.4 s
  var TRAVEL = 560;  // ms for one dot to reach its seat
  var css = getComputedStyle(document.documentElement);
  var grey = css.getPropertyValue('--faint').trim();
  var green = css.getPropertyValue('--present').trim();
  var anims = [];
  var played = false;

  // A fixed pseudo-random scatter (same every visit), so the "hall
  // arriving" looks the same in every screenshot and review.
  function rng(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      var t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }

  // Build paused animations from a scattered start to each dot's seat.
  // Rebuilt on resize until it has played, because the seats move.
  function build() {
    anims.forEach(function (a) { a.cancel(); });
    var rand = rng(200);
    var w = grid.offsetWidth, h = grid.offsetHeight;
    anims = dots.map(function (dot, i) {
      // Scatter across the grid's box, spilling a little past its edges.
      var x = (rand() * 1.3 - .15) * w - dot.offsetLeft;
      var y = (rand() * 1.6 - .3) * h - dot.offsetTop;
      var a = dot.animate([
        { transform: 'translate(' + x + 'px,' + y + 'px) scale(.8)', opacity: .5, backgroundColor: grey },
        { offset: .65, backgroundColor: grey },
        { transform: 'none', opacity: 1, backgroundColor: green }
      ], { delay: i * STEP, duration: TRAVEL, easing: EASE_OUT, fill: 'both' });
      a.pause();
      return a;
    });
    counter.textContent = '0';
    section.classList.add('ready');
  }

  // The count follows the dots: each one counts when it turns green.
  function tick(start) {
    var elapsed = performance.now() - start;
    var landed = Math.floor((elapsed - TRAVEL * .65) / STEP) + 1;
    counter.textContent = Math.max(0, Math.min(dots.length, landed));
    if (landed < dots.length) requestAnimationFrame(function () { tick(start); });
  }

  function play() {
    played = true;
    anims.forEach(function (a) { a.play(); });
    tick(performance.now());
    Promise.all(anims.map(function (a) { return a.finished; })).then(function () {
      // Hand the end state back to the markup.
      counter.textContent = dots.length;
      section.classList.add('played');
      anims.forEach(function (a) { a.cancel(); });
    }, function () {});
  }

  build();

  var resizeTimer;
  window.addEventListener('resize', function () {
    if (played) return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(build, 150);
  });

  var io = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) { io.disconnect(); play(); }
  }, { threshold: 0.4 });
  io.observe(grid);
})();
