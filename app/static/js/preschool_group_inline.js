document.querySelectorAll('[data-group-row]').forEach((row) => {
  const toggle = row.querySelector('[data-group-toggle]');
  const cancel = row.querySelector('[data-group-cancel]');
  if (!toggle || !cancel) return;

  const setEditing = (editing) => {
    row.querySelectorAll('[data-group-display]').forEach((element) => { element.classList.toggle('d-none', editing); });
    row.querySelectorAll('[data-group-edit]').forEach((element) => { element.classList.toggle('d-none', !editing); });
    if (editing) toggle.style.setProperty('display', 'none', 'important');
    else toggle.style.removeProperty('display');
  };

  toggle.addEventListener('click', () => setEditing(true));
  cancel.addEventListener('click', () => setEditing(false));
});
