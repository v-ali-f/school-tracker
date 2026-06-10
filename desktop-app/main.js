const { app, BrowserWindow, Menu, shell, dialog, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

let currentConfig = null;
let sessionCookie = '';

function readConfig() {
  const configPath = path.join(__dirname, 'config.json');
  const fallback = {
    portalUrl: 'http://10.172.85.55/',
    apiBaseUrl: 'http://10.172.85.55/mobile/api',
    appTitle: 'Альтаир'
  };

  try {
    const raw = fs.readFileSync(configPath, 'utf8');
    const config = { ...fallback, ...JSON.parse(raw) };
    config.portalUrl = normalizeUrl(config.portalUrl);
    config.apiBaseUrl = normalizeUrl(config.apiBaseUrl || `${config.portalUrl}mobile/api`).replace(/\/$/, '');
    return config;
  } catch (error) {
    return fallback;
  }
}

function normalizeUrl(value) {
  return String(value || '').trim().replace(/\/?$/, '/');
}

function publicConfig() {
  return {
    portalUrl: currentConfig.portalUrl,
    apiBaseUrl: currentConfig.apiBaseUrl,
    appTitle: currentConfig.appTitle
  };
}

function updateSessionCookie(response) {
  const setCookies = typeof response.headers.getSetCookie === 'function'
    ? response.headers.getSetCookie()
    : [response.headers.get('set-cookie')].filter(Boolean);

  if (!setCookies.length) {
    return;
  }

  const jar = new Map(
    sessionCookie
      .split(';')
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const index = item.indexOf('=');
        return [item.slice(0, index), item.slice(index + 1)];
      })
  );

  for (const raw of setCookies) {
    const first = String(raw).split(';')[0];
    const index = first.indexOf('=');
    if (index > 0) {
      jar.set(first.slice(0, index), first.slice(index + 1));
    }
  }

  sessionCookie = Array.from(jar.entries()).map(([key, value]) => `${key}=${value}`).join('; ');
}

function apiUrl(apiPath, query) {
  const url = new URL(`${currentConfig.apiBaseUrl}${apiPath.startsWith('/') ? apiPath : `/${apiPath}`}`);
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return url;
}

async function handleApiRequest(event, request) {
  const method = request.method || 'GET';
  const headers = {
    Accept: 'application/json'
  };

  if (sessionCookie) {
    headers.Cookie = sessionCookie;
  }

  const options = { method, headers };
  if (request.body !== undefined && request.body !== null) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(request.body);
  }

  try {
    const response = await fetch(apiUrl(request.path, request.query), options);
    updateSessionCookie(response);

    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (error) {
      data = null;
    }

    if (request.path === '/auth/logout') {
      sessionCookie = '';
    }

    return {
      ok: response.ok,
      status: response.status,
      data,
      text
    };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      data: {
        ok: false,
        error: 'network_error',
        message: 'Не удалось подключиться к серверу портала.'
      },
      text: String(error && error.message ? error.message : error)
    };
  }
}

function createWindow() {
  currentConfig = readConfig();

  const win = new BrowserWindow({
    width: 1180,
    height: 780,
    minWidth: 1040,
    minHeight: 680,
    title: currentConfig.appTitle,
    backgroundColor: '#f6f7f3',
    show: false,
    autoHideMenuBar: true,
    icon: path.join(__dirname, 'assets', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: true
    }
  });

  Menu.setApplicationMenu(null);

  win.once('ready-to-show', () => {
    win.show();
  });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  win.webContents.on('did-fail-load', () => {
    dialog.showMessageBox(win, {
      type: 'warning',
      title: 'Приложение недоступно',
      message: 'Не удалось открыть рабочий экран приложения.',
      buttons: ['Повторить', 'Закрыть']
    }).then((result) => {
      if (result.response === 0) {
        win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
      } else {
        app.quit();
      }
    });
  });
}

ipcMain.handle('portal-api:config', () => publicConfig());
ipcMain.handle('portal-api:request', handleApiRequest);
ipcMain.handle('portal-api:open-portal', () => {
  shell.openExternal(currentConfig.portalUrl);
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  app.quit();
});
