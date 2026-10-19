# Health-ing Android

在 Android Studio 選擇 **Open** → `C:\tube\Health-ing\android`。

實機請把伺服器改成電腦區網 IP，例如 `http://192.168.1.10:8000`，並確認防火牆放行 8000 埠。模擬器用 `http://10.0.2.2:8000`。

## 模擬器崩潰（Android Emulator closed unexpectedly）

這是 qemu 模擬器本身當掉，不是 App Kotlin crash。建議先按 **Don't send**。

1. Device Manager → 該 AVD 右側選單 → **Cold Boot Now**（不要用 Quick Boot / 舊 snapshot）。
2. 同一個選單 → **Wipe Data**。
3. 鉛筆編輯 AVD → Show Advanced Settings：
   - Graphics：**Automatic** 或 **Software**（ANGLE / SwiftShader）
   - RAM：**2048**
   - Front camera：**Emulated** 或 Webcam；Back camera：**VirtualScene**（不要設 **None**，否則 CameraX 開機就會失敗）
4. Windows：開啟 **Hyper-V** 與 **Windows Hypervisor Platform**，然後重開機。
5. 仍崩潰就刪掉舊 AVD，新建 **Pixel 6/7、API 34**（比 API 36 穩）。
6. 不要同時開兩個 AVD。App 啟動會綁定鏡頭；模擬器解析度會自動降到 640×480。
