document.addEventListener('click', (event) => {
  const add = event.target.closest('[data-add-passport-row]');
  if (add) {
    const body = document.querySelector(`#passport-table-${add.dataset.addPassportRow} tbody`);
    if (!body || !body.firstElementChild) return;
    const clone = body.firstElementChild.cloneNode(true);
    clone.querySelectorAll('input').forEach((input) => { input.value = ''; });
    body.appendChild(clone);
    clone.querySelector('input')?.focus();
    return;
  }
  const remove = event.target.closest('[data-remove-passport-row]');
  if (remove) {
    const row = remove.closest('tr');
    const body = row?.parentElement;
    if (!row || !body) return;
    if (body.children.length === 1) row.querySelectorAll('input').forEach((input) => { input.value = ''; });
    else row.remove();
  }
});
