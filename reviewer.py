import json
import logging
import os
import re
import secrets
import signal
import socket
import subprocess
import threading
import webbrowser
from pathlib import Path

import cleaner as cleaner_mod
from flask import Flask, Response, jsonify, request

logging.getLogger("werkzeug").setLevel(logging.ERROR)

REVIEW_PORT = 5888
# The server only listens on loopback, but a web page whose own domain is re-pointed
# at 127.0.0.1 (DNS rebinding) still reaches it, under that domain's name.
LOCAL_HOST = re.compile(r"(localhost|127\.0\.0\.1|\[::1\])(:\d+)?", re.IGNORECASE)
TOKEN_HEADER = "X-MacMaid-Token"
STALE_PAGE = "This page is from an earlier MacMaid session. Reload it, then try again."


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


RESULTS_PATH = Path.home() / "Library" / "Logs" / "mac-maid-last-results.json"
TOKENS_PATH = Path(__file__).with_name("tokens.css")


def _persist_results(categories: dict[str, list[dict]]) -> None:
    """Update every tracked category in the results JSON to reflect deletions."""
    try:
        if not RESULTS_PATH.exists():
            return
        results = json.loads(RESULTS_PATH.read_text())
        for r in results:
            cat = r.get("category")
            if cat in categories:
                r["items"] = categories[cat]
        RESULTS_PATH.write_text(json.dumps(results))
    except Exception:
        pass


def _make_app(categories: dict[str, list[dict]]) -> Flask:
    app = Flask(__name__)
    token = secrets.token_urlsafe(32)
    tab_names = list(categories.keys())

    # Shared path index across all tabs; one path can be listed in more than one
    path_index: dict[str, dict] = {i["path"]: i for items in categories.values() for i in items}

    # Mutable per-category lists (deletions splice these in-place)
    cat_lists: dict[str, list[dict]] = {k: list(v) for k, v in categories.items()}

    @app.before_request
    def guard():
        if not LOCAL_HOST.fullmatch(request.headers.get("Host", "")):
            return jsonify({"error": "Open this page as http://localhost"}), 403
        # Every POST acts on the Mac, so each must carry the token from this session's page.
        sent = request.headers.get(TOKEN_HEADER, "")
        if request.method == "POST" and not secrets.compare_digest(sent.encode(), token.encode()):
            return jsonify({"error": STALE_PAGE}), 403
        return None

    @app.after_request
    def no_framing(response):
        # A framed page carries a working token, so another site could steer clicks onto it.
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/")
    def index():
        return Response(_html(token), mimetype="text/html", headers={"Cache-Control": "no-store"})

    @app.get("/api/tabs")
    def tabs():
        return jsonify({name: len(cat_lists[name]) for name in tab_names})

    @app.get("/api/files")
    def files():
        first = tab_names[0] if tab_names else None
        return jsonify(cat_lists[first] if first else [])

    @app.get("/api/files/<tab>")
    def files_for_tab(tab: str):
        if tab not in cat_lists:
            return jsonify({"error": "Unknown tab"}), 404
        return jsonify(cat_lists[tab])

    @app.post("/api/delete")
    def delete():
        paths = (request.get_json(silent=True) or {}).get("paths", [])
        to_clean = [path_index[p] for p in paths if p in path_index]
        result = cleaner_mod.clean_items(to_clean)
        removed = set(result.moved_paths or [])
        not_found = {p for p, e in result.error_paths if "not found" in e.lower()}
        removed |= not_found
        for p in removed:
            path_index.pop(p, None)
        for cat, items in cat_lists.items():
            cat_lists[cat] = [i for i in items if i["path"] not in removed]
        _persist_results(cat_lists)
        return jsonify({
            "moved": result.moved,
            "errors": result.errors - len(not_found),
            "bytes_freed": result.bytes_freed,
            "error_paths": [(p, e) for p, e in result.error_paths if p not in not_found],
            "moved_paths": result.moved_paths,
            "changed_paths": result.changed_paths,
            "not_found_paths": list(not_found),
        })

    @app.post("/api/reveal")
    def reveal():
        path = (request.get_json(silent=True) or {}).get("path", "")
        if not os.path.exists(path):
            return jsonify({"ok": False, "error": "File not found on disk"}), 404
        subprocess.run(["open", "-R", path], check=False)
        return jsonify({"ok": True})

    @app.post("/api/quit")
    def quit_server():
        def _shutdown():
            import time
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGINT)
        threading.Thread(target=_shutdown, daemon=True).start()
        return jsonify({"ok": True})

    return app


def start(categories: dict[str, list[dict]]) -> None:
    """Start the Flask review server and open the browser."""
    app = _make_app(categories)
    port = _free_port()
    url = f"http://localhost:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="localhost", port=port, use_reloader=False)


def serve(categories: dict[str, list[dict]]) -> None:
    """Start the Flask review server on the fixed port without opening a browser."""
    app = _make_app(categories)
    app.run(host="localhost", port=REVIEW_PORT, use_reloader=False)


def _html(token: str) -> str:
    return _PAGE.replace("/*TOKENS*/", TOKENS_PATH.read_text()).replace("__SESSION_TOKEN__", token)


_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MacMaid — Review Files</title>
<style>
/*TOKENS*/
  body{padding-block:16px;margin:0}
  #sticky{position:sticky;top:0;z-index:100;background:var(--bg);padding-bottom:4px}
  h1{margin:0 0 12px;font-size:1.25rem}
  .tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;border-bottom:2px solid var(--line);padding-bottom:8px}
  .badge{display:inline-block;margin-left:10px;padding:0 10px;border-radius:12px;border:1px solid var(--on-btn)}
  .controls{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap}
  input[type=text]{flex:1;min-width:200px;border-width:2px}
  input[type=text]::placeholder{color:var(--dim);opacity:1}
  input[type=checkbox]{width:24px;height:24px}
  /* Cells wrap anywhere for long paths; a button label must not break mid-word. */
  td button{white-space:nowrap}
  /* Dashed, not faded: dimmed letters on a control are refused. */
  button:disabled{opacity:1;border:2px dashed var(--edge-grey)}
  table{width:100%;border-collapse:collapse}
  th{text-align:left;padding:7px 8px;border-bottom:2px solid var(--line);cursor:pointer;user-select:none;
     position:sticky;top:var(--thead-top,0);background:var(--bg);z-index:99}
  th.no-sort{cursor:default}
  th:not(.no-sort):hover{text-decoration:underline}
  td{padding:5px 8px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}
  tr{cursor:pointer}
  tr:hover td{background:var(--panel-2)}
  tr.sel td{background:#1e3a52}
  tr.sel:hover td{background:#254a68}
  .size{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;overflow-wrap:normal}
  .path{color:var(--dim)}
  #note:not(:empty){margin-bottom:10px}
  .pager{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:10px 0}
  .summary{margin-top:10px;min-height:36px;overflow-wrap:anywhere}
  .freed{color:var(--ok)}
  .err{color:var(--bad)}
  .si{margin-left:4px}
  #toast{position:fixed;bottom:20px;right:var(--gutter);background:var(--btn-grey);color:var(--on-btn);padding:10px 16px;
         border:2px solid var(--edge-grey);border-radius:6px;display:none;z-index:999}
  @media (max-width:900px){
    #sticky,th{position:static}
    table,tbody,thead{display:block}
    tr{display:flex;flex-wrap:wrap;align-items:center;border-bottom:2px solid var(--line)}
    th,td{border-bottom:0}
    td.path,td:nth-child(2){flex-basis:100%}
  }
</style>
</head>
<body>
<div id="sticky">
<h1>&#x1f9f9; MacMaid &#x2014; Review Files</h1>
<div class="tabs" id="tabBar"></div>
<div class="controls">
  <input type="text" id="filter" placeholder="Filter by name or path&#x2026;" oninput="applyFilter()">
  <button class="destroy" id="trashBtn" onclick="moveToTrash()" disabled>
    Move to Trash (<span id="selCount">0</span> files, <span id="selSize">0 B</span>)
  </button>
  <button class="affirm" onclick="done()">Done</button>
  <span id="count"></span>
</div>
<div id="note"></div>
</div>
<table>
  <thead id="thead"><tr></tr></thead>
  <tbody id="tbody"></tbody>
</table>
<div class="pager">
  <button class="secondary" id="prevBtn" onclick="goPage(-1)" disabled>&#x2039; Prev</button>
  <span id="pageInfo"></span>
  <button class="secondary" id="nextBtn" onclick="goPage(1)" disabled>Next &#x203a;</button>
</div>
<div class="summary" id="summary"></div>
<div id="toast"></div>
<script>
var tabs={},currentTab=null,pathMap={},bytesFreed=0,PAGE=200;
var TOKEN='__SESSION_TOKEN__';
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-MacMaid-Token':TOKEN},body:JSON.stringify(body||{})});}
async function refused(r){
  if(r.status!==403)return false;
  var d=await r.json();
  document.getElementById('note').innerHTML='<span class="err">'+esc(d.error)+'</span>';
  setStickyOffset();
  return true;
}
var BASE_COLS=[
  {key:'label',label:'Name',sort:true},
  {key:'path',label:'Full Path',sort:true,cls:'path'},
  {key:'size_bytes',label:'Size',sort:true,cls:'size'}
];
var NOTES={
  'Mail Store':'This is your whole mail folder. Some of its mail may exist nowhere else.',
  'iOS Backups':'Remove old devices or duplicate backups only.'
};
var CONFIRMS={
  'Mail Store':'This is your WHOLE mail folder (~/Library/Mail). Mail kept only on this Mac would be lost.',
  'iOS Backups':'A device backup cannot be recreated once the device is gone or has changed.'
};
var COLS={
  'iOS Backups':BASE_COLS.concat([{key:'last_backup',label:'Last Backup',sort:true}]),
  'Large & Old Files':[
    {key:'label',label:'Name',sort:true},
    {key:'path',label:'Full Path',sort:true,cls:'path'},
    {key:'size_bytes',label:'Size',sort:true,cls:'size'},
    {key:'age_days',label:'Age (days)',sort:true,cls:'size'},
    {key:'last_modified',label:'Last Modified',sort:true}
  ],
  'Duplicates':[
    {key:'label',label:'Name',sort:true},
    {key:'path',label:'Full Path',sort:true,cls:'path'},
    {key:'size_bytes',label:'Size',sort:true,cls:'size'},
    {key:'duplicate_of',label:'Duplicate of',sort:false}
  ]
};
function cols(){return COLS[currentTab]||BASE_COLS;}
function makeTab(){return{allFiles:[],filtered:[],selected:new Set(),page:0,sortKey:'size_bytes',sortAsc:false,loaded:false};}
function st(){return tabs[currentTab];}
function setStickyOffset(){var h=document.getElementById('sticky').offsetHeight;document.documentElement.style.setProperty('--thead-top',h+'px');}
window.addEventListener('resize',setStickyOffset);
function fmt(b){if(b>=1e9)return(b/1e9).toFixed(1)+' GB';if(b>=1e6)return(b/1e6).toFixed(1)+' MB';if(b>=1e3)return(b/1e3).toFixed(0)+' KB';return b+' B';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function val(f,k){
  if(k==='age_days')return f.meta&&f.meta.age_days!=null?f.meta.age_days:0;
  if(k==='last_modified')return f.meta&&f.meta.last_modified?f.meta.last_modified:'';
  if(k==='last_backup')return f.meta&&f.meta.last_backup?f.meta.last_backup:'';
  if(k==='duplicate_of')return f.meta&&f.meta.duplicate_of?f.meta.duplicate_of:'';
  return f[k]!=null?f[k]:'';
}
function cellHtml(f,col){
  var v=val(f,col.key);
  var cls=col.cls?' class="'+col.cls+'"':'';
  if(col.key==='size_bytes')return'<td class="size">'+fmt(f.size_bytes)+'</td>';
  if(col.key==='age_days')return'<td class="size">'+(v||'\u2014')+'</td>';
  if(col.key==='path')return'<td class="path" title="'+esc(f.path)+'">'+esc(f.path)+'</td>';
  if(col.key==='duplicate_of'){var keeper=v?v.split('/').pop():'\u2014';return'<td class="path" title="'+esc(v)+'">'+esc(keeper)+'</td>';}
  return'<td'+cls+'>'+esc(v||'\u2014')+'</td>';
}
async function init(){
  var r=await fetch('/api/tabs');
  var counts=await r.json();
  Object.keys(counts).forEach(function(name){tabs[name]=makeTab();tabs[name].count=counts[name];});
  renderTabBar(counts);
  var first=Object.keys(counts)[0];
  if(first)await switchTab(first);
  setStickyOffset();
}
function renderTabBar(counts){
  var bar=document.getElementById('tabBar');
  bar.innerHTML=Object.keys(tabs).map(function(name){
    var active=name===currentTab?' active':' secondary';
    var c=tabs[name].loaded?tabs[name].allFiles.length:(counts?counts[name]:tabs[name].count);
    return'<button class="tab-btn'+active+'" data-tab="'+esc(name)+'">'
      +(name===currentTab?'\\u25b6 ':'')+esc(name)+'<span class="badge">'+(typeof c==='number'?c.toLocaleString():c)+'</span></button>';
  }).join('');
  bar.querySelectorAll('.tab-btn').forEach(function(btn){
    btn.addEventListener('click',function(){switchTab(this.dataset.tab);});
  });
}
async function switchTab(name){
  currentTab=name;
  document.getElementById('note').textContent=NOTES[name]||'';
  document.getElementById('filter').value='';
  renderTabBar();
  if(!st().loaded){
    var r=await fetch('/api/files/'+encodeURIComponent(name));
    var items=await r.json();
    items.forEach(function(f){pathMap[f.path]=f;});
    st().allFiles=items;
    st().loaded=true;
    renderTabBar();
  }
  renderTableHeader();
  applyFilter();
  setStickyOffset();
}
function renderTableHeader(){
  var c=cols();
  var thead=document.getElementById('thead');
  var html='<th><input type="checkbox" id="selectAll" onchange="toggleAll(this.checked)"></th>';
  c.forEach(function(col){
    var ns=col.sort?'':' no-sort';
    var al=col.cls==='size'?' style="text-align:right"':'';
    var dk=col.sort?' data-sortkey="'+esc(col.key)+'"':'';
    html+='<th class="'+ns.trim()+'"'+al+dk+'>'+esc(col.label)+'<span class="si" id="si-'+col.key+'"></span></th>';
  });
  html+='<th class="no-sort"></th>';
  thead.innerHTML='<tr>'+html+'</tr>';
  thead.querySelectorAll('th[data-sortkey]').forEach(function(th){
    th.addEventListener('click',function(){sortBy(this.dataset.sortkey);});
  });
}
function applyFilter(){
  if(!currentTab||!st().loaded)return;
  var q=document.getElementById('filter').value.toLowerCase();
  st().filtered=st().allFiles.filter(function(f){return f.label.toLowerCase().indexOf(q)>=0||f.path.toLowerCase().indexOf(q)>=0;});
  st().page=0;
  sortAndRender();
}
function sortBy(k){var s=st();if(s.sortKey===k)s.sortAsc=!s.sortAsc;else{s.sortKey=k;s.sortAsc=k!=='size_bytes';}s.page=0;sortAndRender();}
function sortAndRender(){
  var s=st();
  s.filtered.sort(function(a,b){var av=val(a,s.sortKey),bv=val(b,s.sortKey);return av<bv?(s.sortAsc?-1:1):av>bv?(s.sortAsc?1:-1):0;});
  cols().forEach(function(col){var el=document.getElementById('si-'+col.key);if(el)el.textContent=s.sortKey===col.key?(s.sortAsc?'\u25b2':'\u25bc'):'';});
  renderTable();
}
function renderTable(){
  var s=st();
  var pages=Math.ceil(s.filtered.length/PAGE)||1;
  var start=s.page*PAGE,end=Math.min(start+PAGE,s.filtered.length),slice=s.filtered.slice(start,end);
  var body=document.getElementById('tbody');body.innerHTML='';
  slice.forEach(function(f){
    var tr=document.createElement('tr');
    tr.dataset.path=f.path;
    if(s.selected.has(f.path))tr.classList.add('sel');
    tr.addEventListener('click',function(e){if(e.target.closest('button,input'))return;toggleRow(tr);});
    var chk=s.selected.has(f.path)?'checked ':'';
    var cells=cols().map(function(col){return cellHtml(f,col);}).join('');
    tr.innerHTML='<td><input type="checkbox" '+chk+'></td>'+cells+'<td><button class="reveal secondary" title="Reveal in Finder">Show</button></td>';
    tr.querySelector('input').addEventListener('click',function(e){e.stopPropagation();rowChk(this);});
    tr.querySelector('.reveal').addEventListener('click',function(e){e.stopPropagation();reveal(f.path);});
    body.appendChild(tr);
  });
  document.getElementById('count').textContent=(end?start+1+'\u2013'+end:'0')+' of '+s.filtered.length.toLocaleString()+' files';
  document.getElementById('pageInfo').textContent='Page '+(s.page+1)+' / '+pages;
  document.getElementById('prevBtn').disabled=s.page===0;
  document.getElementById('nextBtn').disabled=s.page>=pages-1;
  updateSel();
}
function toggleRow(tr){var s=st();var cb=tr.querySelector('input[type=checkbox]');cb.checked=!cb.checked;if(cb.checked){s.selected.add(tr.dataset.path);tr.classList.add('sel');}else{s.selected.delete(tr.dataset.path);tr.classList.remove('sel');}updateSel();}
function rowChk(cb){var s=st();var tr=cb.closest('tr');if(cb.checked){s.selected.add(tr.dataset.path);tr.classList.add('sel');}else{s.selected.delete(tr.dataset.path);tr.classList.remove('sel');}updateSel();}
function updateSel(){
  var s=st();
  var sz=0;s.selected.forEach(function(p){var f=pathMap[p];if(f)sz+=f.size_bytes;});
  document.getElementById('selCount').textContent=s.selected.size;
  document.getElementById('selSize').textContent=fmt(sz);
  document.getElementById('trashBtn').disabled=s.selected.size===0;
  var start=s.page*PAGE,pageFiles=s.filtered.slice(start,start+PAGE);
  var sa=document.getElementById('selectAll');
  var allChk=pageFiles.length>0&&pageFiles.every(function(f){return s.selected.has(f.path);});
  var someChk=pageFiles.some(function(f){return s.selected.has(f.path);});
  sa.checked=allChk;sa.indeterminate=!allChk&&someChk;
}
function toggleAll(c){var s=st();var start=s.page*PAGE;s.filtered.slice(start,start+PAGE).forEach(function(f){if(c)s.selected.add(f.path);else s.selected.delete(f.path);});renderTable();}
function goPage(d){var s=st();var pages=Math.ceil(s.filtered.length/PAGE)||1;s.page=Math.max(0,Math.min(s.page+d,pages-1));renderTable();window.scrollTo(0,0);}
async function moveToTrash(){
  var s=st();
  var paths=Array.from(s.selected);
  var shown=new Set(s.filtered.map(function(f){return f.path;}));
  var hidden=paths.filter(function(p){return!shown.has(p);}).length;
  var warn=hidden?'\\n\\n'+'Hidden by the current filter: '+hidden+'.':'';
  if(CONFIRMS[currentTab])warn+='\\n\\n'+CONFIRMS[currentTab]+' The nightly clean can delete it permanently from the Trash, as soon as its next run.';
  if(!confirm('Move '+paths.length+' file(s) to Trash?'+warn))return;
  var r=await post('/api/delete',{paths:paths});
  if(await refused(r))return;
  var res=await r.json();
  bytesFreed+=res.bytes_freed;
  var gone=new Set((res.moved_paths||[]).concat(res.not_found_paths||[]));
  Object.keys(tabs).forEach(function(name){
    var t=tabs[name];
    if(!t.loaded)return;
    t.allFiles=t.allFiles.filter(function(f){return!gone.has(f.path);});
    gone.forEach(function(p){t.selected.delete(p);});
  });
  gone.forEach(function(p){delete pathMap[p];});
  var msg='';
  if(res.bytes_freed>0)msg+='<span class="freed">Freed '+fmt(bytesFreed)+' total this session.</span> ';
  if((res.not_found_paths||[]).length>0)msg+='<span class="err">'+(res.not_found_paths.length)+' file(s) no longer on disk \u2014 removed from list.</span> ';
  var changed=(res.changed_paths||[]).length;
  if(changed)msg+='<span class="err">'+changed+' item(s) changed since the scan \\u2014 left alone. Run a new scan to review them.</span> ';
  if(res.errors>0)msg+='<span class="err">'+res.errors+' error(s): '+res.error_paths.map(function(e){return esc(e[0]+' ('+e[1]+')');}).join(', ')+'</span>';
  document.getElementById('summary').innerHTML=msg||'Done.';
  applyFilter();
  renderTabBar();
  // The server's counts also cover tabs that have not been opened yet.
  var counts=await(await fetch('/api/tabs')).json();
  Object.keys(tabs).forEach(function(name){tabs[name].count=counts[name];});
  renderTabBar();
}
var toastTimer;
function toast(msg,color){var t=document.getElementById('toast');t.textContent=msg;t.style.background=color||'var(--btn-grey)';t.style.borderColor=color?'var(--edge-red)':'var(--edge-grey)';t.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.style.display='none';},3000);}
async function reveal(path){var r=await post('/api/reveal',{path:path});if(await refused(r))return;if(!r.ok){var d=await r.json();toast(d.error||'Could not reveal file','var(--btn-red)');}}
async function done(){var r=await post('/api/quit');if(await refused(r))return;if(!r.ok){document.getElementById('note').innerHTML='<span class="err">The server did not stop. Try Done again.</span>';setStickyOffset();return;}document.body.innerHTML='<p style="padding:40px 0">MacMaid server stopped. You can close this tab.</p>';}
init();
</script>
</body>
</html>"""
