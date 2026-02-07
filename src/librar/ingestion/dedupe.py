"""Document fingerprinting and duplicate detection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from librar.ingestion.models import ExtractedDocument
from librar.ingestion.normalization import normalize_text

_METADATA_LINE_RE = re.compile(r"^(title|author|название|автор)\s*:\s*", re.IGNORECASE)


@dataclass(slots=True)
class DocumentFingerprint:
    """Dual fingerprint representation for ingestion dedupe decisions."""

    binary_hash: str
    normalized_text_hash: str


@dataclass(slots=True)
class DedupeDecision:
    """Result of duplicate evaluation for one document."""

    is_duplicate: bool
    reason: str | None
    fingerprint: DocumentFingerprint


class FingerprintRegistry:
    """In-memory fingerprint registry for duplicate checks."""

    def __init__(self) -> None:
        self._binary_hashes: set[str] = set()
        self._normalized_text_hashes: set[str] = set()

    def evaluate(self, fingerprint: DocumentFingerprint) -> DedupeDecision:
        if fingerprint.binary_hash in self._binary_hashes:
            return DedupeDecision(is_duplicate=True, reason="binary-match", fingerprint=fingerprint)
        if fingerprint.normalized_text_hash in self._normalized_text_hashes:
            return DedupeDecision(
                is_duplicate=True,
                reason="normalized-content-match",
                fingerprint=fingerprint,
            )

        self._binary_hashes.add(fingerprint.binary_hash)
        self._normalized_text_hashes.add(fingerprint.normalized_text_hash)
        return DedupeDecision(is_duplicate=False, reason=None, fingerprint=fingerprint)


def fingerprint_document(raw_bytes: bytes, document: ExtractedDocument) -> DocumentFingerprint:
    """Build binary and normalized-text fingerprints for a document."""

    binary_hash = hashlib.sha256(raw_bytes).hexdigest()
    text_payload = "\n".join(
        block.text for block in document.blocks if block.text and not _METADATA_LINE_RE.match(block.text)
    )
    normalized_text = normalize_text(text_payload)
    normalized_text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    return DocumentFingerprint(binary_hash=binary_hash, normalized_text_hash=normalized_text_hash)
