(() => {
  const details = document.getElementById('summary-details');
  if (!details) return;
  const openTarget = (id, smooth = true) => {
    const target = document.getElementById(id);
    if (!target || !details.contains(target)) return;
    details.open = true;
    requestAnimationFrame(() => target.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' }));
  };
  document.querySelectorAll('[data-summary-target]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      const id = link.getAttribute('data-summary-target');
      history.replaceState(null, '', `#${id}`);
      openTarget(id);
    });
  });
  if (location.hash.startsWith('#section-')) openTarget(location.hash.slice(1), false);
})();
