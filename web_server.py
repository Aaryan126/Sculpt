#!/usr/bin/env python3
"""Small local UI for JD-based resume generation and PDF preview."""

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

import yaml

from review_flow import (
    apply_decisions, candidates_for_selection, plan_catalog, request_suggestions,
    revise_suggestion,
)
from tailor import TailorError, assemble_tailored, normalize_parsed_jd, parse_job_description, request_selection


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
TAILORED_CONTENT_DIR = ROOT / "content" / "tailored"
TAILORED_OUTPUT_DIR = ROOT / "output" / "tailored"
MAX_REQUEST_BYTES = 100_000
RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")
MASTER_PATH = ROOT / "content" / "master.yaml"


def master_snapshot():
    source = MASTER_PATH.read_bytes()
    return yaml.safe_load(source), hashlib.sha256(source).hexdigest()


def draft_path(run_id):
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise TailorError("Invalid review ID.")
    return TAILORED_OUTPUT_DIR / run_id / "review.json"


def load_draft(run_id):
    path = draft_path(run_id)
    if not path.is_file():
        raise TailorError("Review not found. Start a new tailoring run.")
    draft = json.loads(path.read_text(encoding="utf-8"))
    _, current_hash = master_snapshot()
    if draft.get("master_hash") != current_hash:
        raise TailorError("The master resume changed during this review. Start a new tailoring run.")
    return draft


def save_draft(draft):
    path = draft_path(draft["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def public_draft(draft, master):
    public = {
        "run_id": draft["run_id"], "stage": draft["stage"],
        "parsed_jd": draft["parsed_jd"], "selection": draft["selection"],
        "catalog": plan_catalog(master), "suggestions": draft.get("suggestions", []),
        "decisions": draft.get("decisions", {}),
        "pdf_url": draft.get("pdf_url"), "warnings": draft.get("warnings", []),
    }
    if draft["stage"] == "final":
        content_path = TAILORED_CONTENT_DIR / f"{draft['run_id']}.yaml"
        if content_path.is_file():
            tailored = yaml.safe_load(content_path.read_text(encoding="utf-8"))
            public["projects"] = [{"id": item["id"], "name": item["name"]} for item in tailored["projects"]]
            public["summary"] = tailored["summary"]
            public["review_note"] = "The PDF contains your approved structure and wording decisions. Master content remains unchanged."
    return public


class Handler(BaseHTTPRequestHandler):
    def _authorized(self):
        password = os.environ.get("RESUME_ACCESS_PASSWORD", "")
        if not password:
            return True
        authorization = self.headers.get("Authorization", "")
        if authorization.startswith("Basic "):
            try:
                credentials = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
                username, supplied_password = credentials.split(":", 1)
                expected_username = os.environ.get("RESUME_ACCESS_USERNAME", "resume")
                if (hmac.compare_digest(username, expected_username)
                        and hmac.compare_digest(supplied_password, password)):
                    return True
            except (binascii.Error, UnicodeDecodeError, ValueError):
                pass
        body = b"Authentication required."
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Resume Tailor", charset="UTF-8"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)
        return False

    def _send(self, status, data, content_type, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, value):
        self._send(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if not self._authorized():
            return
        request_path = urlsplit(self.path).path
        assets = {
            "/": (WEB_DIR / "index.html", "text/html; charset=utf-8"),
            "/app.js": (WEB_DIR / "app.js", "text/javascript; charset=utf-8"),
            "/style.css": (WEB_DIR / "style.css", "text/css; charset=utf-8"),
            "/api/master.pdf": (ROOT / "output" / "resume.pdf", "application/pdf"),
        }
        if request_path in assets:
            path, content_type = assets[request_path]
            if not path.is_file():
                self._json(404, {"error": f"File not found: {path.name}. Run python build.py first."})
                return
            self._send(200, path.read_bytes(), content_type)
            return
        match = re.fullmatch(r"/api/(pdf|preview)/([^/?]+)", request_path)
        if match and RUN_ID_PATTERN.fullmatch(match.group(2)):
            pdf_dir = TAILORED_OUTPUT_DIR / match.group(2)
            if match.group(1) == "preview":
                pdf_dir /= "preview"
            pdf_path = pdf_dir / "resume.pdf"
            if pdf_path.is_file():
                self._send(200, pdf_path.read_bytes(), "application/pdf")
                return
        match = re.fullmatch(r"/api/review/([^/?]+)", request_path)
        if match:
            try:
                draft = load_draft(match.group(1))
                master, _ = master_snapshot()
                self._json(200, public_draft(draft, master))
            except TailorError as error:
                self._json(404, {"error": str(error)})
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self):
        if not self._authorized():
            return
        if self.path not in {"/api/parse", "/api/plan", "/api/draft", "/api/decision", "/api/revise", "/api/preview", "/api/finalize"}:
            self._json(404, {"error": "Not found."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._json(415, {"error": "Send JSON requests with Content-Type: application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid request length."})
            return
        if length < 1 or length > MAX_REQUEST_BYTES:
            self._json(413, {"error": "Request must be under 100 KB."})
            return
        try:
            body = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            self._json(400, {"error": "Invalid JSON request."})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "Request must be an object."})
            return
        if self.path == "/api/parse":
            jd = body.get("jd", "")
            if not isinstance(jd, str) or not jd.strip() or len(jd) > 30_000:
                self._json(400, {"error": "Paste a job description under 30,000 characters."})
                return
            try:
                parsed = parse_job_description(jd)
            except TailorError as error:
                self._json(502, {"error": str(error)})
                return
            except Exception as error:
                self._json(500, {"error": f"Parsing failed: {error}"})
                return
            self._json(200, {"parsed_jd": parsed})
            return

        try:
            if self.path == "/api/plan":
                parsed_jd = normalize_parsed_jd(body.get("parsed_jd"))
                master, master_hash = master_snapshot()
                selection = request_selection(parsed_jd, master)
                run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
                draft = {
                    "run_id": run_id, "master_hash": master_hash, "stage": "plan",
                    "parsed_jd": parsed_jd, "selection": selection,
                    "suggestions": [], "decisions": {}, "warnings": [],
                }
                save_draft(draft)
                self._json(200, public_draft(draft, master))
                return

            draft = load_draft(body.get("run_id"))
            master, _ = master_snapshot()
            if self.path == "/api/draft":
                selection = body.get("selection")
                assemble_tailored(master, selection)
                candidates = candidates_for_selection(master, selection)
                suggestions = request_suggestions(draft["parsed_jd"], candidates)
                draft.pop("pdf_url", None)
                draft.update(stage="wording", selection=selection, suggestions=suggestions, decisions={}, warnings=[])
                save_draft(draft)
                self._json(200, public_draft(draft, master))
                return

            if draft["stage"] not in {"wording", "final"}:
                raise TailorError("Approve the structure plan before reviewing wording.")
            suggestions_by_id = {item["id"]: item for item in draft["suggestions"]}
            item_id = body.get("suggestion_id")
            if self.path in {"/api/decision", "/api/revise"} and item_id not in suggestions_by_id:
                raise TailorError("Unknown wording suggestion ID.")

            if self.path == "/api/decision":
                action = body.get("action")
                if action not in {"accept", "keep", "edit"}:
                    raise TailorError("Choose Accept, Keep master, or Edit for this suggestion.")
                decision = {"action": action}
                if action == "edit":
                    edited = body.get("text")
                    if not isinstance(edited, str) or not edited.strip():
                        raise TailorError("Edited wording cannot be empty.")
                    decision["text"] = edited.strip()
                draft["stage"] = "wording"
                draft.pop("pdf_url", None)
                draft["decisions"][item_id] = decision
                save_draft(draft)
                self._json(200, {"decisions": draft["decisions"]})
                return

            if self.path == "/api/revise":
                candidates = {item["id"]: item for item in candidates_for_selection(master, draft["selection"])}
                revised = revise_suggestion(
                    draft["parsed_jd"], candidates[item_id],
                    suggestions_by_id[item_id], body.get("feedback", ""),
                )
                draft["stage"] = "wording"
                draft.pop("pdf_url", None)
                draft["suggestions"] = [revised if item["id"] == item_id else item for item in draft["suggestions"]]
                draft["decisions"].pop(item_id, None)
                save_draft(draft)
                self._json(200, {"suggestion": revised, "decisions": draft["decisions"]})
                return

            if self.path == "/api/preview":
                tailored, review_warnings = apply_decisions(
                    master, draft["selection"], draft["suggestions"], draft["decisions"],
                    require_complete=False,
                )
                run_id = draft["run_id"]
                output_dir = TAILORED_OUTPUT_DIR / run_id / "preview"
                output_dir.mkdir(parents=True, exist_ok=True)
                content_path = output_dir / "preview-content.yaml"
                content_path.write_text(
                    yaml.safe_dump(tailored, sort_keys=False, allow_unicode=True), encoding="utf-8"
                )
                environment = os.environ.copy()
                environment["PATH"] = "/Library/TeX/texbin:" + environment.get("PATH", "")
                command = [
                    sys.executable, str(ROOT / "build.py"), "--profile", "tailored",
                    "--content", str(content_path), "--output-dir", str(output_dir),
                ]
                try:
                    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90)
                except subprocess.TimeoutExpired:
                    self._json(504, {"error": "Draft PDF preview timed out. Try again."})
                    return
                if result.returncode != 0:
                    self._json(422, {
                        "error": "The current draft does not pass the PDF rules. Adjust wording or structure before building.",
                        "details": result.stdout.strip() or result.stderr.strip(),
                    })
                    return
                pending = len(draft["suggestions"]) - len(draft["decisions"])
                warnings = review_warnings + [line.strip() for line in result.stdout.splitlines() if "[WARN]" in line]
                self._json(200, {
                    "pdf_url": f"/api/preview/{run_id}", "pending": pending, "warnings": warnings,
                })
                return

            tailored, review_warnings = apply_decisions(
                master, draft["selection"], draft["suggestions"], draft["decisions"]
            )
            run_id = draft["run_id"]
            content_path = TAILORED_CONTENT_DIR / f"{run_id}.yaml"
            output_dir = TAILORED_OUTPUT_DIR / run_id
            TAILORED_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
            content_path.write_text(yaml.safe_dump(tailored, sort_keys=False, allow_unicode=True), encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = "/Library/TeX/texbin:" + environment.get("PATH", "")
            command = [
                sys.executable, str(ROOT / "build.py"), "--profile", "tailored",
                "--content", str(content_path), "--output-dir", str(output_dir),
            ]
            try:
                result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=90)
            except subprocess.TimeoutExpired:
                self._json(504, {"error": "PDF build timed out. Review your accepted wording and try again.", "run_id": run_id})
                return
            if result.returncode != 0:
                self._json(422, {
                    "error": "The reviewed resume did not pass the PDF rules. Adjust the structure or wording and build again.",
                    "details": result.stdout.strip() or result.stderr.strip(), "run_id": run_id,
                })
                return
            (output_dir / "parsed_jd.json").write_text(
                json.dumps(draft["parsed_jd"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            warnings = review_warnings + [line.strip() for line in result.stdout.splitlines() if "[WARN]" in line]
            draft.update(stage="final", pdf_url=f"/api/pdf/{run_id}", warnings=warnings)
            save_draft(draft)
            self._json(200, {
                "run_id": run_id, "pdf_url": draft["pdf_url"],
                "projects": [{"id": item["id"], "name": item["name"]} for item in tailored["projects"]],
                "summary": tailored["summary"], "warnings": warnings,
                "review_note": "The PDF contains your approved structure and wording decisions. Master content remains unchanged.",
            })
        except TailorError as error:
            self._json(400, {"error": str(error)})
        except Exception as error:
            self._json(500, {"error": f"Review workflow failed: {error}"})


def main():
    parser = argparse.ArgumentParser(description="Run the resume tailoring UI")
    parser.add_argument("--host", default="0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        password = os.environ.get("RESUME_ACCESS_PASSWORD", "")
        if len(password) < 20:
            parser.error("A public binding requires RESUME_ACCESS_PASSWORD with at least 20 characters.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Resume Tailor listening on {args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
