document.addEventListener('DOMContentLoaded', () => {
  const descriptionToggle = document.querySelector('[data-description-toggle]');
  if (descriptionToggle) {
    const descriptionView = document.querySelector('[data-description-view]');
    const descriptionEdit = document.querySelector('[data-description-edit]');
    const descriptionInput = descriptionEdit.querySelector('textarea');
    descriptionToggle.addEventListener('click', () => {
      const editing = descriptionToggle.getAttribute('aria-expanded') === 'true';
      descriptionView.hidden = !editing;
      descriptionEdit.hidden = editing;
      descriptionToggle.setAttribute('aria-expanded', String(!editing));
      descriptionToggle.innerHTML = editing
        ? '<i class="bi bi-pencil" aria-hidden="true"></i> Редактировать'
        : 'Отменить';
      if (editing) descriptionInput.value = descriptionInput.defaultValue;
      else descriptionInput.focus();
    });
  }

  const previewModal = document.getElementById('appealAttachmentModal');
  if (previewModal) {
    const frame = previewModal.querySelector('.appeals-attachment-frame');
    const title = previewModal.querySelector('#appealAttachmentModalTitle');
    const download = previewModal.querySelector('[data-preview-download]');
    previewModal.addEventListener('show.bs.modal', (event) => {
      const button = event.relatedTarget;
      if (!button) return;
      const filename = button.dataset.previewTitle || 'Просмотр файла';
      title.textContent = filename;
      frame.title = `Содержимое файла ${filename}`;
      frame.src = button.dataset.previewUrl || 'about:blank';
      download.href = button.dataset.downloadUrl || '#';
    });
    previewModal.addEventListener('hidden.bs.modal', () => {
      frame.src = 'about:blank';
      download.href = '#';
    });
  }

  const picker = document.querySelector('[data-user-picker]');
  if (!picker) return;

  const selected = document.querySelector('[data-selected-users]');
  const options = picker.querySelector('[data-user-options]');
  const search = picker.querySelector('[data-user-search-input]');
  const noResults = picker.querySelector('[data-no-results]');

  const normalize = (text) => (text || '').toLowerCase().replaceAll('ё', 'е').trim();
  const refresh = () => {
    const query = normalize(search.value);
    let visible = 0;
    options.querySelectorAll('.appeal-user-option').forEach((item) => {
      const matches = normalize(item.dataset.userSearch).includes(query);
      item.hidden = !matches;
      if (matches) visible += 1;
    });
    noResults.hidden = visible !== 0;
    const empty = selected.querySelector('[data-empty-users]');
    if (empty) empty.hidden = selected.querySelectorAll('.appeal-user-option').length !== 0;
  };

  document.querySelectorAll('input[name="responsible_user_ids"]').forEach((input) => {
    input.addEventListener('change', () => {
      const item = input.closest('.appeal-user-option');
      item.classList.toggle('is-selected', input.checked);
      item.querySelector('.appeal-user-option-action').textContent = input.checked ? 'Назначен' : 'Добавить';
      (input.checked ? selected : options).appendChild(item);
      refresh();
    });
  });
  search.addEventListener('input', refresh);
  refresh();
});
