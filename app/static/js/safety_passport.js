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

const passportPreviewModal = document.getElementById('passport-preview-modal');
if (passportPreviewModal) {
  const frame = document.getElementById('passport-preview-frame');
  const printButton = document.getElementById('passport-preview-print');

  passportPreviewModal.addEventListener('show.bs.modal', () => {
    printButton.disabled = true;
    frame.src = frame.dataset.previewUrl;
  });

  frame.addEventListener('load', () => {
    try {
      const expectedUrl = new URL(frame.dataset.previewUrl, window.location.href).href;
      printButton.disabled = frame.contentWindow.location.href !== expectedUrl;
    } catch (_error) {
      printButton.disabled = true;
    }
  });

  printButton.addEventListener('click', () => {
    if (printButton.disabled) return;
    frame.contentWindow.focus();
    frame.contentWindow.print();
  });

  passportPreviewModal.addEventListener('hidden.bs.modal', () => {
    printButton.disabled = true;
    frame.src = 'about:blank';
  });
}
