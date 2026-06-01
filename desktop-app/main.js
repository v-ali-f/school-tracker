const { app, BrowserWindow, Menu, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

function readConfig() {
  const configPath = path.join(__dirname, 'config.json');
  const fallback = {
    portalUrl: 'http://10.172.85.55/',
    appTitle: 'Система сопровождения обучающихся'
  };

  try {
    const raw = fs.readFileSync(configPath, 'utf8');
    return { ...fallback, ...JSON.parse(raw) };
  } catch (error) {
    return fallback;
  }
}

function createWindow() {
  const config = readConfig();

  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 1000,
    minHeight: 650,
    title: config.appTitle,
    backgroundColor: '#ffffff',
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

  win.loadURL(config.portalUrl);

  win.webContents.setWindowOpenHandler(({ url }) => {
    const portalOrigin = new URL(config.portalUrl).origin;

    try {
      const targetOrigin = new URL(url).origin;
      if (targetOrigin === portalOrigin) {
        return { action: 'allow' };
      }
    } catch (error) {
      // ignore
    }

    shell.openExternal(url);
    return { action: 'deny' };
  });

  win.webContents.on('did-fail-load', () => {
    dialog.showMessageBox(win, {
      type: 'warning',
      title: 'Портал недоступен',
      message: 'Не удалось открыть школьный портал.',
      detail: 'Проверьте подключение к школьной сети и доступность сервера: ' + config.portalUrl,
      buttons: ['Повторить', 'Закрыть']
    }).then((result) => {
      if (result.response === 0) {
        win.loadURL(config.portalUrl);
      } else {
        app.quit();
      }
    });
  });
}

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
