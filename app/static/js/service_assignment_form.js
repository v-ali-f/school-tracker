(function () {
  "use strict";

  const form = document.querySelector("[data-service-assignment-form]");
  if (!form) return;

  form.querySelectorAll(".role-checkbox").forEach(function (checkbox) {
    const updateRole = function () {
      const wrap = form.querySelector('[data-role-wrap="' + checkbox.value + '"]');
      const row = checkbox.closest("[data-role-row]");
      if (!wrap) return;
      wrap.classList.toggle("d-none", !checkbox.checked);
      if (row) row.classList.toggle("is-enabled", checkbox.checked);
      const select = wrap.querySelector("select");
      if (select) {
        select.required = checkbox.checked;
        if (!checkbox.checked) select.value = "";
      }
    };
    checkbox.addEventListener("change", updateRole);
    updateRole();
  });

  const grade = document.getElementById("saGrade");
  const schoolClass = document.getElementById("saClass");
  const teacher = document.getElementById("saTeacher");
  const search = document.getElementById("saChildSearch");
  const roster = document.getElementById("saRoster");
  if (!grade || !schoolClass || !roster) return;

  const classOptions = Array.from(schoolClass.options).filter(function (option) { return option.value; });
  const children = Array.from(roster.querySelectorAll(".sa-child-option"));
  const count = document.getElementById("saSelectedCount");
  const empty = document.getElementById("saRosterEmpty");

  function visibleChildren() {
    return children.filter(function (item) { return !item.hidden; });
  }

  function updateCount() {
    const selected = children.filter(function (item) { return item.querySelector("input").checked; }).length;
    if (count) count.textContent = "Выбрано: " + selected;
  }

  function filterChildren() {
    const classId = schoolClass.value;
    const query = (search ? search.value : "").trim().toLocaleLowerCase("ru");
    children.forEach(function (item) {
      const inClass = Boolean(classId) && item.dataset.classId === classId;
      const matches = !query || (item.dataset.childSearch || "").includes(query);
      item.hidden = !(inClass && matches);
    });
    if (empty) {
      const hasVisible = visibleChildren().length > 0;
      empty.hidden = hasVisible;
      const label = empty.querySelector("span");
      if (label) label.textContent = classId ? "В выбранном классе ничего не найдено" : "Выберите параллель и класс";
    }
    updateCount();
  }

  function rebuildClasses(selectedId) {
    const value = grade.value;
    schoolClass.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = value ? "Выберите класс" : "Сначала параллель";
    schoolClass.appendChild(placeholder);
    classOptions.filter(function (option) { return option.dataset.grade === value; }).forEach(function (option) {
      const clone = option.cloneNode(true);
      if (selectedId && clone.value === selectedId) clone.selected = true;
      schoolClass.appendChild(clone);
    });
  }

  function updateClass() {
    const option = schoolClass.options[schoolClass.selectedIndex];
    if (teacher) teacher.value = option && option.value ? (option.dataset.teacher || "Не указан") : "";
    children.forEach(function (item) {
      if (item.dataset.classId !== schoolClass.value) item.querySelector("input").checked = false;
    });
    filterChildren();
  }

  grade.addEventListener("change", function () { rebuildClasses(""); updateClass(); });
  schoolClass.addEventListener("change", updateClass);
  if (search) search.addEventListener("input", filterChildren);
  children.forEach(function (item) { item.querySelector("input").addEventListener("change", updateCount); });

  const selectVisible = document.getElementById("saSelectVisible");
  if (selectVisible) selectVisible.addEventListener("click", function () {
    visibleChildren().forEach(function (item) { item.querySelector("input").checked = true; });
    updateCount();
  });
  const clear = document.getElementById("saClearSelection");
  if (clear) clear.addEventListener("click", function () {
    children.forEach(function (item) { item.querySelector("input").checked = false; });
    updateCount();
  });

  const preselected = children.find(function (item) { return item.querySelector("input").checked; });
  if (preselected) {
    const classOption = classOptions.find(function (option) { return option.value === preselected.dataset.classId; });
    if (classOption) {
      grade.value = classOption.dataset.grade;
      rebuildClasses(classOption.value);
    }
  } else {
    rebuildClasses("");
  }
  updateClass();

  form.addEventListener("submit", function (event) {
    if (!children.some(function (item) { return item.querySelector("input").checked; })) {
      event.preventDefault();
      if (empty) {
        empty.hidden = false;
        const label = empty.querySelector("span");
        if (label) label.textContent = "Выберите хотя бы одного обучающегося";
      }
    }
  });
})();
