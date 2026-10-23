// "How it works": the phone beside the steps shows each step's real screen.
//
// On desktop the phone stays in place (position: sticky) while the three
// steps scroll past. Whichever step crosses the middle of the window becomes
// active: the phone crossfades to its screen (CSS, 200 ms) and its time
// marker stays indigo. On narrower screens the phone isn't sticky, so it
// keeps step 1's screen and nothing switches.

(function () {
  var list = document.getElementById('steps');
  var figure = document.getElementById('step-phone');
  if (!list || !figure || !('IntersectionObserver' in window)) return;
  var screen = figure.querySelector('.phone-screen');
  var shots = screen.querySelectorAll('img[data-step]');
  var wide = window.matchMedia('(min-width: 901px)');

  function activate(step) {
    if (!wide.matches) {
      // Not sticky here: no switching and no dimmed markers (they'd point
      // at step 1 while the visitor reads step 2 or 3).
      delete list.dataset.active;
      delete figure.dataset.active;
      delete screen.dataset.active;
      return;
    }
    if (list.dataset.active === step) return;
    list.dataset.active = step;
    figure.dataset.active = step;
    screen.dataset.active = step;
    // Only the visible screen is exposed to screen readers.
    shots.forEach(function (img) {
      if (img.dataset.step === step) img.removeAttribute('aria-hidden');
      else img.setAttribute('aria-hidden', 'true');
    });
  }

  // A thin band across the middle of the window: a step is active while
  // its row is in that band.
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) activate(e.target.dataset.step);
    });
  }, { rootMargin: '-45% 0px -45% 0px' });
  list.querySelectorAll('li[data-step]').forEach(function (li) { io.observe(li); });

  wide.addEventListener && wide.addEventListener('change', function () { activate('1'); });
})();
