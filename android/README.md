# Health-ing Android

在 Android Studio 選擇 **Open** → `C:\tube\Health-ing\android`（開這個資料夾，不要開整個 Python 專案當 Android 工程）。

## 伺服器位址

| 環境 | API base |
|------|----------|
| 模擬器 | `http://10.0.2.2:8000`（10.0.2.2 = 模擬器眼中的電腦 localhost） |
| 實體手機 | `http://<電腦區網IP>:8000`，**不要用 10.0.2.2** |

手機與電腦必須同一 Wi-Fi。電腦上啟動 API：

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` 才能讓區網連進來。Windows 防火牆請放行 TCP 8000。查 LAN IP：`ipconfig` 的 IPv4（例如 `192.168.1.10`），App 頂部伺服器欄填 `http://192.168.1.10:8000`。

App 會記住上次填的伺服器位址。臉／舌用**前置**鏡頭；寸關尺脈診用**後置**鏡頭，有閃光會開燈（蓋住鏡頭，與指尖 PPG 同一做法）。脈診仍是 12 段 × 15 秒亮度計次，尚未在實機驗證準確度。

## 自己轉 APK（debug 即可個人測試）

1. 安裝 [Android Studio](https://developer.android.com/studio)（內建 SDK；這支 App **compileSdk / targetSdk 36**，對應 Android 16）。
2. **File → Open** → 選 `C:\tube\Health-ing\android` → Trust the project。
3. 等 Gradle Sync 完成。若提示安裝 **Android SDK 36** / Platform，按 Install。
4. 上方裝置選單可先選 **No Devices**（不必開模擬器也能出 APK）。
5. 功能表：**Build → Build Bundle(s) / APK(s) → Build APK(s)**。
   - 若沒有這一項： **Build → Generate App Bundles or APKs → Generate APKs**。
   - 或右側 Gradle：`Healthing` → `app` → `Tasks` → `build` → **assembleDebug**。
6. 完成後右下角 **locate**，或到  
   `android\app\build\outputs\apk\debug\app-debug.apk`  
   把 APK 拷到手機。

不要提交 `android/.gradle`、`android/app/build`、APK 進 git。

## 裝到手機（PD2502EF / vivo·iQOO、Android 16）

USB 安裝（建議）：

1. 設定 → 關於手機 → 連點「版本號」約 7 次，打開開發人員選項。
2. 設定 → 系統 / 額外設定 → **開發人員選項** → 開 **USB 偵錯**（必要時再開「USB 安裝」）。
3. USB 接電腦，手機選檔案傳輸，允許這台電腦偵錯。
4. Android Studio 裝置選單選這支手機 → 綠三角 Run，或 `adb install -r app-debug.apk`。

只拷 APK：

1. 把 `app-debug.apk` 傳到手機。
2. 開檔案時允許「從此來源安裝」／未知來源（vivo 常在：設定 → 安全 → 更多安全設定）。
3. 第一次開 App 允許**相機**。脈診需要後置鏡頭；閃光非必要，沒有 LED 仍可預覽。

首次相機權限若拒，進系統設定 → App → Health-ing → 權限 → 相機。

## 模擬器崩潰（Android Emulator closed unexpectedly）

這是 qemu 模擬器本身當掉，不是 App Kotlin crash。建議先按 **Don't send**。

1. Device Manager → 該 AVD 右側選單 → **Cold Boot Now**（不要用 Quick Boot / 舊 snapshot）。
2. 同一個選單 → **Wipe Data**。
3. 鉛筆編輯 AVD → Show Advanced Settings：
   - Graphics：**Automatic** 或 **Software**（ANGLE / SwiftShader）
   - RAM：**2048**
   - Front camera：**Emulated** 或 Webcam；Back camera：**VirtualScene**（不要設 **None**，否則後置脈診綁定會失敗）
4. Windows：開啟 **Hyper-V** 與 **Windows Hypervisor Platform**，然後重開機。
5. 仍崩潰就刪掉舊 AVD，新建 **Pixel 6/7、API 34**（比 API 36 穩）。
6. 不要同時開兩個 AVD。App 啟動會綁定鏡頭；模擬器解析度會自動降到 640×480。
