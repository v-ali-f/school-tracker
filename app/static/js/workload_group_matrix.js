(function () {
  "use strict";

  var root = document.querySelector("[data-group-matrix]");
  if (!root) return;

  var saveUrl = root.dataset.saveUrl;
  var status = root.querySelector("[data-group-matrix-status]");
  var saveButton = root.querySelector("[data-group-matrix-save]");
  var saveLabel = root.querySelector("[data-group-matrix-save-label]");

  function setStatus(message, state) {
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-success", state === "success");
    status.classList.toggle("is-error", state === "error");
  }

  root.querySelectorAll("[data-group-matrix-filters]").forEach(function (form) {
    form.querySelectorAll("[data-group-matrix-filter]").forEach(function (filter) {
      filter.addEventListener("change", function () { form.submit(); });
    });
  });

  function updateCellState(input, count, needsComposition) {
    var cell = input.closest(".group-matrix__cell");
    if (!cell) return;
    cell.classList.toggle("is-divided", count > 1);
    cell.classList.toggle("needs-composition", needsComposition);
    cell.classList.remove("is-approved");
    var approvalMarker = cell.querySelector(".group-matrix__approval-marker");
    if (approvalMarker) approvalMarker.remove();
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

  function changedInputs() {
    return Array.from(root.querySelectorAll("[data-group-count]")).filter(
      function (input) {
        return String(input.value) !== String(input.dataset.originalValue);
      }
    );
  }

  function validate(input) {
    var value = Number.parseInt(input.value, 10);
    var original = Number.parseInt(input.dataset.originalValue, 10);
    if (!Number.isInteger(value) || value < 1 || value > 9) {
      input.value = String(original);
      setStatus("Количество групп должно быть от 1 до 9.", "error");
      return false;
    }
    return true;
  }

  function syncDirtyState(updateMessage) {
    var inputs = changedInputs();
    root.querySelectorAll("[data-group-count]").forEach(function (input) {
      input.closest(".group-matrix__cell")?.classList.toggle(
        "is-dirty",
        inputs.includes(input)
      );
    });
    if (saveButton) saveButton.disabled = inputs.length === 0;
    if (saveLabel) {
      saveLabel.textContent = inputs.length
        ? "Сохранить изменения (" + inputs.length + ")"
        : "Сохранить изменения";
    }
    if (updateMessage && inputs.length) {
      setStatus("Есть несохранённые изменения: " + inputs.length + ".");
    }
    return inputs;
  }

  async function saveAll() {
    var inputs = syncDirtyState(false);
    if (!inputs.length) return;
    if (!inputs.every(validate)) {
      syncDirtyState(false);
      return;
    }

    inputs.forEach(function (input) {
      input.disabled = true;
      input.closest(".group-matrix__cell")?.classList.add("is-saving");
    });
    if (saveButton) saveButton.disabled = true;
    setStatus("Сохраняю изменения и пересчитываю затронутые предметы…");

    try {
      var response = await fetch(saveUrl, {
        method: "POST",
        body: JSON.stringify({
          version_id: root.dataset.versionId,
          changes: inputs.map(function (input) {
            return {
              plan_line_id: input.dataset.planLineId,
              snapshot_class_id: input.dataset.snapshotClassId,
              plan_id: input.dataset.planId,
              group_count: input.value
            };
          })
        }),
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest"
        }
      });
      var payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "Не удалось сохранить изменения.");
      }
      var resultByKey = new Map(
        payload.results.map(function (result) { return [result.key, result]; })
      );
      inputs.forEach(function (input) {
        var key = [
          input.dataset.planLineId,
          input.dataset.snapshotClassId,
          input.dataset.planId
        ].join(":");
        var result = resultByKey.get(key);
        if (!result) return;
        input.value = String(result.group_count);
        input.dataset.originalValue = String(result.group_count);
        updateCellState(input, result.group_count, Boolean(result.needs_composition));
      });
      setStatus(payload.message, "success");
    } catch (error) {
      setStatus(error.message, "error");
    } finally {
      inputs.forEach(function (input) {
        input.disabled = false;
        input.closest(".group-matrix__cell")?.classList.remove("is-saving");
      });
      syncDirtyState(false);
    }
  }

  root.querySelectorAll("[data-group-count]").forEach(function (input) {
    input.addEventListener("input", function () {
      syncDirtyState(true);
    });
    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        saveAll();
      }
      if (event.key === "Escape") {
        input.value = input.dataset.originalValue;
        syncDirtyState(true);
      }
    });
  });
  saveButton?.addEventListener("click", saveAll);
  window.addEventListener("beforeunload", function (event) {
    if (!changedInputs().length) return;
    event.preventDefault();
    event.returnValue = "";
  });
})();
