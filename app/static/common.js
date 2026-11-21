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
    recipeNote: "可不選國家，直接輸入想吃的食譜；系統會先在 Recipe.xls 找出對應國家並帶出，找不到再網路搜尋並補齊欄位（含國家，找不到則用 Global）。有選國家時，食譜欄列出該國可用食譜。沒選「依身體狀況建議」時只排除過敏原；有選才依今日檢測濾除禁忌。選定後顯示食譜、煮法、益處與元素。教學示範，非診斷。",
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
    recipeEnsuring: "搜尋建檔中",
    recipeCreateAction: "建立此食譜",
    recipeEnsurePartial: "部分欄位未能從網路可靠取得，已留白，請人工核對。教學示範，非醫療建議。",
    recipeEnsureFailed: "無法建立此食譜，請稍後再試。",
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
    recipeNote: "Country is optional. Type a dish to look it up in Recipe.xls (country is filled in) or web-research all fields when missing (country becomes Global if unknown). With a country selected, the recipe list is scoped to that country. Teaching demo, not a diagnosis.",
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
    recipeEnsuring: "Searching and creating data",
    recipeCreateAction: "Create this recipe",
    recipeEnsurePartial: "Some fields could not be filled reliably from the web and were left blank. Teaching demo, not medical advice.",
    recipeEnsureFailed: "Could not create this recipe. Try again later.",
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
    recipeNote: "国の一覧は、フィルター後にレシピが残っている国だけです。先頭文字で検索して選びます（英字は大文字小文字を区別しません）。レシピ欄を開くとその国の残っているレシピをすべて表示し、入力で絞り込めます。「依身體狀況建議」を選んでいないときはアレルゲンだけを除きます。選んだときだけ、今日の検出で禁忌を除きます。選ぶとレシピ・作り方・益処・栄養素を表示します。教材であり診断ではありません。",
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
    recipeEnsuring: "検索してデータを作成中",
    recipeCreateAction: "このレシピを作成",
    recipeEnsurePartial: "一部の欄はネットから確実に取れず空欄のままです。教材デモであり医療助言ではありません。",
    recipeEnsureFailed: "このレシピを作成できませんでした。後でもう一度お試しください。",
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
    recipeNote: "국가 목록은 걸러낸 뒤 레시피가 남은 국가만 보여 줍니다. 앞글자를 입력해 고릅니다(라틴 문자는 대소문자 무시). 레시피 칸을 열면 그 나라의 남은 레시피가 모두 나오고, 입력하면 좁혀집니다. 「依身體狀況建議」를 끄면 알레르기만 제외합니다. 켰을 때만 오늘 검사로 금기를 제외합니다. 고르면 레시피, 조리법, 유익, 영양소를 보여 줍니다. 교육용이며 진단이 아닙니다.",
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
    recipeEnsuring: "검색하며 데이터 작성 중",
    recipeCreateAction: "이 레시피 만들기",
    recipeEnsurePartial: "일부 항목은 웹에서 확실히 채우지 못해 비워 두었습니다. 교육용 시연이며 의료 조언이 아닙니다.",
    recipeEnsureFailed: "이 레시피를 만들 수 없습니다. 나중에 다시 시도하세요.",
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
