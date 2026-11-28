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
from typing import Callable

import cleaner as cleaner_mod
import config as cfg
from modules import mail as mail_module
from flask import Flask, Response, jsonify, request

logging.getLogger("werkzeug").setLevel(logging.ERROR)

REVIEW_PORT = 5888
# The server only listens on loopback, but a web page whose own domain is re-pointed
# at 127.0.0.1 (DNS rebinding) still reaches it, under that domain's name.
LOCAL_HOST = re.compile(r"(localhost|127\.0\.0\.1|\[::1\])(:\d+)?", re.IGNORECASE)
LOCAL_ORIGIN = re.compile(r"http://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?", re.IGNORECASE)
TOKEN_HEADER = "X-MacMaid-Token"
STALE_PAGE = "This page is from an earlier MacMaid session. Reload it, then try again."
SCAN_RUNNING = "A scan is running. Wait for it to finish, then try again."
NOT_REMOVABLE = "Nothing in this category can be removed from here."
EMPTY_TRASH_UNCONFIRMED = "Emptying the Trash needs its own confirmation. Use the Empty old Trash button."
MAIL_CATEGORY = "Mail Store"
WHOLE_MAIL_WARNING = ("This is your WHOLE mail folder (~/Library/Mail). "
                      "Mail kept only on this Mac would be lost.")
WHOLE_MAIL_UNCONFIRMED = ("Moving your whole mail folder (~/Library/Mail) needs its own confirmation: "
                          "mail kept only on this Mac would be lost. Use the Move to Trash button on the Mail Store tab.")


def is_whole_mail(category: str, item: dict) -> bool:
    return category == MAIL_CATEGORY or item.get("path") == mail_module.MAIL_DIR


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


def _save_results(results: list[dict]) -> bool:
    """Write atomically, so `--review` never reads half a file. False if it could not be saved."""
    temp = RESULTS_PATH.with_name(RESULTS_PATH.name + ".tmp")
    try:
        temp.write_text(json.dumps(results))
        os.replace(temp, RESULTS_PATH)
        return True
    except OSError:
        return False


def _review_results(categories: dict[str, list[dict]]) -> list[dict]:
    """The saved scan's review categories, shaped like module results."""
    return [{"category": name, "risk": "review", "action": "trash", "items": list(items),
             "suggestion": ""} for name, items in categories.items()]


def _retention_days() -> int:
    return cfg.get("trash_retention_days") or cleaner_mod.DEFAULT_TRASH_RETENTION_DAYS


def _make_app(categories: dict[str, list[dict]],
              scan: Callable[[str], dict] | None = None, modules: list[str] = ()) -> Flask:
    """The review page for `categories`, or with `scan` the whole scan, report and clean flow.

    Every item goes to the Trash. The one permanent deletion is the Trash's own old
    entries, emptied only on a separate confirmation.
    """
    app = Flask(__name__)
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state = {"scanning": False, "scan_id": 0, "progress": [], "save_failed": False}
    # Mutable per-category lists (deletions splice these); one path can be listed in more than one
    cat_lists: dict[str, list[dict]] = {}
    info: dict[str, dict] = {}

    def load(results: list[dict]) -> None:
        cat_lists.clear()
        info.clear()
        for r in results:
            cat_lists[r["category"]] = list(r["items"])
            info[r["category"]] = {"risk": r["risk"], "action": r["action"],
                                   "suggestion": r.get("suggestion", ""), "tab": bool(r["items"])}

    load(_review_results(categories))

    def tab_names() -> list[str]:
        return [name for name in cat_lists if info[name]["tab"]]

    @app.before_request
    def guard():
        if not LOCAL_HOST.fullmatch(request.headers.get("Host", "")):
            return jsonify({"error": "Open this page as http://localhost"}), 403
        if request.method != "POST":
            return None
        # Every POST acts on the Mac, so each must come from this session's page.
        origin = request.headers.get("Origin")
        sent = request.headers.get(TOKEN_HEADER, "")
        if (origin is not None and not LOCAL_ORIGIN.fullmatch(origin)) \
                or not secrets.compare_digest(sent.encode(), token.encode()):
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

    @app.get("/api/state")
    def get_state():
        with lock:
            return jsonify({
                "can_scan": scan is not None, "scanning": state["scanning"],
                "scan_id": state["scan_id"], "progress": state["progress"],
                "save_failed": state["save_failed"],
                "retention_days": _retention_days(),
                "categories": [{"name": name, **info[name], "count": len(items),
                                "size": sum(i.get("size_bytes", 0) for i in items)}
                               for name, items in cat_lists.items()],
            })

    @app.get("/api/tabs")
    def tabs():
        return jsonify({name: len(cat_lists[name]) for name in tab_names()})

    @app.get("/api/files")
    def files():
        first = next(iter(tab_names()), None)
        return jsonify(cat_lists[first] if first else [])

    @app.get("/api/files/<tab>")
    def files_for_tab(tab: str):
        if tab not in cat_lists:
            return jsonify({"error": "Unknown tab"}), 404
        return jsonify(cat_lists[tab])

    def run_scan() -> None:
        results = []
        try:
            for step in state["progress"]:
                step["status"] = "scanning"
                result = scan(step["module"])
                results.append(result)
                step.update(status="done", category=result["category"],
                            size=sum(i.get("size_bytes", 0) for i in result["items"]))
            state["save_failed"] = not _save_results(results)
        finally:
            with lock:
                load(results)
                state["scanning"] = False
                state["scan_id"] += 1

    @app.post("/api/scan")
    def start_scan():
        if scan is None:
            return jsonify({"error": "This page shows a saved scan. Run MacMaid to scan again."}), 404
        with lock:
            if state["scanning"]:
                return jsonify({"error": SCAN_RUNNING}), 409
            state["scanning"] = True
            state["progress"] = [{"module": m, "label": m.replace("_", " ").title(),
                                  "status": "waiting"} for m in modules]
        threading.Thread(target=run_scan, daemon=True).start()
        return jsonify({"ok": True}), 202

    def chosen(body: dict) -> list[dict]:
        """Each chosen item, tagged with its own category's action for the cleaner."""
        paths = body.get("paths", [])
        tab = body.get("tab")
        names = [tab] if tab in cat_lists else [] if tab is not None else list(cat_lists)
        found: dict[str, dict] = {}
        for name in names:
            for item in cat_lists[name]:
                if item["path"] in paths and item["path"] not in found:
                    found[item["path"]] = {**item, "action": info[name]["action"], "category": name}
        return list(found.values())

    @app.post("/api/delete")
    def delete():
        body = request.get_json(silent=True) or {}
        with lock:
            if state["scanning"]:
                return jsonify({"error": SCAN_RUNNING}), 409
            to_clean = chosen(body)
            actions = {i["action"] for i in to_clean}
            if actions - {"trash", "empty-trash"}:
                return jsonify({"error": NOT_REMOVABLE}), 400
            if "empty-trash" in actions and body.get("empty_trash") is not True:
                return jsonify({"error": EMPTY_TRASH_UNCONFIRMED}), 400
            if any(is_whole_mail(i["category"], i) for i in to_clean) \
                    and body.get("confirm_whole_mail") is not True:
                return jsonify({"error": WHOLE_MAIL_UNCONFIRMED}), 400
            result = cleaner_mod.clean_items(to_clean, permanent=False,
                                             trash_retention_days=_retention_days())
            cleaner_mod.log_errors(result)
            # An emptied Trash folder stays listed while anything in it could not be removed.
            failed = [p for p, _ in result.error_paths]
            removed = {p for p in result.moved_paths or []
                       if not any(f == p or f.startswith(p + os.sep) for f in failed)}
            not_found = {p for p, e in result.error_paths if "not found" in e.lower()}
            removed |= not_found
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
            "removed_paths": sorted(removed),
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
        # Waits for a clean in progress, and never cuts a scan short.
        with lock:
            if state["scanning"]:
                return jsonify({"error": SCAN_RUNNING}), 409

        def _shutdown():
            import time
            time.sleep(0.3)
            os.kill(os.getpid(), signal.SIGINT)
        threading.Thread(target=_shutdown, daemon=True).start()
        return jsonify({"ok": True})

    return app


def _run(app: Flask) -> None:
    port = _free_port()
    url = f"http://localhost:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="localhost", port=port, use_reloader=False)


def start(categories: dict[str, list[dict]]) -> None:
    """Start the Flask review server and open the browser."""
    _run(_make_app(categories))


def start_app(modules: list[str], scan: Callable[[str], dict]) -> None:
    """Open the whole MacMaid flow in the browser; the page starts the first scan."""
    _run(_make_app({}, scan=scan, modules=modules))


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
<title>MacMaid</title>
<style>
/*TOKENS*/
  body{padding-block:16px;margin:0}
  [hidden]{display:none!important}
  #sticky{position:sticky;top:0;z-index:100;background:var(--bg);padding-bottom:4px}
  h1{margin:0 0 12px;font-size:1.25rem}
  .tabs{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;border-bottom:2px solid var(--line);padding-bottom:8px}
  .tabs:empty{display:none}
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
  tr.static{cursor:default}
  tr:hover td{background:var(--panel-2)}
  tr.sel td{background:#1e3a52}
  tr.sel:hover td{background:#254a68}
  .size{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;overflow-wrap:normal}
  .kind{white-space:nowrap}
  .path{color:var(--dim)}
  #note:not(:empty){margin-bottom:10px}
  #progressList{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(12em,1fr));gap:4px 24px}
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
<h1 id="title">&#x1f9f9; MacMaid &#x2014; Review Files</h1>
<div class="tabs" id="tabBar"></div>
<div class="controls">
  <button class="affirm" id="scanBtn" hidden>Scan again</button>
  <input type="text" id="filter" placeholder="Filter by name or path&#x2026;" oninput="applyFilter()">
  <button class="destroy" id="trashBtn" onclick="moveToTrash()" disabled>
    Move to Trash (<span id="selCount">0</span> files, <span id="selSize">0 B</span>)
  </button>
  <button class="destroy" id="emptyBtn" hidden>Empty old Trash</button>
  <button class="affirm" onclick="done()">Done</button>
  <span id="count"></span>
</div>
<div id="note"></div>
</div>
<div id="progress" hidden>
  <p id="progressHead"></p>
  <ol id="progressList"></ol>
</div>
<div id="results">
<table>
  <thead id="thead"><tr></tr></thead>
  <tbody id="tbody"></tbody>
</table>
<div class="pager" id="pager">
  <button class="secondary" id="prevBtn" onclick="goPage(-1)" disabled>&#x2039; Prev</button>
  <span id="pageInfo"></span>
  <button class="secondary" id="nextBtn" onclick="goPage(1)" disabled>Next &#x203a;</button>
</div>
</div>
<div class="summary" id="summary"></div>
<div id="toast"></div>
<script>
var tabs={},info={},summaryRows=[],currentTab=null,pathMap={},bytesFreed=0,PAGE=200;
var CAN_SCAN=false,RETENTION=7,SUMMARY='Summary';
var TOKEN='__SESSION_TOKEN__';
function post(url,body){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-MacMaid-Token':TOKEN},body:JSON.stringify(body||{})});}
function showError(msg){document.getElementById('note').innerHTML='<span class="err">'+esc(msg)+'</span>';setStickyOffset();}
async function refused(r){
  if(r.status!==403)return false;
  var d=await r.json();
  showError(d.error);
  return true;
}
// A refusal, or any other answer that is not a success, is shown and stops the action.
async function failed(r){
  if(await refused(r))return true;
  if(r.ok)return false;
  var d={};try{d=await r.json();}catch(e){}
  showError(d.error||'MacMaid did not answer. Run it again, then reload this page.');
  return true;
}
var BASE_COLS=[
  {key:'label',label:'Name',sort:true},
  {key:'path',label:'Full Path',sort:true,cls:'path'},
  {key:'size_bytes',label:'Size',sort:true,cls:'size'}
];
var INFO_COLS=[
  {key:'label',label:'Name',sort:true},
  {key:'size_bytes',label:'Size',sort:true,cls:'size'}
];
var MAIL_TAB='Mail Store';
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
// 'trash': choose items to move to the Trash; 'empty': the Trash's own old entries; 'info': nothing to remove.
function kindOf(name){var a=info[name]&&info[name].action;return a==='none'?'info':a==='empty-trash'?'empty':'trash';}
function kindLabel(c){
  if(c.action==='none')return'Information only';
  if(c.action==='empty-trash')return'Empty old Trash';
  return c.risk==='review'?'You choose':'Safe to clean';
}
function kind(){return currentTab===SUMMARY?'summary':kindOf(currentTab);}
function cols(){return kind()==='info'?INFO_COLS:(COLS[currentTab]||BASE_COLS);}
function makeTab(){return{allFiles:[],filtered:[],selected:new Set(),page:0,sortKey:'size_bytes',sortAsc:false,loaded:false};}
function st(){return tabs[currentTab];}
function setStickyOffset(){var h=document.getElementById('sticky').offsetHeight;document.documentElement.style.setProperty('--thead-top',h+'px');}
window.addEventListener('resize',setStickyOffset);
function fmt(b){if(b>=1e9)return(b/1e9).toFixed(1)+' GB';if(b>=1e6)return(b/1e6).toFixed(1)+' MB';if(b>=1e3)return(b/1e3).toFixed(0)+' KB';return b+' B';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function sizeOf(files){return files.reduce(function(n,f){return n+(f.size_bytes||0);},0);}
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
  if(col.key==='size_bytes')return'<td class="size">'+(f.size_bytes||kind()!=='info'?fmt(f.size_bytes):'—')+'</td>';
  if(col.key==='age_days')return'<td class="size">'+(v||'—')+'</td>';
  if(col.key==='path')return'<td class="path" title="'+esc(f.path)+'">'+esc(f.path)+'</td>';
  if(col.key==='duplicate_of'){var keeper=v?v.split('/').pop():'—';return'<td class="path" title="'+esc(v)+'">'+esc(keeper)+'</td>';}
  return'<td'+cls+'>'+esc(v||'—')+'</td>';
}
async function state(){return(await fetch('/api/state')).json();}
async function init(){
  document.getElementById('scanBtn').addEventListener('click',scanNow);
  document.getElementById('emptyBtn').addEventListener('click',emptyTrash);
  var s=await state();
  CAN_SCAN=s.can_scan;RETENTION=s.retention_days;
  if(CAN_SCAN){
    document.getElementById('title').textContent='\\u{1f9f9} MacMaid';
    document.getElementById('scanBtn').hidden=false;
  }
  if(s.scanning)return watchScan();
  if(CAN_SCAN&&s.scan_id===0)return scanNow();
  await show(s);
}
function remember(s){
  summaryRows=s.categories;
  s.categories.forEach(function(c){info[c.name]=c;if(tabs[c.name])tabs[c.name].count=c.count;});
}
async function show(s){
  tabs={};info={};pathMap={};currentTab=null;
  s.categories.forEach(function(c){if(c.tab){tabs[c.name]=makeTab();}});
  remember(s);
  document.getElementById('progress').hidden=true;
  document.getElementById('results').hidden=false;
  document.getElementById('scanBtn').disabled=false;
  var first=CAN_SCAN?SUMMARY:Object.keys(tabs)[0];
  if(first)await switchTab(first);
  if(s.save_failed)showError('This scan could not be saved, so main.py --review will show an older one.');
  setStickyOffset();
}
async function scanNow(){
  var r=await post('/api/scan');
  if(r.status!==409&&await failed(r))return;
  document.getElementById('summary').textContent='';
  await watchScan();
}
async function watchScan(){
  document.getElementById('scanBtn').disabled=true;
  ['filter','trashBtn','emptyBtn','results'].forEach(function(id){document.getElementById(id).hidden=true;});
  document.getElementById('tabBar').innerHTML='';
  document.getElementById('note').textContent='';
  document.getElementById('count').textContent='';
  document.getElementById('progress').hidden=false;
  setStickyOffset();
  for(;;){
    var s;
    try{s=await state();}catch(e){showError('Lost contact with MacMaid. Run it again, then reload this page.');return;}
    renderProgress(s.progress);
    if(!s.scanning)return show(s);
    await new Promise(function(done){setTimeout(done,500);});
  }
}
function renderProgress(steps){
  var finished=steps.filter(function(p){return p.status==='done';}).length;
  document.getElementById('progressHead').textContent='Scanning… '+finished+' of '+steps.length+' done';
  document.getElementById('progressList').innerHTML=steps.map(function(p){
    if(p.status==='done')return'<li>✓ '+esc(p.category)+(p.size?' — '+fmt(p.size):'')+'</li>';
    if(p.status==='scanning')return'<li>▶ '+esc(p.label)+' — scanning</li>';
    return'<li>· '+esc(p.label)+' — waiting</li>';
  }).join('');
}
function renderTabBar(){
  var bar=document.getElementById('tabBar');
  var names=(CAN_SCAN?[SUMMARY]:[]).concat(Object.keys(tabs));
  bar.innerHTML=names.map(function(name){
    var active=name===currentTab?' active':' secondary';
    var badge='';
    if(name!==SUMMARY){var t=tabs[name];var c=t.loaded?t.allFiles.length:t.count;badge='<span class="badge">'+c.toLocaleString()+'</span>';}
    return'<button class="tab-btn'+active+'" data-tab="'+esc(name)+'">'
      +(name===currentTab?'▶ ':'')+esc(name)+badge+'</button>';
  }).join('');
  bar.querySelectorAll('.tab-btn').forEach(function(btn){
    btn.addEventListener('click',function(){switchTab(this.dataset.tab);});
  });
}
async function switchTab(name){
  currentTab=name;
  var k=kind();
  document.getElementById('results').hidden=false;
  document.getElementById('filter').value='';
  document.getElementById('filter').hidden=k==='summary';
  document.getElementById('trashBtn').hidden=k!=='trash';
  document.getElementById('emptyBtn').hidden=k!=='empty';
  document.getElementById('pager').hidden=k==='summary';
  document.getElementById('note').textContent=k==='summary'?'':[NOTES[name],info[name]&&info[name].suggestion].filter(Boolean).join(' ');
  renderTabBar();
  if(k==='summary'){renderSummary();setStickyOffset();return;}
  var t=st();
  if(!t.loaded){
    var r=await fetch('/api/files/'+encodeURIComponent(name));
    var items=await r.json();
    // Another tab may have been opened, or a new scan started, while this one loaded.
    if(tabs[name]!==t)return;
    items.forEach(function(f){pathMap[f.path]=f;});
    t.allFiles=items;
    t.loaded=true;
    if(currentTab!==name)return;
    renderTabBar();
  }
  renderTableHeader();
  applyFilter();
  setStickyOffset();
}
function renderSummary(){
  document.getElementById('thead').innerHTML='<tr><th class="no-sort">Category</th><th class="no-sort">What happens</th>'
    +'<th class="no-sort" style="text-align:right">Items</th><th class="no-sort" style="text-align:right">Size</th>'
    +'<th class="no-sort">Details</th></tr>';
  var body=document.getElementById('tbody');body.innerHTML='';
  var total=0;
  summaryRows.forEach(function(c){
    if(c.action!=='none')total+=c.size;
    var tr=document.createElement('tr');
    tr.className='static';
    var name=tabs[c.name]?'<button class="secondary open-tab">'+esc(c.name)+'</button>':esc(c.name);
    tr.innerHTML='<td>'+name+'</td><td class="kind">'+kindLabel(c)+'</td><td class="size">'+c.count.toLocaleString()+'</td>'
      +'<td class="size">'+(c.size?fmt(c.size):'—')+'</td><td class="path">'+esc(c.suggestion||'')+'</td>';
    var open=tr.querySelector('.open-tab');
    if(open)open.addEventListener('click',function(){switchTab(c.name);});
    body.appendChild(tr);
  });
  document.getElementById('count').textContent=fmt(total)+' to clean or review';
}
function renderTableHeader(){
  var c=cols(),k=kind();
  var thead=document.getElementById('thead');
  var html=k==='trash'?'<th><input type="checkbox" id="selectAll" onchange="toggleAll(this.checked)"></th>':'';
  c.forEach(function(col){
    var ns=col.sort?'':' no-sort';
    var al=col.cls==='size'?' style="text-align:right"':'';
    var dk=col.sort?' data-sortkey="'+esc(col.key)+'"':'';
    html+='<th class="'+ns.trim()+'"'+al+dk+'>'+esc(col.label)+'<span class="si" id="si-'+col.key+'"></span></th>';
  });
  if(k!=='info')html+='<th class="no-sort"></th>';
  thead.innerHTML='<tr>'+html+'</tr>';
  thead.querySelectorAll('th[data-sortkey]').forEach(function(th){
    th.addEventListener('click',function(){sortBy(this.dataset.sortkey);});
  });
}
function applyFilter(){
  if(!currentTab||currentTab===SUMMARY||!st().loaded)return;
  var q=document.getElementById('filter').value.toLowerCase();
  st().filtered=st().allFiles.filter(function(f){return f.label.toLowerCase().indexOf(q)>=0||f.path.toLowerCase().indexOf(q)>=0;});
  st().page=0;
  sortAndRender();
}
function sortBy(k){var s=st();if(s.sortKey===k)s.sortAsc=!s.sortAsc;else{s.sortKey=k;s.sortAsc=k!=='size_bytes';}s.page=0;sortAndRender();}
function sortAndRender(){
  var s=st();
  s.filtered.sort(function(a,b){var av=val(a,s.sortKey),bv=val(b,s.sortKey);return av<bv?(s.sortAsc?-1:1):av>bv?(s.sortAsc?1:-1):0;});
  cols().forEach(function(col){var el=document.getElementById('si-'+col.key);if(el)el.textContent=s.sortKey===col.key?(s.sortAsc?'▲':'▼'):'';});
  renderTable();
}
function renderTable(){
  var s=st(),k=kind();
  var pages=Math.ceil(s.filtered.length/PAGE)||1;
  var start=s.page*PAGE,end=Math.min(start+PAGE,s.filtered.length),slice=s.filtered.slice(start,end);
  var body=document.getElementById('tbody');body.innerHTML='';
  slice.forEach(function(f){
    var tr=document.createElement('tr');
    tr.dataset.path=f.path;
    if(k!=='trash')tr.className='static';
    if(s.selected.has(f.path))tr.classList.add('sel');
    var cells=cols().map(function(col){return cellHtml(f,col);}).join('');
    var chk=k==='trash'?'<td><input type="checkbox" '+(s.selected.has(f.path)?'checked ':'')+'></td>':'';
    var show=k!=='info'?'<td><button class="reveal secondary" title="Reveal in Finder">Show</button></td>':'';
    tr.innerHTML=chk+cells+show;
    if(k==='trash'){
      tr.addEventListener('click',function(e){if(e.target.closest('button,input'))return;toggleRow(tr);});
      tr.querySelector('input').addEventListener('click',function(e){e.stopPropagation();rowChk(this);});
    }
    if(show)tr.querySelector('.reveal').addEventListener('click',function(e){e.stopPropagation();reveal(f.path);});
    body.appendChild(tr);
  });
  var noun=k==='info'?' items':' files';
  document.getElementById('count').textContent=(end?start+1+'–'+end:'0')+' of '+s.filtered.length.toLocaleString()+noun;
  document.getElementById('pageInfo').textContent='Page '+(s.page+1)+' / '+pages;
  document.getElementById('prevBtn').disabled=s.page===0;
  document.getElementById('nextBtn').disabled=s.page>=pages-1;
  updateSel();
}
function toggleRow(tr){var s=st();var cb=tr.querySelector('input[type=checkbox]');cb.checked=!cb.checked;if(cb.checked){s.selected.add(tr.dataset.path);tr.classList.add('sel');}else{s.selected.delete(tr.dataset.path);tr.classList.remove('sel');}updateSel();}
function rowChk(cb){var s=st();var tr=cb.closest('tr');if(cb.checked){s.selected.add(tr.dataset.path);tr.classList.add('sel');}else{s.selected.delete(tr.dataset.path);tr.classList.remove('sel');}updateSel();}
function updateSel(){
  var s=st(),k=kind();
  if(k==='empty'){
    var btn=document.getElementById('emptyBtn');
    btn.textContent='Empty old Trash ('+fmt(sizeOf(s.allFiles))+')';
    btn.disabled=s.allFiles.length===0;
  }
  if(k!=='trash')return;
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
  var ask=currentTab===MAIL_TAB?'Move your whole mail folder to the Trash?':'Move '+paths.length+' file(s) to Trash?';
  if(!confirm(ask+warn))return;
  var body={tab:currentTab,paths:paths};
  if(currentTab===MAIL_TAB)body.confirm_whole_mail=true;
  var r=await post('/api/delete',body);
  if(await failed(r))return;
  await cleaned(await r.json());
}
async function emptyTrash(){
  var s=st();
  var paths=s.allFiles.map(function(f){return f.path;});
  if(!confirm('Permanently delete everything that has been in the Trash for more than '+RETENTION+' days ('+fmt(sizeOf(s.allFiles))+')?'
    +'\\n\\nThis cannot be undone. Anything binned more recently stays in the Trash.'))return;
  var r=await post('/api/delete',{tab:currentTab,paths:paths,empty_trash:true});
  if(await failed(r))return;
  await cleaned(await r.json());
}
async function cleaned(res){
  bytesFreed+=res.bytes_freed;
  var gone=new Set(res.removed_paths||(res.moved_paths||[]).concat(res.not_found_paths||[]));
  Object.keys(tabs).forEach(function(name){
    var t=tabs[name];
    if(!t.loaded)return;
    t.allFiles=t.allFiles.filter(function(f){return!gone.has(f.path);});
    gone.forEach(function(p){t.selected.delete(p);});
  });
  gone.forEach(function(p){delete pathMap[p];});
  var msg='';
  if(res.bytes_freed>0)msg+='<span class="freed">Freed '+fmt(bytesFreed)+' total this session.</span> ';
  if((res.not_found_paths||[]).length>0)msg+='<span class="err">'+(res.not_found_paths.length)+' file(s) no longer on disk — removed from list.</span> ';
  var changed=(res.changed_paths||[]).length;
  if(changed)msg+='<span class="err">'+changed+' item(s) changed since the scan — left alone. Run a new scan to review them.</span> ';
  if(res.errors>0)msg+='<span class="err">'+res.errors+' error(s): '+res.error_paths.map(function(e){return esc(e[0]+' ('+e[1]+')');}).join(', ')+'</span>';
  document.getElementById('summary').innerHTML=msg||'Done.';
  applyFilter();
  // The server's counts also cover tabs that have not been opened yet.
  remember(await state());
  renderTabBar();
}
var toastTimer;
function toast(msg,color){var t=document.getElementById('toast');t.textContent=msg;t.style.background=color||'var(--btn-grey)';t.style.borderColor=color?'var(--edge-red)':'var(--edge-grey)';t.style.display='block';clearTimeout(toastTimer);toastTimer=setTimeout(function(){t.style.display='none';},3000);}
async function reveal(path){var r=await post('/api/reveal',{path:path});if(await refused(r))return;if(!r.ok){var d=await r.json();toast(d.error||'Could not reveal file','var(--btn-red)');}}
async function done(){var r=await post('/api/quit');if(await refused(r))return;if(r.status===409){await failed(r);return;}if(!r.ok){document.getElementById('note').innerHTML='<span class="err">The server did not stop. Try Done again.</span>';setStickyOffset();return;}document.body.innerHTML='<p style="padding:40px 0">MacMaid server stopped. You can close this tab.</p>';}
init();
</script>
</body>
</html>"""
