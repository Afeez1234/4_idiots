const themeToggle = document.getElementById('themeToggle');
const body = document.body;

function applyTheme(theme) {
  body.classList.remove('dark-theme', 'light-theme');
  body.classList.add(theme === 'light' ? 'light-theme' : 'dark-theme');
  if (themeToggle) {
    themeToggle.textContent = theme === 'light' ? '🌙 Dark Mode' : '☀️ Light Mode';
  }
}

const savedTheme = localStorage.getItem('dashboardTheme');
applyTheme(savedTheme || 'dark');

if (themeToggle) {
  themeToggle.addEventListener('click', function () {
    const nextTheme = body.classList.contains('light-theme') ? 'dark' : 'light';
    localStorage.setItem('dashboardTheme', nextTheme);
    applyTheme(nextTheme);
  });
}
