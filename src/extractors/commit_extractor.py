"""Extract commit metadata and file-modification pairs from a git repository."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple

from ..graph.edges.modified_by_edge import ModifiedByEdge
from ..graph.nodes.commit_node import CommitNode

logger = logging.getLogger(__name__)

_FIELD_SEP = "\x1f"
_COMMIT_MARKER = f"COMMIT{_FIELD_SEP}"
_DEFAULT_MAX_COMMITS = 200


def _commit_id(commit_hash: str) -> str:
    """Return the stable node id used for a commit."""
    return f"commit::{commit_hash}"


def _file_id_from_git_path(git_path: str) -> str:
    """Convert a git-reported POSIX-style path to the local FileNode id format.

    Git always reports forward-slash paths. ``FileNode`` ids are produced via
    ``str(Path.relative_to(...))``, which yields OS-native separators. This helper
    normalises a git path to that form so commit-touched files can be matched against
    the file nodes already in the graph.
    """
    return str(Path(git_path))


class CommitExtractor:
    """Run ``git log`` and parse commit records plus changed-file lists.

    The extractor is best-effort: if the directory is not a git working tree, or
    ``git`` is not on ``PATH``, it logs a warning and returns empty results so the
    rest of the pipeline keeps working (e.g. for ZIP-uploaded repositories).
    """

    def __init__(self, repo_path: Path, *, max_commits: int = _DEFAULT_MAX_COMMITS) -> None:
        """Store inputs and cap on how many recent commits to pull.

        Args:
            repo_path: Absolute path to the repository root.
            max_commits: Upper bound on commits parsed (most recent first). Use a
                cap to keep the graph manageable on long-lived repositories.
        """
        self.repo_path = repo_path
        self.max_commits = max(0, int(max_commits))

    def extract(self) -> Tuple[List[CommitNode], List[Tuple[str, str]]]:
        """Return commit nodes plus ``(file_id, commit_id)`` modification pairs.

        Returns:
            Tuple ``(commits, modifications)`` where ``commits`` is a list of
            :class:`CommitNode` and ``modifications`` is a list of
            ``(file_id, commit_id)`` tuples for every changed-file entry. The
            caller resolves ``file_id`` against the file nodes already produced.
        """
        if self.max_commits == 0:
            return [], []

        if not (self.repo_path / ".git").exists():
            logger.info("commit_extractor_skipped reason=no_git_dir repo=%s", self.repo_path)
            return [], []

        try:
            output = self._run_git_log()
        except FileNotFoundError:
            logger.warning("commit_extractor_skipped reason=git_not_on_path repo=%s", self.repo_path)
            return [], []
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "commit_extractor_failed repo=%s returncode=%s stderr=%s",
                self.repo_path,
                exc.returncode,
                (exc.stderr or "").strip()[:200],
            )
            return [], []

        commits, modifications = self._parse_log(output)
        logger.info(
            "commit_extractor_done repo=%s commits=%d modifications=%d",
            self.repo_path,
            len(commits),
            len(modifications),
        )
        return commits, modifications

    def _run_git_log(self) -> str:
        """Invoke ``git log`` and return its stdout as text."""
        command = [
            "git",
            "-C",
            str(self.repo_path),
            "log",
            "--no-merges",
            f"--max-count={self.max_commits}",
            f"--pretty=format:{_COMMIT_MARKER}%H{_FIELD_SEP}%an{_FIELD_SEP}%aI{_FIELD_SEP}%s",
            "--name-only",
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return result.stdout

    @staticmethod
    def _parse_log(output: str) -> Tuple[List[CommitNode], List[Tuple[str, str]]]:
        """Parse the custom-delimited ``git log`` output into nodes and edge pairs."""
        commits: List[CommitNode] = []
        modifications: List[Tuple[str, str]] = []
        current_commit_id: str | None = None
        seen_pairs: set[Tuple[str, str]] = set()

        for raw_line in output.splitlines():
            line = raw_line.strip("\r")
            if not line:
                continue
            if line.startswith(_COMMIT_MARKER):
                payload = line[len(_COMMIT_MARKER):]
                parts = payload.split(_FIELD_SEP)
                if len(parts) < 4:
                    current_commit_id = None
                    continue
                commit_hash, author, date, subject = parts[0], parts[1], parts[2], _FIELD_SEP.join(parts[3:])
                node_id = _commit_id(commit_hash)
                commits.append(
                    CommitNode(
                        id=node_id,
                        hash=commit_hash,
                        author=author,
                        date=date,
                        message=subject,
                    )
                )
                current_commit_id = node_id
                continue
            if current_commit_id is None:
                continue
            file_id = _file_id_from_git_path(line)
            pair = (file_id, current_commit_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            modifications.append(pair)
        return commits, modifications


def build_modified_by_edges(
    modifications: Iterable[Tuple[str, str]],
    known_file_ids: Iterable[str],
) -> List[ModifiedByEdge]:
    """Create ``MODIFIED_BY`` edges from ``File`` nodes to ``Commit`` nodes.

    Args:
        modifications: ``(file_id, commit_id)`` pairs produced by
            :class:`CommitExtractor`.
        known_file_ids: File ids actually present in the graph (typically Python
            files). Pairs whose ``file_id`` is not in this set are dropped so the
            edges never dangle.

    Returns:
        Deduplicated list of :class:`ModifiedByEdge` instances.
    """
    file_id_set = set(known_file_ids)
    edges: List[ModifiedByEdge] = []
    seen: set[Tuple[str, str]] = set()
    for file_id, commit_id in modifications:
        if file_id not in file_id_set:
            continue
        pair = (file_id, commit_id)
        if pair in seen:
            continue
        seen.add(pair)
        edges.append(ModifiedByEdge(source=file_id, target=commit_id))
    return edges
