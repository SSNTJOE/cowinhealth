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
let lastFacePreviewUrl = null;
let lastTonguePreviewUrl = null;
/** Matches --align-* on #camera-stage (fractions of the stage). Video, yellow frame, and dim hole share this box. */
const ALIGN_FRAMES = {
  face: { left: 0.275, top: 0.10, width: 0.45, height: 0.80, zoom: 2, yBias: 0 },
  tongue: { left: 0.36, top: 0.22, width: 0.28, height: 0.52, zoom: 3.7, yBias: 0.08 },
  stool: { left: 0.27, top: 0.14, width: 0.46, height: 0.72, zoom: 2, yBias: 0 },
  urine: { left: 0.27, top: 0.14, width: 0.46, height: 0.72, zoom: 2, yBias: 0 },
};
const CIRCLE_SHOTS = new Set(["stool", "urine"]);
/**
 * Face color JPEG vs the yellow guides. Guides stay put. Tongue capture does not use this.
 * One cell is 1/4 of the analysis frame. The face itself moves UP by 1/4 of a cell,
 * and the captured window is 1/0.9 of the guide so the face draws at 0.9×.
 */
const FACE_SHIFT_UP_CELLS = 0.25;
const FACE_SCALE = 0.9;
const ALIGN_HINTS = {
  face: "對準臉：髮際以下～下巴，兩耳以內",
  tongue: "對準舌：上緣對齊上排牙齒，舌體填滿黃框",
  stool: "對準大便：置於黃圓內；油光／淡脂為教學線索（非診斷）",
  urine: "對準尿尿：置於黃圓內（教學示範，非診斷）",
};
let alignMode = "face";
let lastFaceGrid = null;
let lastTongueGrid = null;
let complexionHistory = [];
/** Today's modality short lines (persist until that modality is re-shot). */
let lastDayLines = { face: "", tongue: "", stool: "", urine: "", pulse: "" };
/** @deprecated alias kept for stool/urine helpers */
let lastCircleLines = lastDayLines;

const organs = [
  { key: "lung", name: "肺", score: "lung_score", pattern: "lung_pattern", spots: [{ x: 44, y: 31.5 }, { x: 56, y: 31.5 }] },
  { key: "heart", name: "心", score: "heart_score", pattern: "heart_pattern", spots: [{ x: 53.5, y: 35.5 }] },
  { key: "liver", name: "肝", score: "liver_score", pattern: "liver_pattern", spots: [{ x: 44, y: 41.5 }] },
  { key: "gallbladder", name: "膽", score: "gallbladder_score", pattern: "gallbladder_pattern", spots: [{ x: 41.5, y: 44.5 }] },
  { key: "spleen", name: "脾", score: "spleen_score", pattern: "spleen_pattern", spots: [{ x: 56.5, y: 43.5 }] },
  { key: "stomach", name: "胃", score: "stomach_score", pattern: "stomach_pattern", spots: [{ x: 60, y: 48 }] },
  { key: "large_intestine", name: "大腸", score: "large_intestine_score", pattern: "large_intestine_pattern", spots: [{ x: 38, y: 52 }, { x: 62, y: 52 }] },
  { key: "small_intestine", name: "小腸", score: "small_intestine_score", pattern: "small_intestine_pattern", spots: [{ x: 50, y: 54 }] },
  { key: "kidney", name: "腎", score: "kidney_score", pattern: "kidney_pattern", spots: [{ x: 44, y: 61 }, { x: 56, y: 61 }] },
  { key: "bladder", name: "膀胱", score: "bladder_score", pattern: "bladder_pattern", spots: [{ x: 50, y: 64.5 }] },
  { key: "uterus", name: "子宮", score: "uterus_score", pattern: "uterus_pattern", femaleOnly: true, spots: [{ x: 50, y: 62.5 }] },
];
const SPLEEN_STOMACH_PATTERNS = ["脾實熱", "脾實寒", "脾虛熱", "脾虛寒", "胃實熱", "胃實寒", "胃虛熱", "胃虛寒"];
let currentBody = "boy";
let lastResult = null;

function showsFemaleOrgans() {
  return currentBody === "girl";
}

function visibleOrgans() {
  if (showsFemaleOrgans()) return organs;
  return organs.filter((org) => !org.femaleOnly);
}

function withoutUterusStatement(text) {
  const value = String(text || "");
  if (showsFemaleOrgans() || !value.includes("子宮")) return value;
  const kept = [];
  let buf = "";
  for (const ch of value) {
    buf += ch;
    if (ch === "。" || ch === "；" || ch === "\n") {
      if (!buf.includes("子宮")) kept.push(buf);
      buf = "";
    }
  }
  if (buf && !buf.includes("子宮")) kept.push(buf);
  return kept.join("").trim();
}

function syncUterusNotes() {
  document.querySelectorAll(".uterus-note").forEach((node) => {
    node.classList.toggle("hidden", !showsFemaleOrgans());
  });
}
let trendChart = null;
let mealIntakeChart = null;
let mealSurplusChart = null;
let mealNutrientTrendChart = null;
let mealSelectedDate = "";
let mealViewYear = 0;
let mealViewMonth = 0;
let mealMonthData = null;
let mealDayData = null;

const MEAL_TREND_COLORS = [
  "#2a6f97", "#c45a3c", "#2e8b57", "#8b5a2b", "#6a5acd",
  "#d2691e", "#20b2aa", "#b22222", "#708090", "#daa520",
  "#4169e1", "#cd5c5c", "#556b2f", "#9932cc",
];

/** Distinct marker shapes for each nutrient series on the surplus scatter trend. */
const MEAL_TREND_POINT_STYLES = [
  "circle", "triangle", "rect", "rectRot", "cross", "crossRot", "star",
  "dash", "line", "rectRounded", "circle", "triangle", "rect", "cross",
];

const MEAL_CHART_WHITE_BG = {
  id: "mealChartWhiteBg",
  beforeDraw(chart) {
    const { ctx, width, height } = chart;
    ctx.save();
    ctx.globalCompositeOperation = "destination-over";
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    ctx.restore();
  },
};

function pad2(n) {
  return String(n).padStart(2, "0");
}

function todayIsoDate() {
  const now = new Date();
  return `${now.getFullYear()}-${pad2(now.getMonth() + 1)}-${pad2(now.getDate())}`;
}

function shortNutrientLabel(key) {
  return String(key || "").replace(/[（(][^）)]*[）)]/g, "").trim() || key;
}

const TREND_POINT_STYLE = {
  circle: "circle",
  triangle: "triangle",
  square: "rect",
  diamond: "rectRot",
  x: "cross",
  star: "star",
  plus: "crossRot",
  rounded: "rectRounded",
  dash: "dash",
  line: "line",
};

async function checkMysql() {
  try {
    const data = await api("/api/health");
    const cat = data.catalog || {};
    const parts = [
      cat.catalog_recipes != null ? `食譜 ${cat.catalog_recipes}` : null,
      cat.catalog_foods != null ? `食材 ${cat.catalog_foods}` : null,
      cat.catalog_daily_nutrient != null ? `營養建議 ${cat.catalog_daily_nutrient}` : null,
      cat.catalog_deviations != null ? `檢測差異 ${cat.catalog_deviations}` : null,
    ].filter(Boolean);
    mysqlStatus.textContent = data.mysql
      ? uiText("mysqlOk") + (parts.length ? `（${parts.join("／")}）` : "")
      : uiText("mysqlBad");
    mysqlStatus.className = data.mysql ? "status ok" : "status err";
  } catch (err) {
    mysqlStatus.textContent = uiText("mysqlOffline") + formatApiError(err);
    mysqlStatus.className = "status err";
  }
}

async function loadBackupStatus() {
  const el = document.getElementById("backup-status");
  if (!el) return;
  try {
    const data = await api("/api/backup/status");
    const c = data.counts || {};
    el.textContent =
      `MySQL 即時筆數：Recipe ${c["Recipe.xls"] ?? "—"}／Foods ${c["Foods.xls"] ?? "—"}／` +
      `daily_nutrient ${c["daily_nutrient.xlsx"] ?? "—"}／deviation ${c["deviation.xls"] ?? "—"}`;
    el.className = "status ok";
  } catch (err) {
    el.textContent = "備存狀態：" + formatApiError(err);
    el.className = "status err";
  }
}

function setBodyImage(kind) {
  currentBody = kind === "girl" ? "girl" : "boy";
  const img = document.getElementById("body-img");
  img.src = currentBody === "girl" ? "/media/girl-body.png" : "/media/boy-body.png";
  img.alt = currentBody === "girl" ? "女生五臟六腑圖" : "男生五臟六腑圖";
  syncUterusNotes();
  if (lastResult) {
    renderScoreCards(lastResult);
    drawOrgans(lastResult);
  }
}

function applyUserBodyImage(user) {
  setBodyImage(bodyKindFromGender(user && user.gender));
}

fillHealthFlags(document, {});

function fillProfile(user) {
  document.getElementById("anon-id").textContent = user.user_id;
  document.getElementById("height").value = user.height ?? "";
  document.getElementById("weight").value = user.weight ?? "";
  fillHealthFlags(document, user);
  applyUserBodyImage(user);
  if (typeof updateHomeBmi === "function") updateHomeBmi();
}

async function loadMe() {
  const data = await api("/api/me");
  if (!data.logged_in) {
    authCard.classList.remove("hidden");
    appCard.classList.add("hidden");
    applyUiLangChrome();
    return;
  }
  if (!data.profile_complete) {
    window.location.href = "/profile";
    return;
  }
  authCard.classList.add("hidden");
  appCard.classList.remove("hidden");
  applyPreferredLangFromUser(data.user);
  fillProfile(data.user);
  applyUiLangChrome();
  bindRecipePickers();
  try {
    await loadRecipeCountries();
  } catch (err) {
    const detail = document.getElementById("recipe-detail");
    if (detail) detail.textContent = formatApiError(err);
  }
  await startCamera();
  await loadRecords();
  await loadBackupStatus();
  try {
    await initMealCalendar();
  } catch (err) {
    const mealMsg = document.getElementById("meal-msg");
    if (mealMsg) {
      mealMsg.textContent = formatApiError(err);
      mealMsg.className = "status err";
    }
  }
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
  if (mode === "tongue") alignMode = "tongue";
  else if (mode === "stool") alignMode = "stool";
  else if (mode === "urine") alignMode = "urine";
  else alignMode = "face";
  const isCircle = CIRCLE_SHOTS.has(alignMode);
  const stage = document.getElementById("camera-stage");
  const frame = document.getElementById("align-frame");
  const dim = document.getElementById("align-dim");
  const hint = document.getElementById("align-hint");
  if (stage) {
    stage.classList.toggle("is-face", alignMode === "face");
    stage.classList.toggle("is-tongue", alignMode === "tongue");
    stage.classList.toggle("is-circle", isCircle);
  }
  if (frame) {
    frame.classList.toggle("is-face", alignMode === "face");
    frame.classList.toggle("is-tongue", alignMode === "tongue");
    frame.classList.toggle("is-circle", isCircle);
  }
  if (dim) {
    dim.classList.toggle("is-face", alignMode === "face");
    dim.classList.toggle("is-tongue", alignMode === "tongue");
    dim.classList.toggle("is-circle", isCircle);
  }
  if (hint) hint.textContent = ALIGN_HINTS[alignMode] || ALIGN_HINTS.face;
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
  if (CIRCLE_SHOTS.has(alignMode)) {
    const cx = left + fr.width / 2;
    const cy = top + fr.height / 2;
    const r = Math.min(fr.width, fr.height) / 2;
    const hole = `radial-gradient(circle ${r}px at ${cx}px ${cy}px, transparent ${r}px, #000 ${r + 0.5}px)`;
    dim.style.webkitMaskImage = hole;
    dim.style.maskImage = hole;
    dim.style.webkitMaskSize = "100% 100%";
    dim.style.maskSize = "100% 100%";
    dim.style.webkitMaskPosition = "0 0";
    dim.style.maskPosition = "0 0";
    dim.style.webkitMaskComposite = "source-over";
    dim.style.maskComposite = "overwrite";
    return;
  }
  dim.style.webkitMaskImage = "linear-gradient(#000 0 0), linear-gradient(#000 0 0)";
  dim.style.maskImage = "linear-gradient(#000 0 0), linear-gradient(#000 0 0)";
  const size = `100% 100%, ${fr.width}px ${fr.height}px`;
  const pos = `0 0, ${left}px ${top}px`;
  dim.style.webkitMaskSize = size;
  dim.style.maskSize = size;
  dim.style.webkitMaskPosition = pos;
  dim.style.maskPosition = pos;
  dim.style.webkitMaskComposite = "xor";
  dim.style.maskComposite = "exclude";
}

function objectPositionFractions(value) {
  const parts = String(value || "50% 50%").trim().split(/\s+/);
  const axis = (token) => {
    if (!token || token === "center") return 0.5;
    if (token === "left" || token === "top") return 0;
    if (token === "right" || token === "bottom") return 1;
    if (String(token).endsWith("%")) return parseFloat(token) / 100;
    return 0.5;
  };
  return { x: axis(parts[0]), y: axis(parts[1] || parts[0]) };
}

/** Teeth guide in .tongue-guides (viewBox 0 0 100 160, line y=12). */
const TONGUE_TEETH_Y = 12 / 160;

function tongueTeethFraction(clipRect) {
  const line = document.querySelector("#align-frame .tongue-guides line");
  if (!line || !clipRect || clipRect.height < 2) return TONGUE_TEETH_Y;
  const lr = line.getBoundingClientRect();
  const mid = lr.top + lr.height / 2;
  const frac = (mid - clipRect.top) / clipRect.height;
  if (!Number.isFinite(frac)) return TONGUE_TEETH_Y;
  return Math.min(0.45, Math.max(0, frac));
}

function coverSourceWindow(vw, vh, ew, eh, localX, localY, localW, localH, pos) {
  const scale = Math.max(ew / vw, eh / vh);
  const offsetX = (ew - vw * scale) * pos.x;
  const offsetY = (eh - vh * scale) * pos.y;
  return {
    sx: (localX - offsetX) / scale,
    sy: (localY - offsetY) / scale,
    srcW: localW / scale,
    srcH: localH / scale,
    destW: localW,
    destH: localH,
  };
}

/** Pixels actually shown inside the yellow tongue clip (CSS zoom + object-fit). */
function tongueClipSource(vw, vh) {
  const clip = document.getElementById("camera-clip");
  const vr = video.getBoundingClientRect();
  const cr = clip ? clip.getBoundingClientRect() : null;
  if (cr && vr.width > 2 && vr.height > 2 && cr.width > 2 && cr.height > 2) {
    const pos = objectPositionFractions(getComputedStyle(video).objectPosition);
    const localX = cr.left - vr.left;
    const localY = cr.top - vr.top;
    return {
      clipRect: cr,
      source: coverSourceWindow(vw, vh, vr.width, vr.height, localX, localY, cr.width, cr.height, pos),
    };
  }
  const stage = document.getElementById("camera-stage") || video;
  const sw = Math.max(1, stage.clientWidth || 640);
  const sh = Math.max(1, stage.clientHeight || 480);
  const frame = ALIGN_FRAMES.tongue;
  const clipW = frame.width * sw;
  const clipH = frame.height * sh;
  const zoom = frame.zoom || 1;
  const ew = clipW * zoom;
  const eh = clipH * zoom;
  const localX = -((clipW - ew) / 2);
  const localY = -((clipH - eh) / 2 + 0.12 * clipH);
  return {
    clipRect: null,
    source: coverSourceWindow(vw, vh, ew, eh, localX, localY, clipW, clipH, { x: 0.5, y: 0.62 }),
  };
}

function captureTongueFrame() {
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  const { clipRect, source } = tongueClipSource(vw, vh);
  const topFrac = tongueTeethFraction(clipRect);
  let sx = source.sx;
  let sy = source.sy + source.srcH * topFrac;
  let srcW = source.srcW;
  let srcH = source.srcH * (1 - topFrac);
  const x0 = Math.max(0, sx);
  const y0 = Math.max(0, sy);
  const x1 = Math.min(vw, sx + srcW);
  const y1 = Math.min(vh, sy + srcH);
  if (x1 - x0 >= 1 && y1 - y0 >= 1) {
    sx = x0;
    sy = y0;
    srcW = x1 - x0;
    srcH = y1 - y0;
  }
  const destW = Math.max(1, Math.round(source.destW));
  const destH = Math.max(1, Math.round(source.destH * (1 - topFrac)));
  canvas.width = destW;
  canvas.height = destH;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.translate(destW, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, sx, sy, srcW, srcH, 0, 0, destW, destH);
  ctx.restore();
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92);
  });
}

/** Pixels shown inside the yellow face clip (2× CSS zoom + object-fit). The guides divide this window into 12 cells. */
function faceClipSource(vw, vh) {
  const clip = document.getElementById("camera-clip");
  const vr = video.getBoundingClientRect();
  const cr = clip ? clip.getBoundingClientRect() : null;
  if (cr && vr.width > 2 && vr.height > 2 && cr.width > 2 && cr.height > 2) {
    const pos = objectPositionFractions(getComputedStyle(video).objectPosition);
    const localX = cr.left - vr.left;
    const localY = cr.top - vr.top;
    return coverSourceWindow(vw, vh, vr.width, vr.height, localX, localY, cr.width, cr.height, pos);
  }
  const stage = document.getElementById("camera-stage") || video;
  const sw = Math.max(1, stage.clientWidth || 640);
  const sh = Math.max(1, stage.clientHeight || 480);
  const frame = ALIGN_FRAMES.face;
  const clipW = frame.width * sw;
  const clipH = frame.height * sh;
  const zoom = frame.zoom || 1;
  const ew = clipW * zoom;
  const eh = clipH * zoom;
  const localX = -((clipW - ew) / 2);
  const localY = -((clipH - eh) / 2 + (frame.yBias || 0) * clipH);
  return coverSourceWindow(vw, vh, ew, eh, localX, localY, clipW, clipH, { x: 0.5, y: 0.5 });
}

/** Guide window, then the face moves up 1/4 cell and shrinks to 0.9×. */
function faceAnalysisSource(vw, vh) {
  const source = faceClipSource(vw, vh);
  const srcW = source.srcW / FACE_SCALE;
  const srcH = source.srcH / FACE_SCALE;
  const sx = source.sx + (source.srcW - srcW) / 2;
  const syCentered = source.sy + (source.srcH - srcH) / 2;
  const shiftUp = srcH * (FACE_SHIFT_UP_CELLS / 4);
  return {
    sx,
    sy: syCentered + shiftUp,
    srcW,
    srcH,
    destW: source.destW,
    destH: source.destH,
    shiftUp,
  };
}

function captureFaceFrame() {
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  const source = faceAnalysisSource(vw, vh);
  let sx = source.sx;
  let sy = source.sy;
  let srcW = source.srcW;
  let srcH = source.srcH;
  const x0 = Math.max(0, sx);
  const y0 = Math.max(0, sy);
  const x1 = Math.min(vw, sx + srcW);
  const y1 = Math.min(vh, sy + srcH);
  if (x1 - x0 >= 1 && y1 - y0 >= 1) {
    sx = x0;
    sy = y0;
    srcW = x1 - x0;
    srcH = y1 - y0;
  }
  const destW = Math.max(1, Math.round(source.destW));
  const destH = Math.max(1, Math.round(source.destH));
  canvas.width = destW;
  canvas.height = destH;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.translate(destW, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, sx, sy, srcW, srcH, 0, 0, destW, destH);
  ctx.restore();
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92);
  });
}

/** Circle ROI crop at ~2× zoom (stool / urine). No preview UI. */
function circleClipSource(vw, vh, kind) {
  const clip = document.getElementById("camera-clip");
  const vr = video.getBoundingClientRect();
  const cr = clip ? clip.getBoundingClientRect() : null;
  if (cr && vr.width > 2 && vr.height > 2 && cr.width > 2 && cr.height > 2) {
    const pos = objectPositionFractions(getComputedStyle(video).objectPosition);
    return coverSourceWindow(vw, vh, vr.width, vr.height, localXSafe(cr, vr), localYSafe(cr, vr), cr.width, cr.height, pos);
  }
  const stage = document.getElementById("camera-stage") || video;
  const sw = Math.max(1, stage.clientWidth || 640);
  const sh = Math.max(1, stage.clientHeight || 480);
  const frame = ALIGN_FRAMES[kind] || ALIGN_FRAMES.stool;
  const clipW = frame.width * sw;
  const clipH = frame.height * sh;
  const zoom = frame.zoom || 1;
  const ew = clipW * zoom;
  const eh = clipH * zoom;
  const localX = -((clipW - ew) / 2);
  const localY = -((clipH - eh) / 2 + (frame.yBias || 0) * clipH);
  return coverSourceWindow(vw, vh, ew, eh, localX, localY, clipW, clipH, { x: 0.5, y: 0.5 });
}

function localXSafe(cr, vr) {
  return cr.left - vr.left;
}

function localYSafe(cr, vr) {
  return cr.top - vr.top;
}

function captureCircleFrame(kind) {
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  const source = circleClipSource(vw, vh, kind);
  let sx = source.sx;
  let sy = source.sy;
  let srcW = source.srcW;
  let srcH = source.srcH;
  const x0 = Math.max(0, sx);
  const y0 = Math.max(0, sy);
  const x1 = Math.min(vw, sx + srcW);
  const y1 = Math.min(vh, sy + srcH);
  if (x1 - x0 >= 1 && y1 - y0 >= 1) {
    sx = x0;
    sy = y0;
    srcW = x1 - x0;
    srcH = y1 - y0;
  }
  const destW = Math.max(1, Math.round(source.destW));
  const destH = Math.max(1, Math.round(source.destH));
  canvas.width = destW;
  canvas.height = destH;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.translate(destW, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, sx, sy, srcW, srcH, 0, 0, destW, destH);
  ctx.restore();
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), "image/jpeg", 0.92);
  });
}

function captureFrame(kind) {
  const mode = CIRCLE_SHOTS.has(kind) ? kind : kind === "tongue" ? "tongue" : "face";
  setAlignMode(mode);
  if (mode === "tongue") return captureTongueFrame();
  if (CIRCLE_SHOTS.has(mode)) return captureCircleFrame(mode);
  return captureFaceFrame();
}

/** Static teaching note under stool/urine interpretation (no checkbox questionnaire). */
const DYE_CONFUSION_NOTE =
  "火龍果, 紅色蔬果, 豬血, 深綠色蔬菜, 鐵劑, 制酸劑, 鋇劑等皆有可能染色排泄物造成混淆";

const SYNDROME_STICKERS = new Set([
  "strong-hot.png",
  "strong-cold.png",
  "weak-hot.png",
  "weak-cold.png",
  "mositure.png",
]);

/** Opacity for the four syndrome stickers. 8–10 is healthy, so those stickers are hidden. */
function syndromeStickerOpacity(score) {
  const transparency = { 1: 0, 2: 0.2, 3: 0.4, 4: 0.5, 5: 0.6, 6: 0.7, 7: 0.8 };
  if (score == null || score === "") return 1;
  const n = Math.round(Number(score));
  if (!Number.isFinite(n)) return 1;
  if (n >= 8) return 0;
  const t = transparency[Math.max(1, Math.min(7, n))];
  return 1 - t;
}

function drawOrgans(result) {
  lastResult = result;
  const box = document.getElementById("organ-pins");
  box.innerHTML = "";
  visibleOrgans().forEach((org) => {
    const file = result.overlays ? result.overlays[org.key] : null;
    if (!file) return;
    const score = result.scores ? result.scores[org.score] : result[org.score];
    const opacity = SYNDROME_STICKERS.has(file) ? syndromeStickerOpacity(score) : 1;
    if (opacity <= 0) return;
    const pattern = (result.patterns && result.patterns[org.pattern]) || "";
    org.spots.forEach((spot) => {
      const img = document.createElement("img");
      img.className = "sticker";
      img.src = "/media/" + file;
      img.alt = org.name + pattern;
      img.style.left = spot.x + "%";
      img.style.top = spot.y + "%";
      img.style.opacity = String(opacity);
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

function frameBox(cell) {
  const box = cell && cell.box;
  if (box && box.right > box.left && box.bottom > box.top) return box;
  const row = cell ? Number(cell.row) || 0 : 0;
  const col = cell ? Number(cell.col) || 0 : 0;
  return { left: col / 3, top: row / 4, right: (col + 1) / 3, bottom: (row + 1) / 4 };
}

function placeFrame(el, box) {
  el.style.left = (box.left * 100) + "%";
  el.style.top = (box.top * 100) + "%";
  el.style.width = ((box.right - box.left) * 100) + "%";
  el.style.height = ((box.bottom - box.top) * 100) + "%";
}

function stripWhere(part) {
  const band = part.part === "upper" ? "上" : part.part === "lower" ? "下" : "";
  const side = part.side === "left" ? "左" : part.side === "right" ? "右" : part.side === "middle" ? "中" : "";
  return band + side;
}

function renderFaceGrid(grid, previewUrl) {
  const wrap = document.getElementById("face-grid-wrap");
  if (!grid || !grid.cells) {
    wrap.classList.add("hidden");
    return;
  }
  lastFaceGrid = grid;
  wrap.classList.remove("hidden");
  const img = document.getElementById("face-preview");
  if (previewUrl) {
    img.src = previewUrl;
    img.classList.remove("hidden");
  } else if (!img.src) {
    img.removeAttribute("src");
  }
  const overlay = document.getElementById("face-grid-overlay");
  overlay.innerHTML = "";
  const orderedCells = [...grid.cells].sort((a, b) => (a.row - b.row) || (a.col - b.col) || (a.id - b.id));
  orderedCells.forEach((cell) => {
    const strips = (cell.split || []).filter((part) => part.box);
    if (strips.length) {
      strips.forEach((part) => {
        const strip = document.createElement("div");
        strip.className = "face-cell strip";
        placeFrame(strip, part.box);
        const where = stripWhere(part);
        strip.innerHTML = `<strong>${part.organs}</strong>${where ? " " + where : ""}<br>${part.bias || ""}`;
        overlay.appendChild(strip);
      });
      return;
    }
    const box = document.createElement("div");
    box.className = "face-cell" + (cell.split ? " split" : "");
    placeFrame(box, frameBox(cell));
    if (cell.split) {
      cell.split.forEach((part) => {
        const half = document.createElement("div");
        half.className = "half";
        const tag = part.part === "upper" ? "上" : "下";
        const lab = part.lab ? `L${Math.round(part.lab.L)} a${part.lab.a >= 0 ? "+" : ""}${Math.round(part.lab.a)} b${part.lab.b >= 0 ? "+" : ""}${Math.round(part.lab.b)}` : "";
        half.innerHTML = `<strong>8${tag}</strong> ${part.organs}<br>${lab}<br>${part.bias}`;
        box.appendChild(half);
      });
    } else {
      box.innerHTML = `<strong>${cell.id}</strong> ${cell.organs}<br>${cell.name}<br>${cell.lab_text || ""}<br>${cell.bias || ""}`;
    }
    overlay.appendChild(box);
  });
  const flagBox = document.getElementById("face-lab-flags");
  if (flagBox) {
    const flags = (grid.flags || []).filter((item) => showsFemaleOrgans() || !String(item.text || "").includes("子宮"));
    if (flags.length) {
      flagBox.textContent = flags.map((item) => item.text).join("；") + "（教學示範）";
      flagBox.classList.remove("hidden");
    } else {
      flagBox.textContent = "";
      flagBox.classList.add("hidden");
    }
  }
  const complexion = grid.complexion || {};
  const now = document.getElementById("complexion-now");
  const lab = complexion.lab || {};
  now.textContent = complexion.interpretation
    ? `臉色（${complexion.hex || ""} L${lab.L ?? "–"} a${lab.a ?? "–"} b${lab.b ?? "–"} ${complexion.bias || ""} → ${complexion.pattern || ""}）：${complexion.interpretation}`
    : "";
  const list = document.getElementById("face-cells-list");
  list.innerHTML = "";
  const ordered = [...grid.cells].sort((a, b) => a.id - b.id);
  ordered.forEach((cell) => {
    const card = document.createElement("div");
    card.className = "face-cell-card";
    const splitHtml = (cell.split || [])
      .map((part) => {
        const where = stripWhere(part);
        const title = where ? `${where}${part.organs}` : (part.organs || "");
        return `<div><span class="swatch" style="background:${part.hex}"></span>${title} ${part.hex} ${part.bias} → ${part.meaning}</div>`;
      })
      .join("");
    const hsv = cell.hsv || {};
    const labCell = cell.lab || {};
    card.innerHTML = `<div><span class="swatch" style="background:${cell.hex}"></span><b>第 ${cell.id} 格 ${cell.name}</b>（${cell.organs}）</div>
      <div>${cell.hex}　${cell.lab_text || `L${labCell.L ?? "–"} a${labCell.a ?? "–"} b${labCell.b ?? "–"}`}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
      <div>${cell.health_score != null ? `色差健康分 ${cell.health_score}（ΔE ${cell.delta_e ?? "–"}）` : ""}</div>
      <div>${cell.reading || cell.bias || ""}</div>
      <div>${cell.interpretation || ""}</div>${splitHtml}`;
    list.appendChild(card);
  });
}

function syncTongueDetailFold(grid) {
  const fold = document.getElementById("tongue-detail-fold");
  if (!fold) return;
  const hasTongue = Boolean(grid && grid.cells && grid.cells.length);
  const colorLabel = (document.getElementById("color-label") || {}).textContent || "";
  const colorHex = (document.getElementById("color-hex") || {}).textContent || "";
  const hasColor = Boolean(String(colorLabel).trim() || String(colorHex).trim());
  if (hasTongue || hasColor) fold.classList.remove("hidden");
  else fold.classList.add("hidden");
}

function renderTongueGrid(grid, previewUrl) {
  const wrap = document.getElementById("tongue-grid-wrap");
  if (!grid || !grid.cells) {
    wrap.classList.add("hidden");
    syncTongueDetailFold(null);
    return;
  }
  lastTongueGrid = grid;
  wrap.classList.remove("hidden");
  syncTongueDetailFold(grid);
  const img = document.getElementById("tongue-preview");
  if (previewUrl) {
    img.src = previewUrl;
    img.classList.remove("hidden");
  } else if (!img.src) {
    img.removeAttribute("src");
  }
  const overlay = document.getElementById("tongue-grid-overlay");
  overlay.innerHTML = "";
  (grid.cells || []).forEach((cell) => {
    const box = document.createElement("div");
    box.className = "tongue-zone";
    box.style.left = (cell.left * 100) + "%";
    box.style.top = (cell.top * 100) + "%";
    box.style.width = ((cell.right - cell.left) * 100) + "%";
    box.style.height = ((cell.bottom - cell.top) * 100) + "%";
    const labText = cell.lab_text || "";
    box.innerHTML = `<strong>${cell.label}</strong> ${cell.organs}<br>${cell.anatomy}<br>${labText}<br>${cell.bias || ""}`;
    overlay.appendChild(box);
  });
  const flagEl = document.getElementById("tongue-tip-flag");
  if (flagEl) {
    const bits = [];
    if (grid.tip_heat_flag && grid.tip_heat_flag_text) {
      const delta = grid.delta_a_tip_minus_center;
      const gate = grid.delta_a_threshold;
      bits.push(`${grid.tip_heat_flag_text}（Δa* 舌尖−舌中 ${delta >= 0 ? "+" : ""}${delta}，門檻 ${gate}；教學示範）`);
    }
    if (grid.liver_side_flag_text) bits.push(grid.liver_side_flag_text);
    if (grid.root_flag_text) bits.push(grid.root_flag_text);
    if (bits.length) {
      flagEl.textContent = bits.join(" ");
      flagEl.classList.remove("hidden");
    } else {
      flagEl.textContent = "";
      flagEl.classList.add("hidden");
    }
  }
  const coating = grid.coating || {};
  const now = document.getElementById("tongue-coat-now");
  now.textContent = coating.interpretation
    ? `第六層舌苔（${coating.hex || ""} ${coating.bias || ""} → ${coating.meaning || ""}）：${coating.interpretation}`
    : (grid.sixth_note || "");
  const list = document.getElementById("tongue-cells-list");
  list.innerHTML = "";
  (grid.cells || []).forEach((cell) => {
    const card = document.createElement("div");
    card.className = "face-cell-card";
    const hsv = cell.hsv || {};
    const lab = cell.lab || {};
    card.innerHTML = `<div><span class="swatch" style="background:${cell.hex}"></span><b>${cell.label} ${cell.organs}</b>（${cell.anatomy}）</div>
      <div>${cell.hex}　${cell.lab_text || `L${lab.L ?? "–"} a${lab.a ?? "–"} b${lab.b ?? "–"}`}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
      <div>${cell.health_score != null ? `舌質健康分 ${cell.health_score}（ΔE ${cell.delta_e ?? "–"}）；苔 ${cell.coat_health_score ?? "–"}（ΔE ${cell.coat_delta_e ?? "–"}）` : ""}</div>
      <div>${cell.reading || cell.bias || ""}</div>
      <div>${cell.interpretation || ""}</div>`;
    list.appendChild(card);
  });
  if (coating.bias) {
    const card = document.createElement("div");
    card.className = "face-cell-card";
    const hsv = coating.hsv || {};
    const lab = coating.lab || {};
    card.innerHTML = `<div><span class="swatch" style="background:${coating.hex}"></span><b>第六層 舌苔</b>（胃／膽／大腸疊加）</div>
      <div>${coating.hex || ""}　${coating.lab_text || `L${lab.L ?? "–"} a${lab.a ?? "–"} b${lab.b ?? "–"}`}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
      <div>${coating.health_score != null ? `舌苔健康分 ${coating.health_score}（ΔE ${coating.delta_e ?? "–"}）` : ""}</div>
      <div>${coating.reading || ""}</div>
      <div>${coating.interpretation || ""}</div>`;
    list.appendChild(card);
  }
}

function renderComplexionHistory(records) {
  complexionHistory = (records || [])
    .filter((row) => row.complexion_label || (row.face_grid && row.face_grid.complexion))
    .map((row) => {
      const complexion = (row.face_grid && row.face_grid.complexion) || {};
      return {
        date: (row.record_date || "").toString().replace("T", " ").slice(0, 19),
        label: row.complexion_label || complexion.bias || "",
        hex: row.complexion_hex || complexion.hex || "",
        pattern: complexion.pattern || "",
      };
    });
  const box = document.getElementById("complexion-history");
  if (!box) return;
  if (!complexionHistory.length) {
    box.textContent = "尚無臉色紀錄";
    return;
  }
  const rows = complexionHistory
    .map((item) => `<tr><td>${item.date}</td><td><span class="swatch" style="background:${item.hex};width:14px;height:14px;border-radius:50%;display:inline-block;vertical-align:middle;margin-right:6px;border:1px solid #ccc"></span>${item.hex}</td><td>${item.label}</td><td>${item.pattern}</td></tr>`)
    .join("");
  box.innerHTML = `<table><thead><tr><th>日期</th><th>臉色色碼</th><th>偏色</th><th>證型傾向</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function shownScore(score) {
  const n = Number(score);
  return Number.isFinite(n) ? String(n) : "10";
}

function hidesSpleenStomachPatternList(text) {
  const value = String(text || "").trim();
  if (!value || SPLEEN_STOMACH_PATTERNS.includes(value)) return Boolean(value);
  if (value.startsWith("脾與胃證型分開計分")) return true;
  const counted = value.match(/^症狀「[\s\S]*」分開計入(.+)$/);
  if (!counted) return false;
  const parts = counted[1].split("、").map((part) => part.trim()).filter(Boolean);
  return parts.length > 0 && parts.every((part) => SPLEEN_STOMACH_PATTERNS.includes(part));
}

function patternLabel(score, pattern) {
  const n = Number(score);
  if (!Number.isFinite(n) || n >= 8) return "健康";
  if (n === 5 && (pattern === "未定" || pattern == null || pattern === "")) return "待觀察";
  return pattern || "";
}

function renderScoreCards(result) {
  const scores = document.getElementById("scores");
  if (!scores || !result) return;
  scores.innerHTML = "";
  visibleOrgans().forEach((org) => {
    const div = document.createElement("div");
    div.className = "score";
    const score = result.scores ? result.scores[org.score] : result[org.score];
    const rawPattern = result.patterns ? result.patterns[org.pattern] : "";
    div.innerHTML = `<span>${org.name}</span><b>${shownScore(score)}</b><small>${patternLabel(score, rawPattern)}</small>`;
    scores.appendChild(div);
  });
}

function briefCircleLine(note, kind) {
  if (!note || typeof note !== "object") return "";
  // day_modalities.<kind>.note holds class; legacy callers may pass note or class itself.
  const hit = (note.note && note.note.class) || note.class || note.note || note;
  const label = String((hit && hit.label) || "").trim();
  if (!label) return "";
  const tag = kind === "urine" ? "尿尿" : "大便";
  // Stool nearest-standard: show class +「接近判定標準」, never「無法對照」.
  const nearStd = Boolean(
    hit &&
      (hit.near_standard ||
        label.includes("接近判定標準"))
  );
  if (nearStd && kind !== "urine") {
    const abnormal = Boolean(hit && hit.abnormal);
    return abnormal
      ? `${tag}：需留意 — ${label}`
      : `${tag}：正常 — ${label}`;
  }
  const outside = Boolean(
    hit &&
      (hit.id === "outside_palette" ||
        (hit.far_from_palette && !nearStd))
  );
  if (outside) {
    const hint = String((hit && hit.hint) || "").trim();
    return hint
      ? `${tag}：無法對照 — ${label}（${hint.slice(0, 48)}）`
      : `${tag}：無法對照 — ${label}`;
  }
  const abnormal = Boolean(hit && hit.abnormal);
  const confirm = String((hit && hit.confirm) || "").trim();
  const confirmHint =
    confirm === "diet_or_drug_matte_black" || confirm === "clear_water_diet_red"
      ? "（染色較可能）"
      : confirm === "pink_water_fresh_blood"
        ? "（水液偏粉紅）"
        : confirm === "glossy_tar_like"
          ? "（偏油亮）"
          : "";
  return abnormal
    ? `${tag}：需留意 — ${label}${confirmHint}`
    : `${tag}：正常 — ${label}`;
}

/** Face Lab teaching lines must not appear under 食療整理 / findings. */
function isFaceColorTeachingFinding(text) {
  const s = String(text || "");
  return (
    s.startsWith("教學正常值") ||
    s.includes("臉色分數") ||
    s.includes("ΔE*/20") ||
    s.includes("8–10 健康") ||
    s.includes("8-10 健康")
  );
}

function findingsFromDayModalities(organHealth) {
  const dm = (organHealth && organHealth.day_modalities) || {};
  const out = [];
  for (const key of ["face", "tongue", "stool", "urine", "pulse"]) {
    const block = dm[key];
    if (!block || typeof block !== "object") continue;
    const list = Array.isArray(block.findings) ? block.findings : [];
    list.forEach((t) => {
      const s = String(t || "").trim();
      if (s) out.push(s);
    });
  }
  return out;
}

function updateCircleLinesFromResult(result) {
  if (!result) return;
  const oh = result.organ_health || {};
  const dm = oh.day_modalities || {};
  const su = oh.stool_urine || {};
  if (dm.face && dm.face.color_label) {
    lastDayLines.face = `臉：${dm.face.color_label}`;
  }
  if (dm.tongue && dm.tongue.color_label) {
    lastDayLines.tongue = `舌：${dm.tongue.color_label}`;
  }
  if (dm.pulse && (dm.pulse.present || (dm.pulse.findings || []).length)) {
    lastDayLines.pulse = "脈：已測";
  }
  const stoolNote =
    result.stool || su.stool || (dm.stool && (dm.stool.note || dm.stool.class)) || null;
  const urineNote =
    result.urine || su.urine || (dm.urine && (dm.urine.note || dm.urine.class)) || null;
  const stoolLine = briefCircleLine(stoolNote, "stool");
  const urineLine = briefCircleLine(urineNote, "urine");
  if (stoolLine) lastDayLines.stool = stoolLine;
  else if (dm.stool && dm.stool.color_label) lastDayLines.stool = `大便：${dm.stool.color_label}`;
  if (urineLine) lastDayLines.urine = urineLine;
  else if (dm.urine && dm.urine.color_label) lastDayLines.urine = `尿尿：${dm.urine.color_label}`;
  // Fallback: newest matching finding (re-shots append; first match was stale).
  if (Array.isArray(result.findings)) {
    let stoolHit = "";
    let urineHit = "";
    result.findings.forEach((t) => {
      const s = String(t || "");
      if (s.startsWith("大便")) stoolHit = s.split("（")[0].trim();
      if (s.startsWith("尿尿")) urineHit = s.split("（")[0].trim();
    });
    if (!lastDayLines.stool && stoolHit) lastDayLines.stool = stoolHit;
    if (!lastDayLines.urine && urineHit) lastDayLines.urine = urineHit;
  }
}

function renderCircleResultPanel() {
  const el = document.getElementById("circle-result");
  if (!el) return;
  const lines = [];
  if (lastDayLines.face) lines.push(lastDayLines.face);
  if (lastDayLines.tongue) lines.push(lastDayLines.tongue);
  if (lastDayLines.stool) {
    lines.push(lastDayLines.stool);
    lines.push(DYE_CONFUSION_NOTE);
  }
  if (lastDayLines.urine) {
    lines.push(lastDayLines.urine);
    lines.push(DYE_CONFUSION_NOTE);
  }
  if (lastDayLines.pulse) lines.push(lastDayLines.pulse);
  if (!lines.length) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = lines.join("\n");
  el.classList.remove("hidden");
}

function renderResult(result) {
  updateCircleLinesFromResult(result);
  renderCircleResultPanel();
  if (result.dominant_color) {
    document.getElementById("color-chip").style.background = result.dominant_color;
    document.getElementById("color-hex").textContent = result.dominant_color;
  }
  const cct = result.color_temperature_k;
  const brightGain = result.brightness_gain;
  const lightBits = [];
  if (cct != null && cct !== "") lightBits.push(`色溫約 ${cct}K`);
  if (brightGain != null && brightGain !== "") {
    const g = Number(brightGain);
    if (Number.isFinite(g)) lightBits.push(`明暗校正 ×${g.toFixed(2)}`);
  }
  const lightNote = lightBits.length ? `（自動${lightBits.join("，")}）` : "";
  document.getElementById("color-label").textContent = " " + (result.color_label || "") + lightNote;
  syncTongueDetailFold(result.tongue_grid || lastTongueGrid);
  document.getElementById("disclaimer").textContent = result.disclaimer || "";
  const findings = document.getElementById("findings");
  findings.innerHTML = "";
  (result.findings || []).forEach((text) => {
    if (hidesSpleenStomachPatternList(text)) return;
    if (isFaceColorTeachingFinding(text)) return;
    const line = withoutUterusStatement(text);
    if (!line) return;
    const li = document.createElement("li");
    li.textContent = line;
    findings.appendChild(li);
  });
  const advice = withoutUterusStatement(result.diet_advice || "");
  // Hide face color-analysis teaching blobs if they ever ride inside diet_advice.
  const adviceClean = isFaceColorTeachingFinding(advice) ? "" : advice;
  document.getElementById("advice").textContent = adviceClean ? "食療整理：" + adviceClean : "";
  const links = document.getElementById("links");
  links.innerHTML = "";
  const dietArticleQ = (result.diet_query || "").trim() || (() => {
    try {
      const u = new URL(result.diet_url || "", window.location.origin);
      return (u.searchParams.get("q") || "").trim();
    } catch (_err) {
      return "";
    }
  })();
  const dietVideoQ = (result.diet_video_query || "").trim() || (
    dietArticleQ ? `食譜 影片 ${dietArticleQ}` : ""
  );
  const dietArticle = result.diet_url || (dietArticleQ
    ? `https://www.google.com/search?q=${encodeURIComponent(dietArticleQ)}`
    : "");
  const dietVideo = result.diet_video_url || (dietVideoQ
    ? `https://www.google.com/search?tbm=vid&q=${encodeURIComponent(dietVideoQ)}`
    : "");
  if (dietArticle) {
    links.innerHTML += `<a href="${dietArticle}" target="_blank" rel="noreferrer">${uiText("dietLinkArticles")}</a>　`;
  }
  if (dietVideo) {
    links.innerHTML += `<a href="${dietVideo}" target="_blank" rel="noreferrer">${uiText("dietLinkVideos")}</a>　`;
  }
  const acuImageQ = (result.acupoint_query || "").trim() || (() => {
    try {
      const u = new URL(result.acupoint_url || "", window.location.origin);
      return (u.searchParams.get("q") || "").trim();
    } catch (_err) {
      return "";
    }
  })();
  const acuVideoQ = (result.acupoint_video_query || "").trim() || (
    acuImageQ
      ? `穴道 影片 ${acuImageQ.replace(/^穴道\s+(?:照片|圖片)\s+/, "")}`
      : ""
  );
  const acuImages = result.acupoint_url || (acuImageQ
    ? `https://www.google.com/search?tbm=isch&q=${encodeURIComponent(acuImageQ)}`
    : "");
  const acuVideo = result.acupoint_video_url || (acuVideoQ
    ? `https://www.google.com/search?tbm=vid&q=${encodeURIComponent(acuVideoQ)}`
    : "");
  if (acuImages) {
    links.innerHTML += `<a href="${acuImages}" target="_blank" rel="noreferrer">${uiText("acupointLinkImages")}</a>　`;
  }
  if (acuVideo) {
    links.innerHTML += `<a href="${acuVideo}" target="_blank" rel="noreferrer">${uiText("acupointLinkVideos")}</a>`;
  }
  renderScoreCards(result);
  drawOrgans(result);
  if (result.face_preview) lastFacePreviewUrl = result.face_preview;
  if (result.tongue_preview) lastTonguePreviewUrl = result.tongue_preview;
  renderFaceGrid(result.face_grid, lastFacePreviewUrl);
  renderTongueGrid(result.tongue_grid, lastTonguePreviewUrl);
  refreshRecipeChoices({ keepSelection: selectedRecipeId != null }).catch(() => {});
}

let countryNames = [];
let recipeRows = [];
let selectedRecipeId = null;
let recipeByBody = false;

function recipeLabel(row) {
  return row.name + (row.benefit_match ? " ★" : "");
}

function countryPrefixMatch(label, query) {
  const name = String(label || "");
  const q = String(query || "").trim();
  if (!q) return true;
  return name.toLowerCase().startsWith(q.toLowerCase());
}

function recipeTextMatch(label, query) {
  const name = String(label || "").toLowerCase();
  const q = String(query || "").trim().toLowerCase();
  if (!q) return true;
  return name.includes(q);
}

function judgmentField(result, bucket, key) {
  if (!result) return undefined;
  const nested = result[bucket];
  if (nested && typeof nested === "object" && Object.prototype.hasOwnProperty.call(nested, key)) {
    const value = nested[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  if (Object.prototype.hasOwnProperty.call(result, key)) {
    const value = result[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function closeCombo(input, list) {
  if (!list) return;
  list.hidden = true;
  if (input) input.setAttribute("aria-expanded", "false");
}

function renderCombo(input, list, labels, onPick, mode, emptyText, options) {
  if (!input || !list) return;
  const query = mode === "all" ? "" : input.value.trim();
  const matched = labels.filter((label) => {
    if (mode === "prefix") return countryPrefixMatch(label, query);
    if (mode === "all") return true;
    return recipeTextMatch(label, query);
  });
  list.innerHTML = "";
  if (!matched.length) {
    const empty = document.createElement("li");
    empty.className = "combo-empty";
    empty.textContent = emptyText || uiText("searchEmpty");
    list.appendChild(empty);
    if (options && typeof options.onEmptyCreate === "function" && query) {
      const createItem = document.createElement("li");
      createItem.className = "combo-create";
      const createBtn = document.createElement("button");
      createBtn.type = "button";
      createBtn.className = "combo-create-btn";
      createBtn.textContent = uiText("recipeCreateAction");
      createBtn.addEventListener("mousedown", (event) => {
        event.preventDefault();
        closeCombo(input, list);
        options.onEmptyCreate(query);
      });
      createItem.appendChild(createBtn);
      list.appendChild(createItem);
    }
  } else {
    matched.forEach((label) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.addEventListener("mousedown", (event) => {
        event.preventDefault();
        input.value = label;
        closeCombo(input, list);
        onPick(label);
      });
      item.appendChild(button);
      list.appendChild(item);
    });
  }
  list.hidden = false;
  input.setAttribute("aria-expanded", "true");
  return matched;
}

function recipeLabelWithCountry(row) {
  const base = recipeLabel(row);
  const country = (row && row.country) || "";
  const countryInput = document.getElementById("recipe-country");
  const selectedCountry = countryInput ? countryInput.value.trim() : "";
  if (!country || (selectedCountry && selectedCountry === country)) return base;
  return `${recipeNamePlain(base)}（${country}）`;
}

function applyRecipeCountry(row) {
  if (!row || !row.country) return;
  const countryInput = document.getElementById("recipe-country");
  if (!countryInput) return;
  const country = String(row.country).trim();
  if (!country) return;
  countryInput.value = country;
  if (!countryNames.includes(country)) countryNames = countryNames.concat([country]);
}

function rememberRecipeChoice(label) {
  const row = recipeRows.find((item) => recipeLabelWithCountry(item) === label)
    || recipeRows.find((item) => recipeLabel(item) === label)
    || findRecipeByTypedName(label);
  selectedRecipeId = row ? row.id : null;
  if (row) applyRecipeCountry(row);
  return row || null;
}

function recipeNamePlain(label) {
  return String(label || "")
    .replace(/\s*★\s*$/, "")
    .replace(/（[^）]+）\s*$/, "")
    .replace(/\s*\([^)]+\)\s*$/, "")
    .trim();
}

function findRecipeByTypedName(typed) {
  const label = String(typed || "").trim();
  const plain = recipeNamePlain(label).toLowerCase();
  if (!plain) return null;
  return (
    recipeRows.find((item) => recipeLabelWithCountry(item) === label)
    || recipeRows.find((item) => recipeLabel(item) === label)
    || recipeRows.find((item) => recipeNamePlain(recipeLabel(item)).toLowerCase() === plain)
    || recipeRows.find((item) => String(item.name || "").trim().toLowerCase() === plain)
    || null
  );
}

function formatRecipeNutrients(nutrients) {
  if (!nutrients || typeof nutrients !== "object") return "";
  const parts = [];
  for (const [key, raw] of Object.entries(nutrients)) {
    const value = Number(raw);
    if (!Number.isFinite(value) || value === 0) continue;
    parts.push(`${key} ${value}`);
  }
  return parts.join("、");
}

let recipeEnsureSeq = 0;
let recipeListSeq = 0;
let recipeEnsureBusy = false;
let recipeEnsureFollowUp = null;

function isRecipeStatusMessage(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  return value === uiText("recipeSearching")
    || value === uiText("recipeEnsuring")
    || value === uiText("recipeEnsureFailed");
}

function showSelectedRecipe(extraNote) {
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  if (!pick || !detail) return;
  const label = pick.value.trim();
  const row = recipeRows.find((item) => String(item.id) === String(selectedRecipeId) && recipeLabel(item) === label)
    || recipeRows.find((item) => recipeLabel(item) === label)
    || findRecipeByTypedName(label);
  if (!row) {
    selectedRecipeId = null;
    // Never keep another dish's ingredients/method under a different typed name.
    if (!label) detail.textContent = "";
    else if (!recipeEnsureBusy && !isRecipeStatusMessage(detail.textContent)) detail.textContent = "";
    return;
  }
  selectedRecipeId = row.id;
  const lines = [
    ["fieldRecipe", row.recipe],
    ["fieldMethod", row.method],
    ["fieldBenefit", row.benefit],
    ["fieldNutrient", row.nutrient],
    ["fieldBan", row.ban],
    ["fieldAllergens", row.allergens],
  ].filter((item) => item[1]);
  let text = lines.map((item) => uiText(item[0]) + "\n" + item[1]).join("\n\n");
  const nutrientLine = row.nutrient_line || formatRecipeNutrients(row.nutrients);
  if (nutrientLine) text = (text ? text + "\n\n" : "") + nutrientLine;
  if (extraNote) text = (text ? text + "\n\n" : "") + extraNote;
  detail.textContent = text;
}

function recipeHasSubstringMatch(typed) {
  const q = recipeNamePlain(typed).toLowerCase();
  if (!q) return true;
  return recipeRows.some((item) => recipeTextMatch(recipeLabel(item), q));
}

function showRecipeSearchStatus(typed) {
  const detail = document.getElementById("recipe-detail");
  if (!detail) return;
  const plain = recipeNamePlain(typed);
  if (!plain) {
    selectedRecipeId = null;
    if (!recipeEnsureBusy) detail.textContent = "";
    return;
  }
  if (findRecipeByTypedName(typed)) {
    showSelectedRecipe();
    return;
  }
  if (recipeEnsureBusy) {
    detail.textContent = uiText("recipeEnsuring");
    return;
  }
  if (!recipeHasSubstringMatch(typed)) {
    detail.textContent = uiText("recipeSearching");
    return;
  }
  // Substring hits exist but exact dish not selected — drop stale detail from another dish.
  if (!isRecipeStatusMessage(detail.textContent)) detail.textContent = "";
}

async function ensureRecipeFromInput(options) {
  const countryInput = document.getElementById("recipe-country");
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  const list = document.getElementById("recipe-name-list");
  if (!countryInput || !pick || !detail) return null;
  let country = countryInput.value.trim();
  if (country && !countryNames.includes(country)) country = "";
  const typed = (options && options.name) || pick.value.trim();
  const plain = recipeNamePlain(typed);
  if (!plain) return null;
  const existing = findRecipeByTypedName(typed);
  const needsFill = Boolean(
    existing
    && (
      !(existing.recipe && String(existing.recipe).trim())
      || !(existing.method && String(existing.method).trim())
      || !(existing.benefit && String(existing.benefit).trim())
      || !(existing.nutrient && String(existing.nutrient).trim())
    )
  );
  if (existing && !needsFill) {
    selectedRecipeId = existing.id;
    applyRecipeCountry(existing);
    pick.value = recipeLabel(existing);
    showSelectedRecipe();
    return existing;
  }
  if (!needsFill && recipeHasSubstringMatch(typed) && !(options && options.forceCreate)) {
    // Substring hits exist — wait for an exact pick; do not auto-create.
    showSelectedRecipe();
    return null;
  }
  const seq = ++recipeEnsureSeq;
  recipeEnsureBusy = true;
  closeCombo(pick, list);
  pick.value = plain;
  detail.textContent = uiText("recipeEnsuring");
  try {
    // Re-read country at request time so a late country fill is included.
    let ensureCountry = countryInput.value.trim();
    if (ensureCountry && !countryNames.includes(ensureCountry)) ensureCountry = "";
    const data = await api("/api/recipes/create", {
      method: "POST",
      body: formBody({ country: ensureCountry, name: plain, lang: getUiLang() }),
    });
    if (seq !== recipeEnsureSeq) return null;
    if (data && data.rejected) {
      detail.textContent = data.note || uiText("recipeLangUnsupported");
      return null;
    }
    const created = data && data.recipe;
    if (created && created.id != null) selectedRecipeId = created.id;
    if (created) applyRecipeCountry(created);
    const resolvedCountry = (created && created.country) || countryInput.value.trim();
    // Always reload that country's list when catalog corrected the country selector.
    if (resolvedCountry && (countryNames.includes(resolvedCountry) || data.country_corrected)) {
      if (resolvedCountry && !countryNames.includes(resolvedCountry)) {
        countryNames = countryNames.concat([resolvedCountry]);
      }
      await loadRecipesForCountry({ keepSelection: true, preserveTyped: plain });
    } else if (created) {
      recipeRows = [created].concat(recipeRows.filter((item) => String(item.id) !== String(created.id)));
    }
    if (seq !== recipeEnsureSeq) return null;
    let row =
      (created && recipeRows.find((item) => String(item.id) === String(created.id)))
      || findRecipeByTypedName(plain)
      || null;
    if (!row && created && created.id != null) {
      row = created;
      if (!recipeRows.some((item) => String(item.id) === String(row.id))) {
        recipeRows = recipeRows.concat([row]);
      }
    }
    if (row && row.id != null) {
      selectedRecipeId = row.id;
      applyRecipeCountry(row);
      pick.value = row.name ? recipeLabel(row) : plain;
      const note = data.partial
        ? (data.note || uiText("recipeEnsurePartial"))
        : (data.note || "");
      showSelectedRecipe(note);
      return row;
    }
    detail.textContent = uiText("recipeEnsureFailed");
    return null;
  } catch (err) {
    if (seq !== recipeEnsureSeq) return null;
    detail.textContent = formatApiError(err) || uiText("recipeEnsureFailed");
    return null;
  } finally {
    if (seq === recipeEnsureSeq) {
      recipeEnsureBusy = false;
      const followUp = recipeEnsureFollowUp;
      recipeEnsureFollowUp = null;
      if (followUp && followUp.name) {
        ensureRecipeFromInput(followUp).catch((err) => {
          const box = document.getElementById("recipe-detail");
          if (box) box.textContent = formatApiError(err) || uiText("recipeEnsureFailed");
        });
      }
    }
  }
}

function recipeFilterParams() {
  const params = new URLSearchParams({
    lang: getUiLang(),
    female: currentBody === "girl" ? "1" : "0",
    by_body: recipeByBody ? "1" : "0",
  });
  if (!lastResult) return params;
  const scores = {};
  const patterns = {};
  organs.forEach((org) => {
    const score = judgmentField(lastResult, "scores", org.score);
    const pattern = judgmentField(lastResult, "patterns", org.pattern);
    if (score !== undefined) scores[org.score] = score;
    if (pattern) patterns[org.pattern] = pattern;
  });
  params.set("scores", JSON.stringify(scores));
  params.set("patterns", JSON.stringify(patterns));
  return params;
}

function recipeQueryParams(country) {
  const params = recipeFilterParams();
  params.set("country", country);
  return params;
}

function clearRecipeSelection() {
  recipeRows = [];
  selectedRecipeId = null;
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  const list = document.getElementById("recipe-name-list");
  if (pick) pick.value = "";
  if (detail) detail.textContent = "";
  closeCombo(pick, list);
}

async function loadRecipeCountries() {
  const input = document.getElementById("recipe-country");
  if (!input) return;
  const current = input.value.trim();
  const data = await api("/api/recipes/countries?" + recipeFilterParams().toString());
  countryNames = data.countries || [];
  if (current && !countryNames.includes(current)) {
    input.value = "";
    clearRecipeSelection();
  }
}

async function refreshRecipeChoices(options) {
  const keepSelection = Boolean(options && options.keepSelection);
  await loadRecipeCountries();
  const countryInput = document.getElementById("recipe-country");
  if (countryInput && countryNames.includes(countryInput.value.trim())) {
    await loadRecipesForCountry({ keepSelection });
    return;
  }
  const pick = document.getElementById("recipe-name");
  const typed = pick ? recipeNamePlain(pick.value) : "";
  if (typed) await loadRecipesByName(typed, { keepSelection });
}

async function loadRecipesByName(name, options) {
  const keepSelection = Boolean(options && options.keepSelection);
  const keepId = keepSelection ? selectedRecipeId : null;
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  const list = document.getElementById("recipe-name-list");
  if (!pick || !detail) return;
  const plain = recipeNamePlain(name || pick.value);
  const seq = ++recipeListSeq;
  closeCombo(pick, list);
  if (!plain) {
    recipeRows = [];
    return;
  }
  const params = recipeFilterParams();
  params.set("name", plain);
  const data = await api("/api/recipes?" + params.toString());
  if (seq !== recipeListSeq) return;
  recipeRows = data.recipes || [];
  if (keepId != null) {
    const row = recipeRows.find((item) => String(item.id) === String(keepId));
    if (row) {
      selectedRecipeId = row.id;
      applyRecipeCountry(row);
      pick.value = recipeLabel(row);
      showSelectedRecipe();
      return;
    }
  }
}

async function loadRecipesForCountry(options) {
  const keepSelection = Boolean(options && options.keepSelection);
  const keepId = keepSelection ? selectedRecipeId : null;
  const preserveTypedRaw = options && options.preserveTyped;
  const countryInput = document.getElementById("recipe-country");
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  const list = document.getElementById("recipe-name-list");
  if (!countryInput || !pick || !detail) return;
  const country = countryInput.value.trim();
  const typedBefore = recipeNamePlain(
    preserveTypedRaw != null && preserveTypedRaw !== true && preserveTypedRaw !== false
      ? preserveTypedRaw
      : pick.value
  );
  const preserveTyped = Boolean(preserveTypedRaw) || Boolean(typedBefore && (keepSelection || recipeEnsureBusy));
  const seq = ++recipeListSeq;
  closeCombo(pick, list);
  if (!keepSelection && !preserveTyped) {
    selectedRecipeId = null;
    recipeRows = [];
    pick.value = "";
    detail.textContent = "";
  } else if (preserveTyped && typedBefore) {
    // Keep the pending dish name; do not flash another country's first recipe.
    pick.value = typedBefore;
  }
  if (!countryNames.includes(country)) {
    // Country optional: keep typed dish name and search across Recipe.xls.
    const typed = typedBefore || recipeNamePlain(pick.value);
    if (typed) {
      await loadRecipesByName(typed, { keepSelection: true });
      return;
    }
    if (seq === recipeListSeq) recipeRows = [];
    return;
  }
  const data = await api("/api/recipes?" + recipeQueryParams(country).toString());
  if (seq !== recipeListSeq) return;
  recipeRows = data.recipes || [];
  if (keepId != null) {
    const row = recipeRows.find((item) => String(item.id) === String(keepId));
    if (row) {
      selectedRecipeId = row.id;
      pick.value = recipeLabel(row);
      showSelectedRecipe();
      return;
    }
  }
  if (preserveTyped && typedBefore) {
    const matched = findRecipeByTypedName(typedBefore);
    if (matched) {
      selectedRecipeId = matched.id;
      pick.value = recipeLabel(matched);
      showSelectedRecipe();
      return;
    }
    // Typed dish is not in this country list yet — keep name + status; caller may ensure.
    selectedRecipeId = null;
    pick.value = typedBefore;
    if (!recipeEnsureBusy && !isRecipeStatusMessage(detail.textContent)) {
      detail.textContent = uiText("recipeSearching");
    }
    return;
  }
  selectedRecipeId = null;
  pick.value = "";
  detail.textContent = recipeRows.length ? "" : uiText(recipeByBody ? "emptyRecipesBody" : "emptyRecipes");
}

/** Country just became valid: reload list without dropping a typed dish; ensure if missing. */
function onRecipeCountryChosen() {
  const pick = document.getElementById("recipe-name");
  const detail = document.getElementById("recipe-detail");
  const pickList = document.getElementById("recipe-name-list");
  const typed = pick ? recipeNamePlain(pick.value) : "";
  loadRecipesForCountry({ preserveTyped: typed || true })
    .then(() => {
      if (!typed) {
        // Open recipe dropdown after country so the filtered list is visible.
        if (pick && pickList && recipeRows.length) {
          renderCombo(pick, pickList, recipeRows.map(recipeLabel), (label) => {
            rememberRecipeChoice(label);
            showSelectedRecipe();
          }, "all");
        }
        return;
      }
      if (findRecipeByTypedName(typed)) {
        showSelectedRecipe();
        return;
      }
      // Country filled after name: ensure this dish under the chosen country.
      // If an ensure is already running (often started before country was set),
      // queue a follow-up with the new country instead of racing the write lock.
      if (recipeEnsureBusy) {
        recipeEnsureFollowUp = { name: typed, forceCreate: true };
        if (detail) detail.textContent = uiText("recipeEnsuring");
        return;
      }
      return ensureRecipeFromInput({ name: typed, forceCreate: true });
    })
    .catch((err) => {
      if (detail) detail.textContent = formatApiError(err);
    });
}

async function reloadRecipesForLanguage() {
  const countryInput = document.getElementById("recipe-country");
  if (countryInput && countryNames.includes(countryInput.value.trim())) {
    await loadRecipesForCountry({ keepSelection: true });
    return;
  }
  const pick = document.getElementById("recipe-name");
  const typed = pick ? recipeNamePlain(pick.value) : "";
  if (typed) await loadRecipesByName(typed, { keepSelection: true });
}

function bindRecipePickers() {
  const country = document.getElementById("recipe-country");
  const countryList = document.getElementById("recipe-country-list");
  const pick = document.getElementById("recipe-name");
  const pickList = document.getElementById("recipe-name-list");
  if (!country || !pick || country.dataset.bound) return;
  country.dataset.bound = "1";
  country.placeholder = uiText("pickCountry");
  pick.placeholder = uiText("pickRecipe");
  const bodyBtn = document.getElementById("recipe-body-advice");
  if (bodyBtn) {
    bodyBtn.addEventListener("click", () => {
      recipeByBody = bodyBtn.getAttribute("aria-pressed") !== "true";
      bodyBtn.setAttribute("aria-pressed", recipeByBody ? "true" : "false");
      refreshRecipeChoices({ keepSelection: true }).catch((err) => {
        const detail = document.getElementById("recipe-detail");
        if (detail) detail.textContent = formatApiError(err);
      });
    });
  }
  const showCountries = () => renderCombo(country, countryList, countryNames, () => {
    // Keep a typed pending dish; do not clear selection into the country's first recipe.
    onRecipeCountryChosen();
  }, "prefix");
  const hasCountry = () => countryNames.includes(country.value.trim());
  const usableRecipeLabels = () => {
    if (hasCountry()) return recipeRows.map(recipeLabel);
    // No country: show cross-country hits with country tags.
    return recipeRows.map(recipeLabelWithCountry);
  };
  const showAllRecipes = () => {
    const labels = usableRecipeLabels();
    if (!hasCountry() && !labels.length) {
      // Allow typing a dish with no country selected.
      closeCombo(pick, pickList);
      return;
    }
    if (!labels.length && hasCountry()) {
      closeCombo(pick, pickList);
      return;
    }
    renderCombo(pick, pickList, labels, (label) => {
      rememberRecipeChoice(label);
      showSelectedRecipe();
    }, hasCountry() ? "all" : "contains");
  };
  const startCreateRecipe = (typedName) => {
    ensureRecipeFromInput({ name: typedName, forceCreate: true }).catch((err) => {
      const box = document.getElementById("recipe-detail");
      if (box) box.textContent = formatApiError(err) || uiText("recipeEnsureFailed");
    });
  };
  let recipeNameSearchTimer = 0;
  const filterRecipes = () => {
    const labels = usableRecipeLabels();
    renderCombo(pick, pickList, labels, (label) => {
      rememberRecipeChoice(label);
      showSelectedRecipe();
    }, "contains", uiText("searchEmpty"), {
      onEmptyCreate: startCreateRecipe,
    });
  };
  const searchRecipesWithoutCountry = () => {
    if (hasCountry()) return;
    const typed = recipeNamePlain(pick.value);
    window.clearTimeout(recipeNameSearchTimer);
    if (!typed) {
      recipeRows = [];
      filterRecipes();
      return;
    }
    recipeNameSearchTimer = window.setTimeout(() => {
      loadRecipesByName(typed, { keepSelection: true })
        .then(() => {
          filterRecipes();
          showRecipeSearchStatus(pick.value);
        })
        .catch((err) => {
          const box = document.getElementById("recipe-detail");
          if (box) box.textContent = formatApiError(err);
        });
    }, 220);
  };
  country.addEventListener("focus", showCountries);
  country.addEventListener("click", showCountries);
  country.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeCombo(country, countryList);
    if (event.key !== "Enter") return;
    event.preventDefault();
    const button = countryList.querySelector("button");
    if (!button) return;
    country.value = button.textContent;
    closeCombo(country, countryList);
    onRecipeCountryChosen();
  });
  country.addEventListener("input", () => {
    showCountries();
    const exact = countryNames.includes(country.value.trim());
    if (exact) {
      onRecipeCountryChosen();
    } else {
      // Keep dish text; search across countries when the user types a recipe name.
      selectedRecipeId = null;
      recipeRows = [];
      closeCombo(pick, pickList);
      const detail = document.getElementById("recipe-detail");
      if (detail && !recipeNamePlain(pick.value) && !recipeEnsureBusy) detail.textContent = "";
      else if (detail && recipeNamePlain(pick.value) && !recipeEnsureBusy && !isRecipeStatusMessage(detail.textContent)) {
        detail.textContent = "";
      }
      searchRecipesWithoutCountry();
    }
  });
  country.addEventListener("blur", () => closeCombo(country, countryList));
  pick.addEventListener("focus", showAllRecipes);
  pick.addEventListener("click", showAllRecipes);
  pick.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeCombo(pick, pickList);
    if (event.key !== "Enter") return;
    event.preventDefault();
    const typed = pick.value.trim();
    const optionButtons = [...pickList.querySelectorAll("button:not(.combo-create-btn)")];
    const exactBtn = optionButtons.find((btn) => btn.textContent === typed);
    const button = exactBtn || (optionButtons.length === 1 ? optionButtons[0] : null);
    if (button && findRecipeByTypedName(button.textContent)) {
      rememberRecipeChoice(button.textContent);
      pick.value = recipeLabel(findRecipeByTypedName(button.textContent) || { name: recipeNamePlain(button.textContent) });
      closeCombo(pick, pickList);
      showSelectedRecipe();
      return;
    }
    closeCombo(pick, pickList);
    if (!recipeHasSubstringMatch(typed)) {
      startCreateRecipe(typed);
      return;
    }
    showRecipeSearchStatus(typed);
  });
  pick.addEventListener("input", () => {
    if (!hasCountry()) searchRecipesWithoutCountry();
    else {
      filterRecipes();
      showRecipeSearchStatus(pick.value);
    }
  });
  pick.addEventListener("blur", () => {
    closeCombo(pick, pickList);
    const typed = pick.value.trim();
    if (!typed || findRecipeByTypedName(typed)) return;
    if (!recipeHasSubstringMatch(typed)) {
      // Blur with no list hit → ensure/search/fill (雞腿便當 flow).
      if (recipeEnsureBusy) {
        recipeEnsureFollowUp = { name: recipeNamePlain(typed), forceCreate: true };
        const detail = document.getElementById("recipe-detail");
        if (detail) detail.textContent = uiText("recipeEnsuring");
        return;
      }
      ensureRecipeFromInput({ name: typed, forceCreate: true }).catch((err) => {
        const box = document.getElementById("recipe-detail");
        if (box) box.textContent = formatApiError(err) || uiText("recipeEnsureFailed");
      });
      return;
    }
    showRecipeSearchStatus(typed);
  });
}

async function loadRecords(opts = {}) {
  const data = await api("/api/records");
  const box = document.getElementById("records");
  renderTrend(data.trend);
  if (!data.records.length) {
    box.textContent = "尚無紀錄";
    renderComplexionHistory([]);
    return;
  }
  const latest = data.records[0];
  const oh = latest.organ_health || {};
  const su = oh.stool_urine || {};
  const dmFindings = findingsFromDayModalities(oh);
  const circleFindings = Array.isArray(su.findings) ? su.findings.slice() : [];
  const textBits = [latest.symptoms, latest.discomfort].filter(Boolean);
  // Keep today's modality findings; do not replace them with only symptoms.
  const mergedFindings = (dmFindings.length ? dmFindings : circleFindings).concat(textBits);
  const findings = opts.preserveFindings ? undefined : mergedFindings;
  if (!opts.skipResult) {
    const payload = {
      scores: latest,
      patterns: latest,
      overlays: latest.overlays || {},
      pattern_scores: latest.pattern_scores,
      organ_health: latest.organ_health,
      stool: su.stool || null,
      urine: su.urine || null,
      findings: findings || textBits,
      diet_advice: latest.diet_advice,
      diet_url: latest.diet_url,
      diet_video_url: latest.diet_video_url,
      diet_query: latest.diet_query,
      diet_video_query: latest.diet_video_query,
      acupoint_url: latest.acupoint_url,
      acupoint_video_url: latest.acupoint_video_url,
      acupoint_query: latest.acupoint_query,
      acupoint_video_query: latest.acupoint_video_query,
      color_label: latest.color_label
        || [latest.face_color, latest.lip_color, latest.tongue_body_color, latest.tongue_coat_color].filter(Boolean).join("／"),
      face_grid: latest.face_grid,
      tongue_grid: latest.tongue_grid,
      complexion: (latest.face_grid && latest.face_grid.complexion) || {
        bias: latest.complexion_label,
        hex: latest.complexion_hex,
      },
      disclaimer: "以下為今日累積檢測（同一天內換拍只更新該項）。教學示範，非診斷。",
    };
    renderResult(payload);
  } else {
    // Live shot just rendered — refresh persistent day panel from DB merge.
    updateCircleLinesFromResult({
      organ_health: latest.organ_health,
      stool: su.stool || null,
      urine: su.urine || null,
      findings: mergedFindings,
    });
    renderCircleResultPanel();
  }
  renderComplexionHistory(data.records);
  const shownOrgans = visibleOrgans();
  const head = ["日期", "狀況", ...shownOrgans.map((o) => o.name), "食療"].map((h) => `<th>${h}</th>`).join("");
  const rows = data.records
    .map((r) => {
      const date = (r.record_date || "").toString().replace("T", " ").slice(0, 19);
      const cells = shownOrgans.map((o) => {
        const pattern = patternLabel(r[o.score], r[o.pattern]);
        return `<td>${shownScore(r[o.score])} ${pattern}</td>`;
      }).join("");
      return `<tr><td>${date}</td><td>${(r.symptoms || "").slice(0, 12)}</td>${cells}<td>${withoutUterusStatement(r.diet_advice || "")}</td></tr>`;
    })
    .join("");
  box.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

async function initMealCalendar() {
  const dateInput = document.getElementById("meal-date");
  if (!dateInput) return;
  if (!mealSelectedDate) mealSelectedDate = todayIsoDate();
  dateInput.value = mealSelectedDate;
  const parts = mealSelectedDate.split("-").map(Number);
  mealViewYear = parts[0];
  mealViewMonth = parts[1];
  bindMealCalendarControls();
  await refreshMealViews();
}

function bindMealCalendarControls() {
  const dateInput = document.getElementById("meal-date");
  const prev = document.getElementById("meal-month-prev");
  const next = document.getElementById("meal-month-next");
  const addBtn = document.getElementById("meal-add-btn");
  if (dateInput && !dateInput.dataset.bound) {
    dateInput.dataset.bound = "1";
    dateInput.addEventListener("change", async () => {
      if (!dateInput.value) return;
      mealSelectedDate = dateInput.value;
      const parts = mealSelectedDate.split("-").map(Number);
      mealViewYear = parts[0];
      mealViewMonth = parts[1];
      await refreshMealViews();
    });
  }
  if (prev && !prev.dataset.bound) {
    prev.dataset.bound = "1";
    prev.addEventListener("click", async () => {
      mealViewMonth -= 1;
      if (mealViewMonth < 1) {
        mealViewMonth = 12;
        mealViewYear -= 1;
      }
      await loadMealMonth();
      renderMealCalendarGrid();
      renderMealNutrientTrend(mealMonthData);
    });
  }
  if (next && !next.dataset.bound) {
    next.dataset.bound = "1";
    next.addEventListener("click", async () => {
      mealViewMonth += 1;
      if (mealViewMonth > 12) {
        mealViewMonth = 1;
        mealViewYear += 1;
      }
      await loadMealMonth();
      renderMealCalendarGrid();
      renderMealNutrientTrend(mealMonthData);
    });
  }
  if (addBtn && !addBtn.dataset.bound) {
    addBtn.dataset.bound = "1";
    addBtn.addEventListener("click", () => addSelectedRecipeMeal());
  }
  const stepsSave = document.getElementById("meal-steps-save-btn");
  if (stepsSave && !stepsSave.dataset.bound) {
    stepsSave.dataset.bound = "1";
    stepsSave.addEventListener("click", () => saveMealActualSteps());
  }
}

async function saveMealActualSteps() {
  const msg = document.getElementById("meal-steps-msg");
  const input = document.getElementById("meal-steps-input");
  if (!input) return;
  if (typeof getToken === "function" && !getToken()) {
    if (msg) {
      msg.textContent = uiText("mealStepsNeedLogin");
      msg.className = "status err";
    }
    return;
  }
  const raw = String(input.value || "").trim();
  if (raw === "" || Number.isNaN(Number(raw))) {
    if (msg) {
      msg.textContent = uiText("mealStepsManualLabel");
      msg.className = "status err";
    }
    return;
  }
  try {
    const data = await api("/api/activity/today", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: mealSelectedDate,
        steps: Math.round(Number(raw)),
        source: "web_manual",
      }),
    });
    if (data.day) mealDayData = data.day;
    if (msg) {
      msg.textContent = uiText("mealStepsSaved");
      msg.className = "status ok";
    }
    renderMealDay();
  } catch (err) {
    if (msg) {
      msg.textContent = formatApiError(err);
      msg.className = "status err";
    }
  }
}

async function refreshMealViews() {
  await Promise.all([loadMealMonth(), loadMealDay()]);
  renderMealCalendarGrid();
  renderMealDay();
}

async function loadMealMonth() {
  if (!mealViewYear || !mealViewMonth) return;
  mealMonthData = await api(`/api/meals/month?year=${mealViewYear}&month=${mealViewMonth}`);
  const label = document.getElementById("meal-month-label");
  if (label) label.textContent = `${mealViewYear}-${pad2(mealViewMonth)}`;
}

async function loadMealDay() {
  if (!mealSelectedDate) return;
  mealDayData = await api(`/api/meals/day?date=${encodeURIComponent(mealSelectedDate)}`);
}

function renderMealCalendarGrid() {
  const grid = document.getElementById("meal-calendar-grid");
  if (!grid || !mealMonthData) return;
  const dows = ["一", "二", "三", "四", "五", "六", "日"];
  const days = mealMonthData.days || [];
  const first = new Date(mealViewYear, mealViewMonth - 1, 1);
  let startPad = (first.getDay() + 6) % 7; // Monday-first
  const byDate = {};
  days.forEach((d) => { byDate[d.date] = d; });
  const today = todayIsoDate();
  const frag = document.createDocumentFragment();
  dows.forEach((name) => {
    const el = document.createElement("div");
    el.className = "meal-cal-dow";
    el.textContent = name;
    frag.appendChild(el);
  });
  for (let i = 0; i < startPad; i += 1) {
    const pad = document.createElement("div");
    pad.className = "meal-cal-pad";
    frag.appendChild(pad);
  }
  const lastDay = days.length || new Date(mealViewYear, mealViewMonth, 0).getDate();
  for (let day = 1; day <= lastDay; day += 1) {
    const iso = `${mealViewYear}-${pad2(mealViewMonth)}-${pad2(day)}`;
    const info = byDate[iso] || { meal_count: 0, kcal_pct: null, has_meals: false };
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "meal-cal-cell";
    if (iso === mealSelectedDate) btn.classList.add("is-selected");
    if (iso === today) btn.classList.add("is-today");
    if (info.has_meals) btn.classList.add("has-meals");
    const num = document.createElement("span");
    num.className = "meal-cal-daynum";
    num.textContent = String(day);
    btn.appendChild(num);
    if (info.has_meals) {
      const meta = document.createElement("span");
      meta.className = "meal-cal-meta";
      const pct = info.kcal_pct == null ? "" : uiText("mealKcalPct").replace("{n}", String(info.kcal_pct));
      meta.textContent = [uiText("mealCountLabel").replace("{n}", String(info.meal_count)), pct].filter(Boolean).join(" · ");
      btn.appendChild(meta);
    }
    btn.addEventListener("click", async () => {
      mealSelectedDate = iso;
      const dateInput = document.getElementById("meal-date");
      if (dateInput) dateInput.value = iso;
      await loadMealDay();
      renderMealCalendarGrid();
      renderMealDay();
    });
    frag.appendChild(btn);
  }
  grid.replaceChildren(frag);
}

function renderMealDay() {
  const list = document.getElementById("meal-list");
  const meta = document.getElementById("meal-day-meta");
  const empty = document.getElementById("meal-chart-empty");
  if (!list || !mealDayData) return;
  const meals = mealDayData.meals || [];
  if (meta) {
    meta.textContent = uiText("mealTargetMeta")
      .replace("{band}", mealDayData.age_band || "")
      .replace("{gender}", mealDayData.gender || "");
  }
  if (!meals.length) {
    list.textContent = uiText("mealEmptyDay");
  } else {
    const frag = document.createDocumentFragment();
    meals.forEach((meal) => {
      const row = document.createElement("div");
      row.className = "meal-item";
      const main = document.createElement("div");
      main.className = "meal-item-main";
      const kcal = meal.nutrients && meal.nutrients["每日熱量(大卡)"];
      main.textContent = `${meal.meal_slot} · ${meal.recipe_name || ""} × ${meal.servings}`
        + (kcal != null ? ` · ${Math.round(kcal)} kcal` : "");
      row.appendChild(main);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "ghost";
      remove.textContent = uiText("mealRemove");
      remove.addEventListener("click", async () => {
        try {
          const data = await api(`/api/meals/${meal.meal_id}?date=${encodeURIComponent(mealSelectedDate)}`, {
            method: "DELETE",
          });
          mealDayData = data.day;
          const mealMsg = document.getElementById("meal-msg");
          if (mealMsg) {
            mealMsg.textContent = uiText("mealDeleted");
            mealMsg.className = "status ok";
          }
          await loadMealMonth();
          renderMealCalendarGrid();
          renderMealDay();
        } catch (err) {
          const mealMsg = document.getElementById("meal-msg");
          if (mealMsg) {
            mealMsg.textContent = formatApiError(err);
            mealMsg.className = "status err";
          }
        }
      });
      row.appendChild(remove);
      frag.appendChild(row);
    });
    list.replaceChildren(frag);
  }
  if (empty) {
    const hasTargets = mealDayData && mealDayData.targets && Object.keys(mealDayData.targets).length;
    empty.classList.toggle("hidden", Boolean(hasTargets) || meals.length > 0);
    empty.textContent = typeof Chart === "undefined"
      ? uiText("mealChartMissingLib")
      : uiText("mealChartEmpty");
  }
  renderMealSteps(mealDayData);
  renderMealCharts(mealDayData);
  renderMealNutrientTrend(mealMonthData);
}

function formatStepsSource(source) {
  const key = String(source || "").toLowerCase();
  if (key === "android_health_connect") return uiText("mealStepsSourceHc");
  if (key === "android_sensor") return uiText("mealStepsSourceSensor");
  if (key === "web_manual" || key === "manual") return uiText("mealStepsSourceManual");
  return source || uiText("mealStepsSourceManual");
}

function renderMealSteps(day) {
  const kcalEl = document.getElementById("meal-steps-kcal");
  const summaryEl = document.getElementById("meal-steps-summary");
  const remainingEl = document.getElementById("meal-steps-remaining");
  const burnedEl = document.getElementById("meal-steps-burned");
  const formulaEl = document.getElementById("meal-steps-formula");
  const intakeBar = document.getElementById("meal-kcal-intake-bar");
  const burnBar = document.getElementById("meal-kcal-burn-bar");
  const intakeLabelEl = document.getElementById("meal-kcal-intake-label");
  const burnLabelEl = document.getElementById("meal-kcal-burn-label");
  const burnLabelAboveEl = document.getElementById("meal-kcal-burn-label-above");
  const needMark = document.getElementById("meal-kcal-need-mark");
  const needLabel = document.getElementById("meal-kcal-ruler-need");
  const netEl = document.getElementById("meal-kcal-net");
  const input = document.getElementById("meal-steps-input");
  if (!summaryEl) return;

  const intake = Number(
    day && day.calories_intake != null
      ? day.calories_intake
      : (day && day.totals && day.totals["每日熱量(大卡)"]) || 0
  );
  const recommended = Number(day && day.recommended_steps != null ? day.recommended_steps : 0);
  const k = Number(day && day.kcal_per_step != null ? day.kcal_per_step : 0.04);
  const minS = Number(day && day.steps_min != null ? day.steps_min : 3000);
  const maxS = Number(day && day.steps_max != null ? day.steps_max : 15000);
  const actual = day && day.actual_steps != null ? Number(day.actual_steps) : null;
  const burned = day && day.burned_kcal != null ? Number(day.burned_kcal) : null;
  const burnedSafe = burned != null && !Number.isNaN(burned) ? Math.max(0, burned) : 0;
  const gap = actual == null
    ? null
    : (day.steps_gap != null ? Number(day.steps_gap) : actual - recommended);
  const targetRaw = day && day.calories_target != null
    ? Number(day.calories_target)
    : (day && day.targets && day.targets["每日熱量(大卡)"] != null
      ? Number(day.targets["每日熱量(大卡)"])
      : null);
  const targetNum = targetRaw != null && !Number.isNaN(targetRaw) && targetRaw > 0
    ? targetRaw
    : null;
  const target = targetNum != null ? Math.round(targetNum) : "—";
  const surplusRaw = day && day.calories_surplus != null
    ? Number(day.calories_surplus)
    : (targetNum != null ? Math.round(intake - targetNum) : null);
  const surplus = surplusRaw == null || Number.isNaN(surplusRaw)
    ? "—"
    : (surplusRaw > 0 ? `+${Math.round(surplusRaw)}` : String(Math.round(surplusRaw)));
  const net = Math.round((intake - burnedSafe) * 10) / 10;

  if (kcalEl) {
    if (intake > 0) {
      kcalEl.textContent = uiText("mealStepsKcal")
        .replace("{intake}", String(Math.round(intake)))
        .replace("{target}", String(target))
        .replace("{surplus}", surplus)
        .replace("{recommended}", String(recommended));
    } else {
      kcalEl.textContent = uiText("mealStepsKcalEmpty");
    }
  }

  // Daily need spans ~half the track; remaining half absorbs intake overflow.
  // Yellow = intake L→R. Green burn from yellow tip R→L as overlay. Never >100%.
  const halfScale = targetNum != null ? targetNum * 2 : null;
  const scale = Math.max(halfScale || 0, intake, burnedSafe, 1);
  const intakePct = Math.min(100, Math.max(0, (100 * intake) / scale));
  const burnPctRaw = Math.max(0, (100 * burnedSafe) / scale);
  const burnWidthPct = Math.min(burnPctRaw, intakePct);
  const burnLeftPct = Math.max(0, intakePct - burnWidthPct);
  const needPct = targetNum != null
    ? Math.min(100, Math.max(0, (100 * targetNum) / scale))
    : 50;
  if (intakeBar) intakeBar.style.width = `${intakePct}%`;
  if (burnBar) {
    burnBar.style.left = `${burnLeftPct}%`;
    burnBar.style.width = `${burnWidthPct}%`;
  }
  if (intakeLabelEl) {
    intakeLabelEl.textContent = intake > 0
      ? uiText("mealKcalBarIntake").replace("{n}", String(Math.round(intake)))
      : "";
    intakeLabelEl.style.display = intake > 0 ? "" : "none";
  }
  const burnText = burnedSafe > 0
    ? uiText("mealKcalBarBurn").replace("{n}", String(Math.round(burnedSafe)))
    : "";
  if (burnLabelEl) {
    burnLabelEl.textContent = burnText;
    // Measure after layout: if green bar is too narrow for the label, lift it above.
    burnLabelEl.style.display = burnedSafe > 0 ? "" : "none";
  }
  if (burnLabelAboveEl) {
    burnLabelAboveEl.textContent = burnText;
    burnLabelAboveEl.hidden = true;
  }
  const placeBurnLabel = () => {
    if (!burnedSafe || burnWidthPct <= 0) {
      if (burnLabelEl) burnLabelEl.style.display = "none";
      if (burnLabelAboveEl) burnLabelAboveEl.hidden = true;
      return;
    }
    const pad = 8;
    const barW = burnBar ? burnBar.clientWidth : 0;
    const textW = burnLabelEl ? burnLabelEl.scrollWidth : 0;
    const fitsInside = barW >= textW + pad && textW > 0;
    if (burnLabelEl) burnLabelEl.style.display = fitsInside ? "" : "none";
    if (burnLabelAboveEl) {
      if (fitsInside) {
        burnLabelAboveEl.hidden = true;
      } else {
        burnLabelAboveEl.hidden = false;
        burnLabelAboveEl.style.left = `${burnLeftPct + burnWidthPct / 2}%`;
      }
    }
  };
  requestAnimationFrame(placeBurnLabel);
  if (needMark) {
    needMark.style.left = `${needPct}%`;
    needMark.style.display = targetNum != null ? "" : "none";
  }
  if (needLabel) {
    needLabel.textContent = targetNum != null
      ? uiText("mealKcalRulerNeed").replace("{target}", String(target))
      : "— kcal";
    needLabel.style.left = `${needPct}%`;
  }

  if (netEl) {
    netEl.classList.remove("is-over", "is-under", "is-equal");
    if (!(intake > 0 || burnedSafe > 0)) {
      netEl.textContent = uiText("mealKcalNetEmpty");
    } else if (targetNum == null) {
      netEl.textContent = uiText("mealKcalNetNoTarget").replace("{net}", String(net));
    } else {
      const diff = Math.round((net - targetNum) * 10) / 10;
      if (diff > 0) {
        netEl.classList.add("is-over");
        netEl.textContent = uiText("mealKcalNetOver")
          .replace("{net}", String(net))
          .replace("{target}", String(target))
          .replace("{over}", String(diff));
      } else if (diff < 0) {
        netEl.classList.add("is-under");
        netEl.textContent = uiText("mealKcalNetUnder")
          .replace("{net}", String(net))
          .replace("{target}", String(target))
          .replace("{under}", String(Math.abs(diff)));
      } else {
        netEl.classList.add("is-equal");
        netEl.textContent = uiText("mealKcalNetEqual")
          .replace("{net}", String(net))
          .replace("{target}", String(target));
      }
    }
  }

  if (actual == null) {
    summaryEl.textContent = uiText("mealStepsNoActual")
      .replace("{recommended}", String(recommended));
  } else {
    const gapText = gap > 0 ? `+${gap}` : String(gap);
    summaryEl.textContent = uiText("mealStepsSummary")
      .replace("{actual}", String(actual))
      .replace("{recommended}", String(recommended))
      .replace("{gap}", gapText);
  }

  if (remainingEl) {
    if (actual == null) {
      remainingEl.textContent = uiText("mealStepsRemainingUnknown")
        .replace("{recommended}", String(recommended));
    } else {
      const remain = recommended - actual;
      if (remain > 0) {
        remainingEl.textContent = uiText("mealStepsRemainingNeed").replace("{n}", String(remain));
      } else if (remain < 0) {
        remainingEl.textContent = uiText("mealStepsRemainingDone").replace("{n}", String(-remain));
      } else {
        remainingEl.textContent = uiText("mealStepsRemainingExact");
      }
    }
  }

  if (burnedEl) {
    if (burned == null) {
      burnedEl.textContent = uiText("mealStepsBurnedNone");
    } else {
      const delta = Math.round((burned - intake) * 10) / 10;
      const deltaText = delta > 0 ? `+${delta}` : String(delta);
      burnedEl.textContent = uiText("mealStepsBurned")
        .replace("{burned}", String(burned))
        .replace("{source}", formatStepsSource(day && day.steps_source))
        .replace("{delta}", deltaText);
    }
  }

  if (formulaEl) {
    formulaEl.textContent = uiText("mealStepsFormula")
      .replace("{k}", String(k))
      .replace("{min}", String(minS))
      .replace("{max}", String(maxS));
  }

  if (input && document.activeElement !== input) {
    input.value = actual != null ? String(actual) : "";
  }
}

function destroyMealChart(kind) {
  if (kind === "intake" && mealIntakeChart) {
    mealIntakeChart.destroy();
    mealIntakeChart = null;
  } else if (kind === "surplus" && mealSurplusChart) {
    mealSurplusChart.destroy();
    mealSurplusChart = null;
  } else if (kind === "trend" && mealNutrientTrendChart) {
    mealNutrientTrendChart.destroy();
    mealNutrientTrendChart = null;
  }
}

function renderMealCharts(day) {
  const intakeCanvas = document.getElementById("meal-intake-chart");
  destroyMealChart("intake");
  destroyMealChart("surplus");
  if (typeof Chart === "undefined") return;
  if (!intakeCanvas) return;
  const keys = (day && day.nutrient_keys) || [];
  if (!keys.length) return;
  const allLabels = (day.chart_labels && day.chart_labels.length === keys.length)
    ? day.chart_labels
    : keys.map(shortNutrientLabel);
  const totals = (day && day.totals) || {};
  const targets = (day && day.targets) || {};
  // Daily bar chart: intake vs age/gender targets (% keeps mixed units readable).
  const labels = [];
  const intakePct = [];
  const targetPct = [];
  keys.forEach((key, index) => {
    const target = Number(targets[key] || 0);
    if (!(target > 0)) return;
    const total = Number(totals[key] || 0);
    labels.push(allLabels[index]);
    intakePct.push(Math.round((1000 * total) / target) / 10);
    targetPct.push(100);
  });
  if (!labels.length) return;
  mealIntakeChart = new Chart(intakeCanvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: uiText("mealIntakeSeries"),
          data: intakePct,
          backgroundColor: "rgba(42, 111, 151, 0.65)",
        },
        {
          label: uiText("mealTargetSeries"),
          data: targetPct,
          backgroundColor: "rgba(120, 120, 120, 0.35)",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: "#000000",
      plugins: {
        title: {
          display: true,
          text: uiText("mealIntakeTitle"),
          color: "#000000",
        },
        legend: {
          display: true,
          labels: { color: "#000000" },
        },
        tooltip: {
          callbacks: {
            label(ctx) {
              const value = ctx.parsed && ctx.parsed.y != null ? ctx.parsed.y : ctx.raw;
              return `${ctx.dataset.label}: ${value}%`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#000000",
            maxRotation: 60,
            minRotation: 30,
            font: { size: 10 },
          },
          grid: { color: "rgba(0, 0, 0, 0.08)" },
          border: { color: "#000000" },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "%", color: "#000000" },
          ticks: {
            color: "#000000",
            callback: (value) => `${value}%`,
          },
          grid: { color: "rgba(0, 0, 0, 0.08)" },
          border: { color: "#000000" },
        },
      },
    },
    plugins: [MEAL_CHART_WHITE_BG],
  });
}

function renderMealNutrientTrend(month) {
  // Prefer dedicated canvas; fall back to former surplus canvas.
  const canvas = document.getElementById("meal-nutrient-trend-chart")
    || document.getElementById("meal-surplus-chart");
  destroyMealChart("trend");
  destroyMealChart("surplus");
  if (typeof Chart === "undefined" || !canvas) return;
  const keys = (month && month.nutrient_keys) || (mealDayData && mealDayData.nutrient_keys) || [];
  const targets = (month && month.targets) || (mealDayData && mealDayData.targets) || {};
  const allLabels = (month && month.chart_labels && month.chart_labels.length === keys.length)
    ? month.chart_labels
    : keys.map(shortNutrientLabel);
  const daysWithMeals = ((month && month.days) || []).filter((d) => d && d.has_meals);
  if (!keys.length || !daysWithMeals.length) return;
  const labels = daysWithMeals.map((d) => {
    const iso = String(d.date || "");
    const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return `${m[2]}/${m[3]}`;
    return iso || d.date;
  });
  const datasets = [];
  let maxAbs = 0;
  keys.forEach((key, index) => {
    const target = Number(targets[key] || 0);
    if (!(target > 0)) return;
    const color = MEAL_TREND_COLORS[index % MEAL_TREND_COLORS.length];
    const pointStyle = MEAL_TREND_POINT_STYLES[index % MEAL_TREND_POINT_STYLES.length];
    // % of target keeps mixed units comparable; 0 = meeting daily standard.
    const data = daysWithMeals.map((d) => {
      const surplus = d.surplus && d.surplus[key];
      const delta = (surplus != null && surplus !== "")
        ? Number(surplus)
        : Number((d.totals && d.totals[key]) || 0) - target;
      const pct = Math.round((1000 * delta) / target) / 10;
      if (Number.isFinite(pct)) maxAbs = Math.max(maxAbs, Math.abs(pct));
      return pct;
    });
    datasets.push({
      label: allLabels[index] || shortNutrientLabel(key),
      data,
      showLine: true,
      tension: 0.35,
      pointStyle,
      pointRadius: 5,
      pointHoverRadius: 7,
      pointBorderWidth: 1.5,
      borderWidth: 2,
      borderColor: color,
      backgroundColor: color,
      spanGaps: true,
    });
  });
  if (!datasets.length) return;
  const axisBound = Math.max(20, Math.ceil(maxAbs / 10) * 10);
  mealNutrientTrendChart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: "#000000",
      plugins: {
        title: {
          display: true,
          text: uiText("mealNutrientTrendTitle"),
          color: "#000000",
        },
        legend: {
          display: true,
          position: "bottom",
          labels: {
            color: "#000000",
            usePointStyle: true,
            boxWidth: 10,
            font: { size: 10 },
          },
        },
        tooltip: {
          callbacks: {
            label(ctx) {
              const value = ctx.parsed && ctx.parsed.y != null ? ctx.parsed.y : ctx.raw;
              const sign = value > 0 ? "+" : "";
              return `${ctx.dataset.label}: ${sign}${value}%`;
            },
          },
        },
      },
      scales: {
        x: {
          title: {
            display: true,
            text: uiText("mealNutrientTrendX"),
            color: "#000000",
          },
          ticks: { color: "#000000" },
          grid: { color: "rgba(0, 0, 0, 0.08)" },
          border: { color: "#000000" },
        },
        y: {
          min: -axisBound,
          max: axisBound,
          title: {
            display: true,
            text: uiText("mealNutrientTrendY"),
            color: "#000000",
          },
          ticks: {
            color: "#000000",
            callback: (value) => `${value}%`,
          },
          grid: {
            color: (ctx) => (ctx.tick.value === 0 ? "#000000" : "rgba(0, 0, 0, 0.08)"),
            lineWidth: (ctx) => (ctx.tick.value === 0 ? 2 : 1),
          },
          border: { color: "#000000" },
        },
      },
    },
    plugins: [MEAL_CHART_WHITE_BG],
  });
}

async function addSelectedRecipeMeal() {
  const mealMsg = document.getElementById("meal-msg");
  const pick = document.getElementById("recipe-name");
  const label = (pick && pick.value.trim()) || "";
  const row = recipeRows.find((item) => String(item.id) === String(selectedRecipeId) && recipeLabel(item) === label)
    || recipeRows.find((item) => recipeLabel(item) === label)
    || findRecipeByTypedName(label);
  if (!row || row.id == null || row.id === "") {
    if (mealMsg) {
      mealMsg.textContent = uiText("mealPickRecipeFirst");
      mealMsg.className = "status err";
    }
    return;
  }
  const slot = (document.getElementById("meal-slot") || {}).value || "午餐";
  const servings = (document.getElementById("meal-servings") || {}).value || "1";
  const dateInput = document.getElementById("meal-date");
  const mealDate = (dateInput && dateInput.value) || mealSelectedDate || todayIsoDate();
  try {
    const data = await api("/api/meals", {
      method: "POST",
      body: formBody({
        recipe_id: String(row.id),
        meal_date: mealDate,
        meal_slot: slot,
        servings: String(servings),
        replace_slot: "1",
        lang: getUiLang(),
      }),
    });
    mealSelectedDate = mealDate;
    mealDayData = data.day;
    if (mealMsg) {
      mealMsg.textContent = uiText("mealAdded");
      mealMsg.className = "status ok";
    }
    const parts = mealSelectedDate.split("-").map(Number);
    mealViewYear = parts[0];
    mealViewMonth = parts[1];
    await loadMealMonth();
    renderMealCalendarGrid();
    renderMealDay();
  } catch (err) {
    if (mealMsg) {
      mealMsg.textContent = formatApiError(err);
      mealMsg.className = "status err";
    }
  }
}

function renderTrend(trend) {
  const empty = document.getElementById("trend-empty");
  const canvas = document.getElementById("trend-chart");
  const trendOrgans = ((trend && trend.organs) || []).filter((org) => showsFemaleOrgans() || org.key !== "uterus");
  const hasPoints = trendOrgans.some((org) => (org.points || []).length);
  if (empty) empty.classList.toggle("hidden", hasPoints);
  if (typeof Chart === "undefined" || !canvas) return;
  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }
  if (!hasPoints) return;
  const labels = (trendOrgans[0].points || []).map((pt) => (pt.t || "").replace("T", " ").slice(0, 16));
  trendChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: trendOrgans.map((org) => ({
        label: org.label,
        data: (org.points || []).map((pt) => pt.y),
        borderColor: org.color,
        backgroundColor: org.color,
        pointStyle: TREND_POINT_STYLE[org.marker] || "circle",
        pointRadius: 6,
        pointHoverRadius: 8,
        borderWidth: 2,
        tension: 0.35,
        spanGaps: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      color: "#000000",
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { color: "#000000", usePointStyle: true, boxWidth: 10 },
        },
        title: {
          display: true,
          text: trend.y_label || "分數趨勢",
          color: "#000000",
        },
      },
      scales: {
        x: {
          title: { display: true, text: "時間", color: "#000000" },
          ticks: { color: "#000000" },
          grid: { color: "rgba(0, 0, 0, 0.08)" },
          border: { color: "#000000" },
        },
        y: {
          min: trend.y_min || 1,
          max: trend.y_max || 10,
          ticks: { stepSize: 1, color: "#000000" },
          title: { display: true, text: "分數", color: "#000000" },
          grid: { color: "rgba(0, 0, 0, 0.08)" },
          border: { color: "#000000" },
        },
      },
    },
    plugins: [MEAL_CHART_WHITE_BG],
  });
}

function silentDeviceHint() {
  try {
    const ua = navigator.userAgent || "";
    const platform = navigator.platform || "";
    const touch = navigator.maxTouchPoints || 0;
    return `${ua} | ${platform} | touch:${touch}`;
  } catch (_err) {
    return navigator.userAgent || "";
  }
}

async function sendRecord(extraShot) {
  camMsg.textContent = "傳送中…";
  const body = new FormData();
  body.append("symptoms", document.getElementById("symptoms").value);
  body.append("discomfort", document.getElementById("discomfort").value);
  body.append("color_temperature_k", "auto");
  body.append("device_hint", silentDeviceHint());
  if (extraShot) {
    const blob = await captureFrame(extraShot);
    if (!blob) throw new Error("無法擷取畫面");
    // Face/tongue may be re-sent later; stool/urine are analyze-only (no photo keep/display).
    if (!CIRCLE_SHOTS.has(extraShot)) {
      lastShots[extraShot] = blob;
    }
    if (extraShot === "face") {
      if (lastFacePreviewUrl && lastFacePreviewUrl.startsWith("blob:")) URL.revokeObjectURL(lastFacePreviewUrl);
      lastFacePreviewUrl = URL.createObjectURL(blob);
    }
    if (extraShot === "tongue") {
      if (lastTonguePreviewUrl && lastTonguePreviewUrl.startsWith("blob:")) URL.revokeObjectURL(lastTonguePreviewUrl);
      lastTonguePreviewUrl = URL.createObjectURL(blob);
    }
    body.append("shot_type", extraShot);
    body.append("image", blob, `${extraShot}.jpg`);
  }
  // Circle re-shot: only send this modality image (server keeps other day_modalities).
  // Re-attaching face/tongue re-runs heavy grids and can time out phones / slow web.
  if (!CIRCLE_SHOTS.has(extraShot)) {
    if (lastShots.face && extraShot !== "face") body.append("face", lastShots.face, "face.jpg");
    if (lastShots.tongue && extraShot !== "tongue") body.append("tongue", lastShots.tongue, "tongue.jpg");
  }
  const result = await api("/api/record", { method: "POST", body });
  camMsg.textContent = CIRCLE_SHOTS.has(extraShot)
    ? "已產生文字判斷（未存照片）"
    : "已寫入 health_records";
  camMsg.className = "status ok";
  // Stool/urine: never show captured image grids.
  if (CIRCLE_SHOTS.has(extraShot)) {
    if (result) {
      result.face_preview = result.face_preview || lastFacePreviewUrl;
      result.tongue_preview = result.tongue_preview || lastTonguePreviewUrl;
    }
  }
  renderResult(result);
  // Circle shots: keep live findings; do not let loadRecords wipe them.
  await loadRecords(CIRCLE_SHOTS.has(extraShot) ? { skipResult: true } : {});
  // Live /api/record wins for the modality just shot (DB same-second race / prior merge).
  if (CIRCLE_SHOTS.has(extraShot) && result) {
    const dm = ((result.organ_health || {}).day_modalities || {})[extraShot] || {};
    const note = result[extraShot] || dm.note || dm;
    const line = briefCircleLine(note, extraShot)
      || (dm.color_label
        ? `${extraShot === "urine" ? "尿尿" : "大便"}：${dm.color_label}`
        : "");
    if (line) {
      lastDayLines[extraShot] = line;
      renderCircleResultPanel();
    }
  }
}

const loginCaptcha = bindCaptchaControls();

document.getElementById("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  authMsg.textContent = "";
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: formBody({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
        ...authCaptchaFields(),
      }),
    });
    try {
      await api("/api/profile", {
        method: "POST",
        body: formBody({ preferred_lang: getUiLang() }),
      });
    } catch (_err) { /* ignore if profile incomplete */ }
    sessionStorage.removeItem("daily-asked");
    if (data.profile_complete === false) {
      window.location.href = "/profile";
      return;
    }
    await loadMe();
  } catch (err) {
    authMsg.textContent = formatApiError(err);
    authMsg.className = "status err";
    loginCaptcha.reload();
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
    const saved = await api("/api/profile", {
      method: "POST",
      body: formBody({
        height: document.getElementById("height").value,
        weight: document.getElementById("weight").value,
        ...selectedHealthFlags(document),
      }),
    });
    if (saved.user) fillProfile(saved.user);
    profileMsg.textContent = "已儲存";
    profileMsg.className = "status ok";
  } catch (err) {
    profileMsg.textContent = formatApiError(err);
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
const btnStool = document.getElementById("btn-stool");
const btnUrine = document.getElementById("btn-urine");
if (btnStool) btnStool.addEventListener("pointerenter", () => setAlignMode("stool"));
if (btnUrine) btnUrine.addEventListener("pointerenter", () => setAlignMode("urine"));
document.getElementById("btn-face").addEventListener("click", async () => {
  try {
    setAlignMode("face");
    await startCamera();
    if (!cameraIsLive()) return;
    await sendRecord("face");
  } catch (err) {
    camMsg.textContent = formatApiError(err);
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
    camMsg.textContent = formatApiError(err);
    camMsg.className = "status err";
  }
});
async function captureCircleShot(kind) {
  try {
    setAlignMode(kind);
    await startCamera();
    if (!cameraIsLive()) return;
    await sendRecord(kind);
  } catch (err) {
    camMsg.textContent = formatApiError(err);
    camMsg.className = "status err";
  }
}
if (btnStool) btnStool.addEventListener("click", () => captureCircleShot("stool"));
if (btnUrine) btnUrine.addEventListener("click", () => captureCircleShot("urine"));
document.getElementById("btn-save").addEventListener("click", async () => {
  try { await sendRecord(null); } catch (err) {
    camMsg.textContent = formatApiError(err);
    camMsg.className = "status err";
  }
});
document.getElementById("open-dialog").addEventListener("click", () => {
  document.getElementById("dialog-symptoms").value = document.getElementById("symptoms").value;
  document.getElementById("dialog-discomfort").value = document.getElementById("discomfort").value;
  dailyDialog.showModal();
});
const backupExportBtn = document.getElementById("backup-export-all");
if (backupExportBtn) {
  backupExportBtn.addEventListener("click", async () => {
    const msg = document.getElementById("backup-msg");
    try {
      const data = await api("/api/backup/export-all", { method: "POST" });
      if (msg) {
        msg.textContent = "已寫回本機：" + Object.values(data.files || {}).join("、");
        msg.className = "status ok";
      }
      await loadBackupStatus();
    } catch (err) {
      if (msg) {
        msg.textContent = formatApiError(err);
        msg.className = "status err";
      }
    }
  });
}
document.getElementById("daily-form").addEventListener("submit", (e) => {
  if (e.submitter && e.submitter.value === "ok") {
    document.getElementById("symptoms").value = document.getElementById("dialog-symptoms").value;
    document.getElementById("discomfort").value = document.getElementById("dialog-discomfort").value;
  }
});

const updateHomeBmi = bindBmiInputs(
  document.getElementById("height"),
  document.getElementById("weight"),
  document.getElementById("bmi-live"),
);

bindUiLang(() => {
  if (appCard && !appCard.classList.contains("hidden")) {
    reloadRecipesForLanguage().catch((err) => {
      const detail = document.getElementById("recipe-detail");
      if (detail) detail.textContent = formatApiError(err);
    });
    if (mealDayData) renderMealDay();
    if (mealMonthData) renderMealCalendarGrid();
  }
});

checkMysql()
  .then(() => loadHealthFlagOptions())
  .then(() => fillHealthFlags(document, {}))
  .then(loadMe);
