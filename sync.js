/* 淩淵 PWA 雲端同步（Supabase）
 * 每一筆變更（op）照原 App 的格式上傳到雲端的 ly_ops，各手機依序套用同一串 op，所以最後內容一致。
 * 離線時 op 先存在這台裝置（outbox），有網路再補傳。資料表全部鎖住，只能透過帶「家庭代碼」的函式讀寫。
 * 需要：config.js 的 window.LY_CLOUD = {url, key}；家庭代碼從 #k=… 連結或手動貼上取得。
 */
(function(){
  var CFG = window.LY_CLOUD || {};
  if(!CFG.url || !CFG.key) return;                       // 還沒設定雲端：維持單機模式
  var DATA_KEY = window.LY_PWA.KEY, K_KEY = "ly-cloud-k", SEQ_KEY = "ly-cloud-seq", OUT_KEY = "ly-cloud-outbox";
  var ls = {
    get: function(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } },
    set: function(k,v){ try{ localStorage.setItem(k,v); return true; }catch(e){ return false; } },
    del: function(k){ try{ localStorage.removeItem(k); }catch(e){} }
  };
  function codeFrom(s){ var m = String(s||"").match(/(?:[#&?]k=)?([A-Za-z0-9_-]{20,})\s*$/); return m ? m[1] : null; }

  /* 家庭代碼：連結 #k=… 進來就記住，並從網址列拿掉 */
  var hm = location.hash.match(/[#&]k=([A-Za-z0-9_-]{20,})/);
  if(hm){ ls.set(K_KEY, hm[1]); try{ history.replaceState(null, "", location.pathname + location.search); }catch(e){} }
  var K = ls.get(K_KEY);

  var box = document.getElementById("pwaBox");
  var head = box && box.querySelector("div");
  function hideImport(){
    var f = document.getElementById("pwaFirst"); if(f) f.hidden = true;   // 先藏起來；雲端也沒資料時再叫回來
    var imp = box && box.querySelector("input[type=file]"); if(imp && imp.parentNode) imp.parentNode.hidden = true;
  }
  hideImport();
  function setStatus(html){ if(head) head.innerHTML = html; }
  function hhmm(d){ return String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0"); }

  if(!K){ askCode(); return; }

  var seq = parseInt(ls.get(SEQ_KEY) || "-1", 10); if(isNaN(seq)) seq = -1;
  var outbox = []; try{ outbox = JSON.parse(ls.get(OUT_KEY) || "[]") || []; }catch(e){ outbox = []; }
  var lastOk = null, pulling = false, pushing = false, failed = false;
  function saveOut(){ ls.set(OUT_KEY, JSON.stringify(outbox)); }
  function saveData(){ try{ DATA.updated = DATA.updated || new Date().toISOString(); }catch(e){} ls.set(DATA_KEY, JSON.stringify(DATA)); }

  function render(){
    var who = ls.get("ly-who");
    var s = failed ? "<b>雲端同步：連不上</b>，先存在這台裝置" : lastOk ? "<b>雲端同步</b>：已連線・" + hhmm(lastOk) + " 更新" : "<b>雲端同步</b>：連線中…";
    if(outbox.length) s += "・<b>" + outbox.length + "</b> 筆等待上傳";
    setStatus(s + '<div class="note" style="margin-top:4px">全家看到同一份紀錄。' + (who ? "" : "記錄前可在「今天」選是誰記的。") + "</div>");
    var bar = document.querySelector(".agebar"), mini = document.getElementById("pwaSyncMini");
    if(bar && !mini){ mini = document.createElement("span"); mini.id = "pwaSyncMini"; bar.appendChild(mini); }
    if(mini){ mini.textContent = failed ? "☁ 離線" + (outbox.length ? "・" + outbox.length + " 筆待上傳" : "") : lastOk ? "☁ 已同步 " + hhmm(lastOk) + (outbox.length ? "・" + outbox.length + " 筆待上傳" : "") : "☁ 連線中"; mini.style.color = failed ? "var(--amber)" : ""; }
  }

  function rpc(fn, body){
    var h = { "apikey": CFG.key, "Content-Type": "application/json" };
    if(/^eyJ/.test(CFG.key)) h["Authorization"] = "Bearer " + CFG.key;
    body = Object.assign({ p_k: K }, body || {});
    return fetch(CFG.url.replace(/\/+$/, "") + "/rest/v1/rpc/" + fn, { method: "POST", headers: h, body: JSON.stringify(body), cache: "no-store" })
      .then(function(r){ return r.text().then(function(t){
        var j = null; try{ j = t ? JSON.parse(t) : null; }catch(e){}
        if(!r.ok){ var err = new Error((j && (j.message || j.hint)) || ("HTTP " + r.status)); err.status = r.status; err.badKey = /bad_key/.test(t); throw err; }
        return j;
      }); });
  }

  function fail(e){
    failed = true; render();
    if(e && e.badKey){ ls.del(K_KEY); askCode("這組家庭代碼不對，請重新貼上。"); }
  }

  /* 原 App 存檔時呼叫 publish：把這次累積的 op 移進 outbox 再上傳 */
  var art = window.claude && window.claude.use("artifact");
  if(art){
    var orig = art.publish;
    art.publish = function(doc){
      try{
        if(typeof pending !== "undefined" && pending.length){
          var by = ls.get("ly-who") || "";
          pending.forEach(function(op){ outbox.push({ op: op, by: by }); });
          pending.length = 0; savePending(); saveOut();
        }
      }catch(e){}
      var p = orig.call(art, doc);
      setTimeout(push, 0);
      return p;
    };
  }

  function push(){
    if(pushing || !outbox.length) { render(); return Promise.resolve(); }
    pushing = true;
    var batch = outbox.slice(0, 200);
    return rpc("ly_push", { p_ops: batch.map(function(x){ return x.op; }), p_by: (batch[0] && batch[0].by) || "" })
      .then(function(){ outbox.splice(0, batch.length); saveOut(); pushing = false; failed = false; return pull(); })
      .catch(function(e){ pushing = false; fail(e); });
  }

  function applyAll(ops){
    var changed = false;
    (ops || []).forEach(function(op){ try{ if(applyOp(op)) changed = true; }catch(e){} });
    return changed;
  }

  function pull(){
    if(pulling) return Promise.resolve();
    pulling = true;
    return rpc("ly_pull", { p_after: seq }).then(function(r){
      pulling = false; failed = false; lastOk = new Date();
      if(!r){ render(); return; }
      if(r.empty){
        /* 雲端還沒有資料：用這台裝置的資料當起點 */
        if(DATA && Array.isArray(DATA.logs) && DATA.logs.length) return rpc("ly_init", { p_data: DATA }).then(function(){ seq = -1; return pull(); });
        /* 這台也沒有資料：把「匯入資料」叫回來，匯入後重新載入就會自動上傳當雲端起點 */
        var imp = box && box.querySelector("input[type=file]"); if(imp && imp.parentNode) imp.parentNode.hidden = false;
        var first = document.getElementById("pwaFirst");
        if(first){ first.hidden = false; first.querySelector("div").innerHTML = "<b>雲端還沒有資料</b>：用「匯入資料」選最新的資料檔（.json）或原本 App 存下來的 .html，匯入後會自動放上雲端，全家都看得到。"; }
        setStatus("<b>雲端還沒有資料</b>：在一台有紀錄的手機打開，或在這裡按下方「匯入資料」選最新的資料檔，匯入後會自動放上雲端給全家。"); return;
      }
      if(r.snap){
        /* 第一次連線（或雲端重整過）：換成雲端資料，再補上這台還沒傳的變更，重新載入 */
        DATA = r.snap; applyAll(r.ops); applyAll(outbox.map(function(x){ return x.op; }));
        saveData(); seq = r.seq; ls.set(SEQ_KEY, String(seq));
        try{ sessionStorage.removeItem("ly-pending"); }catch(e){}
        location.reload(); return;
      }
      var changed = applyAll(r.ops);
      if(changed) applyAll(outbox.map(function(x){ return x.op; }));  // 本機尚未上傳的變更維持在最上層
      if(typeof r.seq === "number" && r.seq > seq){ seq = r.seq; ls.set(SEQ_KEY, String(seq)); }
      if(changed){ saveData(); try{ renderAll(); }catch(e){} }
      render();
    }).catch(function(e){ pulling = false; fail(e); });
  }

  function askCode(msg){
    setStatus("<b>還沒連上全家的雲端紀錄</b>：請看頁面最上方。");
    var w = document.querySelector(".wrap"), old = document.getElementById("pwaCloud"); if(old) old.remove();
    var d = document.createElement("div"); d.className = "pwabox pwafirst"; d.id = "pwaCloud";
    d.innerHTML = "<div><b>連上全家的雲端紀錄</b>：" + (msg || "直接點開張爸傳的「家人連結」，或把連結貼在下面。") + "</div>" +
      '<form class="row" id="pwaCode"><input type="text" id="pwaCodeIn" placeholder="貼上家人連結" autocomplete="off" style="flex:1"><button class="btn" type="submit">連線</button></form>';
    if(w) w.insertBefore(d, w.children[1] || null);
    var f = document.getElementById("pwaCode");
    if(f) f.onsubmit = function(ev){ ev.preventDefault(); var c = codeFrom(document.getElementById("pwaCodeIn").value); if(!c){ alert("看起來不是家人連結"); return; } ls.set(K_KEY, c); ls.set(SEQ_KEY, "-1"); location.reload(); };
  }

  render();
  if(seq < 0) setStatus("<b>雲端同步</b>：第一次連線，正在載入全家的紀錄…");
  push().then(pull);
  setInterval(function(){ if(!document.hidden){ push(); pull(); } }, 15000);
  document.addEventListener("visibilitychange", function(){ if(!document.hidden){ push(); pull(); } });
  window.addEventListener("online", function(){ push(); pull(); });
  window.LY_SYNC = { pull: pull, push: push, state: function(){ return { seq: seq, outbox: outbox.length, failed: failed }; } };
})();
