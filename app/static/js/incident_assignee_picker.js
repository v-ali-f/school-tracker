(function () {
  "use strict";

  var openPicker = null;

  function parts(picker) {
    return {
      picker: picker,
      toggle: picker.querySelector("[data-assignee-toggle]"),
      menu: picker.querySelector("[data-assignee-menu]"),
      search: picker.querySelector("[data-assignee-search]"),
      options: Array.prototype.slice.call(
        picker.querySelectorAll("[data-assignee-option]")
      ),
      empty: picker.querySelector("[data-assignee-empty]")
    };
  }

  function filterPicker(state, value) {
    var query = String(value || "").trim().toLocaleLowerCase("ru");
    var visible = 0;
    state.options.forEach(function (option) {
      var text = option.dataset.search || option.textContent || "";
      var matches = !query || text.toLocaleLowerCase("ru").indexOf(query) !== -1;
      option.classList.toggle("hidden", !matches);
      option.style.display = matches ? "" : "none";
      if (matches) visible += 1;
    });
    if (state.empty) state.empty.style.display = visible ? "none" : "block";
  }

  function positionPicker(state) {
    if (!state.toggle || !state.menu) return;
    var rect = state.toggle.getBoundingClientRect();
    var edge = 12;
    var gap = 6;
    var width = Math.min(360, window.innerWidth - edge * 2);
    var left = Math.max(edge, Math.min(rect.left, window.innerWidth - width - edge));

    state.menu.style.width = width + "px";
    state.menu.style.left = left + "px";
    state.menu.style.right = "auto";
    state.menu.style.top = rect.bottom + gap + "px";
    state.menu.style.bottom = "auto";
    state.menu.style.maxHeight = Math.max(180, window.innerHeight - rect.bottom - gap - edge) + "px";

    var menuHeight = state.menu.getBoundingClientRect().height;
    var spaceBelow = window.innerHeight - rect.bottom - gap - edge;
    var spaceAbove = rect.top - gap - edge;
    if (menuHeight > spaceBelow && spaceAbove > spaceBelow) {
      var allowedHeight = Math.max(180, spaceAbove);
      state.menu.style.maxHeight = allowedHeight + "px";
      menuHeight = Math.min(state.menu.getBoundingClientRect().height, allowedHeight);
      state.menu.style.top = Math.max(edge, rect.top - gap - menuHeight) + "px";
    }
  }

  function closePicker(state, restoreFocus) {
    if (!state) return;
    state.menu.classList.remove("open");
    state.toggle.setAttribute("aria-expanded", "false");
    if (state.search) state.search.value = "";
    filterPicker(state, "");
    if (restoreFocus) state.toggle.focus();
    if (openPicker && openPicker.picker === state.picker) openPicker = null;
  }

  function open(state) {
    if (openPicker && openPicker.picker !== state.picker) closePicker(openPicker, false);
    state.menu.classList.add("open");
    state.toggle.setAttribute("aria-expanded", "true");
    filterPicker(state, "");
    openPicker = state;
    positionPicker(state);
    window.setTimeout(function () {
      positionPicker(state);
      if (state.search) state.search.focus();
    }, 0);
  }

  document.addEventListener("click", function (event) {
    var toggle = event.target.closest && event.target.closest("[data-assignee-toggle]");
    if (toggle) {
      var picker = toggle.closest("[data-assignee-picker]");
      if (!picker) return;
      event.preventDefault();
      event.stopPropagation();
      var state = parts(picker);
      if (state.menu.classList.contains("open")) closePicker(state, false);
      else open(state);
      return;
    }

    if (!openPicker) return;
    if (openPicker.menu.contains(event.target)) return;
    closePicker(openPicker, false);
  });

  document.addEventListener("input", function (event) {
    if (!event.target.matches("[data-assignee-search]")) return;
    var picker = event.target.closest("[data-assignee-picker]");
    if (!picker) return;
    filterPicker(parts(picker), event.target.value);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" || !openPicker) return;
    event.preventDefault();
    closePicker(openPicker, true);
  });

  window.addEventListener("resize", function () {
    if (openPicker) positionPicker(openPicker);
  });
  document.addEventListener("scroll", function () {
    if (openPicker) positionPicker(openPicker);
  }, true);

  window.IncidentAssigneePicker = {
    close: function (picker) {
      if (!picker) return;
      closePicker(parts(picker), false);
    },
    refresh: function (picker) {
      if (picker && openPicker && openPicker.picker === picker) positionPicker(openPicker);
    }
  };
})();
