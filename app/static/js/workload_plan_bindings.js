document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-plan-binding-filters]").forEach((filters) => {
    filters.querySelectorAll("[data-plan-binding-filter]").forEach((field) => {
      field.addEventListener("change", () => filters.submit());
    });
  });

  document.querySelectorAll("[data-plan-assignment-form]").forEach((form) => {
    const select = form.querySelector("[data-plan-assignment-select]");
    const submit = form.querySelector("[data-plan-assignment-submit]");
    const state = form.querySelector(".plan-binding-assignment__state");
    if (!select) return;
    select.dataset.savedValue = select.value;

    select.addEventListener("change", () => {
      if (submit) {
        submit.disabled = select.value === select.dataset.savedValue;
      }
      if (state) {
        state.textContent = select.value === select.dataset.savedValue
          ? ""
          : "Не сохранено";
      }
    });

    form.addEventListener("submit", async (event) => {
      if (!window.fetch || form.classList.contains("is-saving")) return;
      event.preventDefault();
      form.classList.add("is-saving");
      select.disabled = true;
      select.setAttribute("aria-busy", "true");
      if (state) state.textContent = "Сохранение";
      if (submit) submit.disabled = true;

      try {
        const response = await window.fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          credentials: "same-origin",
          headers: {
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const payload = await response.json();
        if (!response.ok || !payload.ok) {
          throw new Error(
            payload.message || "Не удалось сохранить привязку.",
          );
        }

        select.dataset.savedValue = select.value;
        if (state) state.textContent = "Сохранено";
        const row = form.closest("[data-class-binding-row]");
        const counter = row?.querySelector("[data-class-assigned-count]");
        if (counter && Number.isFinite(payload.assigned_count)) {
          counter.textContent = (
            `${payload.assigned_count} / ${payload.student_count}`
          );
          counter.classList.toggle(
            "plan-binding-count--complete",
            payload.assigned_count === payload.student_count,
          );
          counter.classList.toggle(
            "plan-binding-count--warning",
            payload.assigned_count !== payload.student_count,
          );
        }
      } catch (error) {
        select.value = select.dataset.savedValue;
        if (state) state.textContent = error.message;
      } finally {
        form.classList.remove("is-saving");
        select.disabled = false;
        select.removeAttribute("aria-busy");
        if (submit) submit.disabled = true;
      }
    });
  });
});
