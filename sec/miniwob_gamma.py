from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MINIWOB_PLUSPLUS_COMMIT = "7fd85d71a4b60325c6585396ec4f48377d049838"
MINIWOB_PRIMARY_TASKS = [
    "click-button",
    "choose-list",
    "enter-text",
    "click-checkboxes",
    "login-user",
    "use-autocomplete-nodelay",
]
MINIWOB_REPLACEMENT_TASKS = ["click-menu", "choose-date-nodelay", "form-sequence"]
MINIWOB_ALL_PREREG_TASKS = MINIWOB_PRIMARY_TASKS + MINIWOB_REPLACEMENT_TASKS


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _browser_tree_manifest(root: Path) -> dict[str, Any]:
    records: list[tuple[str, int, str]] = []
    total_bytes = 0
    for path in sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(root).as_posix(),
    ):
        relative_path = path.relative_to(root).as_posix()
        length = path.stat().st_size
        records.append((relative_path, length, _sha256_file(path)))
        total_bytes += length
    material = "\n".join(
        f"{relative_path}\t{length}\t{sha256}"
        for relative_path, length, sha256 in records
    )
    return {
        "browser_tree_root": str(root),
        "browser_tree_sha256": hashlib.sha256(material.encode("utf-8")).hexdigest(),
        "browser_tree_file_count": len(records),
        "browser_tree_total_bytes": total_bytes,
    }


def _configure_browsergym_chat(browser_path: str) -> None:
    """BrowserGym launches an auxiliary chat browser without forwarding Chromium kwargs."""
    if not browser_path:
        return
    import browsergym.core.chat as chat_module
    import browsergym.core.env as env_module

    if getattr(env_module, "_antmill_chat_browser_path", "") == browser_path:
        return

    class ConfiguredChat(chat_module.Chat):
        def __init__(self, headless: bool, chat_size=(500, 800), record_video_dir=None, modern=True) -> None:
            self.messages = []
            pw = chat_module._get_global_playwright()
            self.browser = pw.chromium.launch(
                headless=headless,
                args=[f"--window-size={chat_size[0]},{chat_size[1]}"],
                executable_path=browser_path,
            )
            self.context = self.browser.new_context(
                no_viewport=True,
                record_video_dir=Path(record_video_dir) / "chat_video" if record_video_dir else None,
                record_video_size=dict(width=chat_size[0], height=chat_size[1]),
            )
            self.page = self.context.new_page()
            self.recording_start_time = time.time() if record_video_dir else None
            self.page.expose_function(
                "send_user_message", lambda msg: self._js_user_message_received_callback(msg=msg)
            )
            if modern:
                self.page.set_content(chat_module.get_chatbox_modern(chat_module.CHATBOX_DIR))
            else:
                self.page.set_content(chat_module.get_chatbox_classic(chat_module.CHATBOX_DIR))

    env_module.Chat = ConfiguredChat
    env_module._antmill_chat_browser_path = browser_path


def browsergym_version_manifest() -> dict[str, Any]:
    versions: dict[str, str] = {}
    for package in ("browsergym", "browsergym-core", "browsergym-miniwob", "gymnasium", "playwright"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    browser_executable = os.environ.get("MINIWOB_BROWSER_EXECUTABLE", "")
    browser_version = ""
    browser_executable_sha256 = ""
    if browser_executable and Path(browser_executable).exists():
        browser_executable_sha256 = _sha256_file(Path(browser_executable))
        try:
            import win32api

            info = win32api.GetFileVersionInfo(browser_executable, "\\")
            ms = int(info["FileVersionMS"])
            ls = int(info["FileVersionLS"])
            browser_version = (
                f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            )
        except Exception:  # noqa: BLE001
            try:
                browser_version = subprocess.run(
                    [browser_executable, "--version"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                ).stdout.strip()
            except Exception:  # noqa: BLE001
                browser_version = "unavailable"
    tree_root = os.environ.get("MINIWOB_BROWSER_TREE_ROOT", "")
    tree_manifest = (
        _browser_tree_manifest(Path(tree_root))
        if tree_root and Path(tree_root).is_dir()
        else {
            "browser_tree_root": tree_root,
            "browser_tree_sha256": "",
            "browser_tree_file_count": 0,
            "browser_tree_total_bytes": 0,
        }
    )
    return {
        "miniwob_plusplus_commit": MINIWOB_PLUSPLUS_COMMIT,
        "primary_tasks": MINIWOB_PRIMARY_TASKS,
        "replacement_tasks": MINIWOB_REPLACEMENT_TASKS,
        "python_version": sys.version,
        "browser_executable": browser_executable,
        "browser_version": browser_version,
        "browser_executable_sha256": browser_executable_sha256,
        **tree_manifest,
        "versions": versions,
    }


def validate_frozen_browser_runtime() -> dict[str, Any]:
    runtime = browsergym_version_manifest()
    expected_fields = {
        "browser_version": os.environ.get("MINIWOB_BROWSER_EXPECTED_VERSION", ""),
        "browser_executable_sha256": os.environ.get(
            "MINIWOB_BROWSER_EXPECTED_SHA256", ""
        ).lower(),
        "browser_tree_sha256": os.environ.get(
            "MINIWOB_BROWSER_EXPECTED_TREE_SHA256", ""
        ).lower(),
    }
    mismatches = [
        {
            "field": field,
            "expected": expected,
            "actual": str(runtime.get(field) or "").lower(),
        }
        for field, expected in expected_fields.items()
        if expected and str(runtime.get(field) or "").lower() != expected.lower()
    ]
    for field, expected in expected_fields.items():
        if not expected:
            mismatches.append(
                {
                    "field": f"expected.{field}",
                    "expected": "configured frozen value",
                    "actual": expected,
                }
            )
    if not runtime.get("browser_executable"):
        mismatches.append(
            {
                "field": "browser_executable",
                "expected": "configured existing executable",
                "actual": runtime.get("browser_executable"),
            }
        )
    elif not Path(str(runtime["browser_executable"])).exists():
        mismatches.append(
            {
                "field": "browser_executable",
                "expected": "existing executable",
                "actual": runtime["browser_executable"],
            }
        )
    if expected_fields["browser_tree_sha256"] and not runtime.get("browser_tree_root"):
        mismatches.append(
            {
                "field": "browser_tree_root",
                "expected": "configured existing directory",
                "actual": runtime.get("browser_tree_root"),
            }
        )
    return {
        "ok": not mismatches,
        "expected": expected_fields,
        "actual": runtime,
        "mismatches": mismatches,
    }


def validate_miniwob_tasks(
    task_names: list[str] | None = None,
    *,
    runtime_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_names = task_names or MINIWOB_ALL_PREREG_TASKS
    runtime_manifest = runtime_manifest or browsergym_version_manifest()
    try:
        import gymnasium as gym
        import browsergym.miniwob  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc),
            "missing": task_names,
            **runtime_manifest,
        }
    registered = {env_id.removeprefix("browsergym/miniwob.") for env_id in gym.envs.registry.keys()}
    missing = [name for name in task_names if name not in registered]
    return {
        "ok": not missing,
        "missing": missing,
        "n_registered": len(registered),
        **runtime_manifest,
    }


def normalize_axtree_text(obs: Any, *, max_chars: int | None = None) -> str:
    """Bid-free normalized text: used for state hashes, deltas, and reviewer summaries only.

    Volatile BrowserGym bids are stripped so hashes stay stable across episodes. The solver
    prompt must NOT use this path — it needs bids to act (see solver_axtree_text).
    """
    text = _axtree_to_text(obs)
    text = re.sub(r"\[[A-Za-z0-9_.:-]+\]\s*", "", text)
    text = re.sub(r"\b(focused|hovered|selected)=?(True|False|true|false)?\b", "", text)
    text = re.sub(r"\b(browsergym_id|backendDOMNodeId|nodeId|id)=['\"]?[-\w:.]+['\"]?", "", text)
    text = re.sub(r"\b(x|y|top|left|right|bottom|width|height|center|bbox)=\(?[-\d., ]+\)?", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars is not None:
        return text[:max_chars]
    return text


def solver_axtree_text(obs: Any, *, max_chars: int | None = None) -> str:
    """Bid-preserving observation text for the solver prompt.

    BrowserGym high-level actions address elements by bid; hiding bids makes every
    element-targeted action unexecutable (gamma P3 `p3_not_evaluable_action_interface_failure`).
    """
    text = _axtree_to_text(obs, keep_bids=True)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if max_chars is not None:
        return text[:max_chars]
    return text


def _axtree_to_text(obs: Any, *, keep_bids: bool = False) -> str:
    if isinstance(obs, str):
        return obs
    if not isinstance(obs, dict):
        return json.dumps(obs, ensure_ascii=False, sort_keys=True)
    if obs.get("axtree_txt"):
        return str(obs["axtree_txt"])
    if obs.get("axtree_object") is not None:
        try:
            from browsergym.utils.obs import flatten_axtree_to_str

            return flatten_axtree_to_str(
                obs["axtree_object"],
                extra_properties=obs.get("extra_element_properties") or {},
                hide_all_bids=not keep_bids,
                with_visible=False,
                with_clickable=False,
                with_center_coords=False,
                with_bounding_box_coords=False,
                filter_visible_only=False,
            )
        except Exception:  # noqa: BLE001
            return json.dumps(obs["axtree_object"], ensure_ascii=False, sort_keys=True)
    keys = ["goal", "last_action", "last_action_error", "focused_element_bid"]
    return " ".join(f"{key}: {obs.get(key)}" for key in keys if obs.get(key) is not None)


BID_PATTERN = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")
# BrowserGym high-level actions whose first string argument is an element bid.
BID_FIRST_ARG_ACTIONS = {
    "click",
    "dblclick",
    "hover",
    "fill",
    "press",
    "focus",
    "clear",
    "select_option",
    "check",
    "uncheck",
    "drag_and_drop",
    "upload_file",
}
_ACTION_HEAD = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(?:['\"]([^'\"]*)['\"])?")


def extract_bids(observation_text: str) -> set[str]:
    """Bids visible to the solver in a bid-preserving observation text."""
    return set(BID_PATTERN.findall(observation_text or ""))


def action_bid_reference(action: str) -> tuple[str, str | None]:
    """Return (action_name, referenced_bid). referenced_bid is None for non-bid actions."""
    match = _ACTION_HEAD.match(action or "")
    if not match:
        return "", None
    name = match.group(1)
    if name in BID_FIRST_ARG_ACTIONS:
        return name, match.group(2)
    return name, None


def miniwob_state_hash(obs: Any, *, last_action_error: str = "", url: str = "") -> str:
    payload = {
        "axtree": normalize_axtree_text(obs),
        "last_action_error": last_action_error or (obs.get("last_action_error", "") if isinstance(obs, dict) else ""),
        "url": url or (obs.get("url", "") if isinstance(obs, dict) else ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def visible_text_delta(prev_obs: Any, next_obs: Any, *, max_chars: int = 240) -> str:
    prev = set(normalize_axtree_text(prev_obs).split())
    nxt = normalize_axtree_text(next_obs).split()
    added = [tok for tok in nxt if tok not in prev]
    return " ".join(added)[:max_chars]


def reviewer_episode_summary(
    *,
    goal: str,
    success: bool,
    steps: int,
    trajectory: list[dict[str, Any]],
    final_obs: Any,
    final_axtree_chars: int = 1200,
) -> dict[str, Any]:
    errors = [row for row in trajectory if row.get("error")]
    hashes = [str(row.get("state_hash", "")) for row in trajectory]
    repeated = sum(1 for idx, value in enumerate(hashes) if value and value in hashes[:idx])
    compact_steps = [
        {
            "step": row.get("step"),
            "action": row.get("action", ""),
            "state_hash": row.get("state_hash", ""),
            "visible_text_delta": row.get("visible_text_delta", ""),
            "error": row.get("error", ""),
        }
        for row in (trajectory[:3] + trajectory[-8:])
    ]
    return {
        "goal": goal,
        "success": bool(success),
        "steps": int(steps),
        "invalid_or_error_count": len(errors),
        "repeated_state_count": repeated,
        "steps_compact": compact_steps,
        "final_axtree": normalize_axtree_text(final_obs, max_chars=final_axtree_chars),
    }


@dataclass
class MiniWoBEnv:
    task_name: str
    seed: int
    headless: bool = True
    env: Any = None
    action_set: Any = None
    last_reward: float = 0.0
    last_obs: Any = field(default_factory=dict)
    task_id: str = ""
    browser_executable_path: str = ""

    def reset(self, task: dict[str, Any] | None = None) -> str:
        task = task or {}
        self.task_name = str(task.get("task_name") or self.task_name)
        self.seed = int(task.get("seed", self.seed))
        self.task_id = f"miniwob.{self.task_name}.{self.seed}"
        try:
            import gymnasium as gym
            import browsergym.miniwob  # noqa: F401
            from browsergym.core.action.highlevel import HighLevelActionSet
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "MiniWoB requires browsergym-miniwob, gymnasium, Playwright setup, and MINIWOB_URL. "
                "Run the preregistered BrowserGym MiniWoB setup before P3."
            ) from exc
        self.action_set = HighLevelActionSet(subsets=["miniwob_all"], multiaction=False)
        browser_path = self.browser_executable_path or os.environ.get("MINIWOB_BROWSER_EXECUTABLE", "")
        _configure_browsergym_chat(browser_path)
        chromium_kwargs = {"executable_path": browser_path} if browser_path else {}
        self.env = gym.make(
            f"browsergym/miniwob.{self.task_name}",
            action_mapping=self.action_set.to_python_code,
            headless=self.headless,
            terminate_on_infeasible=False,
            pw_chromium_kwargs=chromium_kwargs,
        )
        self.last_obs, _info = self.env.reset(seed=self.seed)
        self.last_reward = 0.0
        return self.observation_text()

    def step(self, action: str) -> tuple[str, bool, dict[str, Any]]:
        if self.env is None:
            raise RuntimeError("MiniWoBEnv.step called before reset")
        prev_obs = self.last_obs
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.last_obs = obs
        self.last_reward = float(reward or 0.0)
        error = str(obs.get("last_action_error", "")) if isinstance(obs, dict) else ""
        done = bool(terminated or truncated)
        info = {
            **(info or {}),
            "reward": self.last_reward,
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "last_action_error": error,
            "state_hash": miniwob_state_hash(obs, last_action_error=error),
            "visible_text_delta": visible_text_delta(prev_obs, obs),
        }
        return self.observation_text(), done, info

    def observation_text(self) -> str:
        goal = self.goal()
        tree = solver_axtree_text(self.last_obs, max_chars=2400)
        err = self.last_obs.get("last_action_error", "") if isinstance(self.last_obs, dict) else ""
        return f"GOAL: {goal}\nLAST_ACTION_ERROR: {err or '(none)'}\nAXTREE:\n{tree}"

    def tools_doc(self) -> str:
        if self.action_set is None:
            return "BrowserGym MiniWoB high-level actions are available after reset."
        doc = self.action_set.describe(with_long_description=False, with_examples=True)
        return (
            f"{doc}\n\n"
            "ELEMENT REFERENCES: every element in AXTREE is prefixed with a bracketed bid such as [12]. "
            "Pass that bid string (without brackets) as the element argument, e.g. "
            "Action: click(\"12\") or Action: fill(\"a5\", \"john\"). "
            "Never pass visible label text as the bid; an unknown bid makes the action fail."
        )

    def is_success(self) -> bool:
        return self.last_reward > 0.0

    def goal(self) -> str:
        if isinstance(self.last_obs, dict):
            return str(self.last_obs.get("goal", ""))
        return ""

    def close(self) -> None:
        if self.env is not None:
            self.env.close()
            self.env = None
