from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JobIntakeConfig:
    root: Path  # shared root (contains runs/ and jobs/)
    jobs_dir: str = "jobs"
    results_root: str = "runs"
    max_inflight: int = 2
    log_json: bool = True
    strict_default: bool = False
    demo_fallbacks_default: bool = False

    @property
    def incoming_dir(self) -> Path:
        return self.root / self.jobs_dir / "incoming"

    @property
    def done_dir(self) -> Path:
        return self.root / self.jobs_dir / "done"
