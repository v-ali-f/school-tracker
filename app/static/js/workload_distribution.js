(() => {
  const workspace = document.querySelector("[data-workload-workspace]");

  const openContextOnNarrowScreen = () => {
    if (!window.matchMedia("(max-width: 1199.98px)").matches) return;
    workspace?.classList.add("is-context-open");
    document.body.classList.add("workload-panel-open");
  };

  const selectRecord = (buttons, selected) => {
    buttons.forEach((button) => {
      const active = button === selected;
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.closest("tr")?.classList.toggle("is-selected", active);
    });
  };

  const groupContext = document.querySelector("[data-group-context]");
  const groupButtons = Array.from(document.querySelectorAll("[data-group-select]"));
  if (groupContext && groupButtons.length) {
    const selectGroup = (button) => {
      selectRecord(groupButtons, button);
      groupContext.querySelector("[data-record-empty]").hidden = true;
      groupContext.querySelector("[data-record-details]").hidden = false;
      groupContext.querySelector("[data-group-name]").textContent = button.dataset.name;
      groupContext.querySelector("[data-group-code]").textContent = button.dataset.code;
      groupContext.querySelector("[data-group-type]").textContent = button.dataset.type;
      groupContext.querySelector("[data-group-activity]").textContent = button.dataset.activity;
      groupContext.querySelector("[data-group-classes]").textContent = button.dataset.classes || "—";
      groupContext.querySelector("[data-group-size]").textContent = button.dataset.plannedSize
        ? `${button.dataset.size} / ${button.dataset.plannedSize}`
        : button.dataset.size;
      groupContext.querySelector("[data-group-composition]").textContent = button.dataset.composition;
      groupContext.querySelector("[data-group-period]").textContent = button.dataset.period;
      groupContext.querySelector("[data-group-department]").textContent = button.dataset.department;
      groupContext.querySelector("[data-group-status]").textContent = button.dataset.status;
      groupContext.querySelector("[data-group-open]").href = button.dataset.detailUrl;
      const edit = groupContext.querySelector("[data-group-edit]");
      if (edit) {
        edit.href = button.dataset.editUrl;
        edit.hidden = button.dataset.statusCode !== "DRAFT";
      }
      openContextOnNarrowScreen();
    };

    groupButtons.forEach((button) => button.addEventListener("click", () => selectGroup(button)));
    selectGroup(groupButtons.find((button) => button.getAttribute("aria-pressed") === "true") || groupButtons[0]);
  }

  const needContext = document.querySelector("[data-need-context]");
  const needButtons = Array.from(document.querySelectorAll("[data-need-select]"));
  if (needContext && needButtons.length) {
    const selectNeed = (button) => {
      selectRecord(needButtons, button);
      needContext.querySelector("[data-record-empty]").hidden = true;
      needContext.querySelector("[data-record-details]").hidden = false;
      needContext.querySelector("[data-need-activity]").textContent = button.dataset.activity;
      needContext.querySelector("[data-need-group]").textContent = button.dataset.group;
      needContext.querySelector("[data-need-weekly]").textContent = button.dataset.weekly;
      needContext.querySelector("[data-need-allocated]").textContent = button.dataset.allocated;
      needContext.querySelector("[data-need-remaining]").textContent = button.dataset.remaining;
      needContext.querySelector("[data-need-assignees]").textContent = button.dataset.assignees || "Не назначены";
      needContext.querySelector("[data-need-department]").textContent = button.dataset.department;
      needContext.querySelector("[data-need-building]").textContent = button.dataset.building;
      needContext.querySelector("[data-need-period]").textContent = button.dataset.period;
      needContext.querySelector("[data-need-status]").textContent = button.dataset.status;
      needContext.querySelector("[data-need-open]").href = button.dataset.detailUrl;
      const assign = needContext.querySelector("[data-need-assign]");
      if (assign) {
        assign.href = button.dataset.assignUrl;
        assign.hidden = Number.parseFloat(button.dataset.remaining) <= 0
          || button.dataset.statusCode === "CANCELLED";
      }
      openContextOnNarrowScreen();
    };

    needButtons.forEach((button) => button.addEventListener("click", () => selectNeed(button)));
    selectNeed(needButtons.find((button) => button.getAttribute("aria-pressed") === "true") || needButtons[0]);
  }
})();
