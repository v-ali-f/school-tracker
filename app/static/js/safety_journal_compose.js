(() => {
  const form = document.getElementById('journal-compose');
  if (!form) return;
  const grade = document.getElementById('journal-grade');
  const classroom = document.getElementById('journal-class');
  const subject = document.getElementById('journal-subject');
  const instruction = document.getElementById('journal-instruction');
  const kind = document.getElementById('journal-kind');
  const briefingAt = document.getElementById('journal-briefing-at');
  const preview = document.getElementById('journal-instruction-preview');
  const roster = document.getElementById('journal-roster');
  const count = document.getElementById('journal-selected-count');
  const selectAll = document.getElementById('journal-select-all');
  const previewJournal = document.getElementById('journal-preview');
  const submit = document.getElementById('journal-submit');
  const message = document.getElementById('journal-choice-message');
  const initial = {
    grade: form.dataset.selectedGrade, classroom: form.dataset.selectedClass,
    subject: form.dataset.selectedSubject, instruction: form.dataset.selectedInstruction,
    children: new Set(JSON.parse(form.dataset.selectedChildren || '[]').map(String)),
  };
  let versions = [];
  let requestNumber = 0;
  let previewUrl = '';

  const fill = (select, items, placeholder, value, label = item => String(item), key = item => String(item)) => {
    select.replaceChildren(new Option(placeholder, ''));
    for (const item of items) select.add(new Option(label(item), key(item)));
    select.value = value || '';
    if (select.value !== String(value || '')) select.value = '';
    select.disabled = items.length === 0;
  };

  const refreshCount = () => {
    const checked = roster.querySelectorAll('input[name="child_ids"]:checked').length;
    count.textContent = `· выбрано ${checked}`;
    const complete = Boolean(grade.value && classroom.value && subject.value && instruction.value && kind.value && briefingAt.value && briefingAt.validity.valid && checked);
    previewJournal.disabled = !complete;
    submit.disabled = !complete;
    selectAll.disabled = !roster.querySelector('input[name="child_ids"]');
  };

  const invalidate = () => { refreshCount(); };

  const showRoster = (items, selected) => {
    roster.replaceChildren();
    if (!items.length) {
      const row = roster.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 3;
      cell.className = 'registry-empty-row';
      cell.textContent = classroom.value ? 'В выбранном классе нет учеников.' : 'Выберите класс.';
    }
    for (const item of items) {
      const row = roster.insertRow();
      const checkboxCell = row.insertCell();
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.name = 'child_ids';
      checkbox.value = item.id;
      checkbox.className = 'form-check-input';
      checkbox.setAttribute('aria-label', `Включить ${item.name}`);
      checkbox.checked = selected.has(String(item.id));
      checkboxCell.append(checkbox);
      row.insertCell().textContent = item.name;
      row.insertCell().textContent = item.birth_date || 'Не указана';
    }
    refreshCount();
  };

  const updatePreview = () => {
    const item = versions.find(version => String(version.id) === instruction.value);
    preview.disabled = !item || !item.preview_url;
    if (item) {
      preview.dataset.pdfUrl = item.preview_url;
      preview.dataset.pdfDownloadUrl = item.download_url;
      preview.dataset.pdfTitle = item.label;
    } else {
      delete preview.dataset.pdfUrl;
    }
    invalidate();
  };

  const load = async (preserve = false, defaultAll = false) => {
    const current = ++requestNumber;
    message.textContent = 'Загружаю список…';
    const query = new URLSearchParams({
      grade: preserve ? initial.grade : grade.value,
      class_id: preserve ? initial.classroom : classroom.value,
      subject: preserve ? initial.subject : subject.value,
      draft_id: form.dataset.draftId,
    });
    try {
      const response = await fetch(`${form.dataset.choicesUrl}?${query}`, {headers: {'Accept': 'application/json'}});
      const data = await response.json();
      if (current !== requestNumber) return;
      if (!response.ok) throw new Error(data.error || 'Не удалось загрузить данные.');
      const gradeValue = preserve ? initial.grade : grade.value;
      fill(grade, data.grades, 'Выберите параллель', gradeValue, item => `${item} класс`);
      const classValue = preserve ? initial.classroom : classroom.value;
      fill(classroom, data.classes, 'Выберите класс', classValue, item => item.name, item => String(item.id));
      const subjectValue = preserve ? initial.subject : subject.value;
      fill(subject, data.subjects, 'Выберите предмет', subjectValue);
      versions = data.instructions;
      fill(instruction, versions, 'Выберите инструкцию', preserve ? initial.instruction : instruction.value,
        item => `${item.label} · ${item.source === 'library' ? 'PDF из перечня' : 'каталог'}`, item => String(item.id));
      const selected = preserve ? initial.children : new Set([...roster.querySelectorAll('input[name="child_ids"]:checked')].map(item => item.value));
      showRoster(data.roster, defaultAll || (preserve && !selected.size && !form.dataset.selectedInstruction)
        ? new Set(data.roster.map(item => String(item.id))) : selected);
      message.textContent = subject.value && !versions.length ? 'Для предмета не найдено подходящих инструкций в каталоге и перечне PDF.' : '';
      updatePreview();
    } catch (error) {
      if (current === requestNumber) { message.textContent = error.message; submit.disabled = true; }
    }
  };

  grade.addEventListener('change', () => { classroom.value = ''; subject.value = ''; instruction.value = ''; invalidate(); load(false, true); });
  classroom.addEventListener('change', () => { subject.value = ''; instruction.value = ''; invalidate(); load(false, true); });
  subject.addEventListener('change', () => { instruction.value = ''; invalidate(); load(); });
  instruction.addEventListener('change', updatePreview);
  kind.addEventListener('change', invalidate);
  briefingAt.addEventListener('input', invalidate);
  roster.addEventListener('change', invalidate);
  document.getElementById('journal-note').addEventListener('input', invalidate);
  selectAll.addEventListener('click', () => { roster.querySelectorAll('input[name="child_ids"]').forEach(input => { input.checked = true; }); invalidate(); });
  previewJournal.addEventListener('click', async () => {
    if (previewJournal.disabled) return;
    const data = new FormData(form);
    const fingerprint = JSON.stringify([...data.entries()]);
    previewJournal.disabled = true;
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
      previewJournal.dataset.pdfUrl = previewUrl;
      previewJournal.dataset.pdfTitle = 'Предпросмотр журнала';
      previewJournal.dataset.pdfPreviewOnly = '1';
      message.textContent = 'Проверьте бланк. Журнал можно сформировать после закрытия просмотра.';
      bootstrap.Modal.getOrCreateInstance(document.getElementById('safety-pdf-preview-modal')).show(previewJournal);
    } catch (error) { message.textContent = error.message; }
    finally { refreshCount(); }
  });
  form.addEventListener('submit', event => { if (submit.disabled) event.preventDefault(); });
  window.addEventListener('pagehide', () => { if (previewUrl) URL.revokeObjectURL(previewUrl); });
  load(true);
})();
