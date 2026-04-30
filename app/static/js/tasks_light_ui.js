
(function () {
  function textOf(el) { return (el && el.textContent || '').toLowerCase().replace(/ё/g, 'е').trim(); }
  function isTasksPage() {
    return location.pathname.indexOf('/tasks') === 0 || location.pathname.indexOf('/tasks/') === 0 || document.querySelector('.kanban-board,.task-kanban,.tasks-kanban,[data-page="tasks"]');
  }
  function addToggle() {
    if (document.querySelector('.v183-task-ui-toggle')) return;
    var target = document.querySelector('.task-toolbar,.tasks-toolbar,.page-actions,.d-flex.justify-content-between,.d-flex.align-items-center');
    if (!target) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'v183-task-ui-toggle';
    btn.textContent = document.body.classList.contains('tasks-detailed-mode') ? 'Компактно' : 'Подробно';
    btn.onclick = function () {
      document.body.classList.toggle('tasks-detailed-mode');
      try { localStorage.setItem('tasksDetailedMode', document.body.classList.contains('tasks-detailed-mode') ? '1' : '0'); } catch(e) {}
      btn.textContent = document.body.classList.contains('tasks-detailed-mode') ? 'Компактно' : 'Подробно';
    };
    target.appendChild(btn);
  }
  function compactFilters() {
    var filters = document.querySelectorAll('.task-filters,.tasks-filters,form.task-filter-form,form.tasks-filter-form');
    filters.forEach(function (f) {
      if (f.dataset.v183Filters === '1') return;
      f.dataset.v183Filters = '1';
      f.classList.add('is-collapsible');
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-outline-secondary btn-sm mb-2';
      b.textContent = 'Фильтры';
      b.onclick = function () { f.classList.toggle('is-open'); };
      f.parentNode.insertBefore(b, f);
    });
  }
  function hideRareColumns() {
    if (document.body.classList.contains('tasks-detailed-mode')) return;
    var words = ['закрыта', 'закрытые', 'отменена', 'отмененные', 'отменённые', 'архив'];
    var columns = document.querySelectorAll('.kanban-column,.task-column,.tasks-column,[data-kanban-column]');
    columns.forEach(function (col) {
      var t = textOf(col.querySelector('h1,h2,h3,h4,h5,.column-title,.kanban-title,.card-header') || col);
      if (words.some(function (w) { return t.indexOf(w) !== -1; })) {
        col.classList.add('v183-hidden-kanban-column');
      }
    });
  }
  function boot() {
    if (!isTasksPage()) return;
    document.body.classList.add('tasks-light-ui');
    try { if (localStorage.getItem('tasksDetailedMode') === '1') document.body.classList.add('tasks-detailed-mode'); } catch(e) {}
    addToggle(); compactFilters(); hideRareColumns();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
