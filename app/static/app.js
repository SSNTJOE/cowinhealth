const mysqlStatus = document.getElementById("mysql-status");
const authCard = document.getElementById("auth-card");
const appCard = document.getElementById("app-card");
const authMsg = document.getElementById("auth-msg");
const profileMsg = document.getElementById("profile-msg");
const camMsg = document.getElementById("cam-msg");
const video = document.getElementById("camera");
const canvas = document.getElementById("snap");
const dailyDialog = document.getElementById("daily-dialog");
const lastShots = { face: null, tongue: null };

const organs = [
  { key: "lung", name: "肺", score: "lung_score", pattern: "lung_pattern", spots: [{ x: 44, y: 31.5 }, { x: 56, y: 31.5 }] },
  { key: "heart", name: "心", score: "heart_score", pattern: "heart_pattern", spots: [{ x: 53.5, y: 35.5 }] },
  { key: "liver", name: "肝", score: "liver_score", pattern: "liver_pattern", spots: [{ x: 44, y: 41.5 }] },
  { key: "gallbladder", name: "膽", score: "gallbladder_score", pattern: "gallbladder_pattern", spots: [{ x: 41.5, y: 44.5 }] },
  { key: "spleen", name: "脾", score: "spleen_score", pattern: "spleen_pattern", spots: [{ x: 56.5, y: 43.5 }] },
  { key: "large_intestine", name: "大腸", score: "large_intestine_score", pattern: "large_intestine_pattern", spots: [{ x: 38, y: 52 }, { x: 62, y: 52 }] },
  { key: "small_intestine", name: "小腸", score: "small_intestine_score", pattern: "small_intestine_pattern", spots: [{ x: 50, y: 54 }] },
  { key: "kidney", name: "腎", score: "kidney_score", pattern: "kidney_pattern", spots: [{ x: 44, y: 61 }, { x: 56, y: 61 }] },
  { key: "bladder", name: "膀胱", score: "bladder_score", pattern: "bladder_pattern", spots: [{ x: 50, y: 64.5 }] },
  { key: "uterus", name: "子宮", score: "uterus_score", pattern: "uterus_pattern", femaleOnly: true, spots: [{ x: 50, y: 62.5 }] },
];
let currentBody = "boy";
let lastResult = null;

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "same-origin", ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "請求失敗");
  }
  return data;
}

function formBody(obj) {
  const body = new FormData();
  Object.entries(obj).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") body.append(k, v);
  });
  return body;
}

async function checkMysql() {
  try {
    const data = await api("/api/health");
    mysqlStatus.textContent = data.mysql ? "MySQL 連線成功" : "MySQL 回應異常";
    mysqlStatus.className = data.mysql ? "status ok" : "status err";
  } catch (err) {
    mysqlStatus.textContent = "MySQL 尚未連上：" + err.message;
    mysqlStatus.className = "status err";
  }
}

function setBodyImage(kind) {
  currentBody = kind === "girl" ? "girl" : "boy";
  document.getElementById("body-img").src = currentBody === "girl" ? "/media/girl-body.png" : "/media/boy-body.png";
  if (lastResult) drawOrgans(lastResult);
}

function fillProfile(user) {
  document.getElementById("anon-id").textContent = user.user_id;
  document.getElementById("height").value = user.height ?? "";
  document.getElementById("weight").value = user.weight ?? "";
  document.getElementById("age").value = user.age ?? "";
  document.getElementById("gender").value = user.gender ?? "";
  document.getElementById("medical_history").value = user.medical_history ?? "";
  setBodyImage(user.gender === "female" ? "girl" : "boy");
}

async function loadMe() {
  const data = await api("/api/me");
  if (!data.logged_in) {
    authCard.classList.remove("hidden");
    appCard.classList.add("hidden");
    return;
  }
  authCard.classList.add("hidden");
  appCard.classList.remove("hidden");
  fillProfile(data.user);
  await startCamera();
  await loadRecords();
  if (!sessionStorage.getItem("daily-asked")) {
    sessionStorage.setItem("daily-asked", "1");
    document.getElementById("dialog-symptoms").value = document.getElementById("symptoms").value;
    document.getElementById("dialog-discomfort").value = document.getElementById("discomfort").value;
    dailyDialog.showModal();
  }
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    camMsg.textContent = "此瀏覽器不支援相機";
    camMsg.className = "status err";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: false,
    });
    video.srcObject = stream;
    camMsg.textContent = "相機已開啟，對準後按按鈕擷取";
    camMsg.className = "status ok";
  } catch (err) {
    camMsg.textContent = "無法開啟相機：" + err.message;
    camMsg.className = "status err";
  }
}

function captureFrame() {
  const w = video.videoWidth || 640;
  const h = video.videoHeight || 480;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, w, h);
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.9);
  });
}

function drawOrgans(result) {
  lastResult = result;
  const box = document.getElementById("organ-pins");
  box.innerHTML = "";
  organs.forEach((org) => {
    if (org.femaleOnly && currentBody !== "girl") return;
    const file = result.overlays ? result.overlays[org.key] : null;
    if (!file) return;
    const pattern = (result.patterns && result.patterns[org.pattern]) || "";
    org.spots.forEach((spot) => {
      const img = document.createElement("img");
      img.className = "sticker";
      img.src = "/media/" + file;
      img.alt = org.name + pattern;
      img.style.left = spot.x + "%";
      img.style.top = spot.y + "%";
      box.appendChild(img);
      const label = document.createElement("div");
      label.className = "sticker-label";
      label.style.left = spot.x + "%";
      label.style.top = spot.y + "%";
      label.textContent = org.name;
      box.appendChild(label);
    });
  });
}

function renderResult(result) {
  if (result.dominant_color) {
    document.getElementById("color-chip").style.background = result.dominant_color;
    document.getElementById("color-hex").textContent = result.dominant_color;
  }
  document.getElementById("color-label").textContent = " " + (result.color_label || "");
  document.getElementById("disclaimer").textContent = result.disclaimer || "";
  const findings = document.getElementById("findings");
  findings.innerHTML = "";
  (result.findings || []).forEach((text) => {
    const li = document.createElement("li");
    li.textContent = text;
    findings.appendChild(li);
  });
  document.getElementById("advice").textContent = result.diet_advice ? "食療整理：" + result.diet_advice : "";
  const links = document.getElementById("links");
  links.innerHTML = "";
  if (result.diet_url) {
    links.innerHTML += `<a href="${result.diet_url}" target="_blank" rel="noreferrer">食療搜尋</a>　`;
  }
  if (result.acupoint_url) {
    links.innerHTML += `<a href="${result.acupoint_url}" target="_blank" rel="noreferrer">穴道按摩搜尋</a>`;
  }
  const scores = document.getElementById("scores");
  scores.innerHTML = "";
  organs.forEach((org) => {
    const div = document.createElement("div");
    div.className = "score";
    div.innerHTML = `<span>${org.name}</span><b>${result.scores[org.score]}</b><small>${result.patterns[org.pattern]}</small>`;
    scores.appendChild(div);
  });
  drawOrgans(result);
}

async function loadRecords() {
  const data = await api("/api/records");
  const box = document.getElementById("records");
  if (!data.records.length) {
    box.textContent = "尚無紀錄";
    return;
  }
  const latest = data.records[0];
  renderResult({
    scores: latest,
    patterns: latest,
    overlays: latest.overlays || {},
    findings: [latest.symptoms, latest.discomfort].filter(Boolean),
    diet_advice: latest.diet_advice,
    diet_url: latest.diet_url,
    acupoint_url: latest.acupoint_url,
    color_label: [latest.face_color, latest.lip_color, latest.tongue_body_color, latest.tongue_coat_color].filter(Boolean).join("／"),
    disclaimer: "以下為最近一次 MySQL 紀錄。",
  });
  const head = ["日期", "狀況", ...organs.map((o) => o.name), "食療"].map((h) => `<th>${h}</th>`).join("");
  const rows = data.records
    .map((r) => {
      const date = (r.record_date || "").toString().replace("T", " ").slice(0, 19);
      const cells = organs.map((o) => `<td>${r[o.score]} ${r[o.pattern] || ""}</td>`).join("");
      return `<tr><td>${date}</td><td>${(r.symptoms || "").slice(0, 12)}</td>${cells}<td>${r.diet_advice || ""}</td></tr>`;
    })
    .join("");
  box.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

async function sendRecord(extraShot) {
  camMsg.textContent = "傳送中…";
  const body = new FormData();
  body.append("symptoms", document.getElementById("symptoms").value);
  body.append("discomfort", document.getElementById("discomfort").value);
  if (extraShot) {
    const blob = await captureFrame();
    if (!blob) throw new Error("無法擷取畫面");
    lastShots[extraShot] = blob;
    body.append("shot_type", extraShot);
    body.append("image", blob, `${extraShot}.jpg`);
  }
  if (lastShots.face && extraShot !== "face") body.append("face", lastShots.face, "face.jpg");
  if (lastShots.tongue && extraShot !== "tongue") body.append("tongue", lastShots.tongue, "tongue.jpg");
  const result = await api("/api/record", { method: "POST", body });
  camMsg.textContent = "已寫入 health_records";
  camMsg.className = "status ok";
  renderResult(result);
  await loadRecords();
}

document.getElementById("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  authMsg.textContent = "";
  try {
    await api("/api/login", {
      method: "POST",
      body: formBody({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    });
    sessionStorage.removeItem("daily-asked");
    await loadMe();
  } catch (err) {
    authMsg.textContent = err.message;
    authMsg.className = "status err";
  }
});

document.getElementById("register-btn").addEventListener("click", async () => {
  authMsg.textContent = "";
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: formBody({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    });
    authMsg.textContent = "已建立匿名 ID：" + data.user_id;
    authMsg.className = "status ok";
    sessionStorage.removeItem("daily-asked");
    await loadMe();
  } catch (err) {
    authMsg.textContent = err.message;
    authMsg.className = "status err";
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  sessionStorage.removeItem("daily-asked");
  await loadMe();
});

document.getElementById("profile-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/api/profile", {
      method: "POST",
      body: formBody({
        height: document.getElementById("height").value,
        weight: document.getElementById("weight").value,
        age: document.getElementById("age").value,
        gender: document.getElementById("gender").value,
        medical_history: document.getElementById("medical_history").value,
      }),
    });
    profileMsg.textContent = "已儲存";
    profileMsg.className = "status ok";
    setBodyImage(document.getElementById("gender").value === "female" ? "girl" : "boy");
  } catch (err) {
    profileMsg.textContent = err.message;
    profileMsg.className = "status err";
  }
});

document.getElementById("btn-face").addEventListener("click", async () => {
  try { await sendRecord("face"); } catch (err) {
    camMsg.textContent = err.message;
    camMsg.className = "status err";
  }
});
document.getElementById("btn-tongue").addEventListener("click", async () => {
  try { await sendRecord("tongue"); } catch (err) {
    camMsg.textContent = err.message;
    camMsg.className = "status err";
  }
});
document.getElementById("btn-save").addEventListener("click", async () => {
  try { await sendRecord(null); } catch (err) {
    camMsg.textContent = err.message;
    camMsg.className = "status err";
  }
});
document.getElementById("open-dialog").addEventListener("click", () => {
  document.getElementById("dialog-symptoms").value = document.getElementById("symptoms").value;
  document.getElementById("dialog-discomfort").value = document.getElementById("discomfort").value;
  dailyDialog.showModal();
});
document.getElementById("daily-form").addEventListener("submit", (e) => {
  if (e.submitter && e.submitter.value === "ok") {
    document.getElementById("symptoms").value = document.getElementById("dialog-symptoms").value;
    document.getElementById("discomfort").value = document.getElementById("dialog-discomfort").value;
  }
});

document.getElementById("body-boy").addEventListener("click", () => setBodyImage("boy"));
document.getElementById("body-girl").addEventListener("click", () => setBodyImage("girl"));

checkMysql().then(loadMe);
