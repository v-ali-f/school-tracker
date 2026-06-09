const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('portalApp', {
  config: () => ipcRenderer.invoke('portal-api:config'),
  request: (request) => ipcRenderer.invoke('portal-api:request', request),
  openPortal: () => ipcRenderer.invoke('portal-api:open-portal')
});
