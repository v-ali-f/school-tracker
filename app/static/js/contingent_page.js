/* Extracted from app/templates/contingent.html; page behavior only. */

(function initializeApplicationsCells() {
    document.querySelectorAll(".applications-cell-input").forEach(function (input) {
      async function saveApplicationsValue() {
        const previousValue = input.dataset.savedValue || "0";
        const nextValue = input.value.trim();
        const normalizedValue = nextValue === "" ? "0" : nextValue;
        if (normalizedValue === previousValue) {
          input.value = normalizedValue === "0" ? "" : normalizedValue;
          return;
        }

        input.classList.add("is-saving");
        const body = new URLSearchParams({
          applications_count: normalizedValue,
          building_id: input.dataset.buildingId || "",
        });

        try {
          const response = await fetch(input.dataset.saveUrl, {
            method: "POST",
            headers: {
              "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
              "X-Requested-With": "XMLHttpRequest",
              "Accept": "application/json",
            },
            body: body.toString(),
          });
          const result = await response.json();
          if (!response.ok || !result.ok) {
            throw new Error(result.error || "Не удалось сохранить значение");
          }
          input.value = result.applications_count ? String(result.applications_count) : "";
          input.dataset.savedValue = String(result.applications_count);
          input.removeAttribute("title");
        } catch (error) {
          input.value = previousValue === "0" ? "" : previousValue;
          input.classList.add("is-invalid");
          input.title = error.message;
        } finally {
          input.classList.remove("is-saving");
        }
      }

      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          input.blur();
        }
      });

      input.addEventListener("input", function () {
        input.value = input.value.replace(/\D/g, "");
        input.classList.remove("is-invalid");
      });

      input.addEventListener("blur", saveApplicationsValue);
    });
  })();

  (function fitContingentTextCells() {
    function fitCell(cell) {
      let fontSize = 15;
      cell.style.setProperty("--fit-font-size", fontSize + "px");
      while (cell.scrollWidth > cell.clientWidth && fontSize > 13) {
        fontSize -= 0.5;
        cell.style.setProperty("--fit-font-size", fontSize + "px");
      }
    }

    function fitAllCells() {
      document.querySelectorAll(".contingent-classes-table .fit-nowrap").forEach(fitCell);
    }

    fitAllCells();
    window.addEventListener("resize", fitAllCells);
  })();
