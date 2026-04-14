import logging
import os
import signal
import socket
import subprocess
import threading
import webbrowser

import cleaner as cleaner_mod
from flask import Flask, Response, jsonify, request

logging.getLogger("werkzeug").setLevel(logging.ERROR)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _make_app(items: list[dict]) -> Flask:
    app = Flask(__name__)
    path_index = {item["path"]: item for item in items}

    @app.get("/")
    def index():
        return Response(_html(), mimetype="text/html")

    @app.get("/api/files")
    def files():
        return jsonify(items)

    @app.post("/api/delete")
    def delete():
        paths = (request.get_json(silent=True) or {}).get("paths", [])
        to_clean = [path_index[p] for p in paths if p in path_index]
        result = cleaner_mod.clean_items(to_clean)
        return jsonify({
            "moved": result.moved,
            "errors": result.errors,
            "bytes_freed": result.bytes_freed,
            "error_paths": result.error_paths,
            "moved_paths": result.moved_paths,
        })

    @app.post("/api/reveal")
    def reveal():
        path = (request.get_json(silent=True) or {}).get("path", "")
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


def start(items: list[dict]) -> None:
    """Start the Flask review server and open the browser."""
    app = _make_app(items)
    port = _free_port()
    url = f"http://localhost:{port}"
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="localhost", port=port, use_reloader=False)


def _html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>MacMaid — Review Large Files</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:20px;background:#1a1a1a;color:#e0e0e0;margin:0}
  h1{color:#f0f0f0;margin-bottom:16px;font-size:20px}
  .controls{display:flex;gap:10px;margin-bottom:14px;align-items:center;flex-wrap:wrap}
  input[type=text]{flex:1;min-width:200px;padding:7px 12px;border-radius:6px;border:1px solid #444;background:#2a2a2a;color:#e0e0e0;font-size:13px}
  button{padding:7px 14px;border-radius:6px;border:none;cursor:pointer;font-size:13px;white-space:nowrap}
  .btn-trash{background:#c0392b;color:#fff}.btn-trash:disabled{background:#555;cursor:not-allowed}
  .btn-done{background:#27ae60;color:#fff}
  table{width:100%;border-collapse:collapse;font-size:13px}
  th{text-align:left;padding:7px 8px;border-bottom:2px solid #444;cursor:pointer;user-select:none;color:#aaa;white-space:nowrap}
  th:hover{color:#fff}
  td{padding:5px 8px;border-bottom:1px solid #222;white-space:nowrap;max-width:400px;overflow:hidden;text-overflow:ellipsis}
  tr:hover td{background:#252525}
  .size{text-align:right;font-variant-numeric:tabular-nums}
  .path{color:#888;font-size:12px}
  .reveal{cursor:pointer;opacity:.5;font-size:15px;border:none;background:none;color:inherit;padding:0}
  .reveal:hover{opacity:1}
  .summary{margin-top:10px;font-size:13px;color:#aaa;min-height:20px}
  .freed{color:#27ae60}
  .err{color:#e74c3c}
  .si{font-size:9px;margin-left:2px}
  #count{color:#888;font-size:13px}
</style>
</head>
<body>
<h1>&#x1f9f9; MacMaid &#x2014; Large Files Review</h1>
<div class="controls">
  <input type="text" id="filter" placeholder="Filter by name or path&#x2026;" oninput="applyFilter()">
  <button class="btn-trash" id="trashBtn" onclick="moveToTrash()" disabled>
    Move to Trash (<span id="selCount">0</span> files, <span id="selSize">0 B</span>)
  </button>
  <button class="btn-done" onclick="done()">Done</button>
  <span id="count"></span>
</div>
<table>
  <thead><tr>
    <th><input type="checkbox" id="selectAll" onchange="toggleAll(this.checked)"></th>
    <th onclick="sortBy('label')">Name<span class="si" id="si-label"></span></th>
    <th onclick="sortBy('path')">Full Path<span class="si" id="si-path"></span></th>
    <th onclick="sortBy('size_bytes')" style="text-align:right">Size<span class="si" id="si-size_bytes"></span></th>
    <th onclick="sortBy('age_days')" style="text-align:right">Age (days)<span class="si" id="si-age_days"></span></th>
    <th onclick="sortBy('last_modified')">Last Modified<span class="si" id="si-last_modified"></span></th>
    <th></th>
  </tr></thead>
  <tbody id="tbody"></tbody>
</table>
<div class="summary" id="summary"></div>
<script>
var allFiles=[],filtered=[],sortKey='size_bytes',sortAsc=false,bytesFreed=0;
function fmt(b){if(b>=1e9)return(b/1e9).toFixed(1)+' GB';if(b>=1e6)return(b/1e6).toFixed(1)+' MB';if(b>=1e3)return(b/1e3).toFixed(0)+' KB';return b+' B';}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
async function load(){var r=await fetch('/api/files');allFiles=await r.json();applyFilter();}
function applyFilter(){var q=document.getElementById('filter').value.toLowerCase();filtered=allFiles.filter(function(f){return f.label.toLowerCase().indexOf(q)>=0||f.path.toLowerCase().indexOf(q)>=0;});sortAndRender();}
function sortBy(k){if(sortKey===k)sortAsc=!sortAsc;else{sortKey=k;sortAsc=k!=='size_bytes';}sortAndRender();}
function val(f,k){if(k==='age_days')return f.meta&&f.meta.age_days!=null?f.meta.age_days:0;if(k==='last_modified')return f.meta&&f.meta.last_modified?f.meta.last_modified:'';return f[k];}
function sortAndRender(){filtered.sort(function(a,b){var av=val(a,sortKey),bv=val(b,sortKey);return av<bv?(sortAsc?-1:1):av>bv?(sortAsc?1:-1):0;});['label','path','size_bytes','age_days','last_modified'].forEach(function(k){var el=document.getElementById('si-'+k);if(el)el.textContent=sortKey===k?(sortAsc?'&#x25b2;':'&#x25bc;'):'';});renderTable();}
function renderTable(){var body=document.getElementById('tbody');body.innerHTML='';filtered.forEach(function(f){var tr=document.createElement('tr');tr.dataset.path=f.path;tr.innerHTML='<td><input type="checkbox" onchange="updateSel()"></td>'+'<td>'+esc(f.label)+'</td>'+'<td class="path" title="'+esc(f.path)+'">'+esc(f.path)+'</td>'+'<td class="size">'+fmt(f.size_bytes)+'</td>'+'<td class="size">'+(f.meta&&f.meta.age_days!=null?f.meta.age_days:'&#x2014;')+'</td>'+'<td>'+(f.meta&&f.meta.last_modified?f.meta.last_modified:'&#x2014;')+'</td>'+'<td><button class="reveal" title="Reveal in Finder" data-path="'+esc(f.path)+'" onclick="reveal(this.dataset.path)">&#x1f4c2;</button></td>';body.appendChild(tr);});document.getElementById('count').textContent=filtered.length.toLocaleString()+' files shown';updateSel();}
function updateSel(){var rows=document.querySelectorAll('#tbody tr');var cnt=0,sz=0;var pathMap={};allFiles.forEach(function(f){pathMap[f.path]=f;});rows.forEach(function(tr){var cb=tr.querySelector('input');if(cb&&cb.checked){cnt++;var f=pathMap[tr.dataset.path];if(f)sz+=f.size_bytes;}});document.getElementById('selCount').textContent=cnt;document.getElementById('selSize').textContent=fmt(sz);document.getElementById('trashBtn').disabled=cnt===0;}
function toggleAll(c){document.querySelectorAll('#tbody input[type=checkbox]').forEach(function(cb){cb.checked=c;});updateSel();}
async function moveToTrash(){var paths=[];document.querySelectorAll('#tbody tr').forEach(function(tr){var cb=tr.querySelector('input');if(cb&&cb.checked)paths.push(tr.dataset.path);});if(!confirm('Move '+paths.length+' file(s) to Trash?'))return;var r=await fetch('/api/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paths:paths})});var res=await r.json();bytesFreed+=res.bytes_freed;var deleted=new Set(res.moved_paths||[]);allFiles=allFiles.filter(function(f){return!deleted.has(f.path);});var msg='<span class="freed">Freed '+fmt(bytesFreed)+' total this session.</span>';if(res.errors>0)msg+=' <span class="err">'+res.errors+' error(s): '+res.error_paths.map(function(e){return esc(e[0]);}).join(', ')+'</span>';document.getElementById('summary').innerHTML=msg;applyFilter();}
async function reveal(path){await fetch('/api/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:path})});}
async function done(){await fetch('/api/quit',{method:'POST'});document.body.innerHTML='<p style="padding:40px;color:#aaa;font-family:sans-serif">MacMaid server stopped. You can close this tab.</p>';}
load();
</script>
</body>
</html>"""
