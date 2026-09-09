// EcoBin AI Live Telemetry Dashboard Client

// Default Settings
let config = {
  firebaseUrl: localStorage.getItem('ecobin_firebase_url') || '',
  esp32Ip: localStorage.getItem('ecobin_esp32_ip') || '192.168.8.112',
  autoDemo: localStorage.getItem('ecobin_auto_demo') === 'true'
};

// State
let stats = {
  biodegradable: 0,
  recyclable: 0,
  residual: 0
};
let logs = [];
let demoInterval = null;

// DOM Elements
const esp32IpDisplay = document.getElementById('esp32-ip-display');
const footerEspIp = document.getElementById('footer-esp-ip');
const syncStatusText = document.getElementById('sync-status-text');
const firebaseBadge = document.getElementById('firebase-badge');

const classOrb = document.getElementById('class-orb');
const classIcon = document.getElementById('class-icon');
const lastClassTag = document.getElementById('last-class-tag');
const classMessage = document.getElementById('class-message');
const confidenceGauge = document.getElementById('confidence-gauge');
const confidenceText = document.getElementById('confidence-text');

const probBioVal = document.getElementById('prob-bio-val');
const probBioBar = document.getElementById('prob-bio-bar');
const probRecycVal = document.getElementById('prob-recyc-val');
const probRecycBar = document.getElementById('prob-recyc-bar');
const probResidVal = document.getElementById('prob-resid-val');
const probResidBar = document.getElementById('prob-resid-bar');
const lastTimeVal = document.getElementById('last-time-val');

const bioCountEl = document.getElementById('bio-count');
const recycCountEl = document.getElementById('recyc-count');
const residCountEl = document.getElementById('resid-count');
const logsTbody = document.getElementById('logs-tbody');

// Modal Elements
const settingsModal = document.getElementById('settings-modal');
const openSettingsBtn = document.getElementById('open-settings-btn');
const closeSettingsBtn = document.getElementById('close-settings-btn');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const inputFirebaseUrl = document.getElementById('input-firebase-url');
const inputEsp32Ip = document.getElementById('input-esp32-ip');
const toggleDemo = document.getElementById('toggle-demo');

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadSavedConfig();
  initFirebase();
  setupEventListeners();

  if (config.autoDemo) {
    startDemoMode();
  }
});

function loadSavedConfig() {
  inputFirebaseUrl.value = config.firebaseUrl;
  inputEsp32Ip.value = config.esp32Ip;
  toggleDemo.checked = config.autoDemo;

  esp32IpDisplay.innerText = config.esp32Ip;
  footerEspIp.innerText = config.esp32Ip;
}

// -------------------------------------------------------------
// FIREBASE REALTIME DATABASE SYNC
// -------------------------------------------------------------
function initFirebase() {
  if (!config.firebaseUrl) {
    syncStatusText.innerText = 'Demo / Standby';
    firebaseBadge.querySelector('.status-dot').style.background = '#f59e0b';
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
    syncStatusText.innerText = 'Connected to Cloud';
    firebaseBadge.querySelector('.status-dot').style.background = '#10b981';

    // Listen for live classification events
    db.ref('ecobin/latest').on('value', (snapshot) => {
      const data = snapshot.val();
      if (data) {
        handleIncomingData(data);
      }
    });

    // Listen for ESP32 status updates
    db.ref('ecobin/esp32_ip').on('value', (snapshot) => {
      const ip = snapshot.val();
      if (ip) {
        config.esp32Ip = ip;
        esp32IpDisplay.innerText = ip;
        footerEspIp.innerText = ip;
      }
    });

  } catch (err) {
    console.warn('Firebase init error:', err);
    syncStatusText.innerText = 'Offline / Direct';
    firebaseBadge.querySelector('.status-dot').style.background = '#6b7280';
  }
}

// -------------------------------------------------------------
// UPDATE UI ON NEW CLASSIFICATION
// -------------------------------------------------------------
function handleIncomingData(data) {
  const label = (data.class || data.detected || 'BIODEGRADABLE').toUpperCase();
  const confidence = typeof data.confidence === 'number' ? data.confidence : 0.95;
  const probs = data.probabilities || {
    biodegradable: label === 'BIODEGRADABLE' ? confidence : 0.03,
    recyclable: label === 'RECYCLABLE' ? confidence : 0.02,
    residual: label === 'RESIDUAL' ? confidence : 0.01
  };
  const timeStr = data.time || new Date().toLocaleTimeString();
  const message = data.message || `Servo command dispatched to ESP32 (${config.esp32Ip})`;

  // Update hero tag
  lastClassTag.innerText = label;
  classMessage.innerText = message;
  lastTimeVal.innerText = timeStr;

  // Set Theme color & icon based on waste type
  let colorVar = '--color-bio';
  let iconClass = 'fa-leaf';
  let tagClass = 'tag-bio';

  if (label.includes('RECYCLABLE')) {
    colorVar = '--color-recyc';
    iconClass = 'fa-arrows-rotate';
    tagClass = 'tag-recyc';
    stats.recyclable++;
  } else if (label.includes('RESIDUAL')) {
    colorVar = '--color-resid';
    iconClass = 'fa-trash';
    tagClass = 'tag-resid';
    stats.residual++;
  } else {
    stats.biodegradable++;
  }

  // Update counts
  bioCountEl.innerText = `${stats.biodegradable} items`;
  recycCountEl.innerText = `${stats.recyclable} items`;
  residCountEl.innerText = `${stats.residual} items`;

  // Update visual orb
  classOrb.style.background = `var(${colorVar}-glow)`;
  classOrb.style.borderColor = `var(${colorVar})`;
  classOrb.style.color = `var(${colorVar})`;
  classOrb.style.boxShadow = `0 0 25px var(${colorVar}-glow)`;
  classOrb.innerHTML = `<i class="fa-solid ${iconClass}" id="class-icon"></i>`;
  lastClassTag.style.color = `var(${colorVar})`;

  // Update Circular Gauge
  const percent = Math.round(confidence * 100);
  confidenceText.innerText = `${(confidence * 100).toFixed(1)}%`;
  const degrees = Math.round((confidence * 360));
  confidenceGauge.style.background = `conic-gradient(var(${colorVar}) ${degrees}deg, rgba(255,255,255,0.08) 0deg)`;

  // Update Probability bars
  const pBio = (probs.biodegradable || 0) * 100;
  const pRec = (probs.recyclable || 0) * 100;
  const pRes = (probs.residual || 0) * 100;

  probBioVal.innerText = `${pBio.toFixed(1)}%`;
  probBioBar.style.width = `${pBio}%`;

  probRecycVal.innerText = `${pRec.toFixed(1)}%`;
  probRecycBar.style.width = `${pRec}%`;

  probResidVal.innerText = `${pRes.toFixed(1)}%`;
  probResidBar.style.width = `${pRes}%`;

  // Append to Activity Logs Table
  addLogRow({
    time: timeStr,
    label: label,
    tagClass: tagClass,
    confidence: `${(confidence * 100).toFixed(1)}%`,
    action: `Rotated Servo to ${label}`,
    status: 'Success'
  });
}

function addLogRow(item) {
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td><i class="fa-regular fa-clock" style="color:#6b7280; margin-right:4px;"></i> ${item.time}</td>
    <td><span class="tag-badge ${item.tagClass}">${item.label}</span></td>
    <td><strong>${item.confidence}</strong></td>
    <td>${item.action}</td>
    <td><span style="color:#10b981; font-weight:600;"><i class="fa-solid fa-circle-check"></i> ${item.status}</span></td>
  `;
  logsTbody.insertBefore(tr, logsTbody.firstChild);

  // Keep max 20 rows
  while (logsTbody.children.length > 20) {
    logsTbody.removeChild(logsTbody.lastChild);
  }
}

// -------------------------------------------------------------
// EVENT LISTENERS & TEST CONTROLS
// -------------------------------------------------------------
function setupEventListeners() {
  // Manual test simulation buttons
  document.getElementById('test-bio-btn').addEventListener('click', () => {
    handleIncomingData({
      class: 'BIODEGRADABLE',
      confidence: 0.965,
      probabilities: { biodegradable: 0.965, recyclable: 0.025, residual: 0.010 },
      time: new Date().toLocaleTimeString(),
      message: 'Simulated classification: Biodegradable item detected.'
    });
  });

  document.getElementById('test-recyc-btn').addEventListener('click', () => {
    handleIncomingData({
      class: 'RECYCLABLE',
      confidence: 0.942,
      probabilities: { biodegradable: 0.031, recyclable: 0.942, residual: 0.027 },
      time: new Date().toLocaleTimeString(),
      message: 'Simulated classification: Plastic / Bottle recyclable detected.'
    });
  });

  document.getElementById('test-resid-btn').addEventListener('click', () => {
    handleIncomingData({
      class: 'RESIDUAL',
      confidence: 0.898,
      probabilities: { biodegradable: 0.045, recyclable: 0.057, residual: 0.898 },
      time: new Date().toLocaleTimeString(),
      message: 'Simulated classification: Residual waste detected.'
    });
  });

  // Clear logs
  document.getElementById('clear-logs-btn').addEventListener('click', () => {
    logsTbody.innerHTML = '';
    stats = { biodegradable: 0, recyclable: 0, residual: 0 };
    bioCountEl.innerText = '0 items';
    recycCountEl.innerText = '0 items';
    residCountEl.innerText = '0 items';
  });

  // Settings modal
  openSettingsBtn.addEventListener('click', () => {
    settingsModal.classList.add('active');
  });

  closeSettingsBtn.addEventListener('click', () => {
    settingsModal.classList.remove('active');
  });

  saveSettingsBtn.addEventListener('click', () => {
    config.firebaseUrl = inputFirebaseUrl.value.trim();
    config.esp32Ip = inputEsp32Ip.value.trim() || '192.168.8.112';
    config.autoDemo = toggleDemo.checked;

    localStorage.setItem('ecobin_firebase_url', config.firebaseUrl);
    localStorage.setItem('ecobin_esp32_ip', config.esp32Ip);
    localStorage.setItem('ecobin_auto_demo', config.autoDemo);

    esp32IpDisplay.innerText = config.esp32Ip;
    footerEspIp.innerText = config.esp32Ip;

    settingsModal.classList.remove('active');

    if (config.autoDemo) {
      startDemoMode();
    } else if (demoInterval) {
      clearInterval(demoInterval);
      demoInterval = null;
    }

    initFirebase();
  });
}

function startDemoMode() {
  if (demoInterval) clearInterval(demoInterval);
  const classes = [
    { name: 'BIODEGRADABLE', conf: 0.97, bio: 0.97, rec: 0.02, res: 0.01 },
    { name: 'RECYCLABLE', conf: 0.93, bio: 0.04, rec: 0.93, res: 0.03 },
    { name: 'RESIDUAL', conf: 0.91, bio: 0.03, rec: 0.06, res: 0.91 }
  ];

  demoInterval = setInterval(() => {
    const item = classes[Math.floor(Math.random() * classes.length)];
    handleIncomingData({
      class: item.name,
      confidence: item.conf,
      probabilities: { biodegradable: item.bio, recyclable: item.rec, residual: item.res },
      time: new Date().toLocaleTimeString(),
      message: `Live telemetry event: Servo commanded to ${item.name}`
    });
  }, 4500);
}
