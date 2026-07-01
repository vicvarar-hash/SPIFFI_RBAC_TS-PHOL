"""Real-OPA runtime integration — the single place the app talks to the `opa` binary.

Two capabilities, both over the SAME rules-as-data policies the Python engines use:

  1. `opa eval`  — one-shot evaluation + parity verification (Policy Studio "Verify").
  2. `opa run --server` — an optional live OPA server you can start and query
     interactively, proving the identical policies run on a standard OPA runtime.

Nothing here is on the replay decision path: the deterministic Python engines remain
authoritative for bulk replay (faster in-process); OPA is the independent oracle that
proves equivalence and the live-runtime story. Everything degrades gracefully when the
`opa` binary is absent.
"""
from __future__ import annotations

import atexit
import functools
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# Layer -> (data file loaded as `data`, generic rego policy, eval query).
LAYERS: Dict[str, Dict[str, Optional[str]]] = {
    "rbac": {
        "data": "policies/rbac.yaml",
        "rego": "policies/rego/rbac.rego",
        "query": "data.paladin.rbac.decision",
    },
    "abac": {
        "data": "policies/abac_rules.yaml",
        "rego": "policies/rego/abac.rego",
        "query": "data.paladin.abac.decision",
    },
    "tsphol": {
        "data": "policies/trac_rules.yaml",
        "rego": "policies/rego/tsphol.rego",
        "query": "data.paladin.tsphol",
    },
}

_SERVER_ADDR = os.environ.get("OPA_SERVER_ADDR", "127.0.0.1:8181")
_proc_lock = threading.Lock()
_server_proc: Optional[subprocess.Popen] = None


# ── binary discovery ────────────────────────────────────────────────────────
def find_opa() -> Optional[str]:
    """Locate the opa binary: OPA_PATH env, then PATH, then common local spots."""
    override = os.environ.get("OPA_PATH")
    if override and os.path.exists(override):
        return override
    which = shutil.which("opa") or shutil.which("opa.exe")
    if which:
        return which
    candidates = [
        os.path.join(os.environ.get("TEMP", ""), "opa.exe"),
        os.path.join(os.environ.get("TMPDIR", ""), "opa"),
        os.path.join("bin", "opa.exe"),
        os.path.join("bin", "opa"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


@functools.lru_cache(maxsize=1)
def opa_status() -> Dict[str, Any]:
    """Cached availability/version probe. Call opa_status.cache_clear() to re-probe."""
    opa = find_opa()
    if not opa:
        return {"available": False, "path": None, "version": None}
    try:
        r = subprocess.run([opa, "version"], capture_output=True, text=True, timeout=10)
        version = "?"
        for line in r.stdout.splitlines():
            if line.lower().startswith("version"):
                version = line.split(":", 1)[1].strip()
                break
        return {"available": True, "path": opa, "version": version}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "path": opa, "version": None, "error": str(e)}


# ── one-shot evaluation ─────────────────────────────────────────────────────
def _write_input(input_obj: Dict[str, Any]) -> str:
    fd, path = tempfile.mkstemp(prefix="_opa_in_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(input_obj, f)
    return path


def opa_eval(deps: List[str], query: str, input_obj: Dict[str, Any],
             fmt: str = "raw") -> Tuple[bool, Any]:
    """Run `opa eval`. Returns (ok, value-or-error). `deps` are -d files (data + rego)."""
    opa = find_opa()
    if not opa:
        return False, "opa binary not found"
    inp = _write_input(input_obj)
    try:
        cmd = [opa, "eval"]
        for d in deps:
            cmd += ["-d", d]
        cmd += ["-i", inp, "-f", fmt, query]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "opa eval failed").strip()
        out = r.stdout.strip()
        if fmt == "json":
            doc = json.loads(out)
            try:
                return True, doc["result"][0]["expressions"][0]["value"]
            except (KeyError, IndexError):
                return True, None
        return True, out
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    finally:
        if os.path.exists(inp):
            os.remove(inp)


def eval_layer(layer: str, input_obj: Dict[str, Any]) -> Tuple[bool, Any]:
    """Evaluate one governance layer via `opa eval` over its rules-as-data policy."""
    spec = LAYERS[layer]
    deps = [p for p in (spec["data"], spec["rego"]) if p]
    fmt = "json" if layer == "tsphol" else "raw"
    return opa_eval(deps, spec["query"], input_obj, fmt=fmt)


# ── policy sources (for display) ────────────────────────────────────────────
def policy_sources(layer: str) -> Dict[str, Optional[str]]:
    """Return the Rego + data document text for a layer, for the compliance view."""
    spec = LAYERS[layer]
    out: Dict[str, Optional[str]] = {
        "rego_path": spec["rego"], "data_path": spec["data"], "query": spec["query"],
        "rego_text": None, "data_text": None,
    }
    try:
        if spec["rego"] and os.path.exists(spec["rego"]):
            out["rego_text"] = open(spec["rego"], encoding="utf-8").read()
        if spec["data"] and os.path.exists(spec["data"]):
            out["data_text"] = open(spec["data"], encoding="utf-8").read()
    except OSError as e:
        out["error"] = str(e)
    return out


# ── parity verification (opa eval vs the Python engines) ─────────────────────
@functools.lru_cache(maxsize=1)
def _load_fixture():
    """Load dataset + engines once (cached) for parity sampling."""
    from app.services import replay_service as rs
    from app.services.experiment_config import PERSONAS
    from app.services.normalization import normalize_mcp_name
    from app.loaders.astra_loader import load_astra_dataset
    from app.loaders.mcp_loader import load_mcp_personas

    tasks = load_astra_dataset("datasets/astra_03_tools.json")
    mcp_personas, _ = load_mcp_personas("mcp_servers")
    rbac_pol, abac_pol, tsphol_pol = rs.baseline_policies()
    engines = rs._engines_from_policies(mcp_personas, rbac_pol, abac_pol, tsphol_pol)
    return rs, PERSONAS, normalize_mcp_name, tasks, engines


def verify_rbac_abac(sample_tasks: int = 10) -> Dict[str, Any]:
    """Bounded RBAC+ABAC parity: `opa eval` vs the isolated Python engines.

    Returns {rbac:{evals,mismatches,ok,examples}, abac:{...}, seconds}.
    """
    if not opa_status()["available"]:
        return {"available": False}
    rs, PERSONAS, normalize_mcp_name, tasks, engines = _load_fixture()
    t0 = time.time()
    res = {
        "rbac": {"evals": 0, "mismatches": 0, "examples": []},
        "abac": {"evals": 0, "mismatches": 0, "examples": []},
    }
    for t in tasks[:sample_tasks]:
        tools, mcps = list(t.candidate_tools), list(t.candidate_mcp)
        dom = normalize_mcp_name(t.groundtruth_mcp[0]) if t.groundtruth_mcp else None
        for pk in PERSONAS:
            spiffe = PERSONAS[pk]["spiffe_id"]
            # RBAC
            rres = rs._eval(engines["rbac"], pk, tools, mcps, t.task, "validation")
            py_deny = rres.final_decision in rs.DENY_STATES
            ok, d = eval_layer("rbac", {"spiffe_id": spiffe, "mcps": mcps, "tools": tools})
            res["rbac"]["evals"] += 1
            if not ok or (d == "DENY") != py_deny:
                res["rbac"]["mismatches"] += 1
                if len(res["rbac"]["examples"]) < 5:
                    res["rbac"]["examples"].append({"persona": pk, "opa": d, "py_deny": py_deny})
            # ABAC
            ares = rs._eval(engines["abac"], pk, tools, mcps, t.task, "validation", task_domain=dom)
            py_deny_a = ares.final_decision in rs.DENY_STATES
            attrs = (ares.context or {}).get("abac_baseline", {}).get("attributes_used")
            if attrs:
                ok, d = eval_layer("abac", {"subject": attrs["subject"],
                                            "resource": attrs["resource"],
                                            "action": attrs["action"]})
                res["abac"]["evals"] += 1
                if not ok or (d == "DENY") != py_deny_a:
                    res["abac"]["mismatches"] += 1
                    if len(res["abac"]["examples"]) < 5:
                        res["abac"]["examples"].append({"persona": pk, "opa": d, "py_deny": py_deny_a})
    for layer in ("rbac", "abac"):
        res[layer]["ok"] = res[layer]["mismatches"] == 0 and res[layer]["evals"] > 0
    res["available"] = True
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ── optional live OPA server ────────────────────────────────────────────────
def server_base() -> str:
    return f"http://{_SERVER_ADDR}"


def server_status() -> Dict[str, Any]:
    """Is a live OPA server answering on the configured address?"""
    import requests
    try:
        r = requests.get(server_base() + "/health", timeout=2)
        return {"running": r.status_code == 200, "addr": _SERVER_ADDR}
    except Exception:  # noqa: BLE001
        return {"running": False, "addr": _SERVER_ADDR}


def start_server() -> Dict[str, Any]:
    """Start `opa run --server` loaded with every rules-as-data policy + data doc."""
    global _server_proc
    if server_status()["running"]:
        return {"ok": True, "message": "already running", "addr": _SERVER_ADDR}
    opa = find_opa()
    if not opa:
        return {"ok": False, "message": "opa binary not found"}
    files: List[str] = []
    for spec in LAYERS.values():
        for p in (spec["data"], spec["rego"]):
            if p and p not in files and os.path.exists(p):
                files.append(p)
    with _proc_lock:
        try:
            _server_proc = subprocess.Popen(
                [opa, "run", "--server", "--addr", _SERVER_ADDR, *files],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}
    for _ in range(25):
        time.sleep(0.2)
        if server_status()["running"]:
            return {"ok": True, "message": "started", "addr": _SERVER_ADDR, "files": files}
    return {"ok": False, "message": "server did not become ready"}


def stop_server() -> Dict[str, Any]:
    global _server_proc
    with _proc_lock:
        if _server_proc and _server_proc.poll() is None:
            _server_proc.terminate()
            try:
                _server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _server_proc.kill()
            _server_proc = None
            return {"ok": True, "message": "stopped"}
    return {"ok": True, "message": "not managed by this process (no-op)"}


def query_server(layer: str, input_obj: Dict[str, Any]) -> Tuple[bool, Any]:
    """Query the LIVE OPA server's REST Data API for a layer decision."""
    import requests
    # data.paladin.rbac.decision -> v1/data/paladin/rbac/decision
    path = LAYERS[layer]["query"].replace("data.", "", 1).replace(".", "/")
    try:
        r = requests.post(f"{server_base()}/v1/data/{path}", json={"input": input_obj}, timeout=10)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        return True, r.json().get("result")
    except Exception as e:  # noqa: BLE001
        return False, str(e)


# Stop any server this process started when the app shuts down (avoids orphans).
atexit.register(lambda: stop_server() if _server_proc is not None else None)
