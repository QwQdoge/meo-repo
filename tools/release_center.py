#!/usr/bin/env python3
"""Local graphical control panel for MeoArch repository releases.

The UI intentionally never handles signing keys or publication credentials.
It validates committed release inputs, shows manifest/recipe drift, and then
delegates publication to the protected GitHub Actions workflow through the
authenticated `gh` CLI.
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
REPO = "QwQdoge/meo-repo"
WORKFLOW = "release.yml"
SESSION_TOKEN = secrets.token_urlsafe(24)
VERSION = re.compile(r"^pkg(?P<field>ver|rel)=(?P<value>[^\s#]+)$", re.MULTILINE)


def run(command: list[str], timeout: int = 120) -> dict[str, object]:
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "code": -1, "output": str(exc)}
    output = (process.stdout + process.stderr).strip()
    return {"ok": process.returncode == 0, "code": process.returncode, "output": output}


def manifests(channel: str) -> list[str]:
    directory = ROOT / "manifests" / channel
    if channel not in {"beta", "stable"} or not directory.is_dir():
        return []
    return [str(path.relative_to(ROOT)) for path in sorted(directory.glob("*.json"), reverse=True)]


def pending_trains(channel: str) -> list[dict[str, object]]:
    """Preparation records are displayed separately and can never be dispatched."""
    if channel not in {"beta", "stable"}:
        return []
    records = []
    for path in sorted((ROOT / "manifests" / "pending").glob("*.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("channel") != channel:
            continue
        if payload.get("schemaVersion") != 1 or payload.get("status") != "preparation":
            raise ValueError(f"invalid preparation record: {path.name}")
        components = payload.get("components")
        if not isinstance(components, list) or not components:
            raise ValueError(f"no preparation components: {path.name}")
        names = set()
        for component in components:
            name = component.get("package", "")
            if (not re.fullmatch(r"[a-z0-9][a-z0-9+._-]*", name)
                    or name in names
                    or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", component.get("repository", ""))
                    or not re.fullmatch(r"[0-9a-f]{40}", component.get("reviewedCommit", ""))
                    or not isinstance(component.get("remaining"), list)
                    or not component["remaining"]
                    or not all(isinstance(item, str) and item for item in component["remaining"])):
                raise ValueError(f"invalid preparation component: {path.name}")
            names.add(name)
        records.append({**payload, "path": str(path.relative_to(ROOT))})
    return records


def read_manifest(path: str, channel: str) -> dict[str, object]:
    candidate = (ROOT / path).resolve()
    expected = (ROOT / "manifests" / channel).resolve()
    try:
        candidate.relative_to(expected)
    except ValueError as exc:
        raise ValueError("manifest is outside the selected channel") from exc
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    return payload


def manifest_components(path: str, channel: str) -> list[str]:
    try:
        payload = read_manifest(path, channel)
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    components = payload.get("components", {})
    return sorted(components) if isinstance(components, dict) else []


def recipe_version(package: str) -> str | None:
    path = ROOT / "packages" / package / "PKGBUILD"
    if not path.is_file():
        return None
    source = path.read_text(encoding="utf-8")
    fields = {
        match.group("field"): match.group("value").strip("'\"")
        for match in VERSION.finditer(source)
    }
    if set(fields) != {"ver", "rel"}:
        return None
    return f"{fields['ver']}-{fields['rel']}"


def manifest_health(path: str, channel: str) -> dict[str, object]:
    try:
        payload = read_manifest(path, channel)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "components": [], "output": str(exc)}
    components = payload.get("components", {})
    if not isinstance(components, dict):
        return {"ok": False, "components": [], "output": "manifest has no component map"}
    rows: list[dict[str, object]] = []
    all_ok = True
    for name, metadata in sorted(components.items()):
        if not isinstance(metadata, dict):
            rows.append({"name": name, "expected": "", "recipe": "", "epoch": False, "ok": False})
            all_ok = False
            continue
        expected = str(metadata.get("expectedVersion", ""))
        actual = recipe_version(name) or "missing recipe"
        epoch = metadata.get("sourceDateEpoch")
        epoch_ok = isinstance(epoch, int) and not isinstance(epoch, bool) and epoch > 0
        row_ok = bool(expected) and expected == actual and epoch_ok
        all_ok = all_ok and row_ok
        rows.append({
            "name": name,
            "expected": expected,
            "recipe": actual,
            "epoch": epoch_ok,
            "ok": row_ok,
        })
    return {"ok": all_ok, "components": rows, "output": "manifest and recipes agree" if all_ok else "manifest requires attention"}


def git_sync(fetch: bool = False) -> dict[str, object]:
    if fetch:
        fetched = run(["git", "fetch", "origin", "main", "--quiet"], timeout=45)
        if not fetched["ok"]:
            return {"ok": False, "output": "could not refresh origin/main\n" + str(fetched["output"])}
    local = run(["git", "rev-parse", "HEAD"], timeout=10)
    remote = run(["git", "rev-parse", "origin/main"], timeout=10)
    if not local["ok"] or not remote["ok"]:
        return {"ok": False, "output": "origin/main is unavailable", "local": "", "remote": ""}
    local_sha = str(local["output"]).strip()
    remote_sha = str(remote["output"]).strip()
    return {
        "ok": local_sha == remote_sha,
        "local": local_sha,
        "remote": remote_sha,
        "output": "local HEAD matches origin/main" if local_sha == remote_sha else "local HEAD does not match origin/main",
    }


def validate_selection(channel: str, manifest: str, candidate: str, full: bool = False) -> dict[str, object]:
    if channel not in {"beta", "stable"}:
        return {"ok": False, "output": "channel must be beta or stable"}
    if manifest not in manifests(channel):
        return {"ok": False, "output": "select a committed manifest from the selected channel"}
    components = manifest_components(manifest, channel)
    if channel == "beta" and not candidate:
        return {"ok": False, "output": "Beta requires one explicit candidate"}
    if candidate and candidate not in components:
        return {"ok": False, "output": f"candidate {candidate!r} is not present in this manifest"}

    dirty = run(["git", "status", "--porcelain", "--", manifest])
    if not dirty["ok"]:
        return dirty
    if dirty["output"]:
        return {"ok": False, "output": "manifest has uncommitted changes; commit it before release"}
    tracked = run(["git", "ls-files", "--error-unmatch", manifest])
    if not tracked["ok"]:
        return {"ok": False, "output": "manifest is not tracked by git"}

    commands = [
        [sys.executable, "scripts/validate_manifest.py", manifest, "--channel", channel],
    ]
    closure = [sys.executable, "scripts/validate_release_closure.py", manifest]
    if candidate:
        closure.extend(["--candidate", candidate])
    commands.append(closure)
    if full:
        commands.append([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    logs: list[str] = []
    for command in commands:
        result = run(command, timeout=240)
        logs.append("$ " + " ".join(command) + "\n" + str(result["output"]))
        if not result["ok"]:
            return {"ok": False, "output": "\n\n".join(logs)}
    return {"ok": True, "output": "\n\n".join(logs) or "Preflight passed."}


def gh_ready() -> dict[str, object]:
    result = run(["gh", "auth", "status"], timeout=20)
    return {"ok": bool(result["ok"]), "output": result["output"]}


def recent_runs() -> list[dict[str, object]]:
    result = run([
        "gh", "run", "list", "--repo", REPO, "--workflow", WORKFLOW,
        "--limit", "10", "--json",
        "databaseId,status,conclusion,displayTitle,createdAt,url,headSha",
    ], timeout=30)
    if not result["ok"]:
        return []
    try:
        payload = json.loads(str(result["output"]))
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def dispatch(channel: str, manifest: str, candidate: str) -> dict[str, object]:
    preflight = validate_selection(channel, manifest, candidate, full=True)
    if not preflight["ok"]:
        return preflight
    sync = git_sync(fetch=True)
    if not sync["ok"]:
        return {"ok": False, "output": str(sync["output"]) + "\nPush/sync main before dispatching a release."}
    auth = gh_ready()
    if not auth["ok"]:
        return {"ok": False, "output": "GitHub CLI is not authenticated. Run: gh auth login"}
    command = [
        "gh", "workflow", "run", WORKFLOW,
        "--repo", REPO,
        "--ref", "main",
        "-f", f"channel={channel}",
        "-f", f"manifest={manifest}",
    ]
    if candidate:
        command.extend(["-f", f"candidate={candidate}"])
    result = run(command, timeout=30)
    if result["ok"]:
        result["output"] = (str(result["output"]) + "\nRelease workflow dispatched. Signing and publication remain protected by the GitHub release environment.").strip()
    return result


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Meo Release Center</title>
<style>
:root{font-family:Inter,Roboto,system-ui,sans-serif;color-scheme:light dark;--bg:#f7f7fb;--surface:#fff;--ink:#202124;--muted:#6f7077;--accent:#6750a4;--accent2:#e9ddff;--line:#dedee8;--ok:#176b3a;--bad:#b3261e}
@media(prefers-color-scheme:dark){:root{--bg:#121217;--surface:#1c1b20;--ink:#e7e1e9;--muted:#c9c3cc;--accent:#d0bcff;--accent2:#4f378b;--line:#49454f;--ok:#8bd6a8;--bad:#ffb4ab}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink)}main{max-width:1120px;margin:auto;padding:28px 22px 64px}.hero{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:24px}h1{font-size:34px;margin:0 0 6px}h2{margin-top:0}p{color:var(--muted);margin:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{background:var(--surface);border:1px solid var(--line);border-radius:24px;padding:22px;box-shadow:0 8px 30px #0000000b}.wide{grid-column:1/-1}.row{display:grid;grid-template-columns:150px 1fr;gap:14px;align-items:center;margin:14px 0}label{font-weight:650}select,button{font:inherit;border-radius:14px;border:1px solid var(--line);padding:11px 14px;background:var(--surface);color:var(--ink)}select{width:100%}button{cursor:pointer;font-weight:700}.primary{background:var(--accent);color:var(--bg);border-color:transparent}.tonal{background:var(--accent2);color:var(--ink);border-color:transparent}.danger{color:var(--bad)}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.status{display:inline-flex;align-items:center;gap:7px;padding:7px 11px;border-radius:999px;background:var(--accent2);font-size:13px;font-weight:700}.dot{width:8px;height:8px;border-radius:50%;background:var(--muted)}.ok .dot{background:var(--ok)}.bad .dot{background:var(--bad)}pre{white-space:pre-wrap;word-break:break-word;max-height:320px;overflow:auto;background:var(--bg);border-radius:16px;padding:14px;border:1px solid var(--line);font-size:12px}.runs,.health{display:grid;gap:10px}.run,.healthRow{border:1px solid var(--line);border-radius:16px;padding:13px 15px;display:flex;justify-content:space-between;gap:18px;align-items:center}.run small,.healthRow small{color:var(--muted)}a{color:var(--accent)}.steps{display:flex;gap:8px;flex-wrap:wrap}.step{padding:8px 12px;border-radius:999px;border:1px solid var(--line);font-size:13px}.note{margin-top:12px;font-size:13px;color:var(--muted)}.badText{color:var(--bad);font-weight:700}.okText{color:var(--ok);font-weight:700}@media(max-width:760px){.grid{grid-template-columns:1fr}.wide{grid-column:auto}.row{grid-template-columns:1fr}.hero{align-items:start;flex-direction:column}}
</style></head><body><main>
<div class="hero"><div><h1>Meo Release Center</h1><p>Prepare, validate and dispatch signed MeoArch releases without handling signing secrets locally.</p></div><div><span id="auth" class="status"><span class="dot"></span>Checking GitHub</span> <span id="sync" class="status"><span class="dot"></span>Checking main</span></div></div>
<div class="steps"><span class="step">1 · Select train</span><span class="step">2 · Inspect drift</span><span class="step">3 · Preflight</span><span class="step">4 · Protected publish</span><span class="step">5 · Remote smoke</span></div>
<div class="grid" style="margin-top:18px">
<section class="card wide"><h2>Next release · preparation</h2><p>Reviewed source commits awaiting integration and immutable release inputs. These records cannot be published.</p><div id="pending" class="health" style="margin-top:14px"></div></section>
<section class="card"><h2>Release selection</h2>
<div class="row"><label>Channel</label><select id="channel"><option value="beta">Beta</option><option value="stable">Stable</option></select></div>
<div class="row"><label>Manifest</label><select id="manifest"></select></div>
<div class="row"><label>Candidate</label><select id="candidate"></select></div>
<p class="note">Beta requires exactly one candidate. Stable may publish a full train or one atomic hotfix candidate.</p>
<div class="actions"><button class="tonal" id="refresh">Refresh</button><button id="quick">Validate selected candidate</button><button id="full">Full preflight</button></div>
</section>
<section class="card"><h2>Safety boundary</h2><p>This tool never imports GPG keys and never receives R2 or Cloudflare credentials. Dispatch is blocked unless local HEAD matches origin/main.</p>
<div class="actions"><button class="primary" id="release">Dispatch release</button></div><p class="note danger">Publishing is real. GitHub's protected release environment still performs signing and publication.</p></section>
<section class="card wide"><h2>Manifest health</h2><div id="health" class="health"></div></section>
<section class="card wide"><h2>Output</h2><pre id="output">Ready.</pre></section>
<section class="card wide"><h2>Recent release runs</h2><div id="runs" class="runs"></div></section>
</div></main>
<script>
const $=id=>document.getElementById(id), out=$('output');let token='';
async function api(path,opts={}){const headers={'Content-Type':'application/json',...(opts.headers||{})};if(token)headers['X-Meo-Token']=token;const r=await fetch(path,{...opts,headers});return r.json()}
function show(x){out.textContent=x.output||JSON.stringify(x,null,2)}
function text(tag,value,cls=''){const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n}
function option(value,label){const n=document.createElement('option');n.value=value;n.textContent=label;return n}
async function load(preserve=true){const oldManifest=preserve?$('manifest').value:'';const oldCandidate=preserve?$('candidate').value:'';const ch=$('channel').value;const s=await api('/api/state?channel='+encodeURIComponent(ch));token=s.token||token;
 $('auth').className='status '+(s.gh.ok?'ok':'bad');$('auth').textContent=s.gh.ok?'● GitHub ready':'● gh login required';
 $('sync').className='status '+(s.sync.ok?'ok':'bad');$('sync').textContent=s.sync.ok?'● main synced':'● main differs';
 $('manifest').replaceChildren(...s.manifests.map(x=>option(x,x.split('/').pop())));if(oldManifest&&s.manifests.includes(oldManifest))$('manifest').value=oldManifest;await components(oldCandidate);renderPending(s.pending);renderRuns(s.runs);await health()}
function renderPending(trains){const nodes=[];for(const train of trains||[]){nodes.push(text('h3',train.release+' · awaiting release inputs'));for(const c of train.components){const row=document.createElement('div');row.className='healthRow';const details=document.createElement('div');details.append(text('b',c.package),text('p',c.changes||''),text('small',`${c.repository} · reviewed ${c.reviewedCommit.slice(0,12)}`));const list=document.createElement('ul');for(const item of c.remaining)list.append(text('li',item));details.append(list);row.append(details);nodes.push(row)}}$('pending').replaceChildren(...(nodes.length?nodes:[text('p','No pending train recorded.')]))}
async function components(preferred=''){const ch=$('channel').value,m=$('manifest').value;if(!m){$('candidate').replaceChildren();return}const x=await api('/api/components?channel='+encodeURIComponent(ch)+'&manifest='+encodeURIComponent(m));const nodes=[];if(ch==='stable')nodes.push(option('','Full stable train'));for(const c of x.components)nodes.push(option(c,c));$('candidate').replaceChildren(...nodes);if(preferred&&x.components.includes(preferred))$('candidate').value=preferred}
async function health(){const ch=$('channel').value,m=$('manifest').value;if(!m){$('health').replaceChildren(text('p','No manifest selected.'));return}const x=await api('/api/health?channel='+encodeURIComponent(ch)+'&manifest='+encodeURIComponent(m));const rows=(x.components||[]).map(c=>{const row=document.createElement('div');row.className='healthRow';const left=document.createElement('div');left.append(text('b',c.name),document.createElement('br'),text('small',`manifest ${c.expected||'missing'} · recipe ${c.recipe||'missing'} · sourceDateEpoch ${c.epoch?'ok':'missing'}`));row.append(left,text('span',c.ok?'Ready':'Needs attention',c.ok?'okText':'badText'));return row});$('health').replaceChildren(...(rows.length?rows:[text('p',x.output||'No health data.')]))}
function renderRuns(runs){const nodes=(runs||[]).map(r=>{const row=document.createElement('div');row.className='run';const left=document.createElement('div');left.append(text('b',r.displayTitle||'Release'),document.createElement('br'),text('small',`${r.createdAt||''} · ${r.status}${r.conclusion?' / '+r.conclusion:''}`));const a=document.createElement('a');a.target='_blank';a.rel='noreferrer';a.href=r.url||'#';a.textContent='Open';row.append(left,a);return row});$('runs').replaceChildren(...(nodes.length?nodes:[text('p','No runs available.')]))}
async function validate(full){out.textContent='Running preflight…';const body={channel:$('channel').value,manifest:$('manifest').value,candidate:$('candidate').value,full};show(await api('/api/validate',{method:'POST',body:JSON.stringify(body)}))}
$('channel').onchange=()=>load(false);$('manifest').onchange=async()=>{await components();await health()};$('refresh').onclick=()=>load(true);$('quick').onclick=()=>validate(false);$('full').onclick=()=>validate(true);
$('release').onclick=async()=>{const summary=`${$('channel').value.toUpperCase()}\n${$('manifest').value}\n${$('candidate').value||'full train'}`;if(!confirm('Dispatch protected release?\n\n'+summary))return;out.textContent='Running full preflight, checking origin/main, and dispatching…';show(await api('/api/dispatch',{method:'POST',body:JSON.stringify({channel:$('channel').value,manifest:$('manifest').value,candidate:$('candidate').value})}));await load(true)};load(false);setInterval(()=>load(true),15000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    def send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == "/api/state":
            channel = query.get("channel", ["beta"])[0]
            self.send_json({"manifests": manifests(channel), "pending": pending_trains(channel), "gh": gh_ready(), "sync": git_sync(False), "runs": recent_runs(), "token": SESSION_TOKEN})
            return
        if parsed.path == "/api/components":
            channel = query.get("channel", ["beta"])[0]
            manifest = query.get("manifest", [""])[0]
            self.send_json({"components": manifest_components(manifest, channel)})
            return
        if parsed.path == "/api/health":
            channel = query.get("channel", ["beta"])[0]
            manifest = query.get("manifest", [""])[0]
            self.send_json(manifest_health(manifest, channel))
            return
        self.send_json({"ok": False, "output": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.headers.get("X-Meo-Token", "") != SESSION_TOKEN:
            self.send_json({"ok": False, "output": "invalid local session token"}, 403)
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_json({"ok": False, "output": "invalid JSON"}, 400)
            return
        channel = str(payload.get("channel", ""))
        manifest = str(payload.get("manifest", ""))
        candidate = str(payload.get("candidate", ""))
        if self.path == "/api/validate":
            self.send_json(validate_selection(channel, manifest, candidate, bool(payload.get("full"))))
            return
        if self.path == "/api/dispatch":
            self.send_json(dispatch(channel, manifest, candidate))
            return
        self.send_json({"ok": False, "output": "not found"}, 404)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch the local Meo Release Center")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Release Center must bind to localhost only")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Meo Release Center: {url}")
    if not args.no_browser:
        threading.Timer(0.25, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
