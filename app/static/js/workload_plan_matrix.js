(() => {
  const matrix = document.querySelector("[data-plan-matrix]");
  if (!matrix) return;

  const scrollStorageKey = `workload-plan-matrix-scroll:${window.location.pathname}`;
  const savedPosition = window.sessionStorage.getItem(scrollStorageKey);
  if (savedPosition !== null) {
    window.sessionStorage.removeItem(scrollStorageKey);
    let position = { scrollY: Number(savedPosition) || 0 };
    try {
      position = JSON.parse(savedPosition);
    } catch (_error) {
      // Поддерживаем сохранённое ранее числовое значение.
    }
    const restorePosition = () => {
      window.scrollTo(0, Number(position.scrollY) || 0);
      if (!position.activityId || !Number.isFinite(position.rowTop)) return;
      const activityInput = document.querySelector(
        `[data-plan-row-reorder] input[name="education_activity_id"]`
        + `[value="${position.activityId}"]`,
      );
      const targetRow = activityInput?.closest("[data-matrix-row]");
      if (!targetRow) return;
      window.scrollBy(
        0,
        targetRow.getBoundingClientRect().top - position.rowTop,
      );
    };
    window.requestAnimationFrame(restorePosition);
    window.setTimeout(restorePosition, 80);
    window.setTimeout(restorePosition, 220);
  }
  document.querySelectorAll("[data-plan-row-reorder]").forEach((form) => {
    form.addEventListener("submit", () => {
      const targetRow = form.closest("[data-matrix-row]");
      window.sessionStorage.setItem(
        scrollStorageKey,
        JSON.stringify({
          scrollY: window.scrollY,
          rowTop: targetRow?.getBoundingClientRect().top ?? null,
          activityId: form.elements.education_activity_id?.value ?? "",
        }),
      );
    });
  });

  const matrixViewStorageKey = "workload-plan-matrix-view";
  const viewButtons = Array.from(
    document.querySelectorAll("[data-plan-matrix-view-option]"),
  );
  const applyMatrixView = (view) => {
    const normalized = view === "weeks" ? "weeks" : "hours";
    matrix.dataset.matrixView = normalized;
    matrix.querySelectorAll("[data-matrix-responsive-colspan]").forEach(
      (cell) => {
        const colspan = normalized === "weeks"
          ? cell.dataset.weeksColspan
          : cell.dataset.hoursColspan;
        cell.colSpan = Number(colspan) || 1;
      },
    );
    viewButtons.forEach((button) => {
      const active = (
        button.dataset.planMatrixViewOption === normalized
      );
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    try {
      window.localStorage.setItem(
        matrixViewStorageKey,
        normalized,
      );
    } catch (_error) {
      // Режим всё равно работает в текущей вкладке.
    }
  };
  let initialMatrixView = "hours";
  try {
    initialMatrixView = (
      window.localStorage.getItem(matrixViewStorageKey)
      || "hours"
    );
  } catch (_error) {
    initialMatrixView = "hours";
  }
  applyMatrixView(initialMatrixView);
  viewButtons.forEach((button) => {
    button.addEventListener("click", () => {
      applyMatrixView(button.dataset.planMatrixViewOption);
    });
  });

  const decimal = (value) => Number.parseFloat(
    String(value ?? "").trim().replace(",", "."),
  );
  const displayDecimal = (value) => {
    const rounded = Math.round((value + Number.EPSILON) * 1000) / 1000;
    return String(rounded).replace(".", ",");
  };
  const refreshFgosHourControl = (control, actual) => {
    if (!control) return;
    const expected = decimal(control.dataset.expectedWeekly);
    if (!Number.isFinite(expected) || !Number.isFinite(actual)) return;

    const difference = actual - expected;
    const state = Math.abs(difference) < 0.0005
      ? "complete"
      : (difference < 0 ? "under" : "over");
    control.classList.remove(
      "workload-fgos-hour-control--complete",
      "workload-fgos-hour-control--under",
      "workload-fgos-hour-control--over",
    );
    control.classList.add(`workload-fgos-hour-control--${state}`);

    let result = "соответствует нормативу";
    if (state === "under") {
      result = `не хватает ${displayDecimal(Math.abs(difference))} ч/нед.`;
    } else if (state === "over") {
      result = `превышение на ${displayDecimal(difference)} ч/нед.`;
    }
    const message = (
      `Норма ФГОС: ${displayDecimal(expected)} ч/нед.; `
      + `внесено: ${displayDecimal(actual)} ч/нед. — ${result}.`
    );
    control.title = message;
    control.setAttribute("aria-label", message);
  };
  const standardForms = () => Array.from(
    matrix.querySelectorAll("[data-plan-cell], [data-plan-cell-create]"),
  );
  const periodForms = () => Array.from(
    matrix.querySelectorAll(
      "[data-plan-period-cell], [data-plan-period-cell-create]",
    ),
  );

  const calculateStandardForm = (form) => {
    const weekly = decimal(form.elements.weekly_hours?.value);
    const weeks = decimal(form.elements.weeks_count?.value);
    const storedAnnual = decimal(form.elements.annual_hours?.value);
    const annual = Number.isFinite(weekly) && Number.isFinite(weeks)
      ? weekly * weeks
      : storedAnnual;
    return {
      weekly: Number.isFinite(weekly) ? weekly : 0,
      weeks: Number.isFinite(weeks) ? weeks : null,
      annual: Number.isFinite(annual) ? annual : 0,
      hasWeekly: Number.isFinite(weekly),
      hasAnnual: Number.isFinite(annual) && Number.isFinite(weekly),
    };
  };

  const periodInputs = (form) => Array.from(
    form.querySelectorAll("[data-period-index]"),
  );
  const periodWeeksInput = (form, index) => (
    form.querySelector(`[data-period-weeks-index="${index}"]`)
  );
  const periodEditableInputs = (form) => Array.from(
    form.querySelectorAll("[data-period-index], [data-period-weeks-index]"),
  );
  const calculatePeriodForm = (form) => {
    const periods = periodInputs(form).map((input, index) => {
      const weekly = decimal(input.value);
      const weeksInput = periodWeeksInput(form, index);
      const weeks = decimal(weeksInput?.value ?? input.dataset.weeks);
      return {
        weekly: Number.isFinite(weekly) ? weekly : 0,
        weeks: Number.isFinite(weeks) ? weeks : 0,
        annual: Number.isFinite(weekly) && Number.isFinite(weeks)
          ? weekly * weeks
          : 0,
        hasValue: Number.isFinite(weekly),
      };
    });
    const hasAny = periods.some((period) => period.hasValue);
    const storedWeekly = decimal(form.dataset.weekly);
    const storedAnnual = decimal(form.dataset.annual);
    return {
      weekly: hasAny
        ? Math.max(...periods.map((period) => period.weekly))
        : (Number.isFinite(storedWeekly) ? storedWeekly : 0),
      annual: hasAny
        ? periods.reduce((total, period) => total + period.annual, 0)
        : (Number.isFinite(storedAnnual) ? storedAnnual : 0),
      periods,
      hasAny,
    };
  };

  const setCellNumber = (cell, value) => {
    if (!cell) return;
    const hasValue = Number.isFinite(value);
    let output = cell.querySelector(":scope > strong, :scope > span");
    const tagName = hasValue ? "STRONG" : "SPAN";
    if (!output || output.tagName !== tagName) {
      output = document.createElement(tagName.toLowerCase());
      cell.replaceChildren(output);
    }
    output.textContent = hasValue ? displayDecimal(value) : "—";
  };

  const refreshStandardForm = (form) => {
    const values = calculateStandardForm(form);
    if (form.elements.annual_hours) {
      form.elements.annual_hours.value = values.hasAnnual
        ? displayDecimal(values.annual)
        : "";
    }
    const annualCell = form.closest("td")?.nextElementSibling;
    setCellNumber(
      annualCell,
      values.hasAnnual ? values.annual : Number.NaN,
    );
    return values;
  };

  const refreshPeriodForm = (form) => {
    const values = calculatePeriodForm(form);
    values.periods.forEach((period, index) => {
      const output = form.querySelector(`[data-period-annual="${index}"]`);
      if (output) {
        output.textContent = period.hasValue
          ? displayDecimal(period.annual)
          : "—";
      }
    });
    const total = form.querySelector("[data-period-total-annual]");
    if (total) {
      total.textContent = values.hasAny || Number.isFinite(decimal(form.dataset.annual))
        ? displayDecimal(values.annual)
        : "—";
    }
    return values;
  };

  const addTotals = (target, weekly, annual) => {
    target.weekly += weekly;
    target.annual += annual;
  };
  const newScopeTotals = () => ({
    weekly: 0,
    annual: 0,
    periods: [],
  });
  const newTotals = () => ({ weekly: 0, annual: 0, scopes: new Map() });
  const scopeTotalsFor = (totals, scopeKey) => {
    const scope = totals.scopes.get(scopeKey) || newScopeTotals();
    totals.scopes.set(scopeKey, scope);
    return scope;
  };
  const addPeriodTotals = (scope, periods) => {
    periods.forEach((period, index) => {
      const target = scope.periods[index] || { weekly: 0, annual: 0 };
      target.weekly += period.weekly;
      target.annual += period.annual;
      scope.periods[index] = target;
    });
  };

  const refreshPeriodTotalsBlock = (block, scope) => {
    block.querySelectorAll("[data-period-total-weekly]").forEach((output) => {
      const index = Number.parseInt(output.dataset.periodTotalWeekly, 10);
      const weekly = scope.periods[index]?.weekly || 0;
      output.textContent = displayDecimal(weekly);
      refreshFgosHourControl(
        output.closest("[data-fgos-hour-control]"),
        weekly,
      );
    });
    block.querySelectorAll("[data-period-total-annual]").forEach((output) => {
      const index = Number.parseInt(output.dataset.periodTotalAnnual, 10);
      output.textContent = displayDecimal(scope.periods[index]?.annual || 0);
    });
    const annual = block.querySelector("[data-period-scope-annual]");
    if (annual) annual.textContent = displayDecimal(scope.annual);
  };

  const recalculateMatrix = () => {
    const sections = new Map();
    const planTotals = newTotals();

    matrix.querySelectorAll("[data-matrix-row]").forEach((row) => {
      const sectionKey = row.dataset.section;
      const section = sections.get(sectionKey) || newTotals();
      sections.set(sectionKey, section);
      const rowTotals = { weekly: 0, annual: 0 };

      row.querySelectorAll("[data-plan-cell], [data-plan-cell-create]").forEach((form) => {
        const values = refreshStandardForm(form);
        const sectionScope = scopeTotalsFor(section, form.dataset.scopeKey);
        const planScope = scopeTotalsFor(planTotals, form.dataset.scopeKey);
        addTotals(rowTotals, values.weekly, values.annual);
        addTotals(section, values.weekly, values.annual);
        addTotals(sectionScope, values.weekly, values.annual);
        addTotals(planTotals, values.weekly, values.annual);
        addTotals(planScope, values.weekly, values.annual);
      });

      row.querySelectorAll(
        "[data-plan-period-cell], [data-plan-period-cell-create]",
      ).forEach((form) => {
        const values = refreshPeriodForm(form);
        const sectionScope = scopeTotalsFor(section, form.dataset.scopeKey);
        const planScope = scopeTotalsFor(planTotals, form.dataset.scopeKey);
        addTotals(rowTotals, values.weekly, values.annual);
        addTotals(section, values.weekly, values.annual);
        addTotals(sectionScope, values.weekly, values.annual);
        addTotals(planTotals, values.weekly, values.annual);
        addTotals(planScope, values.weekly, values.annual);
        addPeriodTotals(sectionScope, values.periods);
        addPeriodTotals(planScope, values.periods);
      });

      setCellNumber(row.querySelector("[data-row-total-annual]"), rowTotals.annual);
    });

    document.querySelectorAll("[data-section-summary]").forEach((summary) => {
      const totals = sections.get(summary.dataset.sectionSummary) || newTotals();
      summary.textContent = `${displayDecimal(totals.weekly)} ч/нед · ${displayDecimal(totals.annual)} ч/год`;
    });
    document.querySelectorAll("[data-section-total-weekly]").forEach((cell) => {
      const totals = sections.get(cell.dataset.sectionTotalWeekly) || newTotals();
      setCellNumber(
        cell,
        scopeTotalsFor(totals, cell.dataset.scopeKey).weekly,
      );
    });
    document.querySelectorAll("[data-section-total-annual]").forEach((cell) => {
      const totals = sections.get(cell.dataset.sectionTotalAnnual) || newTotals();
      setCellNumber(
        cell,
        scopeTotalsFor(totals, cell.dataset.scopeKey).annual,
      );
    });
    document.querySelectorAll("[data-section-period-totals]").forEach((block) => {
      const totals = sections.get(block.dataset.sectionPeriodTotals) || newTotals();
      refreshPeriodTotalsBlock(
        block,
        scopeTotalsFor(totals, block.dataset.scopeKey),
      );
    });
    document.querySelectorAll("[data-section-grand-annual]").forEach((cell) => {
      const totals = sections.get(cell.dataset.sectionGrandAnnual) || newTotals();
      setCellNumber(cell, totals.annual);
    });
    document.querySelectorAll("[data-plan-scope-weekly]").forEach((cell) => {
      const weekly = scopeTotalsFor(
        planTotals,
        cell.dataset.scopeKey,
      ).weekly;
      setCellNumber(
        cell,
        weekly,
      );
      refreshFgosHourControl(
        cell.matches("[data-fgos-hour-control]") ? cell : null,
        weekly,
      );
    });
    document.querySelectorAll("[data-plan-scope-annual]").forEach((cell) => {
      setCellNumber(
        cell,
        scopeTotalsFor(planTotals, cell.dataset.scopeKey).annual,
      );
    });
    document.querySelectorAll("[data-plan-period-totals]").forEach((block) => {
      refreshPeriodTotalsBlock(
        block,
        scopeTotalsFor(planTotals, block.dataset.scopeKey),
      );
    });
    setCellNumber(
      document.querySelector("[data-plan-grand-annual]"),
      planTotals.annual,
    );

    const summaryWeekly = document.querySelector("[data-matrix-total-weekly]");
    const summaryAnnual = document.querySelector("[data-matrix-total-annual]");
    if (summaryWeekly) summaryWeekly.textContent = displayDecimal(planTotals.weekly);
    if (summaryAnnual) summaryAnnual.textContent = displayDecimal(planTotals.annual);
  };

  const standardSnapshot = (form) => [
    form.elements.weekly_hours?.value || "",
    form.elements.weeks_count?.value || "",
    form.elements.annual_hours?.value || "",
  ].join("|");
  const periodSnapshot = (form) => periodInputs(form)
    .map((input, index) => [
      input.value || "",
      periodWeeksInput(form, index)?.value || "",
    ].join(":"))
    .join("|");
  const savedSnapshots = new WeakMap();
  const saveTimers = new WeakMap();
  let saveQueue = Promise.resolve();

  const updateRevisions = (revision) => {
    document.querySelectorAll("input[name='revision']").forEach((input) => {
      input.value = revision;
    });
  };

  const responsePayload = async (response) => {
    try {
      return await response.json();
    } catch (_error) {
      return { ok: false, error: "Сервер вернул некорректный ответ." };
    }
  };

  const postForm = async (form) => {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await responsePayload(response);
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Не удалось сохранить часы.");
    }
    updateRevisions(payload.revision);
    form.action = payload.update_url;
    form.dataset.lineId = payload.line_id;
    form.dataset.weekly = payload.weekly_hours;
    form.dataset.annual = payload.annual_hours;
    return payload;
  };

  const saveStandardForm = async (form) => {
    const values = refreshStandardForm(form);
    if (!values.hasWeekly || !Number.isFinite(values.weeks)) {
      if (!form.hasAttribute("data-plan-cell-create")) {
        form.classList.add("is-save-error");
        window.alert(
          "Заполните часы в неделю и количество учебных недель.",
        );
      }
      return;
    }
    const currentSnapshot = standardSnapshot(form);
    if (savedSnapshots.get(form) === currentSnapshot) return;

    form.classList.add("is-saving");
    form.classList.remove("is-save-error");
    try {
      const payload = await postForm(form);
      form.dataset.weeks = payload.weeks_count;
      form.removeAttribute("data-plan-cell-create");
      form.setAttribute("data-plan-cell", "");
      form.classList.remove("workload-hour-cell--new");
      savedSnapshots.set(form, standardSnapshot(form));
    } catch (error) {
      form.classList.add("is-save-error");
      window.alert(error.message);
    } finally {
      form.classList.remove("is-saving");
    }
  };

  const savePeriodForm = async (form) => {
    const values = refreshPeriodForm(form);
    if (!values.hasAny && form.hasAttribute("data-plan-period-cell-create")) return;
    const currentSnapshot = periodSnapshot(form);
    if (savedSnapshots.get(form) === currentSnapshot) return;

    form.classList.add("is-saving");
    form.classList.remove("is-save-error");
    try {
      const payload = await postForm(form);
      const unchangedDuringSave = periodSnapshot(form) === currentSnapshot;
      if (unchangedDuringSave) {
        payload.periods.forEach((period, index) => {
          const input = periodInputs(form)[index];
          if (!input) return;
          input.value = Number(period.weekly_hours) === 0
            ? ""
            : displayDecimal(Number(period.weekly_hours));
          input.dataset.savedValue = input.value;
          const weeksInput = periodWeeksInput(form, index);
          if (weeksInput) {
            weeksInput.value = displayDecimal(Number(period.weeks_count));
            weeksInput.dataset.savedValue = weeksInput.value;
          }
        });
      }
      form.removeAttribute("data-plan-period-cell-create");
      form.setAttribute("data-plan-period-cell", "");
      form.classList.remove("workload-period-cell--new");
      savedSnapshots.set(form, currentSnapshot);
      recalculateMatrix();
    } catch (error) {
      form.classList.add("is-save-error");
      window.alert(error.message);
    } finally {
      form.classList.remove("is-saving");
    }
  };

  const enqueueSave = (form, save) => {
    saveQueue = saveQueue.then(() => save(form));
    return saveQueue;
  };

  const statusForm = document.querySelector("[data-plan-bundle-status]");
  statusForm?.addEventListener("submit", async (event) => {
    if (statusForm.elements.action?.value !== "SAVE") return;
    event.preventDefault();
    const allStandardForms = standardForms();
    const allPeriodForms = periodForms();
    [...allStandardForms, ...allPeriodForms].forEach((form) => {
      window.clearTimeout(saveTimers.get(form));
    });
    allStandardForms.forEach((form) => {
      enqueueSave(form, saveStandardForm);
    });
    allPeriodForms.forEach((form) => {
      enqueueSave(form, savePeriodForm);
    });
    await saveQueue;
    const hasSaveError = [...allStandardForms, ...allPeriodForms].some(
      (form) => form.classList.contains("is-save-error"),
    );
    if (hasSaveError) {
      window.alert(
        "Не все ячейки удалось сохранить. Исправьте отмеченные значения.",
      );
      return;
    }
    statusForm.submit();
  });
  const scheduleSave = (form, save) => {
    window.clearTimeout(saveTimers.get(form));
    saveTimers.set(
      form,
      window.setTimeout(() => enqueueSave(form, save), 600),
    );
  };

  standardForms().forEach((form) => {
    savedSnapshots.set(
      form,
      form.hasAttribute("data-plan-cell-create")
        ? null
        : standardSnapshot(form),
    );
    form.addEventListener("input", (event) => {
      recalculateMatrix();
      if (
        event.target === form.elements.weekly_hours
        || event.target === form.elements.weeks_count
      ) {
        scheduleSave(form, saveStandardForm);
      }
    });
    form.addEventListener("change", (event) => {
      if (
        event.target === form.elements.weekly_hours
        || event.target === form.elements.weeks_count
      ) {
        enqueueSave(form, saveStandardForm);
      }
    });
    [form.elements.weekly_hours, form.elements.weeks_count].forEach((input) => {
      input?.addEventListener("blur", () => {
        enqueueSave(form, saveStandardForm);
      });
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      enqueueSave(form, saveStandardForm);
    });
    form.addEventListener("keydown", (event) => {
      const isHoursField = (
        event.target === form.elements.weekly_hours
        || event.target === form.elements.weeks_count
      );
      if (!isHoursField) return;
      if (event.key === "Escape") {
        event.preventDefault();
        window.clearTimeout(saveTimers.get(form));
        form.elements.weekly_hours.value = form.dataset.weekly || "";
        form.elements.weeks_count.value = form.dataset.weeks || "34";
        recalculateMatrix();
        event.target.blur();
      }
      if (event.key === "Enter") {
        event.preventDefault();
        window.clearTimeout(saveTimers.get(form));
        enqueueSave(form, saveStandardForm);
      }
    });
  });

  periodForms().forEach((form) => {
    periodEditableInputs(form).forEach((input) => {
      input.dataset.savedValue = input.value;
    });
    savedSnapshots.set(
      form,
      form.hasAttribute("data-plan-period-cell-create")
        ? null
        : periodSnapshot(form),
    );
    form.addEventListener("input", (event) => {
      if (!event.target.matches("[data-period-index], [data-period-weeks-index]")) return;
      recalculateMatrix();
      scheduleSave(form, savePeriodForm);
    });
    form.addEventListener("change", (event) => {
      if (!event.target.matches("[data-period-index], [data-period-weeks-index]")) return;
      enqueueSave(form, savePeriodForm);
    });
    periodEditableInputs(form).forEach((input) => {
      input.addEventListener("blur", () => {
        enqueueSave(form, savePeriodForm);
      });
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      enqueueSave(form, savePeriodForm);
    });
    form.addEventListener("keydown", (event) => {
      if (!event.target.matches("[data-period-index], [data-period-weeks-index]")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        window.clearTimeout(saveTimers.get(form));
        event.target.value = event.target.dataset.savedValue || "";
        recalculateMatrix();
        event.target.blur();
      }
      if (event.key === "Enter") {
        event.preventDefault();
        window.clearTimeout(saveTimers.get(form));
        enqueueSave(form, savePeriodForm);
      }
    });
  });

  recalculateMatrix();
})();
