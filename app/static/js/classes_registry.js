(function () {
  "use strict";

  function setEditing(row, enabled) {
    const form = row.querySelector("[data-inline-class-form]");
    if (!form) {
      return;
    }
    row.classList.toggle("is-editing", enabled);
    row.querySelectorAll("[data-class-view]").forEach(function (element) {
      element.classList.toggle("d-none", enabled);
    });
    row.querySelectorAll("[data-class-edit-control]").forEach(function (element) {
      element.classList.toggle("d-none", !enabled);
    });
    row.querySelector("[data-class-view-actions]").classList.toggle("d-none", enabled);
    row.querySelector("[data-class-edit-actions]").classList.toggle("d-none", !enabled);
    const status = row.querySelector("[data-class-edit-status]");
    status.textContent = "";

    if (enabled) {
      const nameInput = form.elements.namedItem("name");
      if (nameInput) {
        nameInput.focus();
        nameInput.select();
      }
    }
  }

  function resetFormDefaults(form) {
    Array.from(form.elements).forEach(function (control) {
      if (control.tagName === "SELECT") {
        Array.from(control.options).forEach(function (option) {
          option.defaultSelected = option.selected;
        });
      } else if (control.type !== "submit" && control.type !== "button") {
        control.defaultValue = control.value;
      }
    });
  }

  function updateRow(row, schoolClass) {
    row.querySelector('[data-class-view="name"]').textContent = schoolClass.name;
    row.querySelector('[data-class-view="building"]').textContent =
      schoolClass.building_name || "—";
    row.querySelector('[data-class-view="max_students"]').textContent =
      schoolClass.max_students || "—";
    row.querySelector('[data-class-view="applications_count"]').textContent =
      schoolClass.applications_count ? schoolClass.applications_count : "—";
    row.querySelector('[data-class-view="teacher"]').textContent =
      schoolClass.teacher_fio || "—";
    row.querySelector('[data-class-view="phone"]').textContent =
      schoolClass.teacher_phone || "—";
  }

  async function saveRow(row, form) {
    const status = row.querySelector("[data-class-edit-status]");
    const saveButton = row.querySelector('[type="submit"][form="' + form.id + '"]');
    saveButton.disabled = true;
    status.textContent = "Сохранение…";
    status.classList.remove("text-success");

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Не удалось сохранить изменения.");
      }

      updateRow(row, payload.school_class);
      resetFormDefaults(form);
      setEditing(row, false);
      row.classList.add("is-saved");
      window.setTimeout(function () {
        row.classList.remove("is-saved");
      }, 1300);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      saveButton.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const selectAll = document.getElementById("select-all-classes");
    const selections = Array.from(document.querySelectorAll(".class-selection"));
    const deleteButton = document.getElementById("delete-selected-classes");
    const countLabel = document.getElementById("selected-classes-count");
    const bulkForm = document.getElementById("bulk-delete-classes");

    function updateSelectionState() {
      const selectedCount = selections.filter(function (checkbox) {
        return checkbox.checked;
      }).length;
      countLabel.textContent = selectedCount
        ? "Выбрано классов: " + selectedCount
        : "Классы не выбраны";
      deleteButton.disabled = selectedCount === 0;
      selectAll.checked = selections.length > 0 && selectedCount === selections.length;
      selectAll.indeterminate = selectedCount > 0 && selectedCount < selections.length;
    }

    selectAll.addEventListener("change", function () {
      selections.forEach(function (checkbox) {
        checkbox.checked = selectAll.checked;
      });
      updateSelectionState();
    });
    selections.forEach(function (checkbox) {
      checkbox.addEventListener("change", updateSelectionState);
    });
    bulkForm.addEventListener("submit", function (event) {
      const selectedCount = selections.filter(function (checkbox) {
        return checkbox.checked;
      }).length;
      if (
        selectedCount === 0
        || !window.confirm("Удалить выбранные классы: " + selectedCount + "?")
      ) {
        event.preventDefault();
      }
    });

    document.querySelectorAll("[data-inline-class-row]").forEach(function (row) {
      const form = row.querySelector("[data-inline-class-form]");
      row.querySelector("[data-class-edit]").addEventListener("click", function () {
        document.querySelectorAll("[data-inline-class-row].is-editing").forEach(
          function (otherRow) {
            if (otherRow !== row) {
              const otherForm = otherRow.querySelector("[data-inline-class-form]");
              otherForm.reset();
              setEditing(otherRow, false);
            }
          }
        );
        setEditing(row, true);
      });
      row.querySelector("[data-class-cancel]").addEventListener("click", function () {
        form.reset();
        setEditing(row, false);
      });
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        saveRow(row, form);
      });
    });
  });
}());
