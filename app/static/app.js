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
/** Matches --align-* on #camera-stage. */
const ALIGN_FRAMES = {
  face: { left: 0.275, top: 0.10, width: 0.45, height: 0.80, zoom: 1, yBias: 0 },
  tongue: { left: 0.36, top: 0.22, width: 0.28, height: 0.52, zoom: 3.7, yBias: 0.08 },
};
const ALIGN_HINTS = {
  face: "對準臉：髮際以下～下巴，兩耳以內",
  tongue: "對準舌：上緣對齊上排牙齒，舌體填滿黃框",
};
let alignMode = "face";

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
  if (!data.profile_complete) {
    window.location.href = "/profile";
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

function cameraErrorMessage(err) {
  const name = (err && err.name) || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "無法開啟相機：瀏覽器已拒絕相機權限。請允許本網站使用相機後再試。";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "無法開啟相機：找不到攝影機。";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "無法開啟相機：相機正被其他程式占用。";
  }
  if (name === "SecurityError") {
    return "無法開啟相機：目前網址不是安全來源。請用 http://127.0.0.1 開啟。";
  }
  const extra = (err && (err.message || err.name)) || formatApiError(err);
  return extra ? "無法開啟相機：" + extra : "無法開啟相機";
}

function cameraIsLive() {
  const stream = video && video.srcObject;
  if (!stream || typeof stream.getVideoTracks !== "function") return false;
  return stream.getVideoTracks().some((track) => track.readyState === "live");
}

async function waitForVideoMeta(timeoutMs = 2500) {
  if (video.readyState >= 1 && video.videoWidth > 0) return;
  await new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      video.removeEventListener("loadedmetadata", done);
      resolve();
    };
    video.addEventListener("loadedmetadata", done);
    setTimeout(done, timeoutMs);
  });
}

async function attachCameraStream(stream) {
  video.setAttribute("playsinline", "");
  video.setAttribute("webkit-playsinline", "");
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  if (video.srcObject && video.srcObject !== stream) {
    video.srcObject.getTracks().forEach((track) => track.stop());
  }
  video.srcObject = stream;
  await waitForVideoMeta();
  try {
    await video.play();
    if (video.paused) await video.play();
    setAlignMode(alignMode || "face");
  } catch (playErr) {
    camMsg.textContent = "相機已連上但畫面未播放：" + ((playErr && playErr.message) || "請再按一次拍臉");
    camMsg.className = "status err";
    throw playErr;
  }
}

async function startCamera() {
  if (!video) return;
  if (cameraIsLive()) {
    try { await video.play(); } catch (_) { /* already live */ }
    setAlignMode(alignMode || "face");
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    camMsg.textContent = "此瀏覽器不支援相機";
    camMsg.className = "status err";
    return;
  }
  const attempts = [
    { video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false },
    { video: { facingMode: "user" }, audio: false },
    { video: true, audio: false },
  ];
  let lastErr = null;
  for (const constraints of attempts) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      await attachCameraStream(stream);
      camMsg.textContent = "相機已開啟。請對準黃框後再拍照";
      camMsg.className = "status ok";
      setAlignMode(alignMode || "face");
      return;
    } catch (err) {
      lastErr = err;
      if (err && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")) break;
    }
  }
  camMsg.textContent = cameraErrorMessage(lastErr);
  camMsg.className = "status err";
}

function setAlignMode(mode) {
  alignMode = mode === "tongue" ? "tongue" : "face";
  const stage = document.getElementById("camera-stage");
  const frame = document.getElementById("align-frame");
  const dim = document.getElementById("align-dim");
  const hint = document.getElementById("align-hint");
  if (stage) {
    stage.classList.toggle("is-face", alignMode === "face");
    stage.classList.toggle("is-tongue", alignMode === "tongue");
  }
  if (frame) {
    frame.classList.toggle("is-face", alignMode === "face");
    frame.classList.toggle("is-tongue", alignMode === "tongue");
  }
  if (dim) {
    dim.classList.toggle("is-face", alignMode === "face");
    dim.classList.toggle("is-tongue", alignMode === "tongue");
  }
  if (hint) hint.textContent = ALIGN_HINTS[alignMode];
  syncAlignMask();
  requestAnimationFrame(syncAlignMask);
}

function syncAlignMask() {
  const stage = document.getElementById("camera-stage");
  const frame = document.getElementById("align-frame");
  const dim = document.getElementById("align-dim");
  if (!stage || !frame || !dim) return;
  const sr = stage.getBoundingClientRect();
  const fr = frame.getBoundingClientRect();
  if (sr.width < 2 || sr.height < 2 || fr.width < 2 || fr.height < 2) return;
  const left = Math.max(0, fr.left - sr.left);
  const top = Math.max(0, fr.top - sr.top);
  const size = `100% 100%, ${fr.width}px ${fr.height}px`;
  const pos = `0 0, ${left}px ${top}px`;
  dim.style.webkitMaskSize = size;
  dim.style.maskSize = size;
  dim.style.webkitMaskPosition = pos;
  dim.style.maskPosition = pos;
}

function coverDest(vw, vh, sw, sh) {
  const videoAspect = vw / vh;
  const stageAspect = sw / sh;
  if (videoAspect > stageAspect) {
    const dh = sh;
    const dw = vw * (sh / vh);
    return { dx: (sw - dw) / 2, dy: 0, dw, dh };
  }
  const dw = sw;
  const dh = vh * (sw / vw);
  return { dx: 0, dy: (sh - dh) / 2, dw, dh };
}

function sourceCrop(vw, vh, zoom, yBias) {
  const z = Math.max(1, zoom || 1);
  const srcW = vw / z;
  const srcH = vh / z;
  const sx = (vw - srcW) / 2;
  const sy = Math.max(0, Math.min(vh - srcH, (vh - srcH) / 2 + (yBias || 0) * vh));
  return { sx, sy, srcW, srcH };
}

function captureFrame(kind) {
  const mode = kind === "tongue" ? "tongue" : "face";
  setAlignMode(mode);
  const stage = document.getElementById("camera-stage") || video;
  const sw = Math.max(1, stage.clientWidth || video.clientWidth || 640);
  const sh = Math.max(1, stage.clientHeight || video.clientHeight || 480);
  const frame = ALIGN_FRAMES[mode];
  const destW = Math.max(1, Math.round(frame.width * sw));
  const destH = Math.max(1, Math.round(frame.height * sh));
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  const { sx, sy, srcW, srcH } = sourceCrop(vw, vh, frame.zoom, frame.yBias);
  const { dx, dy, dw, dh } = coverDest(srcW, srcH, destW, destH);
  canvas.width = destW;
  canvas.height = destH;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.translate(destW, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, sx, sy, srcW, srcH, dx, dy, dw, dh);
  ctx.restore();
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92);
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
    const blob = await captureFrame(extraShot);
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
    const data = await api("/api/login", {
      method: "POST",
      body: formBody({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    });
    sessionStorage.removeItem("daily-asked");
    if (data.profile_complete === false) {
      window.location.href = "/profile";
      return;
    }
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
        medical_history: document.getElementById("medical_history").value,
      }),
    });
    profileMsg.textContent = "已儲存";
    profileMsg.className = "status ok";
  } catch (err) {
    profileMsg.textContent = err.message;
    profileMsg.className = "status err";
  }
});

window.addEventListener("resize", syncAlignMask);
if (typeof ResizeObserver !== "undefined") {
  const stageEl = document.getElementById("camera-stage");
  if (stageEl) new ResizeObserver(syncAlignMask).observe(stageEl);
}
if (video) {
  video.addEventListener("loadedmetadata", syncAlignMask);
  video.addEventListener("resize", syncAlignMask);
}
setAlignMode(alignMode);
document.getElementById("btn-face").addEventListener("pointerenter", () => setAlignMode("face"));
document.getElementById("btn-tongue").addEventListener("pointerenter", () => setAlignMode("tongue"));
document.getElementById("btn-face").addEventListener("click", async () => {
  try {
    setAlignMode("face");
    await startCamera();
    if (!cameraIsLive()) return;
    await sendRecord("face");
  } catch (err) {
    camMsg.textContent = err.message;
    camMsg.className = "status err";
  }
});
document.getElementById("btn-tongue").addEventListener("click", async () => {
  try {
    setAlignMode("tongue");
    await startCamera();
    if (!cameraIsLive()) return;
    await sendRecord("tongue");
  } catch (err) {
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
