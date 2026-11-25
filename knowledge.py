"""Human-editable career knowledge. JSON is canonical; retrieval never replaces it."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from tailor import ROOT, TailorError

KNOWLEDGE_DIR = Path(os.environ.get("SCULPT_KNOWLEDGE_DIR", ROOT / "knowledge"))
LOCK = threading.RLock()
KINDS = {"fact", "limitation", "uncertain", "planned"}


def storage_notice():
    if os.environ.get("RENDER") and not os.environ.get("SCULPT_KNOWLEDGE_DIR"):
        return "This hosted instance uses temporary storage. Export JSON to preserve your knowledge between server restarts."
    if os.environ.get("SCULPT_KNOWLEDGE_DIR"):
        return "Knowledge is saved in the configured directory. Hosted persistence depends on that directory being on durable storage."
    return "Saved on this computer in knowledge/knowledge.json. You can also edit the file directly while the server is idle."


def now():
    return datetime.now(timezone.utc).isoformat()


def scopes(master):
    return {"general": "General experience", **{
        f"project:{p['id']}": p['name'] for p in master['projects']
    }, **{f"work:{i}": f"{e['company']} — {e['role']}" for i, e in enumerate(master['experience'])}}


def revision(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_document(value):
    if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("entries"), list):
        raise TailorError("Knowledge must be a JSON object with version: 1 and an entries list.")
    seen = set()
    for item in value['entries']:
        if not isinstance(item, dict):
            raise TailorError("Every knowledge entry must be an object.")
        identifier = item.get('id')
        if not isinstance(identifier, str) or not identifier.startswith('kb-') or len(identifier) > 100 or identifier in seen:
            raise TailorError("Knowledge entries need distinct IDs starting with kb- (maximum 100 characters).")
        seen.add(identifier)
        if item.get('kind') not in KINDS:
            raise TailorError(f"Knowledge {identifier}: kind must be fact, limitation, uncertain, or planned.")
        for key, maximum in [('text', 8000), ('scope', 100), ('question', 2000)]:
            text = item.get(key, '')
            if not isinstance(text, str) or len(text) > maximum or (key != 'question' and not text.strip()):
                raise TailorError(f"Knowledge {identifier}: invalid {key} (maximum {maximum} characters).")
        if not isinstance(item.get('archived', False), bool):
            raise TailorError(f"Knowledge {identifier}: archived must be true or false.")
    return value


def read_knowledge(directory=None):
    directory = Path(directory or KNOWLEDGE_DIR)
    path = directory / 'knowledge.json'
    with LOCK:
        if not path.exists():
            data = {'version': 1, 'entries': []}
        else:
            try:
                data = validate_document(json.loads(path.read_text(encoding='utf-8')))
            except (ValueError, OSError) as error:
                raise TailorError(f"Cannot read knowledge.json. Fix the file before continuing: {error}") from error
        return deepcopy(data), revision(data)


def _write(directory, data, previous):
    directory.mkdir(parents=True, exist_ok=True)
    # Preserve the pre-edit state, including user edits made directly in the file.
    history = directory / 'history'
    history.mkdir(exist_ok=True)
    backup = history / f"{revision(previous)}.json"
    if not backup.exists():
        backup.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path = directory / 'knowledge.json'
    temporary = directory / f'.{uuid.uuid4().hex}.tmp'
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def save_entries(entries, master, expected_revision=None, directory=None):
    """Atomic batch upsert. Exact answers are saved before any AI processing."""
    directory = Path(directory or KNOWLEDGE_DIR)
    with LOCK:
        data, current = read_knowledge(directory)
        if expected_revision is not None and expected_revision != current:
            raise TailorError("Knowledge changed elsewhere. Reload it before saving your edit.")
        previous = deepcopy(data)
        existing = {item['id']: item for item in data['entries']}
        for proposed in entries:
            identifier = proposed.get('id') or 'kb-' + uuid.uuid4().hex[:16]
            if proposed.get('scope') not in scopes(master):
                raise TailorError("Choose the project or work entry this knowledge belongs to.")
            if identifier in existing and all(existing[identifier].get(key) == value for key,value in proposed.items()):
                continue
            item = {**existing.get(identifier, {}), **proposed, 'id': identifier, 'updated_at': now()}
            item.setdefault('created_at', now())
            existing[identifier] = item
        data['entries'] = list(existing.values())
        validate_document(data)
        if data != previous:
            _write(directory, data, previous)
        return deepcopy(data), revision(data)


def knowledge_snapshot(master, directory=None):
    data, digest = read_knowledge(directory)
    known = scopes(master)
    active = [item for item in data['entries'] if not item.get('archived')]
    unknown = [item['id'] for item in active if item['scope'] not in known]
    if unknown:
        raise TailorError(f"Knowledge has unknown entry scopes: {', '.join(unknown)}. Edit or archive these entries first.")
    # Full-context semantic reading for a small personal KB: never hide evidence via top-k retrieval.
    if len(json.dumps(active, ensure_ascii=False)) > 140_000:
        raise TailorError("Active knowledge exceeds the full-context limit. Archive irrelevant records or configure a larger retrieval workflow; no entries were discarded.")
    return {'revision': digest, 'entries': deepcopy(active)}
