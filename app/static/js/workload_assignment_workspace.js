/* Extracted from app/templates/workload/assignment_workspace.html; page behavior only. */

(() => {
  const pendingCellSaves = new Set();
  let floatingMatrixHeader = null;
  let floatingMatrixHeaderTable = null;
  let floatingMatrixHeaderSource = null;
  let floatingMatrixHeaderFrame = 0;

  const syncFloatingMatrixHeader = () => {
    floatingMatrixHeaderFrame = 0;
    const matrixWrap = document.querySelector("[data-workload-matrix]");
    const matrixTable = matrixWrap?.querySelector(".workload-assignment-matrix");
    const matrixHead = matrixTable?.querySelector("thead");
    if (!matrixWrap || !matrixTable || !matrixHead) {
      if (floatingMatrixHeader) floatingMatrixHeader.hidden = true;
      return;
    }

    if (!floatingMatrixHeader) {
      floatingMatrixHeader = document.createElement("div");
      floatingMatrixHeader.className = "workload-assignment-floating-header";
      floatingMatrixHeader.setAttribute("aria-hidden", "true");
      floatingMatrixHeader.hidden = true;
      document.body.append(floatingMatrixHeader);
    }

    if (floatingMatrixHeaderSource !== matrixTable) {
      floatingMatrixHeaderTable = matrixTable.cloneNode(false);
      floatingMatrixHeaderTable.append(matrixHead.cloneNode(true));
      floatingMatrixHeader.replaceChildren(floatingMatrixHeaderTable);
      floatingMatrixHeaderSource = matrixTable;
    }

    const navbar = document.querySelector(".app-navbar");
    const navbarBottom = Math.max(
      0,
      navbar?.getBoundingClientRect().bottom || 0,
    );
    const matrixRect = matrixWrap.getBoundingClientRect();
    const headerHeight = matrixHead.getBoundingClientRect().height || 34;
    const visibleLeft = Math.max(0, matrixRect.left);
    const visibleWidth = Math.max(
      0,
      Math.min(matrixRect.right, window.innerWidth) - visibleLeft,
    );
    const shouldFloat = (
      matrixRect.top < navbarBottom
      && matrixRect.bottom > navbarBottom + headerHeight
      && visibleWidth > 0
    );

    floatingMatrixHeader.hidden = !shouldFloat;
    if (!shouldFloat) return;

    floatingMatrixHeader.style.top = `${navbarBottom}px`;
    floatingMatrixHeader.style.left = `${visibleLeft}px`;
    floatingMatrixHeader.style.width = `${visibleWidth}px`;
    floatingMatrixHeader.style.height = `${headerHeight}px`;
    floatingMatrixHeaderTable.style.width = `${matrixTable.scrollWidth}px`;
    floatingMatrixHeaderTable.style.minWidth = `${matrixTable.scrollWidth}px`;
    floatingMatrixHeader.scrollLeft = matrixWrap.scrollLeft;
  };

  const scheduleFloatingMatrixHeader = () => {
    if (floatingMatrixHeaderFrame) return;
    floatingMatrixHeaderFrame = window.requestAnimationFrame(
      syncFloatingMatrixHeader,
    );
  };

  document.addEventListener("scroll", scheduleFloatingMatrixHeader, true);
  window.addEventListener("resize", scheduleFloatingMatrixHeader);
  window.addEventListener("load", scheduleFloatingMatrixHeader);
  scheduleFloatingMatrixHeader();

  const focusHolderRows = (holderKey) => {
    const focusedRows = Array.from(document.querySelectorAll(
      `[data-workload-holder-row="${holderKey}"]`
    ));
    if (!focusedRows.length) return;
    focusedRows[0].scrollIntoView({
      behavior: "smooth",
      block: "center",
      inline: "nearest",
    });
    focusedRows.forEach((row) => row.classList.add("is-row-hovered"));
    window.setTimeout(
      () => focusedRows.forEach((row) => row.classList.remove("is-row-hovered")),
      2400,
    );
  };

  let holderPageRequest = null;
  const loadHolderPage = async (targetUrl, {pushHistory = true} = {}) => {
    const currentRegion = document.querySelector("[data-workload-page-region]");
    if (!currentRegion) {
      window.location.assign(targetUrl);
      return;
    }
    holderPageRequest?.abort();
    const requestController = new AbortController();
    holderPageRequest = requestController;
    const requestUrl = new URL(targetUrl, window.location.href);
    requestUrl.searchParams.set("page_fragment", "1");
    const currentMatrix = currentRegion.querySelector("[data-workload-matrix]");
    const scrollLeft = currentMatrix?.scrollLeft || 0;
    const scrollTop = currentMatrix?.scrollTop || 0;
    const regionTop = currentRegion.getBoundingClientRect().top;
    currentRegion.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(requestUrl, {
        headers: {"Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
        signal: requestController.signal,
      });
      if (!response.ok) throw new Error("Не удалось загрузить страницу педагогов.");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const replacement = page.querySelector("[data-workload-page-region]");
      if (!replacement) throw new Error("Не найдена матрица нагрузки.");
      currentRegion.replaceWith(replacement);
      const replacementMatrix = replacement.querySelector("[data-workload-matrix]");
      if (replacementMatrix) {
        replacementMatrix.scrollLeft = scrollLeft;
        replacementMatrix.scrollTop = scrollTop;
        bindCellControls(replacementMatrix);
      }
      const newRegionTop = replacement.getBoundingClientRect().top;
      window.scrollBy(0, newRegionTop - regionTop);
      const focusHolder = requestUrl.searchParams.get("focus_holder");
      if (focusHolder) {
        window.requestAnimationFrame(() => focusHolderRows(focusHolder));
      }
      if (pushHistory) {
        const historyUrl = new URL(targetUrl, window.location.href);
        historyUrl.searchParams.delete("focus_holder");
        historyUrl.searchParams.delete("page_fragment");
        window.history.pushState(
          {workloadHolderPage: true},
          "",
          historyUrl,
        );
      }
      scheduleFloatingMatrixHeader();
    } catch (error) {
      if (error.name === "AbortError") return;
      window.location.assign(targetUrl);
    } finally {
      if (holderPageRequest === requestController) {
        holderPageRequest = null;
      }
      document.querySelector("[data-workload-page-region]")
        ?.removeAttribute("aria-busy");
    }
  };

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".workload-holder-pagination a");
    if (!link || !document.querySelector("[data-workload-page-region]")) return;
    event.preventDefault();
    loadHolderPage(link.href);
  });
  window.addEventListener("popstate", () => {
    if (document.querySelector("[data-workload-page-region]")) {
      loadHolderPage(window.location.href, {pushHistory: false});
    }
  });

  const normalizeWorkloadSearch = (value) => (value || "")
    .toLocaleLowerCase("ru-RU")
    .replaceAll("ё", "е")
    .trim();
  const filterbar = document.querySelector("[data-workload-filterbar]");
  const workloadHolderFilter = filterbar?.querySelector("[data-workload-holder-filter]");
  const workloadHolderFilterSearch = workloadHolderFilter?.querySelector(
    "[data-workload-holder-filter-search]"
  );
  const workloadHolderFilterResults = workloadHolderFilter?.querySelector(
    "[data-workload-holder-filter-results]"
  );
  const workloadHolderFilterEmpty = workloadHolderFilter?.querySelector(
    "[data-workload-holder-filter-empty]"
  );
  const workloadHolderFilterOptions = () => Array.from(
    workloadHolderFilterResults?.querySelectorAll(
      "[data-workload-holder-filter-option]"
    ) || []
  );
  const closeWorkloadHolderFilter = () => {
    if (!workloadHolderFilterResults || !workloadHolderFilterSearch) return;
    workloadHolderFilterResults.hidden = true;
    workloadHolderFilterSearch.setAttribute("aria-expanded", "false");
  };
  const renderWorkloadHolderFilter = () => {
    if (!workloadHolderFilterResults || !workloadHolderFilterSearch) return;
    const query = normalizeWorkloadSearch(workloadHolderFilterSearch.value);
    if (!query) {
      workloadHolderFilterOptions().forEach((option) => option.hidden = true);
      if (workloadHolderFilterEmpty) workloadHolderFilterEmpty.hidden = true;
      closeWorkloadHolderFilter();
      return;
    }
    let visibleCount = 0;
    workloadHolderFilterOptions().forEach((option) => {
      const matches = (
        normalizeWorkloadSearch(option.dataset.search).includes(query)
        && visibleCount < 30
      );
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    if (workloadHolderFilterEmpty) {
      workloadHolderFilterEmpty.hidden = visibleCount > 0;
    }
    workloadHolderFilterResults.hidden = false;
    workloadHolderFilterSearch.setAttribute("aria-expanded", "true");
  };
  const upsertWorkloadHolderFilterOption = (holderKey, label, isVacancy = false) => {
    if (!workloadHolderFilterResults || !holderKey || !label) return;
    let option = workloadHolderFilterResults.querySelector(
      `[data-holder-key="${holderKey}"]`
    );
    if (!option) {
      option = document.createElement("button");
      option.type = "button";
      option.setAttribute("role", "option");
      option.dataset.workloadHolderFilterOption = "";
      option.dataset.holderKey = holderKey;
      option.append(document.createElement("span"), document.createElement("small"));
      workloadHolderFilterResults.insertBefore(option, workloadHolderFilterEmpty);
    }
    option.dataset.search = normalizeWorkloadSearch(label);
    option.querySelector("span").textContent = label;
    option.querySelector("small").textContent = isVacancy ? "Вакансия" : "Педагог";
  };
  const removeWorkloadHolderFilterOption = (holderKey) => {
    if (!holderKey) return;
    workloadHolderFilterResults
      ?.querySelector(`[data-holder-key="${holderKey}"]`)
      ?.remove();
  };
  workloadHolderFilterSearch?.addEventListener("focus", renderWorkloadHolderFilter);
  workloadHolderFilterSearch?.addEventListener("input", renderWorkloadHolderFilter);
  workloadHolderFilterResults?.addEventListener("click", (event) => {
    const option = event.target.closest("[data-workload-holder-filter-option]");
    if (!option || !workloadHolderFilterSearch) return;
    workloadHolderFilterSearch.value = option.querySelector("span")?.textContent?.trim() || "";
    closeWorkloadHolderFilter();
    filterbar?.requestSubmit();
  });
  filterbar?.querySelectorAll("[data-workload-filter-auto]").forEach((field) => {
    field.addEventListener("change", () => {
      filterbar.requestSubmit();
    });
  });
  filterbar?.querySelectorAll("[data-workload-filter-clear]").forEach((button) => {
    button.addEventListener("click", () => {
      const fieldName = button.dataset.workloadFilterClear;
      filterbar.querySelectorAll(`input[name="${fieldName}"]`).forEach((field) => {
        field.checked = false;
      });
      filterbar.requestSubmit();
    });
  });
  filterbar?.querySelector("[data-workload-subject-clear]")?.addEventListener(
    "click",
    () => {
      filterbar.querySelectorAll('input[name="subject_id"]').forEach((field) => {
        field.checked = false;
      });
      filterbar.requestSubmit();
    },
  );

  document.addEventListener("click", (event) => {
    if (workloadHolderFilter && !workloadHolderFilter.contains(event.target)) {
      closeWorkloadHolderFilter();
    }
    const summary = event.target.closest(".workload-subject-add summary");
    if (summary) {
      document.querySelectorAll(".workload-subject-add").forEach((details) => {
        if (details !== summary.closest("details")) details.removeAttribute("open");
      });
    }
    document.querySelectorAll(".workload-subject-add").forEach((details) => {
      if (details.open && !details.contains(event.target)) {
        details.removeAttribute("open");
      }
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeWorkloadHolderFilter();
    document.querySelectorAll(".workload-subject-add").forEach(
      (details) => details.removeAttribute("open")
    );
  });

  const teacherDialog = document.querySelector("[data-teacher-dialog]");
  const teacherPicker = teacherDialog?.querySelector("[data-teacher-picker]");
  const teacherPickerSearch = teacherPicker?.querySelector("[data-teacher-picker-search]");
  const teacherPickerValue = teacherPicker?.querySelector("[data-teacher-picker-value]");
  const teacherPickerResults = teacherPicker?.querySelector("[data-teacher-picker-results]");
  const teacherPickerEmpty = teacherPicker?.querySelector("[data-teacher-picker-empty]");
  const normalizeTeacherSearch = normalizeWorkloadSearch;
  const teacherPickerOptions = () => Array.from(
    teacherPickerResults?.querySelectorAll("[data-teacher-picker-option]") || []
  );
  const renderTeacherPicker = () => {
    if (!teacherPickerResults || !teacherPickerSearch) return;
    const query = normalizeTeacherSearch(teacherPickerSearch.value);
    if (!query) {
      teacherPickerOptions().forEach((option) => option.hidden = true);
      if (teacherPickerEmpty) teacherPickerEmpty.hidden = true;
      closeTeacherPicker();
      return;
    }
    let visibleCount = 0;
    teacherPickerOptions().forEach((option) => {
      const matches = (
        normalizeTeacherSearch(option.dataset.search).includes(query)
        && visibleCount < 30
      );
      option.hidden = !matches;
      if (matches) visibleCount += 1;
    });
    if (teacherPickerEmpty) teacherPickerEmpty.hidden = visibleCount > 0;
    teacherPickerResults.hidden = false;
    teacherPickerSearch.setAttribute("aria-expanded", "true");
  };
  const closeTeacherPicker = () => {
    if (!teacherPickerResults || !teacherPickerSearch) return;
    teacherPickerResults.hidden = true;
    teacherPickerSearch.setAttribute("aria-expanded", "false");
  };
  const selectTeacherPickerOption = (option) => {
    if (!teacherPickerSearch || !teacherPickerValue) return;
    teacherPickerValue.value = option.dataset.teacherId || "";
    teacherPickerSearch.value = option.querySelector("span")?.textContent?.trim() || "";
    teacherPickerSearch.setCustomValidity("");
    closeTeacherPicker();
  };
  const removeTeacherPickerOption = (teacherId) => {
    if (!teacherId) return;
    teacherPickerResults
      ?.querySelector(`[data-teacher-id="${teacherId}"]`)
      ?.remove();
  };
  const addTeacherPickerOption = (teacher) => {
    if (
      !teacherPickerResults
      || !teacher?.id
      || !teacher?.name
      || teacherPickerResults.querySelector(`[data-teacher-id="${teacher.id}"]`)
    ) return;
    const option = document.createElement("button");
    option.type = "button";
    option.setAttribute("role", "option");
    option.dataset.teacherPickerOption = "";
    option.dataset.teacherId = String(teacher.id);
    option.dataset.search = normalizeTeacherSearch(teacher.name);
    const label = document.createElement("span");
    label.textContent = teacher.name;
    const note = document.createElement("small");
    note.textContent = "Доступен для добавления";
    option.append(label, note);
    teacherPickerResults.prepend(option);
  };
  teacherPickerSearch?.addEventListener("focus", renderTeacherPicker);
  teacherPickerSearch?.addEventListener("input", () => {
    if (teacherPickerValue) teacherPickerValue.value = "";
    teacherPickerSearch.setCustomValidity("");
    renderTeacherPicker();
  });
  teacherPickerResults?.addEventListener("click", (event) => {
    const option = event.target.closest("[data-teacher-picker-option]");
    if (option) selectTeacherPickerOption(option);
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("[data-open-teacher-dialog]")) {
      teacherDialog?.showModal();
      window.requestAnimationFrame(() => {
        teacherPickerSearch?.focus();
        renderTeacherPicker();
      });
    }
    if (event.target.closest("[data-close-teacher-dialog]")) {
      teacherDialog?.close();
    }
    if (teacherPicker && !teacherPicker.contains(event.target)) {
      closeTeacherPicker();
    }
  });
  teacherDialog?.addEventListener("click", (event) => {
    if (event.target === teacherDialog) teacherDialog.close();
  });

  const vacancyDialog = document.querySelector("[data-vacancy-dialog]");
  const vacancyForm = vacancyDialog?.querySelector("[data-vacancy-form]");
  const vacancyKey = vacancyDialog?.querySelector("[data-vacancy-key]");
  const vacancyNote = vacancyDialog?.querySelector("[data-vacancy-note]");
  const vacancyTitle = vacancyDialog?.querySelector("[data-vacancy-dialog-title]");
  const vacancySubmit = vacancyDialog?.querySelector("[data-vacancy-submit]");
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-vacancy-dialog]");
    if (!button || !vacancyDialog || !vacancyForm) return;
    const editing = Boolean(button.dataset.vacancyKey);
    const label = button.dataset.vacancyLabel || "";
    const noteMatch = label.match(/\((.*)\)\s*$/);
    vacancyForm.action = editing
      ? vacancyForm.dataset.editUrl
      : vacancyForm.dataset.createUrl;
    vacancyKey.value = editing ? button.dataset.vacancyKey : "";
    vacancyNote.value = editing && noteMatch ? noteMatch[1] : "";
    vacancyTitle.textContent = editing
      ? "Изменить подпись вакансии"
      : "Добавить вакансию";
    vacancySubmit.textContent = editing
      ? "Сохранить подпись"
      : "Добавить вакансию";
    teacherDialog?.close();
    vacancyDialog.showModal();
    vacancyNote.focus();
  });
  document.querySelectorAll("[data-close-vacancy-dialog]").forEach((button) => {
    button.addEventListener("click", () => vacancyDialog?.close());
  });
  vacancyDialog?.addEventListener("click", (event) => {
    if (event.target === vacancyDialog) vacancyDialog.close();
  });

  const copySubjectsDialog = document.querySelector("[data-copy-subjects-dialog]");
  const copySourceTeacher = copySubjectsDialog?.querySelector("[data-copy-source-teacher]");
  const copySourceLabel = copySubjectsDialog?.querySelector("[data-copy-source-label]");
  const copyTargetTeacher = copySubjectsDialog?.querySelector("[data-copy-target-teacher]");
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-copy-subjects-dialog]");
    if (!button || !copySubjectsDialog) return;
    if (copySourceTeacher) copySourceTeacher.value = button.dataset.sourceTeacherId || "";
    if (copySourceLabel) {
      copySourceLabel.textContent = `«${button.dataset.sourceLabel || "выбранного учителя"}»`;
    }
    if (copyTargetTeacher) copyTargetTeacher.value = "";
    copySubjectsDialog.showModal();
    copyTargetTeacher?.focus();
  });
  document.querySelectorAll("[data-close-copy-subjects-dialog]").forEach((button) => {
    button.addEventListener("click", () => copySubjectsDialog?.close());
  });
  copySubjectsDialog?.addEventListener("click", (event) => {
    if (event.target === copySubjectsDialog) copySubjectsDialog.close();
  });

  const holderDialog = document.querySelector("[data-holder-dialog]");
  const holderSourceType = holderDialog?.querySelector("[data-holder-source-type]");
  const holderSourceTeacher = holderDialog?.querySelector("[data-holder-source-teacher]");
  const holderSourceVacancy = holderDialog?.querySelector("[data-holder-source-vacancy]");
  const holderSourceLabel = holderDialog?.querySelector("[data-holder-source-label]");
  const holderTarget = holderDialog?.querySelector("[data-holder-target]");
  const targetVacancyNote = holderDialog?.querySelector("[data-target-vacancy-note]");
  holderTarget?.addEventListener("change", () => {
    if (targetVacancyNote) {
      targetVacancyNote.hidden = holderTarget.value !== "vacancy";
    }
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-holder-dialog]");
    if (button) {
      if (!holderDialog || !holderTarget) return;
      holderSourceType.value = button.dataset.sourceType || "teacher";
      holderSourceTeacher.value = button.dataset.sourceTeacherId || "";
      holderSourceVacancy.value = button.dataset.sourceVacancyKey || "";
      holderSourceLabel.textContent = `«${button.dataset.sourceLabel || "выбранной строки"}»`;
      holderTarget.value = "";
      if (targetVacancyNote) {
        targetVacancyNote.hidden = true;
        const noteInput = targetVacancyNote.querySelector("input");
        if (noteInput) noteInput.value = "";
      }
      holderTarget.querySelectorAll("[data-teacher-id]").forEach((option) => {
        const isCurrent = option.dataset.teacherId === button.dataset.sourceTeacherId;
        option.hidden = isCurrent;
        option.disabled = isCurrent;
      });
      holderDialog.showModal();
      holderTarget.focus();
    }
  });
  document.querySelectorAll("[data-close-holder-dialog]").forEach((button) => {
    button.addEventListener("click", () => holderDialog?.close());
  });
  holderDialog?.addEventListener("click", (event) => {
    if (event.target === holderDialog) holderDialog.close();
  });

  const formatHours = (value) => {
    if (value === null || value === undefined || value === "") return "";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    return Number.isInteger(number) ? String(number) : String(number).replace(".", ",");
  };

  const numberFromText = (element) => {
    const value = (element?.textContent || "0")
      .replace(/\s/g, "")
      .replace(",", ".");
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
  };

  const adjustTotal = (selector, delta) => {
    const element = document.querySelector(selector);
    if (element) element.textContent = formatHours(numberFromText(element) + delta);
  };

  const updateNeedControls = (payload) => {
    document.querySelectorAll(`[data-workload-cell-form][data-need-id="${payload.need_id}"]`).forEach((cell) => {
      const button = cell.querySelector("[data-workload-cell-toggle]");
      const value = cell.querySelector("[data-workload-cell-value]");
      const label = cell.querySelector("[data-workload-cell-label]");
      const matrix = cell.closest("[data-workload-matrix]");
      const holderRow = cell.closest("tr[data-holder-key]");
      const sameHolder = holderRow?.dataset.holderKey === payload.holder_key;
      const assigned = payload.value !== null && sameHolder;
      const locked = payload.value !== null && !sameHolder;
      const planned = cell.dataset.planned;
      cell.classList.toggle("is-assigned", assigned);
      cell.classList.toggle("is-locked", locked);
      cell.classList.toggle(
        "is-available",
        !assigned && !locked && matrix?.dataset.editable === "1"
      );
      cell.dataset.hours = assigned ? "0" : planned;
      if (value) value.textContent = assigned ? formatHours(planned) : "";
      if (label) label.hidden = !assigned;
      button.disabled = locked || matrix?.dataset.editable !== "1";
      button.title = assigned
        ? `Снять назначение ${formatHours(planned)} ч/нед.`
        : locked
          ? "Назначено другому преподавателю."
          : `Назначить полный объём ${formatHours(planned)} ч/нед.`;
    });
    const holderDelta = Number(payload.holder_delta || 0);
    const allocatedDelta = Number(payload.allocated_delta || 0);
    adjustTotal(`[data-holder-total="${payload.holder_key}"]`, holderDelta);
    adjustTotal(
      `[data-subject-total="${payload.holder_key}:${payload.activity_id}:${payload.plan_kind}"]`,
      holderDelta,
    );
    adjustTotal("[data-workload-total-allocated]", allocatedDelta);
    adjustTotal("[data-workload-total-remaining]", -allocatedDelta);
  };

  const responsePayload = async (response) => {
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Сеанс завершён. Обновите страницу и повторите действие.");
    }
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || "Не удалось сохранить изменения.");
    }
    return payload;
  };

  const sortHolderRows = (matrix) => {
    const body = matrix.querySelector("tbody");
    const addTeacherRow = body?.querySelector(".workload-add-teacher-row");
    if (!body || !addTeacherRow) return;
    const groups = new Map();
    body.querySelectorAll("[data-workload-holder-row]").forEach((row) => {
      const holderKey = row.dataset.workloadHolderRow;
      if (!groups.has(holderKey)) {
        groups.set(holderKey, {
          sortKey: row.dataset.holderSortKey || "",
          rows: [],
        });
      }
      groups.get(holderKey).rows.push(row);
    });
    Array.from(groups.values())
      .sort((left, right) => left.sortKey.localeCompare(
        right.sortKey,
        "ru",
        {sensitivity: "base"},
      ))
      .forEach((group) => {
        group.rows.forEach((row) => body.insertBefore(row, addTeacherRow));
      });
  };

  const refreshMatrix = async (holderKey = "", subjectOptions = null) => {
    const current = document.querySelector("[data-workload-matrix]");
    if (!current) return;
    const scrollLeft = current.scrollLeft;
    const scrollTop = current.scrollTop;
    current.setAttribute("aria-busy", "true");
    const refreshUrl = new URL(window.location.href);
    if (holderKey) refreshUrl.searchParams.set("fragment_holder_key", holderKey);
    const response = await fetch(refreshUrl, {
      headers: {"Accept": "text/html"},
    });
    if (!response.ok) throw new Error("Не удалось обновить матрицу нагрузки.");
    const page = new DOMParser().parseFromString(await response.text(), "text/html");
    ["allocated", "remaining", "excess"].forEach((totalKind) => {
      const selector = `[data-workload-total-${totalKind}]`;
      const currentTotal = document.querySelector(selector);
      const refreshedTotal = page.querySelector(selector);
      if (currentTotal && refreshedTotal) {
        currentTotal.textContent = refreshedTotal.textContent;
      }
    });
    const currentExcessWrap = document.querySelector(
      "[data-workload-total-excess-wrap]"
    );
    const refreshedExcessWrap = page.querySelector(
      "[data-workload-total-excess-wrap]"
    );
    if (currentExcessWrap && refreshedExcessWrap) {
      currentExcessWrap.hidden = refreshedExcessWrap.hidden;
    }
    if (holderKey) {
      const selector = `[data-workload-holder-row="${holderKey}"]`;
      const currentRows = Array.from(current.querySelectorAll(selector));
      const fragment = page.querySelector("[data-workload-holder-fragment]");
      const replacementRows = Array.from(
        fragment?.querySelectorAll(selector) || []
      );
      if (subjectOptions) {
        const replacementSelect = replacementRows
          .map((row) => row.querySelector("[data-activity-plan-kind]"))
          .find(Boolean);
        if (replacementSelect) {
          replacementSelect.replaceChildren(
            ...subjectOptions.map((option) => option.cloneNode(true)),
          );
        }
      }
      const anchor = currentRows[0] || current.querySelector(".workload-add-teacher-row");
      if (replacementRows.length && anchor) {
        anchor.before(...replacementRows);
        currentRows.forEach((row) => row.remove());
        sortHolderRows(current);
        current.removeAttribute("aria-busy");
        current.scrollLeft = scrollLeft;
        current.scrollTop = scrollTop;
        bindCellControls(current);
        scheduleFloatingMatrixHeader();
        return;
      }
    }
    const replacement = page.querySelector("[data-workload-matrix]");
    if (!replacement) throw new Error("Матрица нагрузки не найдена.");
    current.replaceWith(replacement);
    replacement.scrollLeft = scrollLeft;
    replacement.scrollTop = scrollTop;
    bindCellControls(replacement);
    scheduleFloatingMatrixHeader();
  };

  const bindCellControls = (root = document) => {
    const matrices = root.matches?.("[data-workload-matrix]")
      ? [root]
      : Array.from(root.querySelectorAll("[data-workload-matrix]"));
    matrices.forEach((matrix) => {
      if (matrix.dataset.cellControlsBound === "1") return;
      matrix.dataset.cellControlsBound = "1";
      matrix.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-workload-cell-toggle]");
        if (!button || button.disabled || !matrix.contains(button)) return;
        const cell = button.closest("[data-workload-cell-form]");
        const holderRow = cell?.closest("tr[data-holder-key]");
        if (!cell || !holderRow || cell.classList.contains("is-saving")) return;
        const formData = new FormData();
        formData.set("csrf_token", matrix.dataset.csrfToken || "");
        formData.set("version_id", matrix.dataset.versionId || "");
        formData.set("view", matrix.dataset.view || "all");
        formData.set("department_id", matrix.dataset.departmentId || "");
        formData.set("building_id", matrix.dataset.buildingId || "");
        (matrix.dataset.educationLevels || "").split(",").filter(Boolean).forEach(
          (value) => formData.append("education_level", value)
        );
        (matrix.dataset.grades || "").split(",").filter(Boolean).forEach(
          (value) => formData.append("grade", value)
        );
        formData.set("need_id", cell.dataset.needId || "");
        formData.set("holder_type", holderRow.dataset.holderType || "teacher");
        formData.set("teacher_id", holderRow.dataset.teacherId || "");
        formData.set("vacancy_key", holderRow.dataset.vacancyKey || "");
        formData.set("hours", cell.dataset.hours || "");
        cell.classList.add("is-saving");
        button.disabled = true;
        let requestPromise = null;
        try {
          requestPromise = fetch(matrix.dataset.cellUpdateUrl, {
            method: "POST",
            body: formData,
            headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
          });
          pendingCellSaves.add(requestPromise);
          const payload = await responsePayload(await requestPromise);
          updateNeedControls(payload);
        } catch (error) {
          window.alert(error.message);
        } finally {
          if (requestPromise) pendingCellSaves.delete(requestPromise);
          cell.classList.remove("is-saving");
          if (!cell.classList.contains("is-locked") && matrix.dataset.editable === "1") {
            button.disabled = false;
          }
        }
      });
    });
  };

  bindCellControls();

  const clearMatrixHover = (matrix) => {
    matrix.querySelectorAll(".is-row-hovered").forEach(
      (element) => element.classList.remove("is-row-hovered")
    );
    matrix.querySelectorAll(".is-column-hovered").forEach(
      (element) => element.classList.remove("is-column-hovered")
    );
  };
  document.addEventListener("pointerover", (event) => {
    const matrix = event.target.closest("[data-workload-matrix]");
    if (!matrix) return;
    clearMatrixHover(matrix);
    const row = event.target.closest("tbody tr[data-workload-holder-row]");
    row?.classList.add("is-row-hovered");
    const columnCell = event.target.closest("[data-matrix-column-index]");
    const columnIndex = columnCell?.dataset.matrixColumnIndex;
    if (columnIndex === undefined) return;
    matrix.querySelectorAll(
      `[data-matrix-column-index="${columnIndex}"]`
    ).forEach((element) => element.classList.add("is-column-hovered"));
  });
  document.addEventListener("pointerout", (event) => {
    const matrix = event.target.closest("[data-workload-matrix]");
    if (matrix && !matrix.contains(event.relatedTarget)) {
      clearMatrixHover(matrix);
    }
  });

  document.addEventListener("change", async (event) => {
    const select = event.target.closest("[data-activity-plan-kind]");
    if (!select || !select.value) return;
    const form = select.closest("form");
    const formData = new FormData(form);
    const selectedValue = select.value;
    const remainingSubjectOptions = Array.from(select.options)
      .filter((option) => !option.value || option.value !== selectedValue)
      .map((option) => option.cloneNode(true));
    select.closest("details")?.removeAttribute("open");
    select.disabled = true;
    try {
      const payload = await responsePayload(await fetch(form.action, {
        method: "POST",
        body: formData,
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      }));
      await refreshMatrix(
        payload.holder_key || "",
        remainingSubjectOptions,
      );
    } catch (error) {
      window.alert(error.message);
      select.disabled = false;
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-workload-async-subject-delete]");
    if (!form) return;
    event.preventDefault();
    if (!window.confirm(form.dataset.confirm || "Удалить строку?")) return;
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("button").forEach((button) => button.disabled = true);
    try {
      const payload = await responsePayload(await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      }));
      await refreshMatrix(payload.holder_key || "");
    } catch (error) {
      window.alert(error.message);
      form.removeAttribute("aria-busy");
      form.querySelectorAll("button").forEach((button) => button.disabled = false);
    }
  });

  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("[data-workload-async-holder-delete]");
    if (!form) return;
    event.preventDefault();
    if (!window.confirm(form.dataset.confirm || "Удалить строку преподавателя?")) return;
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("button").forEach((button) => button.disabled = true);
    try {
      const payload = await responsePayload(await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      }));
      if (payload.teacher) addTeacherPickerOption(payload.teacher);
      removeWorkloadHolderFilterOption(payload.holder_key);
      const targetUrl = new URL(window.location.href);
      const teacherQuery = document.querySelector(
        "[data-workload-filterbar] [name=\"teacher_query\"]"
      );
      const queryMatchesDeletedTeacher = (
        teacherQuery
        && normalizeTeacherSearch(teacherQuery.value)
          === normalizeTeacherSearch(payload.holder_name)
      );
      if (queryMatchesDeletedTeacher) {
        teacherQuery.value = "";
        targetUrl.searchParams.delete("teacher_query");
        targetUrl.searchParams.delete("holder_page");
      }
      await loadHolderPage(targetUrl, {pushHistory: queryMatchesDeletedTeacher});
      const releasedHours = Number(payload.released_weekly_hours || 0);
      adjustTotal("[data-workload-total-allocated]", -releasedHours);
      adjustTotal("[data-workload-total-remaining]", releasedHours);
    } catch (error) {
      window.alert(error.message);
      form.removeAttribute("aria-busy");
      form.querySelectorAll("button").forEach((button) => button.disabled = false);
    }
  });

  teacherDialog?.querySelector("[data-workload-async-add]")?.addEventListener(
    "submit",
    async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      const submitter = event.submitter;
      const formData = new FormData(form);
      if (submitter?.name) formData.set(submitter.name, submitter.value);
      if (!teacherPickerValue?.value) {
        teacherPickerSearch?.setCustomValidity("Выберите преподавателя из найденных вариантов.");
        teacherPickerSearch?.reportValidity();
        renderTeacherPicker();
        return;
      }
      form.setAttribute("aria-busy", "true");
      form.querySelectorAll("button").forEach((button) => button.disabled = true);
      try {
        const payload = await responsePayload(await fetch(form.action, {
          method: "POST",
          body: formData,
          headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
        }));
        removeTeacherPickerOption(payload.teacher_id);
        upsertWorkloadHolderFilterOption(
          payload.holder_key,
          payload.teacher_name,
          false,
        );
        teacherDialog.close();
        form.reset();
        if (payload.teacher_name && payload.holder_key) {
          const targetUrl = new URL(window.location.href);
          targetUrl.searchParams.set("teacher_query", payload.teacher_name);
          targetUrl.searchParams.set("focus_holder", payload.holder_key);
          targetUrl.searchParams.delete("holder_page");
          const teacherQuery = document.querySelector(
            "[data-workload-filterbar] [name=\"teacher_query\"]"
          );
          if (teacherQuery) teacherQuery.value = payload.teacher_name;
          await loadHolderPage(targetUrl);
        } else {
          await refreshMatrix(payload.holder_key || "");
        }
      } catch (error) {
        window.alert(error.message);
      } finally {
        form.removeAttribute("aria-busy");
        form.querySelectorAll("button").forEach((button) => button.disabled = false);
      }
    },
  );
  vacancyForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    form.setAttribute("aria-busy", "true");
    form.querySelectorAll("button").forEach((button) => button.disabled = true);
    try {
      const payload = await responsePayload(await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
      }));
      upsertWorkloadHolderFilterOption(
        payload.holder_key,
        payload.holder_name,
        true,
      );
      vacancyDialog.close();
      form.reset();
      const targetUrl = new URL(window.location.href);
      targetUrl.searchParams.set("teacher_query", payload.holder_name);
      targetUrl.searchParams.set("focus_holder", payload.holder_key);
      targetUrl.searchParams.delete("holder_page");
      if (workloadHolderFilterSearch) {
        workloadHolderFilterSearch.value = payload.holder_name;
      }
      await loadHolderPage(targetUrl);
    } catch (error) {
      window.alert(error.message);
    } finally {
      form.removeAttribute("aria-busy");
      form.querySelectorAll("button").forEach((button) => button.disabled = false);
    }
  });
  document.querySelector("[data-workload-status-form]")?.addEventListener(
    "submit",
    async (event) => {
      if (!pendingCellSaves.size) return;
      event.preventDefault();
      await Promise.allSettled(Array.from(pendingCellSaves));
      event.currentTarget.submit();
    },
  );

  const focusUrl = new URL(window.location.href);
  const focusHolder = focusUrl.searchParams.get("focus_holder");
  if (focusHolder) {
    window.requestAnimationFrame(() => focusHolderRows(focusHolder));
    focusUrl.searchParams.delete("focus_holder");
    window.history.replaceState({}, "", focusUrl);
  }
})();
