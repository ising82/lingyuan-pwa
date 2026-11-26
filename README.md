# 淩淵 App PWA 試用版

可安裝、可離線的試用版。紀錄只存在使用者自己的裝置（localStorage），**不放在這個 repo 裡**。
第一次打開請按「匯入資料」，選資料檔（.json）或原 App 存下來的 .html。

- `index.html`、`manifest.webmanifest`、`sw.js`、`icons/`：網站本體（GitHub Pages 從 main 根目錄發布）
- `tools/build.py`：從原 App 的 HTML 重新產生 `index.html`（不帶 `--embed` 時不會把紀錄寫進去）
