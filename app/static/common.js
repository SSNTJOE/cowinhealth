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

const UI_LANG_KEY = "healthing_lang";
const UI_I18N = {
  zh: {
    langLabel: "語言",
    homeSub: "用 E-mail 和密碼登入後，畫面只顯示匿名 ID。可寫今日身體狀況、拍照看面色／唇色／舌象，並顯示臟腑虛實寒熱圖。",
    dietLink: "網路食療搜尋連結",
    acupointLink: "穴道按摩搜尋連結",
    recipeHeading: "今日食譜（教學示範）",
    recipeNote: "在國家欄打字搜尋並選定，再於食譜欄打字縮小範圍。通過禁忌／過敏篩選的食譜才會列出。益處欄盡量對應今日證型；數量不足時仍列出通過禁忌與過敏的食譜。選定後顯示食材與煮法。教學示範，非診斷。",
    country: "國家",
    recipe: "食譜",
    pickCountry: "輸入國家搜尋",
    pickRecipe: "輸入食譜搜尋",
    searchEmpty: "沒有符合的項目",
    searchMore: "還有 {n} 筆，請再輸入以縮小範圍",
    emptyRecipes: "沒有符合今日證型、禁忌與過敏條件的食譜。",
    fieldRecipe: "食譜",
    fieldMethod: "煮法",
    fieldBenefit: "益處",
    fieldBan: "禁忌",
    fieldNutrient: "元素",
    fieldAllergens: "過敏原",
  },
  en: {
    langLabel: "Language",
    homeSub: "After email login the page shows only an anonymous ID. Record today’s symptoms, photograph face/lips/tongue, and view organ pattern maps.",
    dietLink: "Diet search link",
    acupointLink: "Acupoint massage search",
    recipeHeading: "Today’s recipes (teaching demo)",
    recipeNote: "Type in the country field to search, then type in the recipe field to narrow the list. Only recipes that pass today’s contraindication and allergy filters are shown. Benefits are preferred when they support today’s patterns. The selected recipe shows ingredients and the cooking method. Teaching demo, not a diagnosis.",
    country: "Country",
    recipe: "Recipe",
    pickCountry: "Type to search countries",
    pickRecipe: "Type to search recipes",
    searchEmpty: "No matches",
    searchMore: "{n} more. Keep typing to narrow the list.",
    emptyRecipes: "No recipes pass today’s pattern, contraindication, and allergy filters.",
    fieldRecipe: "Recipe",
    fieldMethod: "Method",
    fieldBenefit: "Benefits",
    fieldBan: "Contraindications",
    fieldNutrient: "Nutrients",
    fieldAllergens: "Allergens",
  },
  ja: {
    langLabel: "言語",
    homeSub: "メールでログイン後、画面には匿名 ID のみ表示されます。今日の体調・顔／唇／舌の写真から臓腑の虚実寒熱を示します。",
    dietLink: "食事療法の検索リンク",
    acupointLink: "経穴マッサージ検索",
    recipeHeading: "本日のレシピ（教材デモ）",
    recipeNote: "国の欄に入力して絞り込み、次にレシピ欄でも入力して範囲を狭めます。禁忌・アレルギーを通過したものだけが表示されます。益処が証型に合うものを優先。選んだレシピには材料と作り方を表示します。教材であり診断ではありません。",
    country: "国",
    recipe: "レシピ",
    pickCountry: "国名を入力",
    pickRecipe: "レシピ名を入力",
    searchEmpty: "一致する項目がありません",
    searchMore: "ほか {n} 件。続けて入力すると絞り込めます。",
    emptyRecipes: "本日の証型・禁忌・アレルギー条件に合うレシピがありません。",
    fieldRecipe: "レシピ",
    fieldMethod: "作り方",
    fieldBenefit: "益処",
    fieldBan: "禁忌",
    fieldNutrient: "栄養素",
    fieldAllergens: "アレルゲン",
  },
  ko: {
    langLabel: "언어",
    homeSub: "이메일 로그인 후 화면에는 익명 ID만 표시됩니다. 오늘 증상과 얼굴/입술/혀 사진으로 장부의 허실한열을 보여 줍니다.",
    dietLink: "식이요법 검색 링크",
    acupointLink: "혈자리 마사지 검색",
    recipeHeading: "오늘의 레시피（교육 시연）",
    recipeNote: "국가 칸에 입력해 찾고, 레시피 칸에도 입력해 범위를 줄입니다. 금기와 알레르기 조건을 통과한 항목만 나옵니다. 유익이 증형에 맞는 항목을 우선합니다. 고른 레시피에는 재료와 조리법을 표시합니다. 교육용이며 진단이 아닙니다.",
    country: "국가",
    recipe: "레시피",
    pickCountry: "국가 입력 검색",
    pickRecipe: "레시피 입력 검색",
    searchEmpty: "일치하는 항목 없음",
    searchMore: "{n}개 더 있습니다. 계속 입력하면 좁혀집니다.",
    emptyRecipes: "오늘의 증형·금기·알레르기 조건에 맞는 레시피가 없습니다.",
    fieldRecipe: "레시피",
    fieldMethod: "조리법",
    fieldBenefit: "유익",
    fieldBan: "금기",
    fieldNutrient: "영양소",
    fieldAllergens: "알레르기 유발 물질",
  },
};

function readCookie(name) {
  const parts = ("; " + document.cookie).split("; " + name + "=");
  if (parts.length < 2) return "";
  return decodeURIComponent(parts.pop().split(";").shift() || "");
}

function writeCookie(name, value) {
  document.cookie = name + "=" + encodeURIComponent(value) + ";path=/;max-age=31536000;samesite=lax";
}

function normalizeUiLang(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (raw === "en" || raw === "english") return "en";
  if (raw === "ja" || raw === "jp" || raw.indexOf("日本") >= 0) return "ja";
  if (raw === "ko" || raw === "kr" || raw.indexOf("한국") >= 0 || raw.indexOf("韓") >= 0) return "ko";
  return "zh";
}

function getUiLang() {
  return normalizeUiLang(localStorage.getItem(UI_LANG_KEY) || readCookie(UI_LANG_KEY) || "zh");
}

function setUiLang(lang) {
  const value = normalizeUiLang(lang);
  try { localStorage.setItem(UI_LANG_KEY, value); } catch (_err) { /* ignore */ }
  writeCookie(UI_LANG_KEY, value);
  const htmlLang = { zh: "zh-Hant", en: "en", ja: "ja", ko: "ko" }[value] || "zh-Hant";
  document.documentElement.lang = htmlLang;
  return value;
}

function uiText(key) {
  const pack = UI_I18N[getUiLang()] || UI_I18N.zh;
  return pack[key] || UI_I18N.zh[key] || key;
}

function applyUiLangChrome() {
  const lang = setUiLang(getUiLang());
  const select = document.getElementById("ui-lang");
  if (select && select.value !== lang) select.value = lang;
  const langLabel = document.getElementById("lang-label");
  if (langLabel) langLabel.textContent = uiText("langLabel");
  const sub = document.getElementById("home-sub");
  if (sub) sub.textContent = uiText("homeSub");
  const heading = document.getElementById("recipe-heading");
  if (heading) heading.textContent = uiText("recipeHeading");
  const note = document.getElementById("recipe-note");
  if (note) note.textContent = uiText("recipeNote");
  const countryLabel = document.getElementById("recipe-country-label");
  if (countryLabel) countryLabel.textContent = uiText("country");
  const recipeLabel = document.getElementById("recipe-name-label");
  if (recipeLabel) recipeLabel.textContent = uiText("recipe");
  const countryInput = document.getElementById("recipe-country");
  if (countryInput) countryInput.placeholder = uiText("pickCountry");
  const recipeInput = document.getElementById("recipe-name");
  if (recipeInput) recipeInput.placeholder = uiText("pickRecipe");
}

function compactPatternLabel(label) {
  const text = String(label || "");
  if (!text || text === "健康" || text === "未定" || text === "待觀察" || text === "色差基準") return "";
  if (text.indexOf("濕") >= 0) return "濕";
  if (text.indexOf("虛") >= 0 && text.indexOf("熱") >= 0) return "虛熱";
  if (text.indexOf("實") >= 0 && text.indexOf("熱") >= 0) return "實熱";
  if (text.indexOf("虛") >= 0 && text.indexOf("寒") >= 0) return "虛寒";
  if (text.indexOf("實") >= 0 && text.indexOf("寒") >= 0) return "實寒";
  return "";
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
