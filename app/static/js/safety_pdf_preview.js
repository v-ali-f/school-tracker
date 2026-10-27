(() => {
  const modal = document.getElementById('safety-pdf-preview-modal');
  if (!modal) return;

  const frame = document.getElementById('safety-pdf-preview-frame');
  const title = document.getElementById('safety-pdf-preview-title');
  const printButton = document.getElementById('safety-pdf-print');
  const download = document.getElementById('safety-pdf-download');
  const hint = document.getElementById('safety-pdf-print-hint');

  modal.addEventListener('show.bs.modal', (event) => {
    const trigger = event.relatedTarget;
    if (!trigger || !trigger.dataset.pdfUrl) return;
    title.textContent = trigger.dataset.pdfTitle || 'Инструкция';
    download.href = trigger.dataset.pdfDownloadUrl || trigger.dataset.pdfUrl;
    const previewOnly = trigger.dataset.pdfPreviewOnly === '1';
    printButton.hidden = previewOnly;
    download.hidden = previewOnly;
    hint.hidden = true;
    printButton.disabled = true;
    frame.src = trigger.dataset.pdfUrl;
  });

  frame.addEventListener('load', () => {
    if (frame.src !== 'about:blank') printButton.disabled = false;
  });

  printButton.addEventListener('click', () => {
    try {
      frame.contentWindow.focus();
      frame.contentWindow.print();
      hint.hidden = false;
    } catch (_error) {
      hint.hidden = false;
    }
  });

  modal.addEventListener('hidden.bs.modal', () => {
    frame.src = 'about:blank';
    printButton.disabled = true;
    hint.hidden = true;
    download.removeAttribute('href');
    printButton.hidden = false;
    download.hidden = false;
  });
})();
