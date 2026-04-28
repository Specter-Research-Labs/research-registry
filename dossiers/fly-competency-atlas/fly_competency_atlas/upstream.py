from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

TUTORIALS_README_URL = "https://raw.githubusercontent.com/FlyBrainLab/Tutorials/master/README.md"
DATASETS_README_URL = "https://raw.githubusercontent.com/FlyBrainLab/datasets/master/README.md"

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_SECTION_RE = re.compile(r"^## .*?\[([^\]]+)\]")


class UpstreamError(RuntimeError):
    """Raised when the upstream catalog cannot be fetched or parsed."""


@dataclass(frozen=True)
class TutorialRecord:
    level: str
    name: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DatasetRecord:
    dataset: str
    version: str
    last_update: str
    loading_script_url: str | None
    neuronlp_url: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def fetch_text(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise UpstreamError(f"failed to fetch {url}: {exc}") from exc


def parse_tutorials(markdown: str) -> tuple[TutorialRecord, ...]:
    records: list[TutorialRecord] = []
    level = "unspecified"
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("### "):
            level = line.removeprefix("### ").strip()
            continue
        if not line.startswith("* "):
            continue
        match = _LINK_RE.search(line)
        if match is None:
            continue
        records.append(TutorialRecord(level=level, name=match.group(1), url=match.group(2)))
    if not records:
        raise UpstreamError("tutorial catalog parse produced no records")
    return tuple(records)


def parse_datasets(markdown: str) -> tuple[DatasetRecord, ...]:
    records: list[DatasetRecord] = []
    current_dataset: str | None = None
    headers: list[str] | None = None
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        section_match = _SECTION_RE.match(line)
        if section_match is not None:
            current_dataset = section_match.group(1)
            headers = None
            continue
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        if set("".join(cells)) <= {"-", ":"}:
            continue
        if headers is None:
            headers = cells
            continue
        if current_dataset is None:
            continue
        row = dict(zip(headers, cells, strict=False))
        records.append(
            DatasetRecord(
                dataset=current_dataset,
                version=_strip_link_text(_version_cell(row)),
                last_update=_first_present(row, "Last Update"),
                loading_script_url=_extract_link_url(_first_present(row, "Loading Script")),
                neuronlp_url=_extract_link_url(_first_present(row, "NeuroNLP")),
            )
        )
    if not records:
        raise UpstreamError("dataset catalog parse produced no records")
    return tuple(records)


def fetch_tutorials() -> tuple[TutorialRecord, ...]:
    return parse_tutorials(fetch_text(TUTORIALS_README_URL))


def fetch_datasets() -> tuple[DatasetRecord, ...]:
    return parse_datasets(fetch_text(DATASETS_README_URL))


def _extract_link_url(value: str) -> str | None:
    match = _LINK_RE.search(value)
    return None if match is None else match.group(2)


def _strip_link_text(value: str) -> str:
    match = _LINK_RE.search(value)
    if match is None:
        return value
    return match.group(1)


def _first_present(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in row:
            return row[key]
    raise UpstreamError(f"missing expected columns: {keys}")


def _version_cell(row: dict[str, str]) -> str:
    return _first_present(
        row,
        "FlyCircuit Ver.",
        "Hemibrain Ver.",
        "L1EM Ver.",
        "Medulla Ver.",
        "MANC Ver.",
        "FlyWire Snapshot",
        "Fib19 Ver.",
        "Optic-Lobe Ver.",
    )
