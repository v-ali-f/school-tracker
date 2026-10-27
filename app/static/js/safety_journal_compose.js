(() => {
  const form = document.getElementById('journal-compose');
  if (!form) return;
  const grade = document.getElementById('journal-grade');
  const classroom = document.getElementById('journal-class');
  const subject = document.getElementById('journal-subject');
  const instruction = document.getElementById('journal-instruction');
  const kind = document.getElementById('journal-kind');
  const preview = document.getElementById('journal-instruction-preview');
  const roster = document.getElementById('journal-roster');
  const count = document.getElementById('journal-selected-count');
  const selectAll = document.getElementById('journal-select-all');
  const submit = document.getElementById('journal-submit');
  const message = document.getElementById('journal-choice-message');
  const suggestions = document.getElementById('journal-suggestions');
  const initial = {
    grade: form.dataset.selectedGrade, classroom: form.dataset.selectedClass,
    subject: form.dataset.selectedSubject, instruction: form.dataset.selectedInstruction,
    children: new Set(JSON.parse(form.dataset.selectedChildren || '[]').map(String)),
  };
  let versions = [];
  let requestNumber = 0;

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
    submit.disabled = !(grade.value && classroom.value && subject.value && instruction.value && kind.value && checked);
    selectAll.disabled = !roster.querySelector('input[name="child_ids"]');
  };

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

  const showSuggestions = items => {
    suggestions.replaceChildren();
    suggestions.hidden = !items.length;
    if (!items.length) return;
    const title = document.createElement('h3');
    title.className = 'h6';
    title.textContent = 'Подходящие PDF из перечня';
    suggestions.append(title);
    for (const item of items) {
      const row = document.createElement('div');
      row.className = 'd-flex align-items-center justify-content-between gap-2 py-2 border-top flex-wrap';
      const name = document.createElement('span');
      name.textContent = item.title;
      row.append(name);
      const actions = document.createElement('span');
      actions.className = 'd-flex gap-2';
      const view = document.createElement('button');
      view.type = 'button';
      view.className = 'btn btn-sm btn-outline-primary';
      view.textContent = 'Просмотреть';
      view.dataset.bsToggle = 'modal';
      view.dataset.bsTarget = '#safety-pdf-preview-modal';
      view.dataset.pdfUrl = item.preview_url;
      view.dataset.pdfDownloadUrl = item.download_url;
      view.dataset.pdfTitle = item.title;
      actions.append(view);
      if (item.catalog_url) {
        const approve = document.createElement('a');
        approve.className = 'btn btn-sm btn-outline-success';
        approve.href = item.catalog_url;
        approve.textContent = 'Подтвердить для журнала';
        actions.append(approve);
      }
      row.append(actions);
      suggestions.append(row);
    }
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
    refreshCount();
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
      fill(instruction, versions, 'Выберите инструкцию', preserve ? initial.instruction : instruction.value, item => item.label, item => String(item.id));
      const selected = preserve ? initial.children : new Set([...roster.querySelectorAll('input[name="child_ids"]:checked')].map(item => item.value));
      showRoster(data.roster, defaultAll || (preserve && !selected.size && !form.dataset.selectedInstruction)
        ? new Set(data.roster.map(item => String(item.id))) : selected);
      showSuggestions(data.suggestions);
      message.textContent = subject.value && !versions.length ? 'Действующей инструкции по предмету пока нет. Посмотрите подходящие PDF ниже.' : '';
      updatePreview();
    } catch (error) {
      if (current === requestNumber) { message.textContent = error.message; submit.disabled = true; }
    }
  };

  grade.addEventListener('change', () => { classroom.value = ''; subject.value = ''; instruction.value = ''; load(false, true); });
  classroom.addEventListener('change', () => { subject.value = ''; instruction.value = ''; load(false, true); });
  subject.addEventListener('change', () => { instruction.value = ''; load(); });
  instruction.addEventListener('change', updatePreview);
  kind.addEventListener('change', refreshCount);
  roster.addEventListener('change', refreshCount);
  selectAll.addEventListener('click', () => { roster.querySelectorAll('input[name="child_ids"]').forEach(input => { input.checked = true; }); refreshCount(); });
  form.addEventListener('submit', event => { if (submit.disabled) event.preventDefault(); });
  load(true);
})();
