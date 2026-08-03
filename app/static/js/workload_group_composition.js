(function () {
  "use strict";

  var root = document.querySelector("[data-group-composition]");
  if (!root) return;

  var filter = root.querySelector("[data-composition-filter]");
  var filterForm = root.querySelector("[data-composition-filters]");
  var form = root.querySelector("[data-composition-form]");
  var distributeInOrderButton = root.querySelector("[data-distribute-in-order]");
  var distributeInHalvesButton = root.querySelector("[data-distribute-in-halves]");
  var resetButton = root.querySelector("[data-reset-composition]");
  var status = root.querySelector("[data-composition-status]");

  if (filter && filterForm) {
    filter.addEventListener("change", function () {
      filterForm.submit();
    });
  }

  function setStatus(message, state) {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", state === "error");
    status.classList.toggle("is-success", state === "success");
  }

  function refreshDraftSizes() {
    if (!form) return;
    var counts = {};
    form.querySelectorAll("[data-group-option]:checked").forEach(function (input) {
      counts[input.value] = (counts[input.value] || 0) + 1;
    });
    root.querySelectorAll("[data-group-size]").forEach(function (label) {
      label.textContent = String(counts[label.dataset.groupSize] || 0) + " уч.";
    });
  }

  if (form) {
    form.addEventListener("change", refreshDraftSizes);
  }

  function compositionRows() {
    if (!form) return [];
    return Array.from(
      form.querySelectorAll(".group-composition-table tbody tr")
    );
  }

  function compositionGroupIds() {
    if (!form) return [];
    return Array.from(
      new Set(
        Array.from(form.querySelectorAll("[data-group-option]"))
          .map(function (input) { return input.value; })
      )
    );
  }

  function selectGroup(row, groupId) {
    var target = row.querySelector(
      '[data-group-option="' + groupId + '"]'
    );
    if (target) target.checked = true;
  }

  if (distributeInOrderButton && form) {
    distributeInOrderButton.addEventListener("click", function () {
      var rows = compositionRows();
      var groupIds = compositionGroupIds();
      if (!rows.length || !groupIds.length) return;
      rows.forEach(function (row, index) {
        selectGroup(row, groupIds[index % groupIds.length]);
      });
      refreshDraftSizes();
      setStatus(
        "Дети распределены по очереди. Нажмите «Сохранить»."
      );
    });
  }

  if (distributeInHalvesButton && form) {
    distributeInHalvesButton.addEventListener("click", function () {
      var rows = compositionRows();
      var groupIds = compositionGroupIds();
      if (!rows.length || !groupIds.length) return;

      var baseSize = Math.floor(rows.length / groupIds.length);
      var extra = rows.length % groupIds.length;
      var offset = 0;
      groupIds.forEach(function (groupId, groupIndex) {
        var groupSize = baseSize + (groupIndex < extra ? 1 : 0);
        rows
          .slice(offset, offset + groupSize)
          .forEach(function (row) {
            selectGroup(row, groupId);
          });
        offset += groupSize;
      });
      refreshDraftSizes();
      setStatus(
        "Список разделён на последовательные равные части. " +
        "Нажмите «Сохранить»."
      );
    });
  }

  if (resetButton && form) {
    resetButton.addEventListener("click", function () {
      compositionRows().forEach(function (row) {
        var unassigned = row.querySelector("[data-unassigned-option]");
        if (unassigned) unassigned.checked = true;
      });
      refreshDraftSizes();
      setStatus(
        "Распределение сброшено. Нажмите «Сохранить»."
      );
    });
  }

  if (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var submit = form.querySelector('button[type="submit"]');
      if (submit) submit.disabled = true;
      setStatus("Сохраняю состав…");
      try {
        var response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: {"X-Requested-With": "XMLHttpRequest"}
        });
        var payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(payload.message || "Не удалось сохранить состав.");
        }
        setStatus(payload.message, "success");
        window.location.reload();
      } catch (error) {
        setStatus(error.message, "error");
        if (submit) submit.disabled = false;
      }
    });
  }
})();
