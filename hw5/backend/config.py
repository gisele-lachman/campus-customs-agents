"""Settings and limits for the Campus Customs agent team, all in one place."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

HW5_DIR = Path(__file__).resolve().parent.parent
load_dotenv(HW5_DIR / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# The only model any agent may use. Portkey can silently substitute an unknown name, so every reply's
# model is checked against this (a dated release of the same model, e.g. "<MODEL_NAME>-<date>", passes).
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

MCP_SERVER_SCRIPT = HW5_DIR / "mcp_server" / "server.py"
PYTHON = HW5_DIR / ".venv" / "bin" / "python"
ORIGINAL_DB = HW5_DIR / "data" / "campus_customs.db"
WORKING_DB = HW5_DIR / "data" / "campus_customs_new.db"
SCRATCH_DIR = HW5_DIR / "data" / "scratch"


def _scratch_override(env_var: str, default: Path) -> Path:
    """Tests may point a path at data/scratch/ through an environment variable; nothing else is allowed."""
    value = os.environ.get(env_var)
    if not value:
        return default
    path = Path(value).resolve()
    if path != default.resolve() and SCRATCH_DIR.resolve() not in path.parents:
        raise RuntimeError(f"{env_var} must be the default path or a file inside data/scratch/.")
    if path == ORIGINAL_DB.resolve():
        raise RuntimeError("The original database can never be the working database.")
    return path


# The database and audit file the backend uses (the real ones unless a test sets the variables).
DB_PATH = _scratch_override("CAMPUS_CUSTOMS_DB", WORKING_DB)
AUDIT_TRAIL = _scratch_override("CAMPUS_CUSTOMS_AUDIT", HW5_DIR / "output" / "audit_trail.json")
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Limits:
    """Token and loop limits. Hitting any of them stops the run with UsageLimitExceeded."""

    max_delegation_depth: int = 2  # Boss -> specialist -> one more specialist, no deeper
    requests_per_agent_run: int = 8  # model requests in one agent's run
    tool_calls_per_agent_run: int = 10  # MCP + delegation calls in one agent's run
    output_tokens_per_agent_run: int = 16_000  # includes the model's reasoning tokens
    requests_per_ticket: int = 30  # model requests across every agent working one ticket
    tool_calls_per_ticket: int = 45  # tool calls across every agent working one ticket
    max_output_tokens_per_reply: int = 4_000  # includes reasoning tokens
    reasoning_effort: str = "low"  # keeps reasoning tokens (and cost) down
    request_timeout_seconds: float = 75  # one model request; a hung call is cut off and retried
    request_retries: int = 3  # retries on timeouts and 5xx from Portkey (with backoff)


LIMITS = Limits()


def portkey_api_key() -> str:
    key = os.environ.get("PORTKEY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Put it in HW5/.env (see .env.example).")
    return key
