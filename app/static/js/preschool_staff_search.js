document.querySelectorAll('[data-staff-search]').forEach((root) => {
  const input = root.querySelector('input[type="search"]');
  const selectedId = root.querySelector('input[name="user_id"]');
  const results = root.querySelector('[role="listbox"]');
  results.classList.remove('position-absolute', 'start-0', 'end-0');
  document.body.appendChild(results);
  let searchTimer;
  let requestNumber = 0;

  const placeResults = () => {
    const bounds = input.getBoundingClientRect();
    results.style.setProperty('position', 'fixed', 'important');
    results.style.setProperty('left', `${bounds.left}px`, 'important');
    results.style.setProperty('top', `${bounds.bottom + 2}px`, 'important');
    results.style.setProperty('width', `${bounds.width}px`, 'important');
    results.style.setProperty('z-index', '2000', 'important');
  };

  const closeResults = () => {
    results.classList.add('d-none');
    input.setAttribute('aria-expanded', 'false');
  };

  const showResults = (people) => {
    results.replaceChildren();
    if (!people.length) {
      const empty = document.createElement('div');
      empty.className = 'list-group-item text-muted small';
      empty.textContent = 'Сотрудник не найден';
      results.appendChild(empty);
    } else {
      people.forEach((person) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'list-group-item list-group-item-action text-start';
        option.dataset.userId = String(person.id);
        option.dataset.userLabel = person.label;
        option.setAttribute('role', 'option');
        option.textContent = person.label;
        results.appendChild(option);
      });
    }
    placeResults();
    results.classList.remove('d-none');
    input.setAttribute('aria-expanded', 'true');
  };

  input.addEventListener('input', () => {
    selectedId.value = '';
    clearTimeout(searchTimer);
    const query = input.value.trim();
    const currentRequest = ++requestNumber;
    if (!query.length) {
      closeResults();
      return;
    }
    searchTimer = setTimeout(async () => {
      try {
        const url = new URL(root.dataset.searchUrl, window.location.href);
        url.searchParams.set('q', query);
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) throw new Error('Search unavailable');
        const people = await response.json();
        if (currentRequest === requestNumber) showResults(people);
      } catch (_error) {
        if (currentRequest === requestNumber) closeResults();
      }
    }, 200);
  });

  results.addEventListener('click', (event) => {
    const option = event.target.closest('[data-user-id]');
    if (!option) return;
    input.value = option.dataset.userLabel;
    selectedId.value = option.dataset.userId;
    closeResults();
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeResults();
    if (event.key === 'ArrowDown' && !results.classList.contains('d-none')) {
      event.preventDefault();
      results.querySelector('[data-user-id]')?.focus();
    }
  });

  document.addEventListener('click', (event) => {
    if (!root.contains(event.target) && !results.contains(event.target)) closeResults();
  });

  window.addEventListener('scroll', () => {
    if (!results.classList.contains('d-none')) placeResults();
  }, true);
  window.addEventListener('resize', () => {
    if (!results.classList.contains('d-none')) placeResults();
  });

  root.closest('form')?.addEventListener('submit', (event) => {
    if (selectedId.value) return;
    if (!input.required && !input.value.trim()) return;
    event.preventDefault();
    input.setCustomValidity('Выберите сотрудника из результатов поиска.');
    input.reportValidity();
    input.setCustomValidity('');
  });
});
