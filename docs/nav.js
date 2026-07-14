(function () {
  const btn = document.getElementById('hamburger');
  const menu = document.getElementById('menu');
  if (!btn || !menu) return;

  // 標記當前頁面
  const path = window.location.pathname;
  const items = menu.querySelectorAll('.menu-item');
  items.forEach((a) => {
    const href = a.getAttribute('href');
    const target = href.replace('./', '');
    const isHome = target === '' || target === 'index.html';
    if (isHome) {
      const bareDirMatch = window.TARGET_ID && path.endsWith('/' + window.TARGET_ID);
      if (path.endsWith('/') || path.endsWith('/index.html') || bareDirMatch) {
        a.classList.add('current');
      }
    } else if (path.endsWith('/' + target)) {
      a.classList.add('current');
    }
  });

  function open() {
    menu.hidden = false;
    btn.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
  }
  function close() {
    menu.hidden = true;
    btn.classList.remove('open');
    btn.setAttribute('aria-expanded', 'false');
  }

  btn.setAttribute('aria-expanded', 'false');
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (menu.hidden) open();
    else close();
  });

  document.addEventListener('click', (e) => {
    if (!menu.hidden && !menu.contains(e.target) && e.target !== btn) close();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });
})();
