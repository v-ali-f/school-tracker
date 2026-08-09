(() => {
  const form = document.querySelector(".professional-registry-page .registry-filter-panel");
  if (!form) return;

  const submit = () => {
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return;
    }
    form.submit();
  };

  form.querySelectorAll("[data-professional-filter]").forEach((field) => {
    field.addEventListener("change", submit);
  });

  const search = form.querySelector("[data-professional-search]");
  if (!search) return;

  let timer = null;
  search.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(submit, 550);
  });
})();
