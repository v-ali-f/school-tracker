(function () {
  "use strict";

  const form = document.getElementById("lessonVisitForm");
  if (!form) return;

  const teacherSearch = document.getElementById("teacherSearch");
  const teacherSelect = document.getElementById("teacherSelect");
  const teacherResults = document.getElementById("teacherResults");
  const teacherNoResults = document.getElementById("teacherNoResults");
  const teacherClear = document.getElementById("teacherClear");
  const teacherHint = document.getElementById("teacherHint");
  const visitDate = document.getElementById("visitDate");
  const workloadSelect = document.getElementById("workloadSelect");
  const workloadHint = document.getElementById("workloadHint");
  const assignmentInput = document.getElementById("workloadAssignmentId");
  const classInput = document.getElementById("className");
  const subjectInput = document.getElementById("subjectName");
  const workloadUrl = form.dataset.workloadUrl;
  const teacherOptions = Array.from(teacherResults.querySelectorAll(".lv-teacher-option"));
  let selectedTeacherName = "";
  let activeTeacherIndex = -1;

  function normalize(value) {
    return value.trim().toLocaleLowerCase("ru");
  }

  function visibleTeacherOptions() {
    return teacherOptions.filter((option) => !option.hidden);
  }

  function closeTeacherResults() {
    teacherResults.hidden = true;
    teacherSearch.setAttribute("aria-expanded", "false");
    teacherSearch.removeAttribute("aria-activedescendant");
    activeTeacherIndex = -1;
    teacherOptions.forEach((option) => option.classList.remove("is-active"));
  }

  function setActiveTeacher(index) {
    const visible = visibleTeacherOptions();
    if (!visible.length) return;
    activeTeacherIndex = (index + visible.length) % visible.length;
    teacherOptions.forEach((option) => option.classList.remove("is-active"));
    const active = visible[activeTeacherIndex];
    active.classList.add("is-active");
    if (!active.id) active.id = `teacherOption${active.dataset.teacherId}`;
    teacherSearch.setAttribute("aria-activedescendant", active.id);
    active.scrollIntoView({ block: "nearest" });
  }

  function filterTeachers() {
    const query = normalize(teacherSearch.value);
    let visibleCount = 0;
    teacherOptions.forEach((option) => {
      const matches = Boolean(query) && normalize(option.dataset.teacherName).includes(query);
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    teacherNoResults.hidden = !query || visibleCount > 0;
    teacherResults.hidden = !query;
    teacherSearch.setAttribute("aria-expanded", query ? "true" : "false");
    activeTeacherIndex = -1;
    teacherOptions.forEach((option) => option.classList.remove("is-active"));
  }

  function selectTeacher(option) {
    teacherSelect.value = option.dataset.teacherId;
    selectedTeacherName = option.dataset.teacherName;
    teacherSearch.value = selectedTeacherName;
    teacherSearch.setCustomValidity("");
    teacherClear.hidden = false;
    teacherHint.textContent = "Педагог выбран";
    teacherOptions.forEach((item) => item.setAttribute("aria-selected", item === option ? "true" : "false"));
    closeTeacherResults();
    loadWorkload();
  }

  function clearTeacher() {
    teacherSelect.value = "";
    selectedTeacherName = "";
    teacherSearch.value = "";
    teacherClear.hidden = true;
    teacherHint.textContent = "Начните вводить фамилию и выберите педагога из списка";
    teacherOptions.forEach((option) => option.setAttribute("aria-selected", "false"));
    closeTeacherResults();
    resetWorkload("Сначала выберите педагога");
    teacherSearch.focus();
  }

  function resetWorkload(message) {
    workloadSelect.replaceChildren();
    const option = document.createElement("option");
    option.value = "";
    option.textContent = message;
    workloadSelect.appendChild(option);
    workloadSelect.disabled = true;
    workloadHint.textContent = "Класс и предмет можно заполнить вручную";
  }

  async function loadWorkload() {
    const teacherId = teacherSelect.value;
    assignmentInput.value = "";
    if (!teacherId) {
      resetWorkload("Сначала выберите педагога");
      return;
    }
    resetWorkload("Загрузка нагрузки…");
    try {
      const endpoint = workloadUrl.replace(/\/0\/workload$/, `/${teacherId}/workload`);
      const response = await fetch(`${endpoint}?date=${encodeURIComponent(visitDate.value)}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("workload request failed");
      const data = await response.json();
      workloadSelect.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = data.items.length ? "Выберите класс и предмет" : "В нагрузке нет подходящих строк";
      workloadSelect.appendChild(placeholder);
      data.items.forEach((item) => {
        const option = document.createElement("option");
        option.value = JSON.stringify(item);
        option.textContent = `${item.class_name} · ${item.subject_name}`;
        option.dataset.assignmentId = item.assignment_id || "";
        workloadSelect.appendChild(option);
      });
      workloadSelect.disabled = data.items.length === 0;
      workloadHint.textContent = data.items.length
        ? `Найдено вариантов: ${data.items.length}`
        : "Введите класс и предмет вручную";
    } catch (_error) {
      resetWorkload("Не удалось загрузить нагрузку");
    }
  }

  teacherSearch.addEventListener("input", function () {
    if (teacherSearch.value !== selectedTeacherName) {
      teacherSelect.value = "";
      selectedTeacherName = "";
      teacherClear.hidden = true;
      teacherHint.textContent = "Выберите педагога из найденного списка";
      resetWorkload("Сначала выберите педагога");
    }
    teacherSearch.setCustomValidity("");
    filterTeachers();
  });
  teacherSearch.addEventListener("focus", filterTeachers);
  teacherSearch.addEventListener("keydown", function (event) {
    const visible = visibleTeacherOptions();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveTeacher(activeTeacherIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveTeacher(activeTeacherIndex - 1);
    } else if (event.key === "Enter" && activeTeacherIndex >= 0 && visible[activeTeacherIndex]) {
      event.preventDefault();
      selectTeacher(visible[activeTeacherIndex]);
    } else if (event.key === "Escape") {
      closeTeacherResults();
    }
  });
  teacherOptions.forEach((option) => option.addEventListener("click", () => selectTeacher(option)));
  teacherClear.addEventListener("click", clearTeacher);
  document.addEventListener("click", function (event) {
    if (!event.target.closest(".lv-teacher-picker")) closeTeacherResults();
  });
  visitDate.addEventListener("change", loadWorkload);
  workloadSelect.addEventListener("change", function () {
    if (!workloadSelect.value) return;
    const item = JSON.parse(workloadSelect.value);
    classInput.value = item.class_name;
    subjectInput.value = item.subject_name;
    assignmentInput.value = item.assignment_id || "";
  });

  const assessmentInputs = form.querySelectorAll('input[name="check_assessment"]');
  const assessmentType = form.querySelector('[data-check-code="assessment_type"]');
  function syncAssessmentType() {
    const selected = form.querySelector('input[name="check_assessment"]:checked');
    const disabled = selected && selected.value === "not_performed";
    assessmentType.classList.toggle("is-disabled", Boolean(disabled));
    assessmentType.querySelectorAll("input").forEach((input) => {
      input.disabled = Boolean(disabled);
      input.required = !disabled;
      if (disabled) input.checked = false;
    });
  }
  assessmentInputs.forEach((input) => input.addEventListener("change", syncAssessmentType));
  syncAssessmentType();

  const initialTeacher = teacherOptions.find((option) => option.dataset.teacherId === teacherSelect.value);
  if (initialTeacher) {
    selectedTeacherName = initialTeacher.dataset.teacherName;
    teacherSearch.value = selectedTeacherName;
    teacherClear.hidden = false;
    teacherHint.textContent = "Педагог выбран";
    loadWorkload();
  }

  form.addEventListener("submit", function (event) {
    if (teacherSelect.value) return;
    event.preventDefault();
    teacherSearch.setCustomValidity("Выберите педагога из найденного списка.");
    teacherSearch.reportValidity();
    filterTeachers();
  });
})();
