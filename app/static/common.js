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
  const failed = (typeof uiText === "function") ? uiText("requestFailed") : "請求失敗";
  if (!err) return failed;
  if (typeof err === "string") return formatApiDetail(err) || err;
  if (err.detail) return formatApiDetail(err.detail) || failed;
  const message = formatApiDetail(err.message);
  return message || err.message || failed;
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

async function loadCaptcha(imgEl, tokenEl, answerEl) {
  const data = await api("/api/captcha");
  if (tokenEl) tokenEl.value = data.captcha_token || "";
  if (answerEl) answerEl.value = "";
  if (imgEl) {
    const mime = data.mime || "image/png";
    imgEl.src = `data:${mime};base64,${data.image_base64 || ""}`;
  }
  return data;
}

function bindCaptchaControls(prefix = "") {
  const img = document.getElementById(prefix ? `${prefix}-captcha-img` : "captcha-img");
  const token = document.getElementById(prefix ? `${prefix}-captcha_token` : "captcha_token");
  const answer = document.getElementById(prefix ? `${prefix}-captcha_answer` : "captcha_answer");
  const refresh = document.getElementById(prefix ? `${prefix}-captcha-refresh` : "captcha-refresh");
  const reload = () => loadCaptcha(img, token, answer).catch(() => {});
  if (refresh) refresh.addEventListener("click", (e) => { e.preventDefault(); reload(); });
  reload();
  return { reload, img, token, answer };
}

function authCaptchaFields() {
  return {
    captcha_token: (document.getElementById("captcha_token") || {}).value || "",
    captcha_answer: (document.getElementById("captcha_answer") || {}).value || "",
    website_url: (document.getElementById("website_url") || {}).value || "",
  };
}

let CONDITION_OPTIONS = ["糖尿病", "中風", "痛風", "腎臟病", "肝病", "高血壓", "服用抗凝血劑"];
let ALLERGY_OPTIONS = ["蝦蟹", "魚", "芒果", "花生", "堅果", "雞蛋", "牛奶"];

const CRUSTACEAN_ALLERGY_TOKENS = new Set([
  "蝦蟹",
  "蝦",
  "蝦米",
  "蝦仁",
  "龍蝦",
  "螃蟹",
  "蟹",
]);
const FISH_ALLERGY_TOKENS = new Set([
  "魚",
  "鯉魚",
  "鯽魚",
  "鱸魚",
  "草魚",
  "鰱魚",
  "青魚",
  "帶魚",
  "黃魚",
  "鯖魚",
  "鮪魚",
  "鮭魚",
  "鱈魚",
  "鯛魚",
  "秋刀魚",
  "沙丁魚",
  "鰻魚",
  "鱔魚",
  "虱目魚",
  "石斑魚",
  "比目魚",
  "鯊魚",
  "烏魚",
  "鰹魚",
  "吳郭魚",
  "鮑魚",
  "魷魚",
  "章魚",
]);

function canonicalizeAllergyLabel(label) {
  const text = String(label || "").trim();
  if (!text) return null;
  if (CRUSTACEAN_ALLERGY_TOKENS.has(text)) return "蝦蟹";
  if (FISH_ALLERGY_TOKENS.has(text) || text.includes("魚")) return "魚";
  return text;
}

function canonicalizeAllergySelection(selected) {
  const picked = [];
  const seen = new Set();
  for (const item of Array.isArray(selected) ? selected : []) {
    const canon = canonicalizeAllergyLabel(item);
    if (canon && !seen.has(canon)) {
      seen.add(canon);
      picked.push(canon);
    }
  }
  return picked;
}

function consolidateAllergyOptions(options) {
  return canonicalizeAllergySelection(options);
}

async function loadHealthFlagOptions() {
  try {
    const data = await api("/api/flags");
    if (Array.isArray(data.conditions) && data.conditions.length) {
      CONDITION_OPTIONS = data.conditions;
    }
    if (Array.isArray(data.allergies) && data.allergies.length) {
      ALLERGY_OPTIONS = consolidateAllergyOptions(data.allergies);
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
  const allergyOpts = consolidateAllergyOptions(
    user && Array.isArray(user.allergy_options) && user.allergy_options.length
      ? user.allergy_options
      : ALLERGY_OPTIONS,
  );
  renderCheckboxes(
    scope.querySelector("#allergies-group"),
    allergyOpts,
    canonicalizeAllergySelection(user && user.allergies),
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
    dietLinkArticles: "食譜文章搜尋",
    dietLinkVideos: "食譜影片搜尋",
    acupointLink: "穴道按摩搜尋連結",
    acupointLinkImages: "穴道按摩圖片搜尋",
    acupointLinkVideos: "穴道按摩影片搜尋",
    recipeHeading: "今日食譜（教學示範）",
    recipeNote: "",
    recipeBodyAdvice: "依身體狀況建議",
    country: "國家",
    recipe: "食譜",
    pickCountry: "可選：輸入國家開頭",
    pickCountryFirst: "可不選國家，直接輸入食譜",
    pickRecipe: "輸入食譜名稱，或點開列出",
    searchEmpty: "沒有符合的項目",
    searchMore: "還有 {n} 筆，請再輸入以縮小範圍",
    emptyRecipes: "沒有符合過敏條件的食譜。",
    emptyRecipesBody: "沒有符合今日檢測與過敏條件的食譜。",
    recipeSearching: "搜尋中",
    recipeEnsuring: "搜尋建檔中（以中文進行）",
    recipeCreateHint: "清單中沒有此食譜，請點「建立此食譜」",
    recipeCreateAction: "建立此食譜",
    recipeListLoading: "載入該國食譜中…",
    recipeEnsurePartial: "部分欄位未能從網路可靠取得，已留白，請人工核對。教學示範，非醫療建議。",
    recipeEnsureFailed: "無法建立此食譜，請稍後再試。",
    recipeLangUnsupported: "目前僅支援中文／英文／日文／韓文食譜名稱；請改用這四種語文再搜尋或建檔。",
    recipeCountryCorrected: "已依食譜庫找到此菜，並改回正確國家。",
    fieldRecipe: "食譜",
    fieldMethod: "煮法",
    fieldBenefit: "對五臟六腑的幫助",
    fieldBan: "較不適合的情況",
    fieldNutrient: "元素",
    fieldAllergens: "過敏原",
    mealSlot: "餐次",
    mealServings: "份量",
    mealAdd: "加入今日飲食",
    mealCalendarHeading: "飲食日曆與營養對照",
    mealCalendarNote: "依基本資料年齡／性別對照衛福部建議量（daily_nutrient.xlsx）。選定上方食譜後可加入當日飲食；長條圖以達成率（%）比較當日累計攝取與建議量；趨勢圖為各日各營養素的攝取−建議量（正＝超量、負＝不足）。教學示範，非營養處方。",
    mealDate: "日期",
    mealPickRecipeFirst: "請先選定上方食譜再加入。",
    mealAdded: "已加入飲食紀錄。",
    mealDeleted: "已刪除。",
    mealEmptyDay: "這天尚未記錄飲食。",
    mealChartEmpty: "尚無當日飲食紀錄可畫圖。",
    mealChartMissingLib: "圖表函式庫未載入，請重新整理頁面。",
    mealIntakeTitle: "當日攝取 vs 建議量（達成率 %）",
    mealSurplusTitle: "當日差額（攝取−建議量）",
    mealSurplusAxis: "攝取−建議量",
    mealSurplusSeries: "差額",
    mealNutrientTrendTitle: "營養差額趨勢（中線＝建議量）",
    mealNutrientTrendX: "日期",
    mealNutrientTrendY: "相對建議量（%，0＝達標）",
    mealRemove: "刪除",
    mealKcalPct: "熱量達成 {n}%",
    mealCountLabel: "{n} 餐",
    mealTargetMeta: "對照：{band}｜{gender}",
    mealIntakeSeries: "攝取 %",
    mealTargetSeries: "建議量 100%",
    mealStepsHeading: "今日步數建議（教學示範）",
    mealStepsKcal: "當日飲食累計熱量：{intake} kcal（建議量 {target} kcal，差額 {surplus}）→ 建議步行約 {recommended} 步以大致抵銷攝取熱量。",
    mealStepsKcalEmpty: "尚無當日飲食熱量；加入餐次後會依公式計算建議步數。",
    mealStepsSummary: "實際 {actual} ／ 建議 {recommended} 步（差距 {gap}）",
    mealStepsNoActual: "建議 {recommended} 步（尚未同步手機步數；請用 Android App 同步，或下方手動輸入）",
    mealStepsBurned: "步行／運動消耗約 {burned} kcal（來源：{source}）；與攝取差 {delta} kcal。",
    mealStepsBurnedNone: "尚無手機活動資料；Android App 可讀取步數並同步到網站。",
    mealStepsFormula: "公式：recommended_steps = clamp(round(meal_kcal ÷ {k} kcal/步), {min}, {max})。約 0.04 kcal/步（≈25 步/kcal）。教學示範，非醫療／健身處方。",
    mealStepsManualLabel: "實際步數（可手動）",
    mealStepsSave: "儲存步數",
    mealStepsSaved: "已儲存實際步數（網站與 App 同步）。",
    mealStepsNeedLogin: "請先登入後再儲存步數。",
    mealStepsSourceHc: "Health Connect",
    mealStepsSourceSensor: "手機感測器",
    mealStepsSourceManual: "手動",
    mealKcalRulerNeed: "每日建議 {target} kcal",
    mealKcalBarIntake: "攝取 {n} kcal",
    mealKcalBarBurn: "消耗 {n} kcal",
    mealKcalNetOver: "淨攝取 {net} kcal，已超過每日建議 {target} kcal（超出 {over}）。",
    mealKcalNetUnder: "淨攝取 {net} kcal，低於每日建議 {target} kcal（尚餘 {under}）。",
    mealKcalNetEqual: "淨攝取 {net} kcal，約等於每日建議 {target} kcal。",
    mealKcalNetNoTarget: "淨攝取 {net} kcal（尚無年齡／性別建議熱量）。",
    mealKcalNetEmpty: "尚無當日飲食與運動熱量可對照。",
    mealStepsRemainingNeed: "還需約 {n} 步才達建議。",
    mealStepsRemainingDone: "已達建議步數（多出 {n} 步）。",
    mealStepsRemainingExact: "已剛好達建議步數。",
    mealStepsRemainingUnknown: "建議 {recommended} 步（尚未同步實際步數）。",
  },
  en: {
    langLabel: "Language",
    homeSub: "After email login the page shows only an anonymous ID. Record today’s symptoms, photograph face/lips/tongue, and view organ pattern maps.",
    dietLink: "Diet search link",
    dietLinkArticles: "Recipe articles",
    dietLinkVideos: "Recipe videos",
    acupointLink: "Acupoint massage search",
    acupointLinkImages: "Acupoint massage images",
    acupointLinkVideos: "Acupoint massage videos",
    recipeHeading: "Today’s recipes (teaching demo)",
    recipeNote: "",
    recipeBodyAdvice: "依身體狀況建議",
    country: "Country",
    recipe: "Recipe",
    pickCountry: "Optional: type a country prefix",
    pickCountryFirst: "Country optional — type a recipe name",
    pickRecipe: "Type a dish name, or open the list",
    searchEmpty: "No matches",
    searchMore: "{n} more. Keep typing to narrow the list.",
    emptyRecipes: "No recipes pass the allergy filter.",
    emptyRecipesBody: "No recipes pass today’s reading and allergy filters.",
    recipeSearching: "Searching",
    recipeEnsuring: "Searching in Chinese and creating data",
    recipeCreateHint: "Not in this country’s list — tap “Create this recipe”",
    recipeCreateAction: "Create this recipe",
    recipeListLoading: "Loading recipes for this country…",
    recipeEnsurePartial: "Some fields could not be filled reliably from the web and were left blank. Teaching demo, not medical advice.",
    recipeEnsureFailed: "Could not create this recipe. Try again later.",
    recipeLangUnsupported: "Only Chinese, English, Japanese, and Korean recipe names are supported for now.",
    recipeCountryCorrected: "Found this dish in the catalog and corrected the country.",
    fieldRecipe: "Recipe",
    fieldMethod: "Method",
    fieldBenefit: "Helpful for organs",
    fieldBan: "Better to go easy when",
    fieldNutrient: "Nutrients",
    fieldAllergens: "Allergens",
    mealSlot: "Meal",
    mealServings: "Servings",
    mealAdd: "Add to today’s meals",
    mealCalendarHeading: "Meal calendar & nutrients",
    mealCalendarNote: "Compares daily intake with age/gender targets from daily_nutrient.xlsx. Add breakfast/lunch/dinner/snack to accumulate on the bar chart; the trend chart plots intake − target per nutrient per day. Teaching demo only.",
    mealDate: "Date",
    mealPickRecipeFirst: "Select a recipe above first.",
    mealAdded: "Meal added.",
    mealDeleted: "Removed.",
    mealEmptyDay: "No meals logged for this day.",
    mealChartEmpty: "No meals yet to chart for this day.",
    mealChartMissingLib: "Chart library failed to load. Refresh the page.",
    mealIntakeTitle: "Daily intake vs target (% of target)",
    mealSurplusTitle: "Daily surplus (intake − target)",
    mealSurplusAxis: "intake − target",
    mealSurplusSeries: "Surplus",
    mealNutrientTrendTitle: "Nutrient surplus trend (center = daily target)",
    mealNutrientTrendX: "Day",
    mealNutrientTrendY: "% vs target (0 = on target)",
    mealRemove: "Remove",
    mealKcalPct: "Calories {n}% of target",
    mealCountLabel: "{n} meals",
    mealTargetMeta: "Targets: {band} · {gender}",
    mealIntakeSeries: "Intake %",
    mealTargetSeries: "Target 100%",
    mealStepsHeading: "Today’s step suggestion (teaching demo)",
    mealStepsKcal: "Today’s meal calories: {intake} kcal (target {target} kcal, Δ {surplus}) → about {recommended} walking steps to roughly offset that intake.",
    mealStepsKcalEmpty: "No meal calories yet; add meals to compute a step suggestion.",
    mealStepsSummary: "Actual {actual} / recommended {recommended} steps (gap {gap})",
    mealStepsNoActual: "Recommended {recommended} steps (no phone steps yet — sync via the Android app, or enter below)",
    mealStepsBurned: "Walking/exercise burn ≈ {burned} kcal (source: {source}); vs intake Δ {delta} kcal.",
    mealStepsBurnedNone: "No phone activity yet; the Android app can read steps and sync them here.",
    mealStepsFormula: "Formula: recommended_steps = clamp(round(meal_kcal ÷ {k} kcal/step), {min}, {max}). ≈ 0.04 kcal/step (~25 steps/kcal). Teaching demo, not medical/fitness advice.",
    mealStepsManualLabel: "Actual steps (manual OK)",
    mealStepsSave: "Save steps",
    mealStepsSaved: "Actual steps saved (synced with website & App).",
    mealStepsNeedLogin: "Sign in to save steps.",
    mealStepsSourceHc: "Health Connect",
    mealStepsSourceSensor: "Phone sensor",
    mealStepsSourceManual: "Manual",
    mealKcalRulerNeed: "Daily need {target} kcal",
    mealKcalBarIntake: "Intake {n} kcal",
    mealKcalBarBurn: "Burn {n} kcal",
    mealKcalNetOver: "Net intake {net} kcal exceeds daily need {target} kcal (over by {over}).",
    mealKcalNetUnder: "Net intake {net} kcal is under daily need {target} kcal ({under} left).",
    mealKcalNetEqual: "Net intake {net} kcal matches daily need {target} kcal.",
    mealKcalNetNoTarget: "Net intake {net} kcal (no age/gender calorie target yet).",
    mealKcalNetEmpty: "No meal or exercise calories to compare yet.",
    mealStepsRemainingNeed: "About {n} more steps to reach the suggestion.",
    mealStepsRemainingDone: "Step suggestion met ({n} extra).",
    mealStepsRemainingExact: "Step suggestion met exactly.",
    mealStepsRemainingUnknown: "Suggested {recommended} steps (actual steps not synced yet).",
  },
  ja: {
    langLabel: "言語",
    homeSub: "メールでログイン後、画面には匿名 ID のみ表示されます。今日の体調・顔／唇／舌の写真から臓腑の虚実寒熱を示します。",
    dietLink: "食事療法の検索リンク",
    dietLinkArticles: "レシピ記事検索",
    dietLinkVideos: "レシピ動画検索",
    acupointLink: "経穴マッサージ検索",
    acupointLinkImages: "経穴マッサージ画像検索",
    acupointLinkVideos: "経穴マッサージ動画検索",
    recipeHeading: "本日のレシピ（教材デモ）",
    recipeNote: "",
    recipeBodyAdvice: "依身體狀況建議",
    country: "国",
    recipe: "レシピ",
    pickCountry: "国名の先頭を入力",
    pickCountryFirst: "レシピが残っている国を先に選んでください",
    pickRecipe: "開くと一覧、入力で絞り込み",
    searchEmpty: "一致する項目がありません",
    searchMore: "ほか {n} 件。続けて入力すると絞り込めます。",
    emptyRecipes: "アレルギー条件に合うレシピがありません。",
    emptyRecipesBody: "今日の検出とアレルギー条件に合うレシピがありません。",
    recipeSearching: "検索中",
    recipeEnsuring: "中国語で検索してデータを作成中",
    recipeCreateHint: "一覧にない料理です。「このレシピを作成」を押してください",
    recipeCreateAction: "このレシピを作成",
    recipeListLoading: "この国のレシピを読み込み中…",
    recipeEnsurePartial: "一部の欄はネットから確実に取れず空欄のままです。教材デモであり医療助言ではありません。",
    recipeEnsureFailed: "このレシピを作成できませんでした。後でもう一度お試しください。",
    recipeLangUnsupported: "現在は中・英・日・韓のレシピ名のみ対応しています。",
    recipeCountryCorrected: "カタログで見つけたため、国を正しいものに直しました。",
    fieldRecipe: "レシピ",
    fieldMethod: "作り方",
    fieldBenefit: "五臓六腑への助け",
    fieldBan: "控えめがよい場合",
    fieldNutrient: "栄養素",
    fieldAllergens: "アレルゲン",
    mealSlot: "食事",
    mealServings: "分量",
    mealAdd: "今日の食事に追加",
    mealCalendarHeading: "食事カレンダーと栄養",
    mealCalendarNote: "年齢・性別の目安（daily_nutrient.xlsx）と比較します。上のレシピを選んで当日に追加。棒グラフは達成率（%）、差額グラフは目安に対する不足（負）／超過（正）。教材デモです。",
    mealDate: "日付",
    mealPickRecipeFirst: "先に上のレシピを選んでください。",
    mealAdded: "食事を追加しました。",
    mealDeleted: "削除しました。",
    mealEmptyDay: "この日の食事記録はありません。",
    mealChartEmpty: "この日のグラフ用データがありません。",
    mealIntakeTitle: "摂取 vs 目安（達成率 %）",
    mealSurplusTitle: "差額 %（正＝超過、負＝不足）",
    mealRemove: "削除",
    mealKcalPct: "熱量達成 {n}%",
    mealCountLabel: "{n} 食",
    mealTargetMeta: "対照：{band}｜{gender}",
    mealIntakeSeries: "摂取 %",
    mealTargetSeries: "目安 100%",
    mealSurplusSeries: "差額",
    mealChartMissingLib: "チャートライブラリを読み込めません。再読み込みしてください。",
    mealSurplusAxis: "摂取−目安",
    mealNutrientTrendTitle: "栄養差額トレンド（中央線＝目安）",
    mealNutrientTrendX: "日",
    mealNutrientTrendY: "目安比（%、0＝達成）",
    mealStepsHeading: "本日の歩数目安（教材デモ）",
    mealStepsKcal: "当日の食事カロリー合計：{intake} kcal（目安 {target} kcal、差 {surplus}）→ およそ {recommended} 歩で摂取熱量を歩行で相殺する目安。",
    mealStepsKcalEmpty: "当日の食事カロリーがありません。食事を追加すると歩数目安が出ます。",
    mealStepsSummary: "実際 {actual} ／ 目安 {recommended} 歩（差 {gap}）",
    mealStepsNoActual: "目安 {recommended} 歩（スマホ歩数未同期。Android App で同期、または下で手入力）",
    mealStepsBurned: "歩行／運動の消費 ≈ {burned} kcal（出典：{source}）；摂取との差 {delta} kcal。",
    mealStepsBurnedNone: "スマホ活動データなし。Android App で歩数を読み取り同期できます。",
    mealStepsFormula: "式：recommended_steps = clamp(round(meal_kcal ÷ {k} kcal/歩), {min}, {max})。約 0.04 kcal/歩（≈25 歩/kcal）。教材デモであり医療／運動処方ではありません。",
    mealStepsManualLabel: "実際の歩数（手入力可）",
    mealStepsSave: "歩数を保存",
    mealStepsSaved: "実際の歩数を保存しました（サイトと App で同期）。",
    mealStepsNeedLogin: "歩数を保存するにはログインしてください。",
    mealStepsSourceHc: "Health Connect",
    mealStepsSourceSensor: "端末センサー",
    mealStepsSourceManual: "手入力",
    mealKcalRulerNeed: "1日の目安 {target} kcal",
    mealKcalBarIntake: "摂取 {n} kcal",
    mealKcalBarBurn: "消費 {n} kcal",
    mealKcalNetOver: "純摂取 {net} kcal が1日の目安 {target} kcal を超えています（超過 {over}）。",
    mealKcalNetUnder: "純摂取 {net} kcal は1日の目安 {target} kcal 未満です（残り {under}）。",
    mealKcalNetEqual: "純摂取 {net} kcal は1日の目安 {target} kcal とほぼ同じです。",
    mealKcalNetNoTarget: "純摂取 {net} kcal（年齢・性別の目安熱量なし）。",
    mealKcalNetEmpty: "当日の食事・運動カロリーがまだありません。",
    mealStepsRemainingNeed: "目安まであと約 {n} 歩。",
    mealStepsRemainingDone: "目安歩数に到達（+{n} 歩）。",
    mealStepsRemainingExact: "目安歩数にちょうど到達。",
    mealStepsRemainingUnknown: "目安 {recommended} 歩（実際の歩数は未同期）。",
  },
  ko: {
    langLabel: "언어",
    homeSub: "이메일 로그인 후 화면에는 익명 ID만 표시됩니다. 오늘 증상과 얼굴/입술/혀 사진으로 장부의 허실한열을 보여 줍니다.",
    dietLink: "식이요법 검색 링크",
    dietLinkArticles: "레시피 글 검색",
    dietLinkVideos: "레시피 영상 검색",
    acupointLink: "혈자리 마사지 검색",
    acupointLinkImages: "혈자리 마사지 이미지 검색",
    acupointLinkVideos: "혈자리 마사지 영상 검색",
    recipeHeading: "오늘의 레시피（교육 시연）",
    recipeNote: "",
    recipeBodyAdvice: "依身體狀況建議",
    country: "국가",
    recipe: "레시피",
    pickCountry: "국가 앞글자 입력",
    pickCountryFirst: "레시피가 남은 국가를 먼저 고르세요",
    pickRecipe: "열면 목록, 입력하면 좁힘",
    searchEmpty: "일치하는 항목 없음",
    searchMore: "{n}개 더 있습니다. 계속 입력하면 좁혀집니다.",
    emptyRecipes: "알레르기 조건에 맞는 레시피가 없습니다.",
    emptyRecipesBody: "오늘 검사와 알레르기 조건에 맞는 레시피가 없습니다.",
    recipeSearching: "검색 중",
    recipeEnsuring: "중국어로 검색하며 데이터 작성 중",
    recipeCreateHint: "목록에 없습니다. 「이 레시피 만들기」를 누르세요",
    recipeCreateAction: "이 레시피 만들기",
    recipeListLoading: "이 국가 레시피 불러오는 중…",
    recipeEnsurePartial: "일부 항목은 웹에서 확실히 채우지 못해 비워 두었습니다. 교육용 시연이며 의료 조언이 아닙니다.",
    recipeEnsureFailed: "이 레시피를 만들 수 없습니다. 나중에 다시 시도하세요.",
    recipeLangUnsupported: "지금은 중·영·일·한 레시피 이름만 지원합니다.",
    recipeCountryCorrected: "목록에서 이 요리를 찾아 국가를 올바른 값으로 고쳤습니다.",
    fieldRecipe: "레시피",
    fieldMethod: "조리법",
    fieldBenefit: "오장육부에 도움이 되는 점",
    fieldBan: "조심하는 편이 좋은 경우",
    fieldNutrient: "영양소",
    fieldAllergens: "알레르기 유발 물질",
    mealSlot: "끼니",
    mealServings: "분량",
    mealAdd: "오늘 식단에 추가",
    mealCalendarHeading: "식단 달력과 영양 대조",
    mealCalendarNote: "나이/성별 권장량(daily_nutrient.xlsx)과 비교합니다. 위 레시피를 고른 뒤 당일에 추가하세요. 막대는 달성률(%), 차액 그래프는 권장 대비 부족(음)/초과(양). 교육용 시연입니다.",
    mealDate: "날짜",
    mealPickRecipeFirst: "먼저 위 레시피를 선택하세요.",
    mealAdded: "식단에 추가했습니다.",
    mealDeleted: "삭제했습니다.",
    mealEmptyDay: "이 날의 식단 기록이 없습니다.",
    mealChartEmpty: "이 날의 차트 데이터가 없습니다.",
    mealIntakeTitle: "섭취 vs 권장(달성률 %)",
    mealSurplusTitle: "차액 %(양=초과, 음=부족)",
    mealRemove: "삭제",
    mealKcalPct: "열량 달성 {n}%",
    mealCountLabel: "{n}끼",
    mealTargetMeta: "대조: {band}｜{gender}",
    mealIntakeSeries: "섭취 %",
    mealTargetSeries: "권장 100%",
    mealSurplusSeries: "차액",
    mealChartMissingLib: "차트 라이브러리를 불러오지 못했습니다. 새로고침하세요.",
    mealSurplusAxis: "섭취−권장",
    mealNutrientTrendTitle: "영양 차액 추세(중앙선=권장)",
    mealNutrientTrendX: "일",
    mealNutrientTrendY: "권장 대비 %(0=달성)",
    mealStepsHeading: "오늘 걸음 수 권장(교육 시연)",
    mealStepsKcal: "당일 식사 누적 열량: {intake} kcal (권장 {target} kcal, 차 {surplus}) → 대략 {recommended}걸음으로 섭취 열량을 걷기로 상쇄하는 참고치.",
    mealStepsKcalEmpty: "당일 식사 열량이 없습니다. 끼니를 추가하면 권장 걸음이 계산됩니다.",
    mealStepsSummary: "실제 {actual} / 권장 {recommended} 걸음 (차이 {gap})",
    mealStepsNoActual: "권장 {recommended} 걸음 (폰 걸음 미동기화 — Android 앱으로 동기화하거나 아래 수동 입력)",
    mealStepsBurned: "걷기/운동 소모 ≈ {burned} kcal (출처: {source}); 섭취 대비 Δ {delta} kcal.",
    mealStepsBurnedNone: "폰 활동 데이터 없음. Android 앱이 걸음을 읽어 웹에 동기화할 수 있습니다.",
    mealStepsFormula: "공식: recommended_steps = clamp(round(meal_kcal ÷ {k} kcal/걸음), {min}, {max}). 약 0.04 kcal/걸음(≈25걸음/kcal). 교육 시연이며 의료/운동 처방이 아닙니다.",
    mealStepsManualLabel: "실제 걸음(수동 가능)",
    mealStepsSave: "걸음 저장",
    mealStepsSaved: "실제 걸음을 저장했습니다(웹·앱 동기화).",
    mealStepsNeedLogin: "걸음을 저장하려면 먼저 로그인하세요.",
    mealStepsSourceHc: "Health Connect",
    mealStepsSourceSensor: "폰 센서",
    mealStepsSourceManual: "수동",
    mealKcalRulerNeed: "하루 권장 {target} kcal",
    mealKcalBarIntake: "섭취 {n} kcal",
    mealKcalBarBurn: "소모 {n} kcal",
    mealKcalNetOver: "순섭취 {net} kcal이 하루 권장 {target} kcal을 초과했습니다(초과 {over}).",
    mealKcalNetUnder: "순섭취 {net} kcal이 하루 권장 {target} kcal보다 적습니다(남은 {under}).",
    mealKcalNetEqual: "순섭취 {net} kcal이 하루 권장 {target} kcal과 거의 같습니다.",
    mealKcalNetNoTarget: "순섭취 {net} kcal(나이/성별 권장 열량 없음).",
    mealKcalNetEmpty: "당일 식사·운동 열량이 아직 없습니다.",
    mealStepsRemainingNeed: "권장까지 약 {n}걸음 더 필요합니다.",
    mealStepsRemainingDone: "권장 걸음에 도달(+{n}걸음).",
    mealStepsRemainingExact: "권장 걸음에 정확히 도달했습니다.",
    mealStepsRemainingUnknown: "권장 {recommended}걸음(실제 걸음 미동기화).",
  },
};

const UI_I18N_EXTRA = {
  "zh": {
    "loginTitle": "E-mail 登入",
    "email": "E-mail",
    "password": "密碼",
    "captcha": "圖片驗證碼（非郵件）",
    "captchaRefresh": "換一張圖",
    "captchaPlaceholder": "請輸入上方圖片字元（不會寄到信箱）",
    "captchaAlt": "圖片驗證碼",
    "loginBtn": "登入",
    "goRegister": "前往註冊",
    "mysqlChecking": "正在檢查 MySQL…",
    "mysqlOk": "MySQL 連線成功",
    "mysqlBad": "MySQL 回應異常",
    "mysqlOffline": "MySQL 尚未連上：",
    "requestFailed": "請求失敗",
    "registerPageTitle": "建立帳號",
    "registerSub": "先用 E-mail 和密碼註冊並產生匿名 ID。密碼只會加密儲存；暱稱、出生年與性別下一頁再填。",
    "registerFormTitle": "註冊資訊",
    "emailAccount": "E-mail 帳號",
    "passwordMinHint": "至少 6 個字元",
    "registerSubmit": "註冊並產生匿名 ID",
    "haveAccount": "已有帳號？登入",
    "registerNeedFields": "請填寫 E-mail 和至少 6 字密碼",
    "registerOkPrefix": "已建立匿名 ID：",
    "profilePageTitle": "基本資料",
    "profileSub": "補齊暱稱、出生年與性別後即可進入相機與今日狀況。E-mail 只在這一頁顯示。",
    "accountHeading": "帳號",
    "anonIdLabel": "匿名 ID：",
    "nickname": "暱稱",
    "birthYear": "出生年",
    "gender": "性別",
    "genderPick": "請選擇",
    "genderFemale": "女",
    "genderMale": "男",
    "genderOther": "其他",
    "height": "身高 (cm)",
    "weight": "體重 (kg)",
    "conditionsHeading": "特殊疾病（可複選）",
    "conditionsNote": "教學示範用，用來篩選食療與穴道搜尋方向，不是診斷或用藥建議。",
    "allergiesHeading": "過敏（可複選）",
    "allergiesNote": "選項來自 Recipe.xls 過敏原欄，另保留常見分類。勾選後不會推薦含這些食材的食譜。",
    "saveProfileEnter": "儲存並進入主畫面",
    "backBtn": "返回",
    "saved": "已儲存",
    "currentAccount": "目前帳號",
    "anonNote": "網站與 App 畫面只顯示這個 ID，不會顯示 E-mail。",
    "editProfile": "編輯基本資料",
    "logout": "登出",
    "heightWeight": "身高體重",
    "saveBody": "儲存身體資料",
    "todayStatus": "今日身體狀況",
    "howFeel": "今天感覺如何？",
    "howFeelPh": "例如：容易疲倦、口乾、怕冷…",
    "discomfort": "不舒服的地方",
    "discomfortPh": "例如：腰酸、胃脹、喉嚨痛…",
    "openDialog": "再開今日狀況對話框",
    "cameraHeading": "相機擷取",
    "alignHintFace": "對準臉：髮際以下～下巴，兩耳以內",
    "btnFace": "拍臉 / 眼 / 唇",
    "btnTongue": "拍舌頭",
    "btnStool": "大便",
    "btnUrine": "尿尿",
    "btnSaveToday": "儲存今日紀錄（含狀況文字）",
    "faceGridHeading": "臉部分區（4×3，教學示範）",
    "detailSummary": "詳細資料",
    "complexionHistory": "臉色歷史",
    "tongueGridHeading": "舌部分區（上中下左右＋舌苔，教學示範）",
    "tongueDetailSummary": "細部說明",
    "organMapHeading": "臟腑圖（虛／實／熱／寒）",
    "organMapNote": "依基本資料的性別顯示男生或女生身體圖。只有判定出證型的臟腑才會放上貼圖；沒有症狀則不擺。",
    "legendStrongHot": "實證熱證",
    "legendStrongCold": "實證寒證",
    "legendWeakHot": "虛證熱證",
    "legendWeakCold": "虛證寒證",
    "legendMoisture": "濕氣較重",
    "organScoreDetail": "細項說明",
    "organTrendHeading": "臟腑分數趨勢",
    "organTrendNote": "橫軸為檢測時間、縱軸為 1–10 分（近基本色 10，最大色差 1；8–10 健康）。每條線一種臟腑顏色，節點形狀也不同。教學參考，非診斷。",
    "trendEmpty": "尚無足夠紀錄可畫趨勢。",
    "backupSummary": "共用資料庫備存（Excel）",
    "backupNote": "食譜、食材、每日營養建議與檢測差異以 MySQL 即時同步給網站與 App。需要備存時可下載目前內容，或寫回本機 Excel。",
    "backupLoading": "登入後載入筆數…",
    "backupExport": "寫回本機 Excel 備存",
    "recordsSummary": "歷史紀錄",
    "dialogTitle": "今日身體狀況",
    "dialogNote": "登入後可先寫下今天的感覺；不確定也可以留空，稍後再補。",
    "dialogOk": "記下來",
    "dialogSkip": "稍後再說",
    "mealBreakfast": "早餐",
    "mealLunch": "午餐",
    "mealDinner": "晚餐",
    "mealSnack": "點心",
    "teachingDemo": "教學示範，非診斷。",
    "fallbackZhNote": "（部分內容僅有中文，教學示範）"
  },
  "en": {
    "loginTitle": "Email login",
    "email": "Email",
    "password": "Password",
    "captcha": "Image captcha (not email)",
    "captchaRefresh": "New image",
    "captchaPlaceholder": "Type characters from the image (not emailed)",
    "captchaAlt": "Image captcha",
    "loginBtn": "Log in",
    "goRegister": "Create account",
    "mysqlChecking": "Checking MySQL…",
    "mysqlOk": "MySQL connected",
    "mysqlBad": "MySQL response unexpected",
    "mysqlOffline": "MySQL not connected: ",
    "requestFailed": "Request failed",
    "registerPageTitle": "Create account",
    "registerSub": "Register with email and password to get an anonymous ID. Password is stored hashed; nickname, birth year and gender are on the next page.",
    "registerFormTitle": "Registration",
    "emailAccount": "Email",
    "passwordMinHint": "At least 6 characters",
    "registerSubmit": "Register and create anonymous ID",
    "haveAccount": "Already have an account? Log in",
    "registerNeedFields": "Enter email and a password of at least 6 characters",
    "registerOkPrefix": "Anonymous ID created: ",
    "profilePageTitle": "Profile",
    "profileSub": "Add nickname, birth year and gender to use the camera and daily check-in. Email is shown only on this page.",
    "accountHeading": "Account",
    "anonIdLabel": "Anonymous ID: ",
    "nickname": "Nickname",
    "birthYear": "Birth year",
    "gender": "Gender",
    "genderPick": "Please select",
    "genderFemale": "Female",
    "genderMale": "Male",
    "genderOther": "Other",
    "height": "Height (cm)",
    "weight": "Weight (kg)",
    "conditionsHeading": "Conditions (multi-select)",
    "conditionsNote": "Teaching demo only — steers diet and acupoint search, not diagnosis or medication advice.",
    "allergiesHeading": "Allergies (multi-select)",
    "allergiesNote": "Options from Recipe.xls allergens plus common groups. Checked items are excluded from recipe suggestions.",
    "saveProfileEnter": "Save and open home",
    "backBtn": "Back",
    "saved": "Saved",
    "currentAccount": "Current account",
    "anonNote": "Website and app show only this ID, never the email.",
    "editProfile": "Edit profile",
    "logout": "Log out",
    "heightWeight": "Height & weight",
    "saveBody": "Save body data",
    "todayStatus": "Today’s status",
    "howFeel": "How do you feel today?",
    "howFeelPh": "e.g. tired, dry mouth, feeling cold…",
    "discomfort": "Where it hurts",
    "discomfortPh": "e.g. lower back, bloating, sore throat…",
    "openDialog": "Open today’s status dialog again",
    "cameraHeading": "Camera capture",
    "alignHintFace": "Align face: hairline to chin, within both ears",
    "btnFace": "Face / eyes / lips",
    "btnTongue": "Tongue",
    "btnStool": "Stool",
    "btnUrine": "Urine",
    "btnSaveToday": "Save today’s record (with status text)",
    "faceGridHeading": "Face grid (4×3, teaching demo)",
    "detailSummary": "Details",
    "complexionHistory": "Complexion history",
    "tongueGridHeading": "Tongue zones (teaching demo)",
    "tongueDetailSummary": "Detailed notes",
    "organMapHeading": "Organ map (xu/shi/heat/cold)",
    "organMapNote": "Body map follows profile gender. Stickers only for organs with a pattern.",
    "legendStrongHot": "Excess heat",
    "legendStrongCold": "Excess cold",
    "legendWeakHot": "Deficiency heat",
    "legendWeakCold": "Deficiency cold",
    "legendMoisture": "Dampness",
    "organScoreDetail": "Score details",
    "organTrendHeading": "Organ score trend",
    "organTrendNote": "X = check time, Y = 1–10 (near baseline 10; 8–10 healthy). Teaching reference, not a diagnosis.",
    "trendEmpty": "Not enough records for a trend yet.",
    "backupSummary": "Shared DB backup (Excel)",
    "backupNote": "Recipes, foods, daily nutrient targets and deviation tables sync via MySQL. Download or write back local Excel when needed.",
    "backupLoading": "Loading counts after login…",
    "backupExport": "Write back local Excel backup",
    "recordsSummary": "History",
    "dialogTitle": "Today’s status",
    "dialogNote": "After login you can note how you feel; leave blank and fill later if unsure.",
    "dialogOk": "Save note",
    "dialogSkip": "Later",
    "mealBreakfast": "Breakfast",
    "mealLunch": "Lunch",
    "mealDinner": "Dinner",
    "mealSnack": "Snack",
    "teachingDemo": "Teaching demo, not a diagnosis.",
    "fallbackZhNote": "(Some content is Chinese-only; teaching demo)",
    "recipeBodyAdvice": "Suggest by body reading"
  },
  "ja": {
    "loginTitle": "メールでログイン",
    "email": "メール",
    "password": "パスワード",
    "captcha": "画像認証（メールではない）",
    "captchaRefresh": "画像を更新",
    "captchaPlaceholder": "画像の文字を入力（メール送信ではありません）",
    "captchaAlt": "画像認証",
    "loginBtn": "ログイン",
    "goRegister": "新規登録へ",
    "mysqlChecking": "MySQL を確認中…",
    "mysqlOk": "MySQL 接続成功",
    "mysqlBad": "MySQL 応答異常",
    "mysqlOffline": "MySQL 未接続：",
    "requestFailed": "リクエスト失敗",
    "registerPageTitle": "アカウント作成",
    "registerSub": "メールとパスワードで登録し匿名 ID を作成します。パスワードはハッシュ保存。ニックネーム・生年・性別は次のページです。",
    "registerFormTitle": "登録情報",
    "emailAccount": "メールアカウント",
    "passwordMinHint": "6文字以上",
    "registerSubmit": "登録して匿名 ID を作成",
    "haveAccount": "アカウントあり？ログイン",
    "registerNeedFields": "メールと6文字以上のパスワードを入力してください",
    "registerOkPrefix": "匿名 ID を作成しました：",
    "profilePageTitle": "基本情報",
    "profileSub": "ニックネーム・生年・性別を入力するとカメラと今日の状態が使えます。メールはこのページのみ表示。",
    "accountHeading": "アカウント",
    "anonIdLabel": "匿名 ID：",
    "nickname": "ニックネーム",
    "birthYear": "生年",
    "gender": "性別",
    "genderPick": "選択してください",
    "genderFemale": "女",
    "genderMale": "男",
    "genderOther": "その他",
    "height": "身長 (cm)",
    "weight": "体重 (kg)",
    "conditionsHeading": "持病（複数可）",
    "conditionsNote": "教材デモ用。食事療法と経穴検索の方向づけで、診断や薬の助言ではありません。",
    "allergiesHeading": "アレルギー（複数可）",
    "allergiesNote": "Recipe.xls のアレルゲン欄と一般分類。選択した食材を含むレシピは勧めません。",
    "saveProfileEnter": "保存してホームへ",
    "backBtn": "戻る",
    "saved": "保存しました",
    "currentAccount": "現在のアカウント",
    "anonNote": "サイトと App はこの ID のみ表示し、メールは出しません。",
    "editProfile": "基本情報を編集",
    "logout": "ログアウト",
    "heightWeight": "身長・体重",
    "saveBody": "身体データを保存",
    "todayStatus": "今日の体調",
    "howFeel": "今日の調子は？",
    "howFeelPh": "例：疲れやすい、口渇、冷え…",
    "discomfort": "つらい箇所",
    "discomfortPh": "例：腰痛、胃もたれ、喉の痛み…",
    "openDialog": "今日の体調ダイアログを再開",
    "cameraHeading": "カメラ撮影",
    "alignHintFace": "顔合わせ：生え際〜あご、両耳の内側",
    "btnFace": "顔／目／唇",
    "btnTongue": "舌",
    "btnStool": "便",
    "btnUrine": "尿",
    "btnSaveToday": "今日の記録を保存（状態テキスト含む）",
    "faceGridHeading": "顔の区画（4×3・教材デモ）",
    "detailSummary": "詳細",
    "complexionHistory": "顔色履歴",
    "tongueGridHeading": "舌の区画（教材デモ）",
    "tongueDetailSummary": "詳細説明",
    "organMapHeading": "臓腑図（虚／実／熱／寒）",
    "organMapNote": "基本情報の性別で男女の体図を表示。証型がある臓腑だけステッカーを置きます。",
    "legendStrongHot": "実証熱証",
    "legendStrongCold": "実証寒証",
    "legendWeakHot": "虚証熱証",
    "legendWeakCold": "虚証寒証",
    "legendMoisture": "湿が強い",
    "organScoreDetail": "明細",
    "organTrendHeading": "臓腑スコア推移",
    "organTrendNote": "横軸＝検査時刻、縦軸＝1–10（基準色に近いほど10、8–10は健康）。教材であり診断ではありません。",
    "trendEmpty": "推移を描く記録がまだ足りません。",
    "backupSummary": "共有DBバックアップ（Excel）",
    "backupNote": "レシピ・食材・栄養目安・検出差は MySQL で即時同期。必要ならダウンロードまたはローカル Excel へ書き戻し。",
    "backupLoading": "ログイン後に件数を読み込み…",
    "backupExport": "ローカル Excel に書き戻す",
    "recordsSummary": "履歴",
    "dialogTitle": "今日の体調",
    "dialogNote": "ログイン後に今日の感覚を書けます。わからなければ空欄でも後で補えます。",
    "dialogOk": "記録する",
    "dialogSkip": "あとで",
    "mealBreakfast": "朝食",
    "mealLunch": "昼食",
    "mealDinner": "夕食",
    "mealSnack": "間食",
    "teachingDemo": "教材デモであり診断ではありません。",
    "fallbackZhNote": "（一部は中国語のみ・教材デモ）",
    "recipeBodyAdvice": "体調に合わせて提案"
  },
  "ko": {
    "loginTitle": "이메일 로그인",
    "email": "이메일",
    "password": "비밀번호",
    "captcha": "그림 인증(이메일이 아님)",
    "captchaRefresh": "그림 바꾸기",
    "captchaPlaceholder": "그림 글자 입력(이메일로 보내지 않음)",
    "captchaAlt": "그림 인증",
    "loginBtn": "로그인",
    "goRegister": "회원가입",
    "mysqlChecking": "MySQL 확인 중…",
    "mysqlOk": "MySQL 연결 성공",
    "mysqlBad": "MySQL 응답 이상",
    "mysqlOffline": "MySQL 미연결: ",
    "requestFailed": "요청 실패",
    "registerPageTitle": "계정 만들기",
    "registerSub": "이메일과 비밀번호로 등록해 익명 ID를 만듭니다. 비밀번호는 해시 저장. 닉네임·출생년·성별은 다음 페이지입니다.",
    "registerFormTitle": "등록 정보",
    "emailAccount": "이메일 계정",
    "passwordMinHint": "최소 6자",
    "registerSubmit": "등록하고 익명 ID 만들기",
    "haveAccount": "이미 계정이 있나요? 로그인",
    "registerNeedFields": "이메일과 6자 이상 비밀번호를 입력하세요",
    "registerOkPrefix": "익명 ID 생성: ",
    "profilePageTitle": "기본 정보",
    "profileSub": "닉네임·출생년·성별을 채우면 카메라와 오늘 상태를 쓸 수 있습니다. 이메일은 이 페이지만 표시.",
    "accountHeading": "계정",
    "anonIdLabel": "익명 ID: ",
    "nickname": "닉네임",
    "birthYear": "출생년",
    "gender": "성별",
    "genderPick": "선택하세요",
    "genderFemale": "여",
    "genderMale": "남",
    "genderOther": "기타",
    "height": "키 (cm)",
    "weight": "체중 (kg)",
    "conditionsHeading": "특수 질환(복수 선택)",
    "conditionsNote": "교육 시연용. 식이·혈자리 검색 방향용이며 진단·약 조언이 아닙니다.",
    "allergiesHeading": "알레르기(복수 선택)",
    "allergiesNote": "Recipe.xls 알레르기란과 일반 분류. 선택한 식재료가 든 레시피는 추천하지 않습니다.",
    "saveProfileEnter": "저장하고 홈으로",
    "backBtn": "뒤로",
    "saved": "저장됨",
    "currentAccount": "현재 계정",
    "anonNote": "웹과 앱은 이 ID만 보이며 이메일은 표시하지 않습니다.",
    "editProfile": "기본 정보 편집",
    "logout": "로그아웃",
    "heightWeight": "키·체중",
    "saveBody": "신체 데이터 저장",
    "todayStatus": "오늘 몸 상태",
    "howFeel": "오늘 기분은?",
    "howFeelPh": "예: 쉽게 피곤, 구강건조, 추위…",
    "discomfort": "불편한 곳",
    "discomfortPh": "예: 허리 아픔, 더부룩, 목 아픔…",
    "openDialog": "오늘 상태 대화상자 다시 열기",
    "cameraHeading": "카메라 촬영",
    "alignHintFace": "얼굴 맞춤: 헤어라인~턱, 양 귀 안쪽",
    "btnFace": "얼굴 / 눈 / 입술",
    "btnTongue": "혀",
    "btnStool": "대변",
    "btnUrine": "소변",
    "btnSaveToday": "오늘 기록 저장(상태 글 포함)",
    "faceGridHeading": "얼굴 구역(4×3, 교육 시연)",
    "detailSummary": "상세",
    "complexionHistory": "안색 기록",
    "tongueGridHeading": "혀 구역(교육 시연)",
    "tongueDetailSummary": "세부 설명",
    "organMapHeading": "장부도(허/실/열/한)",
    "organMapNote": "기본 정보의 성별에 따라 남/여 체형도. 증형이 있는 장부만 스티커를 둡니다.",
    "legendStrongHot": "실증 열증",
    "legendStrongCold": "실증 한증",
    "legendWeakHot": "허증 열증",
    "legendWeakCold": "허증 한증",
    "legendMoisture": "습이 무거움",
    "organScoreDetail": "세부 설명",
    "organTrendHeading": "장부 점수 추세",
    "organTrendNote": "가로=검사 시각, 세로=1–10(기준색에 가까울수록 10, 8–10 건강). 교육 참고이며 진단이 아닙니다.",
    "trendEmpty": "추세를 그릴 기록이 아직 부족합니다.",
    "backupSummary": "공유 DB 백업(Excel)",
    "backupNote": "레시피·식재·영양 권장·검출 차이는 MySQL로 실시간 동기화. 필요 시 다운로드하거나 로컬 Excel로 되돌립니다.",
    "backupLoading": "로그인 후 건수 불러오는 중…",
    "backupExport": "로컬 Excel로 되돌리기",
    "recordsSummary": "기록",
    "dialogTitle": "오늘 몸 상태",
    "dialogNote": "로그인 후 오늘 느낌을 적을 수 있습니다. 모르면 비워 두고 나중에 채워도 됩니다.",
    "dialogOk": "기록",
    "dialogSkip": "나중에",
    "mealBreakfast": "아침",
    "mealLunch": "점심",
    "mealDinner": "저녁",
    "mealSnack": "간식",
    "teachingDemo": "교육 시연이며 진단이 아닙니다.",
    "fallbackZhNote": "(일부 내용은 중국어만 있음 · 교육 시연)",
    "recipeBodyAdvice": "몸 상태에 맞춰 추천"
  }
};
Object.keys(UI_I18N_EXTRA).forEach((lang) => {
  UI_I18N[lang] = Object.assign({}, UI_I18N[lang] || {}, UI_I18N_EXTRA[lang]);
});


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
  document.querySelectorAll(".js-ui-lang").forEach((select) => {
    if (select.value !== lang) select.value = lang;
  });
  const select = document.getElementById("ui-lang");
  if (select && select.value !== lang) select.value = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    const text = uiText(key);
    if (el.tagName === "TITLE") {
      document.title = text;
      return;
    }
    el.textContent = text;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.placeholder = uiText(key);
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
    const key = el.getAttribute("data-i18n-alt");
    if (key) el.alt = uiText(key);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.title = uiText(key);
  });
  const pageTitle = document.querySelector("title[data-i18n]");
  if (pageTitle) document.title = uiText(pageTitle.getAttribute("data-i18n"));
  const langLabel = document.getElementById("lang-label");
  if (langLabel) langLabel.textContent = uiText("langLabel");
  document.querySelectorAll(".js-lang-label").forEach((el) => {
    el.textContent = uiText("langLabel");
  });
  const sub = document.getElementById("home-sub");
  if (sub) sub.textContent = uiText("homeSub");
  const heading = document.getElementById("recipe-heading");
  if (heading) heading.textContent = uiText("recipeHeading");
  const note = document.getElementById("recipe-note");
  if (note) {
    const recipeNoteText = uiText("recipeNote");
    note.textContent = recipeNoteText;
    note.classList.toggle("hidden", !String(recipeNoteText || "").trim());
  }
  const bodyAdvice = document.getElementById("recipe-body-advice");
  if (bodyAdvice) bodyAdvice.textContent = uiText("recipeBodyAdvice");
  const countryLabel = document.getElementById("recipe-country-label");
  if (countryLabel) countryLabel.textContent = uiText("country");
  const recipeLabel = document.getElementById("recipe-name-label");
  if (recipeLabel) recipeLabel.textContent = uiText("recipe");
  const countryInput = document.getElementById("recipe-country");
  if (countryInput) countryInput.placeholder = uiText("pickCountry");
  const recipeInput = document.getElementById("recipe-name");
  if (recipeInput) recipeInput.placeholder = uiText("pickRecipe");
  const mealHeading = document.getElementById("meal-calendar-heading");
  if (mealHeading) mealHeading.textContent = uiText("mealCalendarHeading");
  const mealNote = document.getElementById("meal-calendar-note");
  if (mealNote) mealNote.textContent = uiText("mealCalendarNote");
  const mealSlotLabel = document.getElementById("meal-slot-label");
  if (mealSlotLabel) mealSlotLabel.textContent = uiText("mealSlot");
  const mealServingsLabel = document.getElementById("meal-servings-label");
  if (mealServingsLabel) mealServingsLabel.textContent = uiText("mealServings");
  const mealAddBtn = document.getElementById("meal-add-btn");
  if (mealAddBtn) mealAddBtn.textContent = uiText("mealAdd");
  const mealDateLabel = document.getElementById("meal-date-label");
  if (mealDateLabel) mealDateLabel.textContent = uiText("mealDate");
  const mealChartEmpty = document.getElementById("meal-chart-empty");
  if (mealChartEmpty) mealChartEmpty.textContent = uiText("mealChartEmpty");
  const mealStepsHeading = document.getElementById("meal-steps-heading");
  if (mealStepsHeading) mealStepsHeading.textContent = uiText("mealStepsHeading");
  const mealStepsManualLabel = document.getElementById("meal-steps-manual-label");
  if (mealStepsManualLabel) mealStepsManualLabel.textContent = uiText("mealStepsManualLabel");
  const mealStepsSaveBtn = document.getElementById("meal-steps-save-btn");
  if (mealStepsSaveBtn) mealStepsSaveBtn.textContent = uiText("mealStepsSave");
  const mealSlot = document.getElementById("meal-slot");
  if (mealSlot) {
    const map = {
      "早餐": "mealBreakfast",
      "午餐": "mealLunch",
      "晚餐": "mealDinner",
      "點心": "mealSnack",
    };
    Array.from(mealSlot.options).forEach((opt) => {
      const key = map[opt.value];
      if (key) opt.textContent = uiText(key);
    });
  }
}

function syncPreferredLangToServer(lang) {
  if (typeof api !== "function") return;
  api("/api/profile", {
    method: "POST",
    body: formBody({ preferred_lang: lang }),
  }).catch(() => {});
}

function bindUiLang(onChange) {
  const selects = Array.from(document.querySelectorAll(".js-ui-lang, #ui-lang"));
  const unique = [];
  const seen = new Set();
  selects.forEach((el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    unique.push(el);
  });
  unique.forEach((select) => {
    if (select.dataset.bound === "1") return;
    select.dataset.bound = "1";
    select.addEventListener("change", () => {
      const lang = setUiLang(select.value);
      unique.forEach((other) => {
        if (other !== select) other.value = lang;
      });
      applyUiLangChrome();
      syncPreferredLangToServer(lang);
      if (typeof onChange === "function") onChange(lang);
    });
  });
  applyUiLangChrome();
}

function applyPreferredLangFromUser(user) {
  if (!user || !user.preferred_lang) return;
  const lang = normalizeUiLang(user.preferred_lang);
  if (lang && lang !== getUiLang()) {
    setUiLang(lang);
    applyUiLangChrome();
  }
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
