(function () {
  "use strict";

  var root = document.querySelector("[data-group-composition]");
  if (!root) return;

  var filter = root.querySelector("[data-composition-filter]");
  var filterForm = root.querySelector("[data-composition-filters]");
  var form = root.querySelector("[data-composition-form]");
  var distributeButton = root.querySelector("[data-distribute-evenly]");
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

  if (distributeButton && form) {
    distributeButton.addEventListener("click", function () {
      var rows = Array.from(
        form.querySelectorAll(".group-composition-table tbody tr")
      );
      var groupIds = Array.from(
        new Set(
          Array.from(form.querySelectorAll("[data-group-option]"))
            .map(function (input) { return input.value; })
        )
      );
      if (!groupIds.length) return;
      rows.forEach(function (row, index) {
        var target = row.querySelector(
          '[data-group-option="' + groupIds[index % groupIds.length] + '"]'
        );
        if (target) target.checked = true;
      });
      refreshDraftSizes();
      setStatus("Распределение подготовлено. Нажмите «Сохранить».");
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
