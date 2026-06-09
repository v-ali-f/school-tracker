const state = {
  user: null,
  permissions: {},
  notifications: [],
  incidents: [],
  categories: [],
  classes: [],
  children: []
};

const elements = {
  loginView: document.getElementById('loginView'),
  shellView: document.getElementById('shellView'),
  loginForm: document.getElementById('loginForm'),
  loginMessage: document.getElementById('loginMessage'),
  username: document.getElementById('username'),
  password: document.getElementById('password'),
  userCaption: document.getElementById('userCaption'),
  pageTitle: document.getElementById('pageTitle'),
  statusLine: document.getElementById('statusLine'),
  unreadCount: document.getElementById('unreadCount'),
  incidentCount: document.getElementById('incidentCount'),
  incidentAccess: document.getElementById('incidentAccess'),
  overviewNotifications: document.getElementById('overviewNotifications'),
  overviewIncidents: document.getElementById('overviewIncidents'),
  notificationList: document.getElementById('notificationList'),
  notificationTotal: document.getElementById('notificationTotal'),
  incidentList: document.getElementById('incidentList'),
  incidentTotal: document.getElementById('incidentTotal'),
  refreshButton: document.getElementById('refreshButton'),
  logoutButton: document.getElementById('logoutButton'),
  openPortalButton: document.getElementById('openPortalButton'),
  incidentForm: document.getElementById('incidentForm'),
  incidentDate: document.getElementById('incidentDate'),
  incidentTime: document.getElementById('incidentTime'),
  incidentCategory: document.getElementById('incidentCategory'),
  incidentDescription: document.getElementById('incidentDescription'),
  classSelect: document.getElementById('classSelect'),
  studentSearch: document.getElementById('studentSearch'),
  studentCounter: document.getElementById('studentCounter'),
  studentList: document.getElementById('studentList'),
  incidentMessage: document.getElementById('incidentMessage'),
  clearIncidentButton: document.getElementById('clearIncidentButton')
};

const sectionTitles = {
  overview: 'Обзор',
  notifications: 'Уведомления',
  incidents: 'Инциденты',
  newIncident: 'Новый инцидент'
};

function setStatus(message, tone) {
  elements.statusLine.textContent = message || '';
  elements.statusLine.style.color = tone === 'error' ? 'var(--danger)' : '';
}

function setMessage(element, message, success = false) {
  element.textContent = message || '';
  element.classList.toggle('success', success);
}

function formatDate(value) {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function todayParts() {
  const now = new Date();
  const yyyy = now.getFullYear();
  const mm = String(now.getMonth() + 1).padStart(2, '0');
  const dd = String(now.getDate()).padStart(2, '0');
  const hh = String(now.getHours()).padStart(2, '0');
  const min = String(now.getMinutes()).padStart(2, '0');
  return { date: `${yyyy}-${mm}-${dd}`, time: `${hh}:${min}` };
}

async function api(path, options = {}) {
  const response = await window.portalApp.request({
    path,
    method: options.method || 'GET',
    query: options.query,
    body: options.body
  });

  if (!response.ok) {
    const message = response.data && response.data.message
      ? response.data.message
      : 'Сервер портала вернул ошибку.';
    const error = new Error(message);
    error.status = response.status;
    error.data = response.data;
    throw error;
  }

  return response.data;
}

function showLogin(message) {
  state.user = null;
  elements.shellView.hidden = true;
  elements.loginView.hidden = false;
  setMessage(elements.loginMessage, message || '');
  elements.username.focus();
}

function showShell() {
  elements.loginView.hidden = true;
  elements.shellView.hidden = false;
}

function switchSection(name) {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.section === name);
  });
  document.querySelectorAll('.content-section').forEach((section) => {
    section.hidden = section.id !== `${name}Section`;
  });
  elements.pageTitle.textContent = sectionTitles[name] || 'Обзор';
}

function renderEmpty(container, text) {
  container.innerHTML = `<p class="empty">${text}</p>`;
}

function notificationItem(item) {
  const title = item.title || 'Уведомление';
  const message = item.message || '';
  const badge = item.is_read ? 'прочитано' : 'новое';
  const warning = item.is_read ? '' : ' warning';
  return `
    <article class="list-item">
      <div class="list-item-header">
        <h3>${escapeHtml(title)}</h3>
        <span class="badge${warning}">${badge}</span>
      </div>
      <p>${escapeHtml(message)}</p>
      <p>${escapeHtml(formatDate(item.created_at))}</p>
    </article>
  `;
}

function incidentItem(item) {
  const children = (item.children || []).map((child) => child.fio).join(', ');
  return `
    <article class="list-item">
      <div class="list-item-header">
        <h3>${escapeHtml(item.category || 'Инцидент')}</h3>
        <span class="badge">${escapeHtml(item.status_label || item.status || '')}</span>
      </div>
      <p>${escapeHtml(item.description || '')}</p>
      <p>${escapeHtml(children || 'Без учеников')} · ${escapeHtml(formatDate(item.occurred_at))}</p>
    </article>
  `;
}

function renderDashboard() {
  elements.userCaption.textContent = state.user
    ? `${state.user.fio || state.user.username} · ${state.user.role || ''}`
    : '';

  const unread = state.notifications.filter((item) => !item.is_read).length;
  elements.unreadCount.textContent = String(unread);
  elements.incidentCount.textContent = String(state.incidents.length);
  elements.incidentAccess.textContent = state.permissions.can_add_incident ? 'есть' : 'нет';

  const recentNotifications = state.notifications.slice(0, 4);
  const recentIncidents = state.incidents.slice(0, 4);

  if (recentNotifications.length) {
    elements.overviewNotifications.innerHTML = recentNotifications.map(notificationItem).join('');
  } else {
    renderEmpty(elements.overviewNotifications, 'Новых уведомлений нет.');
  }

  if (recentIncidents.length) {
    elements.overviewIncidents.innerHTML = recentIncidents.map(incidentItem).join('');
  } else {
    renderEmpty(elements.overviewIncidents, 'Инцидентов пока нет.');
  }

  elements.notificationTotal.textContent = `${state.notifications.length} всего`;
  elements.notificationList.innerHTML = state.notifications.length
    ? state.notifications.map(notificationItem).join('')
    : '<p class="empty">Уведомлений нет.</p>';

  elements.incidentTotal.textContent = `${state.incidents.length} всего`;
  elements.incidentList.innerHTML = state.incidents.length
    ? state.incidents.map(incidentItem).join('')
    : '<p class="empty">Инцидентов нет.</p>';
}

function renderMeta() {
  elements.incidentCategory.innerHTML = [
    '<option value="">Выберите категорию</option>',
    ...state.categories.map((item) => `<option value="${escapeAttribute(item)}">${escapeHtml(item)}</option>`)
  ].join('');

  elements.classSelect.innerHTML = [
    '<option value="">Выберите класс</option>',
    ...state.classes.map((item) => `<option value="${item.id}">${escapeHtml(item.name || `${item.grade} класс`)}</option>`)
  ].join('');
}

function renderChildren() {
  const query = normalize(elements.studentSearch.value);
  const visibleChildren = state.children.filter((child) => normalize(child.fio).includes(query));
  elements.studentCounter.textContent = state.children.length
    ? `Найдено: ${visibleChildren.length}`
    : 'Выберите класс';

  if (!state.children.length) {
    renderEmpty(elements.studentList, 'После выбора класса здесь появятся ученики.');
    return;
  }

  if (!visibleChildren.length) {
    renderEmpty(elements.studentList, 'Совпадений нет.');
    return;
  }

  elements.studentList.innerHTML = visibleChildren.map((child) => `
    <label class="student-item">
      <input type="checkbox" name="child_ids" value="${child.id}">
      <span>${escapeHtml(child.fio)}</span>
    </label>
  `).join('');
}

async function loadDashboard() {
  setStatus('Обновляем данные...');
  try {
    const [me, notifications, incidents, meta, classes] = await Promise.all([
      api('/me'),
      api('/notifications'),
      api('/incidents/mine'),
      api('/incidents/meta'),
      api('/classes')
    ]);

    state.user = me.user;
    state.permissions = me.permissions || {};
    state.notifications = notifications.items || [];
    state.incidents = incidents.items || [];
    state.categories = meta.categories || [];
    state.classes = classes.items || [];

    renderDashboard();
    renderMeta();
    setStatus('Данные обновлены.');
  } catch (error) {
    if (error.status === 401) {
      showLogin();
      return;
    }
    setStatus(error.message, 'error');
  }
}

async function checkSession() {
  try {
    const me = await api('/me');
    state.user = me.user;
    state.permissions = me.permissions || {};
    showShell();
    await loadDashboard();
  } catch (error) {
    showLogin();
  }
}

async function submitLogin(event) {
  event.preventDefault();
  setMessage(elements.loginMessage, '');
  elements.loginForm.querySelector('button').disabled = true;

  try {
    const result = await api('/auth/login', {
      method: 'POST',
      body: {
        username: elements.username.value,
        password: elements.password.value
      }
    });
    state.user = result.user;
    elements.password.value = '';
    showShell();
    await loadDashboard();
  } catch (error) {
    setMessage(elements.loginMessage, error.message);
  } finally {
    elements.loginForm.querySelector('button').disabled = false;
  }
}

async function logout() {
  try {
    await api('/auth/logout', { method: 'POST' });
  } catch (error) {
    // The local app can still return to the login screen.
  }
  showLogin();
}

async function loadChildrenForClass() {
  const classId = elements.classSelect.value;
  state.children = [];
  elements.studentSearch.value = '';

  if (!classId) {
    renderChildren();
    return;
  }

  setStatus('Загружаем учеников...');
  try {
    const result = await api(`/classes/${classId}/children`);
    state.children = result.items || [];
    renderChildren();
    setStatus('');
  } catch (error) {
    setStatus(error.message, 'error');
  }
}

function resetIncidentForm() {
  elements.incidentForm.reset();
  const parts = todayParts();
  elements.incidentDate.value = parts.date;
  elements.incidentTime.value = parts.time;
  state.children = [];
  renderChildren();
  setMessage(elements.incidentMessage, '');
}

async function submitIncident(event) {
  event.preventDefault();
  setMessage(elements.incidentMessage, '');

  const childIds = Array.from(elements.studentList.querySelectorAll('input[name="child_ids"]:checked'))
    .map((input) => Number(input.value));

  if (!childIds.length) {
    setMessage(elements.incidentMessage, 'Выберите хотя бы одного ученика.');
    return;
  }

  elements.incidentForm.querySelector('button[type="submit"]').disabled = true;
  try {
    await api('/incidents', {
      method: 'POST',
      body: {
        occurred_date: elements.incidentDate.value,
        occurred_time: elements.incidentTime.value,
        category: elements.incidentCategory.value,
        description: elements.incidentDescription.value,
        child_ids: childIds
      }
    });

    setMessage(elements.incidentMessage, 'Инцидент сохранен.', true);
    resetIncidentForm();
    await loadDashboard();
    switchSection('incidents');
  } catch (error) {
    setMessage(elements.incidentMessage, error.message);
  } finally {
    elements.incidentForm.querySelector('button[type="submit"]').disabled = false;
  }
}

function normalize(value) {
  return String(value || '').toLowerCase().replace(/ё/g, 'е').trim();
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

function bindEvents() {
  elements.loginForm.addEventListener('submit', submitLogin);
  elements.refreshButton.addEventListener('click', loadDashboard);
  elements.logoutButton.addEventListener('click', logout);
  elements.openPortalButton.addEventListener('click', () => window.portalApp.openPortal());
  elements.classSelect.addEventListener('change', loadChildrenForClass);
  elements.studentSearch.addEventListener('input', renderChildren);
  elements.incidentForm.addEventListener('submit', submitIncident);
  elements.clearIncidentButton.addEventListener('click', resetIncidentForm);

  document.querySelectorAll('.nav-item').forEach((button) => {
    button.addEventListener('click', () => switchSection(button.dataset.section));
  });

  document.querySelectorAll('[data-section-jump]').forEach((button) => {
    button.addEventListener('click', () => switchSection(button.dataset.sectionJump));
  });
}

async function boot() {
  bindEvents();
  resetIncidentForm();
  await checkSession();
}

boot();
