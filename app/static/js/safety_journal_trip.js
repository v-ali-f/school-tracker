(() => {
  const form = document.getElementById('trip-journal-compose');
  if (!form) return;
  const grade = document.getElementById('trip-grade');
  const classroom = document.getElementById('trip-class');
  const instruction = document.getElementById('trip-instruction');
  const instructionPreview = document.getElementById('trip-instruction-preview');
  const roster = document.getElementById('trip-roster');
  const selectedList = document.getElementById('trip-selected-list');
  const selectedInputs = document.getElementById('trip-selected-inputs');
  const selectedCount = document.getElementById('trip-selected-count');
  const selectAll = document.getElementById('trip-select-all');
  const preview = document.getElementById('trip-preview');
  const submit = document.getElementById('trip-submit');
  const message = document.getElementById('trip-choice-message');
  const selected = new Map(JSON.parse(form.dataset.selectedStudents || '[]').map(item => [String(item.id), item]));
  let currentRoster = [];
  let instructions = [];
  let requestNumber = 0;
  let previewReady = false;
  let previewUrl = '';

  const invalidate = () => { previewReady = false; refresh(); };
  const refresh = () => {
    selectedCount.textContent = String(selected.size);
    selectedList.replaceChildren();
    selectedInputs.replaceChildren();
    if (!selected.size) selectedList.textContent = 'Пока никто не выбран.';
    for (const item of [...selected.values()].sort((a, b) => a.class_name.localeCompare(b.class_name, 'ru') || a.name.localeCompare(b.name, 'ru'))) {
      const chip = document.createElement('span');
      chip.className = 'd-inline-flex align-items-center gap-1 border rounded px-2 py-1 me-1 mb-1';
      chip.append(document.createTextNode(`${item.name} · ${item.class_name} · ${item.birth_date || 'дата не указана'}`));
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn btn-link btn-sm p-0 text-danger';
      remove.setAttribute('aria-label', `Исключить ${item.name}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => { selected.delete(String(item.id)); drawRoster(); invalidate(); });
      chip.append(remove);
      selectedList.append(chip);
      const hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = 'child_ids';
      hidden.value = item.id;
      selectedInputs.append(hidden);
    }
    const complete = selected.size > 0 && instruction.value && form.checkValidity();
    preview.disabled = !complete;
    submit.disabled = !complete || !previewReady;
    selectAll.disabled = currentRoster.length === 0;
  };

  const drawRoster = () => {
    roster.replaceChildren();
    if (!currentRoster.length) {
      const row = roster.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 3;
      cell.className = 'registry-empty-row';
      cell.textContent = classroom.value ? 'В выбранном классе нет учеников.' : 'Выберите класс.';
    }
    for (const item of currentRoster) {
      const row = roster.insertRow();
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'form-check-input';
      checkbox.checked = selected.has(String(item.id));
      checkbox.setAttribute('aria-label', `Включить ${item.name}`);
      checkbox.addEventListener('change', () => {
        if (checkbox.checked) selected.set(String(item.id), item);
        else selected.delete(String(item.id));
        invalidate();
      });
      row.insertCell().append(checkbox);
      row.insertCell().textContent = item.name;
      row.insertCell().textContent = item.birth_date || 'Не указана';
    }
    refresh();
  };

  const fill = (element, items, placeholder, value, label = item => String(item), key = item => String(item)) => {
    element.replaceChildren(new Option(placeholder, ''));
    for (const item of items) element.add(new Option(label(item), key(item)));
    element.value = value || '';
    if (element.value !== String(value || '')) element.value = '';
    element.disabled = items.length === 0;
  };

  const updateInstruction = () => {
    const item = instructions.find(entry => entry.id === instruction.value);
    instructionPreview.disabled = !item || !item.preview_url;
    if (item) {
      instructionPreview.dataset.pdfUrl = item.preview_url;
      instructionPreview.dataset.pdfDownloadUrl = item.download_url;
      instructionPreview.dataset.pdfTitle = item.label;
    } else delete instructionPreview.dataset.pdfUrl;
    invalidate();
  };

  const load = async (initial = false) => {
    const current = ++requestNumber;
    const gradeValue = initial ? form.dataset.selectedGrade : grade.value;
    const classValue = initial ? form.dataset.selectedClass : classroom.value;
    message.textContent = 'Загружаю классы и инструкции…';
    try {
      const params = new URLSearchParams({grade: gradeValue || '', class_id: classValue || ''});
      const response = await fetch(`${form.dataset.choicesUrl}?${params}`, {headers: {'Accept': 'application/json'}});
      const data = await response.json();
      if (current !== requestNumber) return;
      if (!response.ok) throw new Error(data.error || 'Не удалось загрузить данные.');
      fill(grade, data.grades, 'Выберите параллель', gradeValue, item => `${item} класс`);
      fill(classroom, data.classes, 'Выберите класс', classValue, item => item.name, item => String(item.id));
      instructions = data.instructions;
      fill(instruction, instructions, 'Выберите инструкцию', initial ? form.dataset.selectedInstruction : instruction.value,
        item => item.label, item => item.id);
      currentRoster = data.roster;
      drawRoster();
      updateInstruction();
      message.textContent = instructions.length ? '' : 'Нет доступных инструкций. Добавьте PDF в перечень инструкций.';
    } catch (error) {
      if (current === requestNumber) { message.textContent = error.message; preview.disabled = true; submit.disabled = true; }
    }
  };

  grade.addEventListener('change', () => { classroom.value = ''; currentRoster = []; drawRoster(); invalidate(); load(); });
  classroom.addEventListener('change', () => { currentRoster = []; drawRoster(); invalidate(); load(); });
  instruction.addEventListener('change', updateInstruction);
  selectAll.addEventListener('click', () => { currentRoster.forEach(item => selected.set(String(item.id), item)); drawRoster(); invalidate(); });
  form.querySelectorAll('input, select, textarea').forEach(field => field.addEventListener('input', invalidate));
  preview.addEventListener('click', async () => {
    if (preview.disabled) return;
    const data = new FormData(form);
    const fingerprint = JSON.stringify([...data.entries()]);
    preview.disabled = true;
    message.textContent = 'Готовлю предварительный просмотр…';
    try {
      const response = await fetch(form.dataset.previewUrl, {method: 'POST', body: data, headers: {'Accept': 'application/pdf'}});
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.error || 'Не удалось подготовить журнал.');
      }
      const blob = await response.blob();
      if (fingerprint !== JSON.stringify([...new FormData(form).entries()])) return;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(blob);
      preview.dataset.pdfUrl = previewUrl;
      preview.dataset.pdfTitle = 'Предпросмотр журнала выезда';
      preview.dataset.pdfPreviewOnly = '1';
      previewReady = true;
      message.textContent = 'Проверьте журнал. После закрытия просмотра нажмите «Сформировать журнал».';
      bootstrap.Modal.getOrCreateInstance(document.getElementById('safety-pdf-preview-modal')).show(preview);
    } catch (error) { message.textContent = error.message; }
    finally { refresh(); }
  });
  form.addEventListener('submit', event => { if (submit.disabled) event.preventDefault(); });
  window.addEventListener('pagehide', () => { if (previewUrl) URL.revokeObjectURL(previewUrl); });
  load(true);
})();
