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
/** Matches --align-* on #camera-stage (fractions of the stage). Video, yellow frame, dim hole, and capture share this box. */
const ALIGN_FRAMES = {
  face: { left: 0.275, top: 0.10, width: 0.45, height: 0.80, zoom: 2, yBias: 0 },
  tongue: { left: 0.36, top: 0.22, width: 0.28, height: 0.52, zoom: 3.7, yBias: 0.08 },
};
const ALIGN_HINTS = {
  face: "對準臉：髮際以下～下巴，兩耳以內",
  tongue: "對準舌：上緣對齊上排牙齒，舌體填滿黃框",
};
let alignMode = "face";
let lastFaceGrid = null;
let lastTongueGrid = null;
let complexionHistory = [];

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
let trendChart = null;
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
    mysqlStatus.textContent = data.mysql ? "MySQL 連線成功" : "MySQL 回應異常";
    mysqlStatus.className = data.mysql ? "status ok" : "status err";
  } catch (err) {
    mysqlStatus.textContent = "MySQL 尚未連上：" + formatApiError(err);
    mysqlStatus.className = "status err";
  }
}

function setBodyImage(kind) {
  currentBody = kind === "girl" ? "girl" : "boy";
  const img = document.getElementById("body-img");
  img.src = currentBody === "girl" ? "/media/girl-body.png" : "/media/boy-body.png";
  img.alt = currentBody === "girl" ? "女生五臟六腑圖" : "男生五臟六腑圖";
  if (lastResult) drawOrgans(lastResult);
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

/** Pixels shown inside the yellow face clip (2× CSS zoom + object-fit). Same window the guides divide into 12 cells. */
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

function captureFaceFrame() {
  const vw = video.videoWidth || 640;
  const vh = video.videoHeight || 480;
  const source = faceClipSource(vw, vh);
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
  const mode = kind === "tongue" ? "tongue" : "face";
  setAlignMode(mode);
  if (mode === "tongue") return captureTongueFrame();
  return captureFaceFrame();
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

function cellByPosition(cells, row, col) {
  return (cells || []).find((cell) => cell.row === row && cell.col === col);
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
  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      const cell = cellByPosition(grid.cells, row, col);
      const box = document.createElement("div");
      box.className = "face-cell" + (cell && cell.split ? " split" : "");
      if (!cell) {
        overlay.appendChild(box);
        continue;
      }
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
    }
  }
  const flagBox = document.getElementById("face-lab-flags");
  if (flagBox) {
    const flags = grid.flags || [];
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
        const tag = part.part === "upper" ? "上段肝膽" : "下段脾胃";
        return `<div><span class="swatch" style="background:${part.hex}"></span>${tag} ${part.hex} ${part.bias} → ${part.meaning}</div>`;
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

function renderTongueGrid(grid, previewUrl) {
  const wrap = document.getElementById("tongue-grid-wrap");
  if (!grid || !grid.cells) {
    wrap.classList.add("hidden");
    return;
  }
  lastTongueGrid = grid;
  wrap.classList.remove("hidden");
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
  if (result.face_preview) lastFacePreviewUrl = result.face_preview;
  if (result.tongue_preview) lastTonguePreviewUrl = result.tongue_preview;
  renderFaceGrid(result.face_grid, lastFacePreviewUrl);
  renderTongueGrid(result.tongue_grid, lastTonguePreviewUrl);
}

async function loadRecords() {
  const data = await api("/api/records");
  const box = document.getElementById("records");
  renderTrend(data.trend);
  if (!data.records.length) {
    box.textContent = "尚無紀錄";
    renderComplexionHistory([]);
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
    face_grid: latest.face_grid,
    tongue_grid: latest.tongue_grid,
    complexion: (latest.face_grid && latest.face_grid.complexion) || {
      bias: latest.complexion_label,
      hex: latest.complexion_hex,
    },
    disclaimer: "以下為最近一次 MySQL 紀錄。教學示範，非診斷。",
  });
  renderComplexionHistory(data.records);
  const head = ["日期", "狀況", ...organs.map((o) => o.name), "食療"].map((h) => `<th>${h}</th>`).join("");
  const rows = data.records
    .map((r) => {
      const date = (r.record_date || "").toString().replace("T", " ").slice(0, 19);
      const cells = organs.map((o) => {
        const pattern = Number(r[o.score]) >= 7 && (r[o.pattern] === "未定" || r[o.pattern] === "待觀察")
          ? "健康"
          : Number(r[o.score]) === 5 && r[o.pattern] === "未定" ? "待觀察" : (r[o.pattern] || "");
        return `<td>${r[o.score]} ${pattern}</td>`;
      }).join("");
      return `<tr><td>${date}</td><td>${(r.symptoms || "").slice(0, 12)}</td>${cells}<td>${r.diet_advice || ""}</td></tr>`;
    })
    .join("");
  box.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderTrend(trend) {
  const empty = document.getElementById("trend-empty");
  const canvas = document.getElementById("trend-chart");
  const organs = (trend && trend.organs) || [];
  const hasPoints = organs.some((org) => (org.points || []).length);
  if (empty) empty.classList.toggle("hidden", hasPoints);
  if (typeof Chart === "undefined" || !canvas) return;
  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }
  if (!hasPoints) return;
  const labels = (organs[0].points || []).map((pt) => (pt.t || "").replace("T", " ").slice(0, 16));
  trendChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: organs.map((org) => ({
        label: org.label,
        data: (org.points || []).map((pt) => pt.y),
        borderColor: org.color,
        backgroundColor: org.color,
        pointStyle: TREND_POINT_STYLE[org.marker] || "circle",
        pointRadius: 6,
        pointHoverRadius: 8,
        borderWidth: 2,
        tension: 0.15,
        spanGaps: true,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true, position: "bottom", labels: { usePointStyle: true, boxWidth: 10 } },
        title: { display: true, text: trend.y_label || "分數趨勢" },
      },
      scales: {
        x: { title: { display: true, text: "時間" } },
        y: {
          min: trend.y_min || 1,
          max: trend.y_max || 10,
          ticks: { stepSize: 1 },
          title: { display: true, text: "分數" },
        },
      },
    },
  });
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
    authMsg.textContent = formatApiError(err);
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

checkMysql()
  .then(() => loadHealthFlagOptions())
  .then(() => fillHealthFlags(document, {}))
  .then(loadMe);
