let config = {
  firebaseUrl: localStorage.getItem('esp32_firebase_url') || 'https://ecobin-c080b-default-rtdb.firebaseio.com',
  esp32Ip: localStorage.getItem('esp32_target_ip') || '192.168.8.112'
};

let lastPingTimestamp = 0;
let stalenessInterval = null;

const statusBox = document.getElementById('status-box');
const statusText = document.getElementById('status-text');
const ipDisplay = document.getElementById('ip-display');
const lastPingDisplay = document.getElementById('last-ping-display');
const detailsDisplay = document.getElementById('details-display');
const pingBtn = document.getElementById('ping-btn');

const toggleSettingsBtn = document.getElementById('toggle-settings-btn');
const settingsPanel = document.getElementById('settings-panel');
const firebaseUrlInput = document.getElementById('firebase-url-input');
const espIpInput = document.getElementById('esp-ip-input');
const saveBtn = document.getElementById('save-btn');

document.addEventListener('DOMContentLoaded', () => {
  firebaseUrlInput.value = config.firebaseUrl;
  espIpInput.value = config.esp32Ip;
  ipDisplay.innerText = config.esp32Ip;

  initFirebase();
  setupEvents();
  startStalenessCheck();
});

function setStatus(isOnline, message = '', timestamp = null) {
  lastPingTimestamp = timestamp || Math.floor(Date.now() / 1000);
  const timeStr = new Date(lastPingTimestamp * 1000).toLocaleTimeString();

  if (isOnline) {
    statusBox.className = 'status-box online';
    statusText.innerText = 'ACTIVE';
    detailsDisplay.innerText = message || 'HTTP 200 OK';
  } else {
    statusBox.className = 'status-box offline';
    statusText.innerText = 'OFFLINE';
    detailsDisplay.innerText = message || 'Device Unreachable';
  }

  lastPingDisplay.innerText = timeStr;
}

function startStalenessCheck() {
  if (stalenessInterval) clearInterval(stalenessInterval);
  stalenessInterval = setInterval(() => {
    if (lastPingTimestamp > 0) {
      const now = Math.floor(Date.now() / 1000);
      if (now - lastPingTimestamp > 12) {
        setStatus(false, 'Heartbeat timed out');
      }
    }
  }, 4000);
}

function initFirebase() {
  if (!config.firebaseUrl) {
    statusBox.className = 'status-box checking';
    statusText.innerText = 'NOT CONNECTED';
    detailsDisplay.innerText = 'Set Firebase URL in Settings to receive live status';
    return;
  }

  try {
    if (!firebase.apps.length) {
      firebase.initializeApp({ databaseURL: config.firebaseUrl });
    }

    const db = firebase.database();
    db.ref('ecobin/esp32_status').on('value', (snapshot) => {
      const data = snapshot.val();
      if (data) {
        if (data.ip) {
          config.esp32Ip = data.ip;
          ipDisplay.innerText = data.ip;
        }
        setStatus(data.online, data.details, data.last_seen);
      }
    });
  } catch (e) {
    setStatus(false, 'Firebase error');
  }
}

function setupEvents() {
  pingBtn.addEventListener('click', async () => {
    pingBtn.innerText = 'Pinging...';
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);
      await fetch(`http://${config.esp32Ip}/`, { method: 'GET', signal: controller.signal, mode: 'no-cors' });
      clearTimeout(timeoutId);
      setStatus(true, 'Local ping success');
    } catch (e) {
      setStatus(false, 'Local ping failed');
    } finally {
      pingBtn.innerText = 'Ping ESP32';
    }
  });

  toggleSettingsBtn.addEventListener('click', () => {
    settingsPanel.classList.toggle('hidden');
  });

  saveBtn.addEventListener('click', () => {
    config.firebaseUrl = firebaseUrlInput.value.trim();
    config.esp32Ip = espIpInput.value.trim() || '192.168.8.112';

    localStorage.setItem('esp32_firebase_url', config.firebaseUrl);
    localStorage.setItem('esp32_target_ip', config.esp32Ip);

    ipDisplay.innerText = config.esp32Ip;
    settingsPanel.classList.add('hidden');
    initFirebase();
  });
}
