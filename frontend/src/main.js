const { app, BrowserWindow, Tray, Menu, nativeImage,
        ipcMain, screen, globalShortcut } = require('electron');
const path    = require('path');
const { spawn } = require('child_process');

let pinWindow  = null;
let mainWindow = null;
let lensWindow = null;
let tray       = null;
let backend    = null;
let isFullscreen = false;

// ── Backend ───────────────────────────────────────────────────────────────────
function startBackend() {
  const backendDir = path.join(__dirname, '../../backend');
  const python     = 'python';
  backend = spawn(python, ['main.py'], {
    cwd: backendDir, stdio: ['ignore','pipe','pipe'], windowsHide: true,
  });
  backend.stdout.on('data', d => process.stdout.write(`[Backend] ${d}`));
  backend.stderr.on('data', d => process.stderr.write(`[Backend] ${d}`));
  backend.on('exit', code => console.log(`[Backend] exited ${code}`));
  return new Promise(res => setTimeout(res, 2000));
}

// ── PIN window ────────────────────────────────────────────────────────────────
function createPinWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  pinWindow = new BrowserWindow({
    width: 340, height: 560,
    x: Math.floor((width - 340) / 2),
    y: Math.floor((height - 560) / 2),
    frame: false, transparent: true,
    resizable: false, alwaysOnTop: true,
    backgroundColor: '#00000000',
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  pinWindow.loadFile(path.join(__dirname, 'pin.html'));
}

// ── Main window ───────────────────────────────────────────────────────────────
function createMainWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  mainWindow = new BrowserWindow({
    width: 420, height: 720,
    x: width - 440,
    y: Math.floor((height - 720) / 2),
    frame: false, transparent: true,
    resizable: true, minWidth: 360, minHeight: 500,
    backgroundColor: '#00000000', hasShadow: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false,
                      backgroundThrottling: false },
  });
  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── LENS window ───────────────────────────────────────────────────────────────
function createLensWindow() {
  const { width, height } = screen.getPrimaryDisplay().bounds;
  lensWindow = new BrowserWindow({
    width, height, x: 0, y: 0,
    frame: false, transparent: true, alwaysOnTop: true,
    skipTaskbar: true, focusable: false, hasShadow: false,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  lensWindow.loadFile(path.join(__dirname, 'lens.html'));
  lensWindow.setIgnoreMouseEvents(true, { forward: true });
  lensWindow.on('closed', () => { lensWindow = null; });
}

// ── Tray ──────────────────────────────────────────────────────────────────────
function createTray() {
  // Simple 16x16 cyan dot icon (inline PNG base64)
  const iconB64 = 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAANklEQVQ4T2NkYGD4z8BAgFFagJGBgeE/hRpHDRg1gBqhQI1UMGoANUKBGqlg1ABqhAI1UgEAn3AENXB1eTcAAAAASUVORK5CYII=';
  const icon = nativeImage.createFromDataURL(`data:image/png;base64,${iconB64}`);
  tray = new Tray(icon);
  const menu = Menu.buildFromTemplate([
    { label: 'Show VNSA',    click: () => mainWindow?.show() },
    { label: 'Hide VNSA',    click: () => mainWindow?.hide() },
    { type: 'separator' },
    { label: 'Fullscreen',   click: () => toggleFullscreen() },
    { type: 'separator' },
    { label: 'Quit VNSA',    click: () => { backend?.kill(); app.quit(); } },
  ]);
  tray.setToolTip('VNSA 2.0');
  tray.setContextMenu(menu);
  tray.on('click', () => {
    if (mainWindow?.isVisible()) mainWindow.focus();
    else mainWindow?.show();
  });
}

// ── Fullscreen ────────────────────────────────────────────────────────────────
function toggleFullscreen() {
  if (!mainWindow) return;
  isFullscreen = !isFullscreen;
  if (isFullscreen) {
    mainWindow.setFullScreen(true);
    mainWindow.setAlwaysOnTop(false);
  } else {
    mainWindow.setFullScreen(false);
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    mainWindow.setSize(420, 720);
    mainWindow.setPosition(width - 440, Math.floor((height - 720) / 2));
  }
  mainWindow.webContents.send('fullscreen-change', isFullscreen);
}

// ── IPC ───────────────────────────────────────────────────────────────────────
ipcMain.on('pin-ok', () => {
  pinWindow?.close();
  pinWindow = null;
  createMainWindow();
  createTray();
});
ipcMain.on('pin-quit',    () => { backend?.kill(); app.quit(); });
ipcMain.on('pin-lockout', () => { backend?.kill(); app.quit(); });

ipcMain.on('lens-open',  () => { if (!lensWindow) createLensWindow(); });
ipcMain.on('lens-close', () => { lensWindow?.close(); });
ipcMain.on('lens-insight', (_, data) => {
  lensWindow?.webContents.send('insight', data);
});

ipcMain.on('window-minimize',  () => mainWindow?.minimize());
ipcMain.on('window-close',     () => mainWindow?.hide());
ipcMain.on('window-fullscreen', () => toggleFullscreen());
ipcMain.on('window-resize',    (_, { w, h }) => mainWindow?.setSize(w, h));

// ── App lifecycle ─────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  await startBackend();
  createPinWindow();

  // F11 shortcut for fullscreen when main window exists
  globalShortcut.register('F11', () => { if (mainWindow) toggleFullscreen(); });
});

app.on('window-all-closed', e => e.preventDefault());
app.on('before-quit', () => { backend?.kill(); globalShortcut.unregisterAll(); });
