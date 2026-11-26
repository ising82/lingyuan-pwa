"""Build the 淩淵 PWA trial from a read-only copy of the artifact HTML.
usage: python3 -I build.py <orig.html> <outdir> [--embed]
Without --embed the records are NOT put into index.html (safe for a public host);
the data is written separately to data-<date>.json for one-time import.
"""
import sys, json, re, os, shutil, hashlib

src, out = sys.argv[1], sys.argv[2]
embed = '--embed' in sys.argv
here = os.path.dirname(os.path.abspath(__file__))
s = open(src, encoding='utf8').read()

# locate the real (first) data block
a0 = s.index('<script type="application/json" id="data">')
a = a0 + len('<script type="application/json" id="data">')
b = s.index('</script>', a)
data = json.loads(s[a:b])
skeleton = {"v": 2, "checks": {}, "growth": [], "miles": {}, "logs": [], "days": [], "qs": [],
            "contacts": "", "updated": "", "links": data.get("links", {})}
body = json.dumps(data if embed else skeleton, ensure_ascii=False).replace('<', '\\u003c')
s = s[:a] + body + s[b:]

HEAD = '''<meta name="theme-color" content="#0f5e6e">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="淩淵">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>淩淵 App 試用版</title>'''
s = s.replace('</head>', HEAD + '</head>', 1)
s = s.replace('<title>張淩淵APP家人版</title>', '', 1)

PRE = r'''<script id="pwa-pre">
/* PWA trial: records live in this device's localStorage instead of the Claude artifact. */
(function(){
  var KEY="ly-pwa-data";
  var emb=null; try{ emb=JSON.parse(document.getElementById("data").textContent); }catch(e){}
  try{
    var raw=localStorage.getItem(KEY);
    if(raw){ var d=JSON.parse(raw); if(d && Array.isArray(d.logs) && (!emb || !emb.updated || (d.updated||"")>=(emb.updated||""))) window.LY_DATA=d; }
  }catch(e){}
  window.LY_PWA={KEY:KEY, hasData:function(){ return !!(window.LY_DATA || (emb && emb.logs && emb.logs.length)); }};
  var art={ publish:function(){ return new Promise(function(res,rej){
    try{ localStorage.setItem(KEY, JSON.stringify(DATA)); res(); }
    catch(e){ var err=new Error("save failed"); err.code=(e&&e.name==="QuotaExceededError")?"too_large":"io"; rej(err); }
  }); } };
  var usr={ canEdit:function(){ return Promise.resolve(true); }, isOwner:function(){ return Promise.resolve(true); }, me:function(){ return Promise.resolve({}); } };
  window.claude={ use:function(n){ return n==="artifact"?art : n==="user"?usr : null; } };
})();
</script>
'''
s = s.replace('<script id="main">', PRE + '<script id="main">', 1)

POST = r'''<style id="pwa-css">
.pwabox{background:var(--surface);border:1px solid var(--accent);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px;font-size:14px;color:var(--ink)}
.pwabox b{color:var(--accent)}
.pwabox .row .btn{padding:8px 14px;font-size:14px}
.pwafirst{border-width:2px}
</style>
<script id="pwa-post">
(function(){
  var KEY=window.LY_PWA.KEY;
  function el(h){ var t=document.createElement("template"); t.innerHTML=h.trim(); return t.content.firstChild; }
  function stamp(){ var d=new Date(), p=function(n){return String(n).padStart(2,"0")}; return d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+"-"+p(d.getHours())+p(d.getMinutes()); }
  function parseImport(txt){
    txt=String(txt||"").trim();
    if(txt.charAt(0)==="<"){ var m=txt.match(/<script type="application\/json" id="data">([\s\S]*?)<\/script>/); if(!m) throw new Error("找不到資料區塊"); txt=m[1]; }
    var d=JSON.parse(txt); if(!d || !Array.isArray(d.logs)) throw new Error("格式不對");
    return d;
  }
  function mergeData(L,I){
    /* 合併：這台裝置的紀錄（L）保留，檔案（I，通常是原 App 的最新資料）帶進新的待辦、看診、報告等 */
    function byKey(a,b,key,preferB){
      var m={}, order=[];
      (a||[]).forEach(function(x){ if(x && x[key]!=null && !(x[key] in m)){ m[x[key]]=x; order.push(x[key]); } });
      (b||[]).forEach(function(x){ if(!x || x[key]==null) return; if(!(x[key] in m)){ order.push(x[key]); m[x[key]]=x; } else if(preferB){ m[x[key]]=x; } });
      return order.map(function(k){ return m[k]; });
    }
    function orTrue(a,b){ var o={}, k; a=a||{}; b=b||{}; for(k in a) o[k]=a[k]; for(k in b) o[k]=b[k]||a[k]; return o; }
    var o={}, k; for(k in L) o[k]=L[k];
    o.logs=byKey(L.logs,I.logs,"id",false).sort(function(x,y){ return x.t<y.t?-1:x.t>y.t?1:0; });
    ["items","visits","qs","reports"].forEach(function(f){ if(I[f]||L[f]) o[f]=byKey(L[f],I[f],"id",true); });
    o.growth=byKey(L.growth,I.growth,"d",false).sort(function(x,y){ return x.d<y.d?-1:x.d>y.d?1:0; });
    o.days=byKey(L.days,I.days,"d",false).sort(function(x,y){ return x.d<y.d?-1:x.d>y.d?1:0; });
    o.checks=orTrue(L.checks,I.checks); o.miles=orTrue(L.miles,I.miles);
    var seen={}; o.feed=(I.feed||[]).concat(L.feed||[]).filter(function(x){ var key=x&&(x.at+"|"+x.text); if(!x||seen[key]) return false; seen[key]=1; return true; }).sort(function(x,y){ return x.at<y.at?1:x.at>y.at?-1:0; });
    ["drive","links","medInfo","idno","contacts"].forEach(function(f){ if(I[f]!=null && I[f]!=="") o[f]=I[f]; });
    o.updated=(L.updated||"")>(I.updated||"")?L.updated:I.updated;
    return o;
  }
  function doImport(file){
    var r=new FileReader();
    r.onload=function(){
      try{
        var d=parseImport(r.result), n=d.logs.length, msg;
        if(window.LY_PWA.hasData()){
          if(confirm("合併：保留這台裝置的紀錄，加入檔案裡新的待辦、看診和其他更新？\n（按「取消」可改成整個取代）")){
            var cur=null; try{ cur=JSON.parse(localStorage.getItem(KEY)); }catch(e){}
            if(!cur && typeof DATA==="object") cur=DATA;
            if(cur && Array.isArray(cur.logs)){ var before=cur.logs.length; d=mergeData(cur,d); msg="已合併：紀錄 "+before+" → "+d.logs.length+" 筆，待辦與看診已更新"; }
          }
          if(!msg && !confirm("要用檔案裡的資料（"+n+" 筆紀錄）整個取代這台裝置目前的資料嗎？這台裝置上新記的紀錄會不見。")) return;
        }
        localStorage.setItem(KEY, JSON.stringify(d)); try{ sessionStorage.removeItem("ly-pending"); }catch(e){}
        alert(msg || ("已匯入 "+n+" 筆紀錄")); location.reload();
      }catch(e){ alert("匯入失敗："+e.message); }
    };
    r.readAsText(file);
  }
  function doExport(){
    var blob=new Blob([JSON.stringify(DATA)],{type:"application/json"});
    var a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="lingyuan-"+stamp()+".json";
    document.body.appendChild(a); a.click(); setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); },1000);
  }
  var standalone = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone===true;
  var ios=/iPhone|iPad|iPod/.test(navigator.userAgent);
  var installTip = standalone ? "已經是安裝好的 App。" : ios ? "安裝：用 Safari 開這頁 → 分享鈕 → 「加入主畫面」。" : "安裝：瀏覽器選單 → 「安裝應用程式」或「加到主畫面」。";
  var box=el('<div class="pwabox" id="pwaBox"><div><b>PWA 試用版</b>：紀錄只存在<b>這台裝置</b>，不會回寫到原本的家人編輯版，也不會同步給家人。</div><div class="note">'+installTip+(ios&&!standalone?"注意：iPhone 加到主畫面後，App 和 Safari 的資料是分開的，請在 App 裡匯入。":"")+'</div><div class="row"><button type="button" class="btn ghost" id="pwaExp">匯出備份</button><label class="btn ghost" style="display:inline-block">匯入資料<input type="file" id="pwaImp" accept=".json,.html,application/json,text/html" hidden></label></div></div>');
  function mount(){
    var f=document.querySelector("footer"); var w=document.querySelector(".wrap");
    if(!window.LY_PWA.hasData() && w){ var first=box.cloneNode(true); first.id="pwaFirst"; first.classList.add("pwafirst"); first.querySelector("div").innerHTML="<b>第一次使用：先匯入資料</b>。用「匯入資料」選 Claude 給你的 lingyuan 資料檔（.json），或原本 App 存下來的 .html 檔。"; w.insertBefore(first, w.children[1]||null); wire(first); }
    if(f){ f.insertBefore(box, f.firstChild); wire(box); }
  }
  function wire(root){
    var e=root.querySelector('[id^=pwaExp]'), i=root.querySelector('input[type=file]');
    if(e) e.onclick=doExport;
    if(i) i.onchange=function(){ if(i.files && i.files[0]) doImport(i.files[0]); i.value=""; };
  }
  mount();
  try{ if(navigator.storage && navigator.storage.persist) navigator.storage.persist(); }catch(e){}
  if("serviceWorker" in navigator && location.protocol!=="file:") navigator.serviceWorker.register("sw.js").catch(function(){});
})();
</script>
'''
k = s.rfind('</body></html>')
s = s[:k] + POST + '<script src="config.js"></script>\n<script src="sync.js"></script>\n' + s[k:]
if 'id="pwa-post"' not in s:
    raise SystemExit('post script not inserted')

os.makedirs(out, exist_ok=True)
open(os.path.join(out, 'index.html'), 'w', encoding='utf8').write(s)
shutil.copytree(os.path.join(here, 'icons'), os.path.join(out, 'icons'), dirs_exist_ok=True)

manifest = {
  "name": "張淩淵 App（試用版）", "short_name": "淩淵", "lang": "zh-Hant-TW",
  "start_url": "./", "scope": "./", "display": "standalone", "orientation": "portrait",
  "background_color": "#f3f6f7", "theme_color": "#0f5e6e",
  "icons": [
    {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
json.dump(manifest, open(os.path.join(out, 'manifest.webmanifest'), 'w', encoding='utf8'), ensure_ascii=False, indent=1)

extra = b''.join(open(os.path.join(out, f), 'rb').read() for f in ('config.js', 'sync.js') if os.path.exists(os.path.join(out, f)))
ver = hashlib.sha1(s.encode() + extra).hexdigest()[:10]  # config.js、sync.js 改了也會換快取版本
sw = open(os.path.join(here, 'sw.template.js'), encoding='utf8').read().replace('__VER__', ver)
open(os.path.join(out, 'sw.js'), 'w', encoding='utf8').write(sw)
open(os.path.join(out, '.nojekyll'), 'w').write('')
if not embed:
    json.dump(data, open(os.path.join(out, '..', 'lingyuan-data-%s.json' % data.get('updated','')[:10]), 'w', encoding='utf8'), ensure_ascii=False)
print('ok', ver, len(s), 'embed' if embed else 'skeleton', len(data['logs']), 'logs')
