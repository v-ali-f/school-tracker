document.addEventListener("DOMContentLoaded", () => {
  const filters = document.querySelector("[data-plan-binding-filters]");
  if (filters) {
    filters.querySelectorAll("[data-plan-binding-filter]").forEach((field) => {
      field.addEventListener("change", () => filters.submit());
    });
  }

  document.querySelectorAll("[data-plan-assignment-form]").forEach((form) => {
    const select = form.querySelector("[data-plan-assignment-select]");
    const state = form.querySelector(".plan-binding-assignment__state");
    if (!select) return;

    select.addEventListener("change", () => {
      select.disabled = true;
      form.classList.add("is-saving");
      if (state) state.textContent = "Сохранение";
      form.submit();
    });
  });
});
