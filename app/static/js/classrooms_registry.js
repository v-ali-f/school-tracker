(function () {
  "use strict";

  function setEditing(row, enabled) {
    row.classList.toggle("is-editing", enabled);
    row.querySelectorAll("[data-classroom-view]").forEach(function (element) {
      element.classList.toggle("d-none", enabled);
    });
    row.querySelectorAll("[data-classroom-edit]").forEach(function (element) {
      element.classList.toggle("d-none", !enabled);
    });
    row.querySelector("[data-classroom-view-actions]").classList.toggle("d-none", enabled);
    row.querySelector("[data-classroom-edit-actions]").classList.toggle("d-none", !enabled);
    if (enabled) {
      const nameInput = row.querySelector('[name="name"]');
      if (nameInput) {
        nameInput.focus();
        nameInput.select();
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-classroom-row]").forEach(function (row) {
      const form = row.querySelector("form[id^='classroom-update-']");
      row.querySelector("[data-classroom-edit-button]").addEventListener("click", function () {
        document.querySelectorAll("[data-classroom-row].is-editing").forEach(function (otherRow) {
          if (otherRow !== row) {
            const otherForm = otherRow.querySelector("form[id^='classroom-update-']");
            otherForm.reset();
            setEditing(otherRow, false);
          }
        });
        setEditing(row, true);
      });
      row.querySelector("[data-classroom-cancel]").addEventListener("click", function () {
        form.reset();
        setEditing(row, false);
      });
    });
  });
}());
