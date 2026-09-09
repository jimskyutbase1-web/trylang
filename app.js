// ESP32 Status Monitor Client

let config = {
  firebaseUrl: localStorage.getItem('esp32_firebase_url') || '',
  esp32Ip: localStorage.getItem('esp32_target_ip') || '192.168.8.112'
};

let lastPingTimestamp = 0;
let stalenessInterval = null;

// DOM Elements
const statusCard = document.getElementById('status-card');
const statusOrb = document.getElementById('status-orb');
const statusTitle = document.getElementById('status-title');
const statusSub = document.getElementById('status-sub');
const ipDisplay = document.getElementById('ip-display');
const lastPingVal = document.getElementById('last-ping-val');
const detailsVal = document.getElementById('details-val');
const refreshBtn = document.getElementById('refresh-btn');

const cloudBadge = document.getElementById('cloud-badge');
const cloudDot = document.getElementById('cloud-dot');
const cloudText = document.getElementById('cloud-text');

// Modal Elements
const settingsModal = document.getElementById('settings-modal');
const openSettingsBtn = document.getElementById('open-settings-btn');
const closeSettingsBtn = document.getElementById('close-settings-btn');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const inputFirebaseUrl = document.getElementById('input-firebase-url');
const inputEsp32Ip = document.getElementById('input-esp32-ip');

document.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  initFirebase();
  setupEvents();
  startStalenessWatcher();
});

function loadConfig() {
  inputFirebaseUrl.value = config.firebaseUrl;
  inputEsp32Ip.value = config.esp32Ip;
  ipDisplay.innerText = config.esp32Ip;
}

// -------------------------------------------------------------
// UPDATE STATUS UI
// -------------------------------------------------------------
function setStatus(isOnline, details = '', timestamp = null) {
  lastPingTimestamp = timestamp || Math.floor(Date.now() / 1000);
  const timeStr = new Date(lastPingTimestamp * 1000).toLocaleTimeString();

  if (isOnline) {
    statusCard.className = 'status-card status-online';
    statusOrb.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
    statusTitle.innerText = 'ESP32 IS ACTIVE';
    statusSub.innerHTML = `Online at IP: <strong>${config.esp32Ip}</strong>`;
    lastPingVal.innerText = timeStr;
    detailsVal.innerText = details || 'HTTP 200 OK • Servo Ready';
    detailsVal.style.color = 'var(--color-online)';
  } else {
    statusCard.className = 'status-card status-offline';
    statusOrb.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i>';
    statusTitle.innerText = 'ESP32 IS OFFLINE';
    statusSub.innerHTML = `Cannot reach: <strong>${config.esp32Ip}</strong>`;
    lastPingVal.innerText = timeStr;
    detailsVal.innerText = details || 'Device Unreachable';
    detailsVal.style.color = 'var(--color-offline)';
  }
}

// Automatically detect if heartbeat stopped arriving (>12s)
function startStalenessWatcher() {
  if (stalenessInterval) clearInterval(stalenessInterval);

  stalenessInterval = setInterval(() => {
    if (lastPingTimestamp > 0) {
      const now = Math.floor(Date.now() / 1000);
      const elapsed = now - lastPingTimestamp;
      if (elapsed > 12) {
        setStatus(false, `Heartbeat lost (${elapsed}s ago)`);
      }
    }
  }, 4000);
}

// -------------------------------------------------------------
// FIREBASE REALTIME LISTENER
// -------------------------------------------------------------
function initFirebase() {
  if (!config.firebaseUrl) {
    cloudText.innerText = 'Direct / Local Mode';
    cloudDot.style.background = '#f59e0b';
    setStatus(false, 'Configure Firebase in settings to view Lemery status');
    return;
  }

  try {
    const firebaseConfig = {
      databaseURL: config.firebaseUrl
    };

    if (!firebase.apps.length) {
      firebase.initializeApp(firebaseConfig);
    }

    const db = firebase.database();
    cloudText.innerText = 'Cloud Connected';
    cloudDot.style.background = '#10b981';

    // Listen for live ESP32 status updates
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

  } catch (err) {
    console.warn('Firebase error:', err);
    cloudText.innerText = 'Sync Error';
    cloudDot.style.background = '#ef4444';
    setStatus(false, 'Failed to connect to Firebase');
  }
}

// -------------------------------------------------------------
// EVENTS
// -------------------------------------------------------------
function setupEvents() {
  // Manual Ping button
  refreshBtn.addEventListener('click', async () => {
    refreshBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Pinging...';

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3000);
      await fetch(`http://${config.esp32Ip}/`, { method: 'GET', signal: controller.signal, mode: 'no-cors' });
      clearTimeout(timeoutId);
      setStatus(true, 'Local ping succeeded');
    } catch (e) {
      setStatus(false, 'Local ping timeout');
    } finally {
      refreshBtn.innerHTML = '<i class="fa-solid fa-rotate"></i> Ping ESP32 Now';
    }
  });

  // Settings
  openSettingsBtn.addEventListener('click', () => settingsModal.classList.add('active'));
  closeSettingsBtn.addEventListener('click', () => settingsModal.classList.remove('active'));

  saveSettingsBtn.addEventListener('click', () => {
    config.firebaseUrl = inputFirebaseUrl.value.trim();
    config.esp32Ip = inputEsp32Ip.value.trim() || '192.168.8.112';

    localStorage.setItem('esp32_firebase_url', config.firebaseUrl);
    localStorage.setItem('esp32_target_ip', config.esp32Ip);

    ipDisplay.innerText = config.esp32Ip;
    settingsModal.classList.remove('active');

    initFirebase();
  });
}
