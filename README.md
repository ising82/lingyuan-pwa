# 淩淵 App PWA 試用版

可安裝、可離線的試用版。紀錄只存在使用者自己的裝置（localStorage），**不放在這個 repo 裡**。
第一次打開請按「匯入資料」，選資料檔（.json）或原 App 存下來的 .html。

- `index.html`、`manifest.webmanifest`、`sw.js`、`icons/`：網站本體（GitHub Pages 從 main 根目錄發布）
- `tools/build.py`：從原 App 的 HTML 重新產生 `index.html`（不帶 `--embed` 時不會把紀錄寫進去）

## 雲端同步（Supabase）

- `config.js`：Supabase 的 Project URL 與 publishable/anon key（公開值）。留空就是單機模式。
- `sync.js`：把原 App 的每一筆變更（op）上傳到 `ly_ops`，各手機照順序套用；離線先存在裝置，有網路再補傳。
- 讀寫都要「家庭代碼」（家人連結 `…/#k=代碼`），代碼不放在 repo。
- `tools/supabase_setup.py`：產生貼進 Supabase SQL Editor 的設定（含起始資料與代碼，**輸出不可 commit**）。重跑等於用新資料重設雲端。
