(function () {
  "use strict";

  var workspace = document.querySelector("[data-workload-workspace]");
  if (!workspace) return;

  var focusBeforePanel = null;

  function closePanels(restoreFocus) {
    workspace.classList.remove("is-scope-open", "is-context-open");
    document.body.classList.remove("workload-panel-open");
    if (restoreFocus && focusBeforePanel) focusBeforePanel.focus();
    focusBeforePanel = null;
  }

  function openPanel(name, trigger) {
    closePanels(false);
    focusBeforePanel = trigger || document.activeElement;
    workspace.classList.add("is-" + name + "-open");
    document.body.classList.add("workload-panel-open");
    var panel = workspace.querySelector('[data-workload-panel="' + name + '"]');
    var closeButton = panel && panel.querySelector("[data-workload-panel-close]");
    if (closeButton) closeButton.focus();
  }

  workspace.querySelectorAll("[data-workload-panel-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      openPanel(button.getAttribute("data-workload-panel-toggle"), button);
    });
  });

  workspace.querySelectorAll("[data-workload-panel-close]").forEach(function (button) {
    button.addEventListener("click", function () {
      closePanels(true);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closePanels(true);
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth >= 1200) closePanels(false);
  });
})();
