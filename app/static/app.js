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

function fillProfile(user) {
  document.getElementById("anon-id").textContent = user.user_id;
  document.getElementById("height").value = user.height ?? "";
  document.getElementById("weight").value = user.weight ?? "";
  document.getElementById("medical_history").value = user.medical_history ?? "";
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
    camMsg.textContent = "無法開啟相機：" + formatApiError(err);
    camMsg.className = "status err";
  }
}

function captureFrame() {
  const w = video.videoWidth || 640;
  const h = video.videoHeight || 480;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.translate(w, 0);
  ctx.scale(-1, 1);
  ctx.drawImage(video, 0, 0, w, h);
  ctx.restore();
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
          half.innerHTML = `<strong>8${tag}</strong> ${part.organs}<br>${part.bias}`;
          box.appendChild(half);
        });
      } else {
        box.innerHTML = `<strong>${cell.id}</strong> ${cell.organs}<br>${cell.name}<br>${cell.bias || ""}`;
      }
      overlay.appendChild(box);
    }
  }
  const complexion = grid.complexion || {};
  const now = document.getElementById("complexion-now");
  now.textContent = complexion.interpretation
    ? `臉色（${complexion.hex || ""} ${complexion.bias || ""} → ${complexion.pattern || ""}）：${complexion.interpretation}`
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
    card.innerHTML = `<div><span class="swatch" style="background:${cell.hex}"></span><b>第 ${cell.id} 格 ${cell.name}</b>（${cell.organs}）</div>
      <div>${cell.hex}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
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
    box.innerHTML = `<strong>${cell.label}</strong> ${cell.organs}<br>${cell.anatomy}<br>${cell.bias || ""}`;
    overlay.appendChild(box);
  });
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
    card.innerHTML = `<div><span class="swatch" style="background:${cell.hex}"></span><b>${cell.label} ${cell.organs}</b>（${cell.anatomy}）</div>
      <div>${cell.hex}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
      <div>${cell.reading || cell.bias || ""}</div>
      <div>${cell.interpretation || ""}</div>`;
    list.appendChild(card);
  });
  if (coating.bias) {
    const card = document.createElement("div");
    card.className = "face-cell-card";
    const hsv = coating.hsv || {};
    card.innerHTML = `<div><span class="swatch" style="background:${coating.hex}"></span><b>第六層 舌苔</b>（胃／全舌疊加）</div>
      <div>${coating.hex || ""}　H${hsv.hue ?? "–"} S${hsv.saturation ?? "–"} V${hsv.value ?? "–"}</div>
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
  renderFaceGrid(result.face_grid, lastFacePreviewUrl);
  renderTongueGrid(result.tongue_grid, lastTonguePreviewUrl);
}

async function loadRecords() {
  const data = await api("/api/records");
  const box = document.getElementById("records");
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
    if (extraShot === "face") {
      if (lastFacePreviewUrl) URL.revokeObjectURL(lastFacePreviewUrl);
      lastFacePreviewUrl = URL.createObjectURL(blob);
    }
    if (extraShot === "tongue") {
      if (lastTonguePreviewUrl) URL.revokeObjectURL(lastTonguePreviewUrl);
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
        medical_history: document.getElementById("medical_history").value,
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

document.getElementById("btn-face").addEventListener("click", async () => {
  try { await sendRecord("face"); } catch (err) {
    camMsg.textContent = formatApiError(err);
    camMsg.className = "status err";
  }
});
document.getElementById("btn-tongue").addEventListener("click", async () => {
  try { await sendRecord("tongue"); } catch (err) {
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

checkMysql().then(loadMe);
