(() => {
  const dashboard = document.querySelector('.department-summary-dashboard');
  const host = dashboard?.querySelector('[data-summary-details-host]');
  if (!host) return;

  const links = [...dashboard.querySelectorAll('.department-kpi, .department-direction')];
  const cache = new Map();
  let visibleSection = dashboard.dataset.summaryCurrent || '';
  let controller = null;
  let requestNumber = 0;

  const sectionOf = (link) => new URL(link.href, window.location.href).searchParams.get('section') || '';
  const updateSelection = () => {
    links.forEach((link) => {
      const selected = visibleSection !== '' && sectionOf(link) === visibleSection;
      link.classList.toggle('is-selected', selected);
      link.setAttribute('aria-expanded', String(selected));
      link.setAttribute('aria-controls', 'summary-details-host');
      if (selected) link.setAttribute('aria-current', 'true');
      else link.removeAttribute('aria-current');
    });
  };
  const scrollToDetails = () => {
    requestAnimationFrame(() => host.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  };
  const overviewUrl = () => {
    const url = new URL(window.location.href);
    url.searchParams.delete('section');
    if (url.hash === '#summary-details') url.hash = '';
    return url;
  };
  const closeDetails = (updateHistory = true) => {
    controller?.abort();
    controller = null;
    requestNumber += 1;
    visibleSection = '';
    host.replaceChildren();
    updateSelection();
    if (updateHistory) history.pushState(null, '', overviewUrl());
  };
  const showDetails = async (section, href, updateHistory = true, scroll = true) => {
    controller?.abort();
    controller = null;
    const currentRequest = ++requestNumber;
    visibleSection = section;
    updateSelection();
    if (updateHistory) history.pushState(null, '', href);

    if (cache.has(section)) {
      host.innerHTML = cache.get(section);
      if (scroll) scrollToDetails();
      return;
    }

    host.innerHTML = '<div class="department-detail-loading" role="status">Загрузка данных…</div>';
    if (scroll) scrollToDetails();
    controller = new AbortController();
    try {
      const response = await fetch(href, {
        headers: { 'X-Department-Summary': 'details' },
        signal: controller.signal,
        credentials: 'same-origin',
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error('Не удалось загрузить данные');
      const html = await response.text();
      if (!html.includes('id="summary-details"')) throw new Error('Нет данных для отображения');
      cache.set(section, html);
      if (currentRequest === requestNumber && visibleSection === section) host.innerHTML = html;
    } catch (error) {
      if (error.name !== 'AbortError' && currentRequest === requestNumber) {
        host.innerHTML = '<div class="department-detail-loading" role="alert">Не удалось загрузить данные. Закройте показатель и откройте его снова.</div>';
      }
    } finally {
      if (currentRequest === requestNumber) controller = null;
    }
  };

  if (visibleSection && host.innerHTML.trim()) cache.set(visibleSection, host.innerHTML);
  updateSelection();
  dashboard.addEventListener('click', (event) => {
    const closeLink = event.target.closest('[data-summary-close]');
    if (closeLink && dashboard.contains(closeLink)) {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      closeDetails();
      return;
    }
    const link = event.target.closest('.department-kpi, .department-direction');
    if (!link || !dashboard.contains(link)) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const section = sectionOf(link);
    if (!section) return;
    event.preventDefault();
    if (section === visibleSection) closeDetails();
    else showDetails(section, link.href);
  });
  window.addEventListener('popstate', () => {
    const section = new URL(window.location.href).searchParams.get('section') || '';
    if (section === visibleSection) return;
    if (!section) closeDetails(false);
    else showDetails(section, window.location.href, false, false);
  });
})();
