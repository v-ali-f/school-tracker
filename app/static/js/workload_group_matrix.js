(function () {
  "use strict";

  var root = document.querySelector("[data-group-matrix]");
  if (!root) return;

  var saveUrl = root.dataset.saveUrl;
  var status = root.querySelector("[data-group-matrix-status]");
  var filter = root.querySelector("[data-group-matrix-filter]");
  var filterForm = root.querySelector("[data-group-matrix-filters]");

  function setStatus(message, state) {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-success", state === "success");
    status.classList.toggle("is-error", state === "error");
  }

  if (filter && filterForm) {
    filter.addEventListener("change", function () {
      filterForm.submit();
    });
  }

  function updateCellState(input, count, needsComposition) {
    var cell = input.closest(".group-matrix__cell");
    if (!cell) return;
    cell.classList.toggle("is-divided", count > 1);
    cell.classList.toggle("needs-composition", needsComposition);
    var marker = cell.querySelector(".group-matrix__marker");
    if (needsComposition && !marker) {
      marker = document.createElement("span");
      marker.className = "group-matrix__marker";
      marker.title = "Нужно распределить учеников по группам";
      marker.setAttribute("aria-label", "Нужно распределить состав");
      cell.appendChild(marker);
    } else if (!needsComposition && marker) {
      marker.remove();
    }
  }

  async function save(input) {
    var value = Number.parseInt(input.value, 10);
    var original = Number.parseInt(input.dataset.originalValue, 10);
    if (!Number.isInteger(value) || value < 1 || value > 9) {
      input.value = String(original);
      setStatus("Количество групп должно быть от 1 до 9.", "error");
      return;
    }
    if (value === original) return;

    var cell = input.closest(".group-matrix__cell");
    cell.classList.add("is-saving");
    input.disabled = true;
    setStatus("Сохраняю количество групп…");

    var body = new FormData();
    body.append("version_id", input.dataset.versionId);
    body.append("plan_line_id", input.dataset.planLineId);
    body.append("snapshot_class_id", input.dataset.snapshotClassId);
    body.append("plan_id", input.dataset.planId);
    body.append("group_count", String(value));

    try {
      var response = await fetch(saveUrl, {
        method: "POST",
        body: body,
        headers: {"X-Requested-With": "XMLHttpRequest"}
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "Не удалось сохранить количество групп.");
      }
      input.value = String(payload.group_count);
      input.dataset.originalValue = String(payload.group_count);
      updateCellState(
        input,
        payload.group_count,
        Boolean(payload.needs_composition)
      );
      setStatus(payload.message, "success");
    } catch (error) {
      input.value = String(original);
      setStatus(error.message, "error");
    } finally {
      input.disabled = false;
      cell.classList.remove("is-saving");
    }
  }

  root.querySelectorAll("[data-group-count]").forEach(function (input) {
    input.addEventListener("change", function () {
      save(input);
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        input.blur();
      }
      if (event.key === "Escape") {
        input.value = input.dataset.originalValue;
        input.blur();
      }
    });
  });
})();
