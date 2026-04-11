"""Sorta.Fit runners -- port of bash runners/*.sh."""
from sortafit.runners.base import BaseRunner, ClaudeRateLimited
from sortafit.runners.refine import RefineRunner
from sortafit.runners.architect import ArchitectRunner
from sortafit.runners.triage import TriageRunner
from sortafit.runners.review import ReviewRunner
from sortafit.runners.bounce import BounceRunner
from sortafit.runners.merge import MergeRunner
from sortafit.runners.code import CodeRunner
from sortafit.runners.documenter import DocumenterRunner
from sortafit.runners.release_notes import release_notes

# Registry mapping runner name to class, used by the main loop
RUNNER_REGISTRY: dict[str, type[BaseRunner]] = {
    "refine": RefineRunner,
    "architect": ArchitectRunner,
    "triage": TriageRunner,
    "review": ReviewRunner,
    "bounce": BounceRunner,
    "merge": MergeRunner,
    "code": CodeRunner,
    "documenter": DocumenterRunner,
}

__all__ = [
    "BaseRunner",
    "ClaudeRateLimited",
    "RefineRunner",
    "ArchitectRunner",
    "TriageRunner",
    "ReviewRunner",
    "BounceRunner",
    "MergeRunner",
    "CodeRunner",
    "DocumenterRunner",
    "release_notes",
    "RUNNER_REGISTRY",
]
