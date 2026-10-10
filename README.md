# Health-ing

Python FastAPI + MySQL：用 E-mail 登入後只顯示匿名 ID（例如 `user_748291`），可存身高體重、寫今日身體狀況、用瀏覽器相機拍臉／舌，做 HSV 色彩與臟腑虛實寒熱評分，並寫入 `health_records`。

這是教學／示範邏輯，**不能取代中醫或西醫診斷**。進階 CNN 需另外蒐集標註臨床照片再訓練。

## 需求

- Python 3.11+（目前可用 3.14）
- Docker Desktop（本機 MySQL 8 已可用 `healthing-mysql`）
- Visual Studio Code
- Android 端：Android Studio（開啟 `android/` 資料夾）

## 啟動 MySQL

```powershell
cd C:\tube\Health-ing
docker compose up -d
```

預設帳密：host `127.0.0.1`、port `3306`、user / password / database 皆為 `healthing`。

## 啟動網站

```powershell
cd C:\tube\Health-ing
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

瀏覽器打開 http://127.0.0.1:8000  
VS Code：用「Health-ing FastAPI」偵錯設定即可。

## 網站功能

1. `/api/health` 確認 MySQL
2. 註冊時產生隨機匿名 `user_id`；畫面不顯示 E-mail
3. 登入後對話框可填今日身體狀況／不適處
4. HTML5 `<video>` 預覽；「拍臉／眼／唇」「拍舌頭」擷取一幀，`fetch` 傳到 `/api/record`
5. Python 轉 HSV，比對紅／白苔／萎黃／青紫；結合文字與（App）脈診，判定虛／實／熱／寒
6. 判定不出來記 **5 分（未定）**；越明確偏移越往 1 分
7. 依性別顯示 `boy-body.png` / `girl-body.png`。有判定的臟腑才疊上證型圖：實證熱 `strong-hot.png`、實證寒 `strong-cold.png`、虛證熱 `weak-hot.png`、虛證寒 `weak-cold.png`；沒有症狀則不擺
8. 依當日資訊做搜尋，整理 **50 字內** 食療陳述，並提供 Google 食療／穴道按摩連結
9. `INSERT INTO health_records`

## Android App

用 Android Studio 開啟 `C:\tube\Health-ing\android`。

- 模擬器伺服器填 `http://10.0.2.2:8000`
- 用同一個 E-mail 帳號登入（回傳 Bearer token）
- 前置鏡頭拍臉／舌
- 寸關尺流程：左右手 × 寸關尺 × 輕按／重按，每段 15 秒  
  - 左手寸：重按心、輕按小腸  
  - 左手關：重按肝、輕按膽  
  - 左手尺：重按腎、輕按膀胱  
  - 右手寸：重按肺、輕按大腸  
  - 右手關：重按脾、輕按胃（胃併入脾系統評分）  
  - 右手尺：重按心包（併入心）、輕按三焦（併入膀胱氣化）  
- 15 秒超過 23 次 → 熱證／實證；少於 14 次 → 寒證／虛證  
- 資料送到同一個 `/api/record` 並寫入 MySQL
