document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector("[data-plan-binding-filters]");
  if (filters) {
    filters.querySelectorAll("[data-plan-binding-filter]").forEach((field) => {
      field.addEventListener("change", () => filters.submit());
    });
  }

  const form = document.querySelector("[data-plan-binding-form]");
  if (!form) return;

  const members = Array.from(
    form.querySelectorAll("[data-plan-binding-member]")
  );
  const selectAll = form.querySelector("[data-plan-binding-select-all]");
  const counter = form.querySelector("[data-plan-binding-selected-count]");
  const search = form.querySelector("[data-plan-binding-search]");

  const updateSelectionState = () => {
    const editableMembers = members.filter((item) => !item.disabled);
    const selected = members.filter((item) => item.checked).length;
    if (counter) counter.textContent = String(selected);
    if (selectAll) {
      selectAll.disabled = editableMembers.length === 0;
      selectAll.checked =
        editableMembers.length > 0 &&
        editableMembers.every((item) => item.checked);
      selectAll.indeterminate =
        editableMembers.some((item) => item.checked) &&
        !selectAll.checked;
    }
  };

  members.forEach((item) => {
    item.addEventListener("change", updateSelectionState);
  });

  if (selectAll) {
    selectAll.addEventListener("change", () => {
      members.forEach((item) => {
        if (!item.disabled) item.checked = selectAll.checked;
      });
      updateSelectionState();
    });
  }

  if (search) {
    search.addEventListener("input", () => {
      const query = search.value.trim().toLocaleLowerCase("ru");
      form.querySelectorAll("[data-plan-binding-row]").forEach((row) => {
        row.hidden = Boolean(
          query && !row.dataset.searchValue.includes(query)
        );
      });
    });
  }

  updateSelectionState();
});
