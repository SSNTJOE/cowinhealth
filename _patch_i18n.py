# -*- coding: utf-8 -*-
from pathlib import Path
import json

EXTRA = {
  "zh": {
    "loginTitle": "E-mail 登入",
    "email": "E-mail",
    "password": "密碼",
    "captcha": "驗證碼",
    "captchaRefresh": "換一張",
    "captchaPlaceholder": "輸入圖片中的字元",
    "captchaAlt": "驗證碼",
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
    "stoolUrineSummary": "近２４小時飲食／藥物（選填，教學用）",
    "stoolLegend": "大便混淆因子",
    "urineLegend": "尿尿染色因子",
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
    "fallbackZhNote": "（部分內容僅有中文，教學示範）",
  },
  "en": {
    "loginTitle": "Email login",
    "email": "Email",
    "password": "Password",
    "captcha": "Captcha",
    "captchaRefresh": "New image",
    "captchaPlaceholder": "Enter the characters in the image",
    "captchaAlt": "Captcha",
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
    "stoolUrineSummary": "Last 24h food/medicine (optional, teaching)",
    "stoolLegend": "Stool confounders",
    "urineLegend": "Urine color confounders",
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
    "recipeBodyAdvice": "Suggest by body reading",
  },
  "ja": {
    "loginTitle": "メールでログイン",
    "email": "メール",
    "password": "パスワード",
    "captcha": "認証コード",
    "captchaRefresh": "別の画像",
    "captchaPlaceholder": "画像の文字を入力",
    "captchaAlt": "認証コード",
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
    "stoolUrineSummary": "直近24時間の食事／薬（任意・教材）",
    "stoolLegend": "便の交絡因子",
    "urineLegend": "尿の染色因子",
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
    "recipeBodyAdvice": "体調に合わせて提案",
  },
  "ko": {
    "loginTitle": "이메일 로그인",
    "email": "이메일",
    "password": "비밀번호",
    "captcha": "인증코드",
    "captchaRefresh": "다른 이미지",
    "captchaPlaceholder": "그림의 글자를 입력",
    "captchaAlt": "인증코드",
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
    "stoolUrineSummary": "최근 24시간 음식/약(선택, 교육용)",
    "stoolLegend": "대변 교란 요인",
    "urineLegend": "소변 염색 요인",
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
    "recipeBodyAdvice": "몸 상태에 맞춰 추천",
  },
}

APPLY_FN = r'''
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
'''

def js_object(d):
    # Produce a JS object literal from a Python dict
    return json.dumps(d, ensure_ascii=False, indent=2)

p = Path(r"C:\Tube\Health-ing\app\static\common.js")
text = p.read_text(encoding="utf-8")

marker = "const UI_I18N = {"
if "UI_I18N_EXTRA" not in text:
    # Insert EXTRA after UI_I18N closing `};` that follows UI_I18N
    close = text.index("};\n\nfunction readCookie", text.index(marker))
    insert = (
        "};\n\n"
        "const UI_I18N_EXTRA = "
        + js_object(EXTRA)
        + ";\n"
        "Object.keys(UI_I18N_EXTRA).forEach((lang) => {\n"
        "  UI_I18N[lang] = Object.assign({}, UI_I18N[lang] || {}, UI_I18N_EXTRA[lang]);\n"
        "});\n"
    )
    # replace the closing `};` of UI_I18N with insert (which includes `};`)
    text = text[:close] + insert + text[close + 2 :]

# Replace applyUiLangChrome function through end before compactPatternLabel
start = text.index("function applyUiLangChrome()")
end = text.index("function compactPatternLabel")
# Remove old bind if present later - we'll keep app.js bind calling bindUiLang
text = text[:start] + APPLY_FN.strip() + "\n\n" + text[end:]

# Improve formatApiError to use uiText when available
old_err = '''function formatApiError(err) {
  if (!err) return "請求失敗";
  if (typeof err === "string") return formatApiDetail(err) || err;
  if (err.detail) return formatApiDetail(err.detail) || "請求失敗";
  const message = formatApiDetail(err.message);
  return message || err.message || "請求失敗";
}'''
new_err = '''function formatApiError(err) {
  const failed = (typeof uiText === "function") ? uiText("requestFailed") : "請求失敗";
  if (!err) return failed;
  if (typeof err === "string") return formatApiDetail(err) || err;
  if (err.detail) return formatApiDetail(err.detail) || failed;
  const message = formatApiDetail(err.message);
  return message || err.message || failed;
}'''
if old_err in text:
    text = text.replace(old_err, new_err)

p.write_text(text, encoding="utf-8")
print("patched common.js", len(text))
