(function () {
  const back = document.querySelector('[data-workspace-back]');
  if (!back) return;

  const key = 'altair-workspace-history-v1';
  const current = location.pathname + location.search;
  let pages = [];
  try {
    pages = JSON.parse(sessionStorage.getItem(key) || '[]');
    if (!Array.isArray(pages)) pages = [];
  } catch (_) {
    pages = [];
  }
  if (pages[pages.length - 1] !== current) pages.push(current);
  pages = pages.slice(-30);
  try { sessionStorage.setItem(key, JSON.stringify(pages)); } catch (_) { /* fallback link remains available */ }

  back.addEventListener('click', function (event) {
    let previous = pages.length > 1 ? pages[pages.length - 2] : null;
    if (!previous && document.referrer) {
      try {
        const referring = new URL(document.referrer);
        if (referring.origin === location.origin) previous = referring.pathname + referring.search;
      } catch (_) { /* fallback link remains available */ }
    }
    if (!previous || previous === current || !previous.startsWith('/') || previous.startsWith('//')) return;
    event.preventDefault();
    if (pages.length > 1) {
      pages.pop();
      try { sessionStorage.setItem(key, JSON.stringify(pages)); } catch (_) { /* navigation still works */ }
    }
    location.assign(previous);
  });
})();
