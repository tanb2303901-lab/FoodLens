"""Loopback diagnostic UI using real Supabase user auth and the real API.

Default: only http://127.0.0.1:8765. `--lan` (owner opt-in) also serves http://<Wi-Fi IP>:8765 so a
phone on the same Wi-Fi can try photos; the backend and Supabase stay on loopback and are reached
only by this server.

No model loading/training here. The separate test account owns its private scans;
credentials stay in the server's ignored session file, never in browser responses.
"""
from base64 import b64encode
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
PROCESSED = ROOT / "data/processed"
ORIGIN = "http://127.0.0.1:8765"
API = "http://127.0.0.1:8000"
AUTH = "http://127.0.0.1:54321"
SESSION = PROCESSED / "scan-test-session.json"
MAX_BODY = 10 * 1024 * 1024 + 65536
MAP75 = "foodlens-75-2026-10-16-v2"


CONTENT = ROOT / "docs/content/food-descriptions-vi-v1.json"
TEXT_FIELDS = ("short_intro", "origin_text", "ingredients_summary", "characteristics", "scope_note")


def draft_preview(food_id):
    """Latest content-file entry for owner review only; never presented as approved content."""
    try:
        document = json.loads(CONTENT.read_text(encoding="utf-8"))
        sources = {s["source_key"]: s for s in document["sources"]}
        entries = [e for e in document["descriptions"] if e["food_id"] == food_id]
        if not entries:
            return None
        entry = max(entries, key=lambda e: e["version"])
        cited = []
        for ref in entry["sources"]:
            source = sources[ref["source_key"]]
            if str(source.get("url", "")).startswith("https://"):
                cited.append({"title": source["title"], "publisher": source["publisher"], "url": source["url"],
                              "supports": ref["supports"], "locator": ref.get("locator")})
        return {"content_status": entry["content_status"], "version": entry["version"],
                "authoring_method": entry["authoring_method"], **{f: entry.get(f) for f in TEXT_FIELDS}, "sources": cited}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def describe(session, food_ids):
    """One real API description call per canonical food; a failure affects only that card."""
    cards = {}
    for food_id in food_ids:
        try:
            response = session.request("GET", "/v1/foods/" + food_id + "/description")
            api = response.json() if response.status_code == 200 else {"status": "error", "http_status": response.status_code}
        except (httpx.HTTPError, ValueError):
            api = {"status": "error"}
        cards[food_id] = {"api": api, "draft_preview": draft_preview(food_id)}
    return cards


def read_state(path):
    try:return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError,ValueError):return {}


def preparation():
    """Only public progress fields; never return paths, logs or credentials."""
    final=read_state(PROCESSED/"ML-05-finish.json")
    if final.get("status") in {"passed","owner_preview_ready"}:return {"stage":"ready"}
    if final.get("status")=="failed":return {"stage":"needs_review"}
    global_state=read_state(PROCESSED/"ML-05-job.json")
    path=Path(global_state.get("job",PROCESSED/"ml-runs/_missing")).resolve()
    state=read_state(path/"status.json") if path.is_relative_to((PROCESSED/"ml-runs").resolve()) else {}
    stage=state.get("stage",global_state.get("stage","waiting"))
    if "failed" in stage or "terminated" in stage:return {"stage":"needs_review"}
    if final.get("stage") in {"real_model_api_integration","activating_tested_local_model","recording_results"}:
        return {"stage":"testing"}
    if stage=="training":
        count=state.get("completed_epochs",0)
        return {"stage":"training","completed_epochs":count if type(count) is int and 0<=count<=10000 else 0,
                "training_cutoff_local":"13:00"}
    if stage=="paused_by_owner":return {"stage":"paused"}
    if stage in {"selecting_extension_checkpoint","evaluating_candidate","trained_pending_evaluation","evaluated_candidate_pending_api_integration"}:
        return {"stage":"evaluating"}
    return {"stage":"waiting"}


def active_model():
    """Bind displayed model identity to this project's verified server process."""
    try:
        import psutil
        from backend.app.detector import verify_bundle
        state=read_state(PROCESSED/"backend-server.json")
        proc=psutil.Process(state["pid"])
        if abs(proc.create_time()-state["create_time"])>.01 or Path(proc.cwd()).resolve()!=ROOT:return None
        args=proc.cmdline()
        if "uvicorn" not in args or "backend.app.main:app" not in args:return None
        config=Path(state["config_path"]).resolve()
        if config not in {(PROCESSED/name).resolve() for name in ("backend-local.json","backend-ml.json","backend-ml75.json")}:
            return None
        selected=Path(read_state(config)["model_bundle_path"]).resolve()
        if not selected.is_relative_to((ROOT/"ml/models").resolve()) or str(selected)!=state.get("model_bundle"):return None
        manifest,mapping,_=verify_bundle(selected)
        return {"model_version":manifest["model_version"],"class_count":len(mapping.foods),"class_map_version":mapping.version}
    except (ImportError,OSError,ValueError,KeyError,TypeError):return None
    except Exception:return None  # Process disappeared or access was denied; fail closed.


def test_status(client):
    result={"ready":False,"target_class_count":75,"preparation":preparation()}
    try:
        response=client.get(API+"/health/ready",timeout=2)
        health=response.json()
        if not isinstance(health,dict):return result
        identity=active_model() if response.status_code==200 and health.get("capabilities",{}).get("scan") is True else None
        accepted=read_state(PROCESSED/"ML-05-finish.json")
        allowed=(accepted.get("status")=="passed" or
                 (accepted.get("status")=="owner_preview_ready" and accepted.get("api_status")=="passed"
                  and accepted.get("owner_preview_decision")=="authorized"))
        if identity:result.update(identity)
        result["ready"]=bool(identity and identity["class_count"]==75 and identity["class_map_version"]==MAP75
                             and allowed and accepted.get("model_version")==identity["model_version"])
    except (httpx.HTTPError,ValueError,TypeError):pass
    return result


class LocalSession:
    def __init__(self):
        config = json.loads((PROCESSED / "supabase-local.json").read_text(encoding="utf-8-sig"))
        if config["API_URL"] != AUTH:
            raise ValueError("Only the dedicated local Supabase instance is allowed")
        self.client = httpx.Client(timeout=65, trust_env=False, follow_redirects=False)
        self.public_key = config["ANON_KEY"]
        if SESSION.exists():
            self.account = json.loads(SESSION.read_text(encoding="utf-8"))
            if self.account.get("auth_url") != AUTH or self.account.get("purpose") != "owner-local-image-test":
                raise ValueError("Existing session is not owned by this tool")
        else:
            email = "foodlens-image-test-" + uuid4().hex + "@example.invalid"
            password = secrets.token_urlsafe(32)
            response = self.client.post(AUTH + "/auth/v1/admin/users",
                headers={"apikey": self.public_key, "Authorization": "Bearer " + config["SERVICE_ROLE_KEY"]},
                json={"email": email, "password": password, "email_confirm": True,
                      "app_metadata": {"foodlens_local_image_test": True}})
            response.raise_for_status()
            self.account = {"purpose": "owner-local-image-test", "auth_url": AUTH,
                            "user_id": response.json()["id"], "email": email, "password": password}
            # Contains credentials: private machine configuration only, never a report.
            SESSION.write_text(json.dumps(self.account, indent=2) + "\n", encoding="utf-8")
        self.login()

    def login(self):
        response = self.client.post(AUTH + "/auth/v1/token?grant_type=password",
            headers={"apikey": self.public_key},
            json={"email": self.account["email"], "password": self.account["password"]})
        response.raise_for_status()
        session = response.json()
        if session["user"]["id"] != self.account["user_id"]:
            raise ValueError("Unexpected local account")
        self.token = session["access_token"]
        self.refresh_at = time.monotonic() + max(1, session.get("expires_in", 3600) - 60)

    def request(self, method, path, **kwargs):
        if time.monotonic() >= self.refresh_at:
            self.login()
        headers = kwargs.pop("headers", {})
        response = self.client.request(method, API + path,
            headers={"Authorization": "Bearer " + self.token, **headers}, **kwargs)
        if response.status_code == 401:
            self.login()
            response = self.client.request(method, API + path,
                headers={"Authorization": "Bearer " + self.token, **headers}, **kwargs)
        return response


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No request bodies, credentials, user filenames or private URLs in logs.

    def send(self, status, payload, content_type="application/json; charset=utf-8"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def local_request(self, mutation=False):
        allowed = self.server.origins  # exact origins this server was started for
        host_ok = "http://" + self.headers.get("Host", "") in allowed
        site_ok = self.headers.get("Sec-Fetch-Site", "none") in {"none", "same-origin"}
        origin = self.headers.get("Origin")
        origin_ok = (origin is None or origin in allowed) if not mutation else origin == "http://" + self.headers.get("Host", "")
        if not (host_ok and site_ok and origin_ok):
            self.send(403, {"error": "LOCAL_ORIGIN_REQUIRED"})
            return False
        return True

    def do_GET(self):
        if not self.local_request():
            return
        if self.path == "/":
            self.send(200, Path(__file__).with_suffix(".html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/foods":
            self.send(200,{"names":list(self.server.names.values()),"scope":"target_catalog75"})
        elif self.path == "/api/status":
            self.send(200,test_status(self.server.status_client))
        else:
            self.send(404, {"error": "NOT_FOUND"})

    def do_POST(self):
        if not self.local_request(mutation=True):
            return
        if self.path != "/api/analyze":
            self.send(404, {"error": "NOT_FOUND"})
            return
        if self.headers.get("X-FoodLens-Test") != "1":
            self.send(403, {"error": "LOCAL_TEST_HEADER_REQUIRED"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY or self.headers.get("Transfer-Encoding"):
            self.send(413, {"error": "IMAGE_TOO_LARGE"})
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data;"):
            self.send(415, {"error": "MULTIPART_REQUIRED"})
            return
        try:
            current=test_status(self.server.status_client)
            if not current["ready"]:
                self.close_connection=True
                self.send(503,{"error":{"code":"MODEL_NOT_READY","message":"Bản 75 món đang được chuẩn bị hoặc kiểm tra."}})
                return
            content = self.rfile.read(length)
            if self.server.session is None:
                session=LocalSession()
                try:
                    catalog=session.request("GET","/v1/foods?limit=100")
                    catalog.raise_for_status()
                    names={item["id"]:item["name_vi"] for item in catalog.json()["items"]}
                    if names!=self.server.names:raise ValueError("Catalog does not match canonical75")
                except BaseException:
                    session.client.close()
                    raise
                self.server.session=session
            started = time.perf_counter()
            response = self.server.session.request("POST", "/v1/scans/analyze", content=content,
                                                   headers={"Content-Type": content_type})
            latency = round((time.perf_counter() - started) * 1000, 1)
            if response.status_code != 201:
                # Forward only the public API error, never upstream request headers.
                error = response.json().get("error", {})
                self.send(response.status_code, {"error": {"code": error.get("code", "API_ERROR"),
                                                          "message": error.get("message", "Analyze failed.")}})
                return
            scan = response.json()
            if scan["model_version"]!=current["model_version"] or scan["class_map_version"]!=MAP75:
                self.send(409,{"error":{"code":"MODEL_CHANGED","message":"Phiên bản nhận diện vừa thay đổi. Hãy thử lại sau."}})
                return
            detections = [{**item, "food_name": self.server.names.get(item["predicted_food_id"], "Chưa rõ tên")}
                          for item in scan["detections"]]
            image = None
            url = urlsplit(scan.get("image_url") or "")
            if url.scheme == "http" and url.netloc == "127.0.0.1:54321" and url.path.startswith("/storage/v1/object/sign/"):
                try:
                    preview = self.server.session.client.get(scan["image_url"])
                    if preview.status_code == 200:
                        image = "data:image/jpeg;base64," + b64encode(preview.content).decode("ascii")
                except httpx.HTTPError:
                    pass
            food_ids = list(dict.fromkeys(item["predicted_food_id"] for item in scan["detections"]))
            self.send(201, {"scan_id": scan["id"], "status": scan["status"], "model_version": scan["model_version"],
                            "class_map_version":scan["class_map_version"],"class_count":75,
                            "detections": detections, "canonical_image": image, "api_latency_ms": latency,
                            "food_info": describe(self.server.session, food_ids)})
        except (httpx.HTTPError, ValueError, KeyError):
            self.send(503, {"error": {"code": "LOCAL_TEST_UNAVAILABLE", "message": "Không kết nối được phiên test/backend. Thử lại sau."}})


def wifi_ip():
    import ipaddress, re
    import psutil
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        if not re.search(r"Wi-?Fi|Wireless|WLAN", name, re.I) or not stats.get(name) or not stats[name].isup:
            continue
        for a in addrs:
            if a.family.name == "AF_INET" and ipaddress.ip_address(a.address).is_private and not a.address.startswith("169.254."):
                return a.address
    return None


def main(argv=None):
    import argparse
    import ipaddress
    parser = argparse.ArgumentParser(description="FoodLens local image test page")
    parser.add_argument("--lan", action="store_true", help="also serve phones on the same Wi-Fi (owner opt-in)")
    parser.add_argument("--host-ip", help="Wi-Fi IPv4 to announce when auto-detection is wrong")
    args = parser.parse_args(argv)
    from backend.app.predictor import ClassMap
    mapping=ClassMap(MAP75)
    origins = {ORIGIN}
    bind = "127.0.0.1"
    if args.lan:
        ip = args.host_ip or wifi_ip()
        if not ip or not ipaddress.ip_address(ip).is_private:
            raise ValueError("No private Wi-Fi IPv4 found; pass --host-ip")
        origins.add(f"http://{ip}:8765")
        bind = "0.0.0.0"
    server = HTTPServer((bind, 8765), Handler)
    server.origins = origins
    server.session = None  # No account/session or scan is created while waiting.
    server.status_client=httpx.Client(timeout=3,trust_env=False,follow_redirects=False)
    server.names={f['id']:f['name_vi'] for f in mapping.foods.values()}
    try:
        import psutil
        (PROCESSED / "scan-test-server.json").write_text(json.dumps({
            "pid": psutil.Process().pid, "create_time": psutil.Process().create_time(),
            "origin": ORIGIN, "lan_origins": sorted(origins - {ORIGIN}), "backend": API, "started_at": datetime.now(timezone.utc).isoformat(),
            "tool_version":2,"target_class_count":75,
            "scope": "local diagnostic (loopback, or owner opt-in Wi-Fi with --lan); real owner-isolated test account; not mobile app acceptance"
        }, indent=2) + "\n", encoding="utf-8")
        print("Local image test ready at " + ", ".join(sorted(origins)), flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        server.status_client.close()
        if server.session is not None:server.session.client.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        # HTTP exception strings may contain signed URLs; print the class only.
        print("Local image test could not start: " + type(exc).__name__, file=sys.stderr, flush=True)
        raise SystemExit(1)
