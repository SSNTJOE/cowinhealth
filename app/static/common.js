function formatDetailItem(item) {
  if (item == null) return "";
  if (typeof item === "string") return item;
  if (typeof item !== "object") return String(item);
  const msg = typeof item.msg === "string" ? item.msg : "";
  const loc = Array.isArray(item.loc)
    ? item.loc.filter((part) => part !== "body" && part !== "query" && part !== "path").join(".")
    : "";
  if (msg && loc) return loc + "：" + msg;
  if (msg) return msg;
  if (loc) return loc;
  if (typeof item.detail === "string") return item.detail;
  return "";
}

function formatApiDetail(detail) {
  if (detail == null || detail === "") return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(formatDetailItem).filter(Boolean).join("；");
  }
  if (typeof detail === "object") {
    if (typeof detail.msg === "string" && detail.msg) return detail.msg;
    if (typeof detail.detail === "string") return detail.detail;
    if (Array.isArray(detail.detail) || (detail.detail && typeof detail.detail === "object")) {
      return formatApiDetail(detail.detail);
    }
    return formatDetailItem(detail);
  }
  return String(detail);
}

function formatApiError(err) {
  if (!err) return "請求失敗";
  if (typeof err === "string") return formatApiDetail(err) || err;
  if (err.detail) return formatApiDetail(err.detail) || "請求失敗";
  const message = formatApiDetail(err.message);
  return message || err.message || "請求失敗";
}

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "include", ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(formatApiDetail(data.detail) || "請求失敗");
  }
  return data;
}

function formBody(obj) {
  const body = new FormData();
  Object.entries(obj).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") body.append(key, value);
  });
  return body;
}

let CONDITION_OPTIONS = ["糖尿病", "中風", "痛風", "腎臟病", "肝病", "高血壓", "服用抗凝血劑"];
let ALLERGY_OPTIONS = ["蝦蟹", "芒果", "花生", "堅果", "雞蛋", "牛奶"];

async function loadHealthFlagOptions() {
  try {
    const data = await api("/api/flags");
    if (Array.isArray(data.conditions) && data.conditions.length) {
      CONDITION_OPTIONS = data.conditions;
    }
    if (Array.isArray(data.allergies) && data.allergies.length) {
      ALLERGY_OPTIONS = data.allergies;
    }
  } catch (_err) {
    /* keep defaults if Recipe.xls is unavailable */
  }
  return { conditions: CONDITION_OPTIONS, allergies: ALLERGY_OPTIONS };
}

function renderCheckboxes(container, options, selected) {
  if (!container) return;
  const picked = new Set(Array.isArray(selected) ? selected : []);
  container.innerHTML = options
    .map((label) => {
      const checked = picked.has(label) ? " checked" : "";
      return (
        '<label class="check"><input type="checkbox" value="' +
        label +
        '"' +
        checked +
        "> " +
        label +
        "</label>"
      );
    })
    .join("");
}

function fillHealthFlags(root, user) {
  const scope = root || document;
  renderCheckboxes(
    scope.querySelector("#conditions-group"),
    CONDITION_OPTIONS,
    user && user.conditions,
  );
  const allergyOpts =
    user && Array.isArray(user.allergy_options) && user.allergy_options.length
      ? user.allergy_options
      : ALLERGY_OPTIONS;
  renderCheckboxes(
    scope.querySelector("#allergies-group"),
    allergyOpts,
    user && user.allergies,
  );
}

function selectedHealthFlags(root) {
  const scope = root || document;
  const read = (selector) =>
    [...scope.querySelectorAll(selector + ' input[type="checkbox"]:checked')].map((el) => el.value);
  return {
    conditions_json: JSON.stringify(read("#conditions-group")),
    allergies_json: JSON.stringify(read("#allergies-group")),
  };
}

const HEALTHY_BMI_MIN = 18.5;
const HEALTHY_BMI_MAX = 24;
const HEALTHY_BMI_MAX_DISPLAY = 23.9;

function parsePositiveNumber(value) {
  const n = typeof value === "number" ? value : parseFloat(String(value).trim());
  return Number.isFinite(n) && n > 0 ? n : null;
}

function computeBmi(heightCm, weightKg) {
  const height = parsePositiveNumber(heightCm);
  const weight = parsePositiveNumber(weightKg);
  if (height == null || weight == null) return null;
  const meters = height / 100;
  if (meters <= 0) return null;
  return weight / (meters * meters);
}

function bmiCategoryTw(bmi) {
  if (bmi == null || !Number.isFinite(bmi)) return "";
  if (bmi < 18.5) return "過輕";
  if (bmi < 24) return "健康體重";
  if (bmi < 27) return "過重";
  if (bmi < 30) return "輕度肥胖";
  if (bmi < 35) return "中度肥胖";
  return "重度肥胖";
}

function healthyWeightRangeKg(heightCm) {
  const height = parsePositiveNumber(heightCm);
  if (height == null) return null;
  const h2 = (height * height) / 10000;
  const minKg = Math.round(HEALTHY_BMI_MIN * h2 * 10) / 10;
  const exclusiveKg = HEALTHY_BMI_MAX * h2;
  const maxKg = Math.round((Math.floor(exclusiveKg * 10 + 1e-8) / 10 - 0.1) * 10) / 10;
  if (!(minKg > 0) || !(maxKg >= minKg)) return null;
  return { min: minKg, max: maxKg };
}

function formatHealthyBmiReference(heightCm) {
  const range = healthyWeightRangeKg(heightCm);
  if (!range) return "";
  return (
    "參考：BMI " +
    HEALTHY_BMI_MIN.toFixed(1) +
    "–" +
    HEALTHY_BMI_MAX_DISPLAY.toFixed(1) +
    "，建議體重 " +
    range.min.toFixed(1) +
    "–" +
    range.max.toFixed(1) +
    " kg"
  );
}

function formatBmiDisplay(heightCm, weightKg) {
  const height = parsePositiveNumber(heightCm);
  if (height == null) return "";
  const ref = formatHealthyBmiReference(height);
  const bmi = computeBmi(height, weightKg);
  if (bmi == null) return "";
  const line = "BMI " + bmi.toFixed(1) + "（" + bmiCategoryTw(bmi) + "）";
  return ref ? line + "　" + ref : line;
}

function bodyKindFromGender(gender) {
  const value = String(gender || "").trim().toLowerCase();
  if (
    value === "female" ||
    value === "f" ||
    value === "girl" ||
    value === "woman" ||
    value === "女" ||
    value === "女生"
  ) {
    return "girl";
  }
  return "boy";
}

function bodyImageSrcFromGender(gender) {
  return bodyKindFromGender(gender) === "girl" ? "/media/girl-body.png" : "/media/boy-body.png";
}

function bindBmiInputs(heightInput, weightInput, outputEl) {
  if (!heightInput || !weightInput || !outputEl) return () => {};
  const update = () => {
    outputEl.textContent = formatBmiDisplay(heightInput.value, weightInput.value);
  };
  heightInput.addEventListener("input", update);
  weightInput.addEventListener("input", update);
  update();
  return update;
}
