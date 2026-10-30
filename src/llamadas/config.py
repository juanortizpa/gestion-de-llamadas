"""Carga de configuracion (settings, lexicons, rubric, agents) y rutas del proyecto."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    raw: dict
    lex: dict
    rubric: dict = field(default_factory=dict)
    agents: list = field(default_factory=list)

    def __getitem__(self, key: str) -> dict:
        return self.raw[key]

    @property
    def data_dir(self) -> Path:
        return ROOT / self.raw["paths"]["data_dir"]

    @property
    def models_dir(self) -> Path:
        return ROOT / self.raw["paths"]["models_dir"]


def _toml(name: str, required: bool = True) -> dict:
    p = ROOT / "config" / name
    if not p.exists() and not required:
        return {}
    with open(p, "rb") as f:
        return tomllib.load(f)


def load_dotenv(path: Path | None = None) -> None:
    """Lee .env (CLAVE=valor) a os.environ sin pisar variables ya definidas. El archivo es local y no se versiona."""
    p = path or ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv()
    return Settings(raw=_toml("settings.toml"), lex=_toml("lexicons.toml"), rubric=_toml("rubric.toml", False),
                    agents=_toml("agents.toml", False).get("names", []))
