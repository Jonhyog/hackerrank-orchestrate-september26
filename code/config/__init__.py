import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    repo_root: Path
    dataset_dir: Path
    output_path: Path
    sandbox_root: Path
    cursor_api_key: str
    model: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config() -> Config:
    root = repo_root()
    load_dotenv(root / ".env")
    return Config(
        repo_root=root,
        dataset_dir=Path(os.environ.get("DATASET_DIR", root / "dataset")),
        output_path=Path(os.environ.get("OUTPUT_PATH", root / "output.csv")),
        sandbox_root=Path(os.environ.get("SANDBOX_ROOT", root / ".sandbox")),
        cursor_api_key=os.environ.get("CURSOR_API_KEY", ""),
        model=os.environ.get("CURSOR_MODEL", ""),
    )
