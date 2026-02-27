# CLAUDE.md — Librar Codebase Guide

> **Purpose:** This file is the authoritative guide for AI assistants (and developers) working on the **Librar** codebase. It covers project structure, development workflows, architectural conventions, and key rules to follow.

---

## Project Overview

**Librar** is a local-first Telegram bot that enables instant search and retrieval of relevant excerpts from a personal book library (PDF, EPUB, FB2, TXT). It uses a hybrid text + semantic search pipeline backed by SQLite FTS5 and FAISS.

- **Language:** Python 3.11+
- **Status:** v1.0 MVP shipped (2026-02-09). Planning v2 milestone.
- **Core value:** For any query, instantly find and deliver the most relevant excerpts from the entire library.

---

## Repository Layout

```
librar/                               # Root shim package (src-layout bridge)
│   └── __init__.py                   # Appends src/librar to __path__
src/librar/                           # All production source code
│   ├── automation/                   # Folder watcher and shared ingestion service
│   ├── bot/                          # Telegram bot: main, config, repository, handlers
│   ├── cli/                          # CLI entry points for all pipeline stages
│   ├── hybrid/                       # Hybrid search: scoring, fusion, query
│   ├── ingestion/                    # Document parsing, chunking, deduplication
│   ├── search/                       # Text search (SQLite FTS5)
│   ├── semantic/                     # Semantic search (OpenRouter embeddings + FAISS)
│   ├── taxonomy/                     # Book classification (v1.0+, new)
│   └── timeline/                     # Timeline/event extraction (v1.0+, new)
tests/                                # Mirror of src/librar/ structure
.planning/                            # Project planning docs (not shipped)
│   ├── PROJECT.md                    # Product definition and scope
│   ├── ROADMAP.md                    # Milestone tracking
│   ├── STATE.md                      # Current session state and continuity notes
│   └── milestones/                   # Archived milestone docs (v1.0-*)
pyproject.toml                        # Package metadata and dependencies
requirements.txt                      # pip-installable mirror of pyproject deps
.env.example                          # Safe env template (no real secrets — safe for git)
```

---

## Architecture: Four Layers

```
Books (PDF/EPUB/FB2/TXT)
        │
        ▼
┌─────────────────────────────────────────┐
│  Layer 1: Ingestion                     │
│  DocumentIngestor → adapters → chunks  │
│  + FingerprintRegistry (deduplication) │
└──────────────────────┬──────────────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
┌──────────────────┐      ┌──────────────────────┐
│  Layer 2: Text   │      │  Layer 3: Semantic    │
│  SQLite FTS5     │      │  FAISS + OpenRouter   │
│  (BM25 + morph)  │      │  embeddings           │
└────────┬─────────┘      └──────────┬────────────┘
         │                            │
         └──────────────┬─────────────┘
                        ▼
            ┌──────────────────────┐
            │  Layer 4: Hybrid     │
            │  Normalize → Fuse    │
            │  alpha=0.7/0.3 blend │
            └──────────┬───────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
  ┌──────────────┐           ┌──────────────────┐
  │  Telegram    │           │  CLI Tools       │
  │  Bot         │           │  (search_*)      │
  └──────────────┘           └──────────────────┘
```

**Shared ingestion pipeline** (`automation/ingestion_service.py`): a single async contract used by both the folder watcher and Telegram file upload handler.

---

## Setup

### Prerequisites

- Python 3.11+
- Tesseract OCR (for PDF OCR fallback): `sudo apt install tesseract-ocr tesseract-ocr-rus`

### Install

```bash
git clone <repo-url> && cd librar
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Environment

```bash
cp .env.example .env
# Edit .env and fill in real values:
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | BotFather token |
| `OPENROUTER_API_KEY` | **Yes** | — | OpenRouter API key for embeddings |
| `OPENROUTER_EMBEDDING_MODEL` | No | `openai/text-embedding-3-small` | Embedding model |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter base URL |
| `LIBRAR_DB_PATH` | No | `.librar-search.db` | SQLite database path |
| `LIBRAR_INDEX_PATH` | No | `.librar-semantic.faiss` | FAISS index path |
| `LIBRAR_WATCH_DIR` | No | `books` | Folder to watch for new books |
| `TELEGRAM_INLINE_TIMEOUT_SECONDS` | No | `25.0` | Inline query timeout |
| `TELEGRAM_INLINE_RESULT_LIMIT` | No | `20` | Max inline results |
| `TELEGRAM_COMMAND_RESULT_LIMIT` | No | `10` | Max command results |
| `TELEGRAM_PAGE_SIZE` | No | `5` | Results per page |

**Security:** Never commit `.env`. If a secret is exposed, rotate it immediately.

---

## Running the Project

### Full Pipeline (one-time index build)

```bash
# 1. Drop books into books/ directory
# 2. Ingest documents (text extraction + chunking)
python -m librar.cli.ingest_books --path books --cache-file .librar-ingestion-cache.json

# 3. Build text search index (SQLite FTS5)
python -m librar.cli.index_books --books-path books --db-path .librar-search.db

# 4. Build semantic index (FAISS embeddings via OpenRouter)
python -m librar.cli.index_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss
```

### Run the Bot

```bash
# Optional: start folder watcher for continuous ingestion
python -m librar.cli.watch_folder --watch-dir books &

# Start the Telegram bot
python -m librar.bot.main
```

### CLI Search (no bot required)

```bash
python -m librar.cli.search_text   --db-path .librar-search.db --query "ваш запрос"
python -m librar.cli.search_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss --query "query"
python -m librar.cli.search_hybrid   --db-path .librar-search.db --index-path .librar-semantic.faiss --query "query"
```

### Console Scripts (after `pip install -e .`)

```bash
classify-books    # Book classification (taxonomy/)
build-timeline    # Timeline extraction (timeline/)
```

---

## Running Tests

```bash
# Run all tests
python -m pytest tests -q

# Run a specific module
python -m pytest tests/ingestion/ -v
python -m pytest tests/bot/ -v

# Run a single test file
python -m pytest tests/hybrid/test_hybrid_integration.py -v
```

**There is no CI pipeline yet.** Tests must be run locally before pushing. Always run the full test suite after any change.

---

## Code Conventions

### Python Style

- **Python 3.11+** features are used throughout; do not use compatibility shims.
- `from __future__ import annotations` is present in most modules for PEP 563 deferred evaluation.
- **Full type annotations** everywhere — maintain this discipline in all new code.
- **Dataclasses with `slots=True`** for domain models (prefer `@dataclass(slots=True)` over plain classes for value objects).
- **No unused imports** — keep imports clean and ordered (stdlib → third-party → local).

### Architecture Patterns

- **Adapter pattern** for document parsers: all format adapters implement `IngestionAdapter` protocol (`ingestion/adapters/`).
- **Repository pattern** for data access: `SearchRepository`, `SemanticRepository`, `BotRepository` own all DB/index I/O.
- **Layered imports**: upper layers may import from lower layers; never import upward (e.g., `bot/` may import from `hybrid/`, never vice versa).
- **Async/await** for all Telegram bot handlers and I/O-bound operations in the bot layer.
- **Custom exception dataclasses** for error types (e.g., `IngestionError`, `VectorStoreError`) — do not raise bare exceptions.

### Error Handling

- Use **dataclass-based error results** rather than raising exceptions at module boundaries.
- Exceptions are acceptable within a single module's internal logic.
- The bot layer wraps all search calls in timeout guards (default 25 s).

### Testing

- **Maintain the ~1:1 source-to-test LOC ratio.** Every new module should have a corresponding test file.
- **Tests live in `tests/`** mirroring the `src/librar/` structure exactly.
- Use `pytest` fixtures in `tests/conftest.py` for shared test data/helpers.
- **Mock external dependencies** (Telegram API, OpenRouter/OpenAI HTTP calls, FAISS where not testing vector logic).
- Use `@pytest.mark.parametrize` for multi-format or multi-input validation.
- Integration tests (e.g., `test_ingestion_pipeline.py`, `test_hybrid_integration.py`) test full layer-to-layer flows.

### Secrets & Data

- **Never commit `.env`**, `*.db`, `*.faiss`, or `books/` — all are in `.gitignore`.
- **Never hardcode API keys, tokens, or paths** in source files; always read from environment.
- The file `.env.example` is the only env file committed — it must contain only placeholder values.

---

## Key Modules Reference

### `src/librar/ingestion/`

| File | Purpose |
|---|---|
| `ingestor.py` | `DocumentIngestor`: routes files to adapters, returns `IngestionResult` |
| `models.py` | `ExtractedDocument`, `TextChunk` — canonical domain models |
| `chunking.py` | Sentence-boundary-aware chunking (razdel for Russian) |
| `dedupe.py` | `FingerprintRegistry`: binary + normalized-text hash deduplication |
| `adapters/pdf.py` | PyMuPDF adapter with OCR fallback (pytesseract) |
| `adapters/epub.py` | EbookLib adapter with chapter tracking |
| `adapters/fb2.py` | lxml-based FB2 parser |
| `adapters/txt.py` | charset-normalized plain text adapter |

### `src/librar/search/`

| File | Purpose |
|---|---|
| `repository.py` | `SearchRepository`: SQLite FTS5 chunk storage and retrieval |
| `schema.py` | DB schema: `chunks` table + `chunks_fts` FTS5 virtual table |
| `query.py` | BM25 search with Russian morphology (pymorphy2 lemmatization) |
| `indexer.py` | Bulk chunk insertion with deduplication and state tracking |

**SQLite pragmas used:** `journal_mode=WAL`, `synchronous=NORMAL`.

### `src/librar/semantic/`

| File | Purpose |
|---|---|
| `vector_store.py` | `FaissVectorStore`: ID-mapped FAISS index (inner product metric) |
| `semantic_repository.py` | SQLite metadata: index state and chunk→vector ID mappings |
| `indexer.py` | Embedding generation + FAISS persistence |
| `query.py` | Vector similarity search via OpenRouter embeddings |
| `config.py` | Defaults: model=`openai/text-embedding-3-small`, dim=1536, metric=IP |
| `openrouter.py` | REST client for OpenRouter embedding API |

### `src/librar/hybrid/`

| File | Purpose |
|---|---|
| `scoring.py` | `normalize_keyword_ranks()`, `normalize_semantic_scores()`, `fuse_normalized_scores()`, `order_fused_scores()` |
| `query.py` | Unified hybrid search combining text + semantic results |

**Fusion weights:** `alpha=0.7` (text/BM25) + `0.3` (semantic). Exact-match boost applied on top. Tie-breaking is deterministic via page/char offsets.

### `src/librar/bot/`

| File | Purpose |
|---|---|
| `main.py` | Async entry point; builds PTB `Application`, registers handlers, manages lifecycle |
| `config.py` | `BotSettings` frozen dataclass; validates all env vars on startup |
| `repository.py` | `BotRepository`: user settings (excerpt size) and dialog history (up to 20 msgs) |
| `search_service.py` | Facade over hybrid/text/semantic search; timeout-guarded (25 s) |
| `handlers/commands.py` | `/start`, `/help`, `/search`, `/ask`, `/books` |
| `handlers/inline.py` | Inline query handler for `@botname query` |
| `handlers/callbacks.py` | Pagination and filter callback query handlers |
| `handlers/upload.py` | File upload → async ingestion pipeline |
| `handlers/settings.py` | `/settings` conversation handler (excerpt size) |
| `handlers/renderers.py` | Shared page/result rendering helpers |

### `src/librar/automation/`

| File | Purpose |
|---|---|
| `watcher.py` | `BookFolderWatcher`: watchdog-based folder monitor |
| `ingestion_service.py` | `run_ingestion_pipeline()`: shared async pipeline for watcher + uploads |

---

## Planning & Continuity

The `.planning/` directory contains project planning state. These files are **not shipped** but are important for maintaining continuity across sessions:

- **`.planning/STATE.md`** — Current milestone position, accumulated decisions, blockers. **Update this after each session.**
- **`.planning/ROADMAP.md`** — Milestone tracking.
- **`.planning/PROJECT.md`** — Product definition, value proposition, scope.
- **`.planning/milestones/`** — Archived per-milestone requirement/audit docs.

**When starting a new session**, read `STATE.md` first to understand where the project is and what decisions have been made.

---

## Known Technical Debt (Non-blocking)

From the v1.0 audit (`.planning/milestones/v1.0-MILESTONE-AUDIT.md`):

1. **Large-corpus performance** — FAISS and FTS5 indexes have not been validated at scale (10k+ books). Operational follow-up needed.
2. **Source-path normalization** — Hybrid search output may contain duplicate chunks if source paths are not normalized consistently.
3. **PTB conversation warning** — python-telegram-bot emits a warning in the `/settings` conversation handler that should be cleaned up.

---

## Git Workflow

- **Never commit secrets** (`.env`, API tokens, bot tokens).
- **Never commit runtime artifacts** (`.db`, `.faiss`, `books/`).
- Write clear, descriptive commit messages referencing the area changed (e.g., `hybrid: fix tie-breaking in fuse_normalized_scores`).
- Run the full test suite (`python -m pytest tests -q`) before pushing.
- Development branches follow the pattern `claude/<description>-<session-id>`.

---

## Dependency Versions (pinned in `pyproject.toml`)

| Package | Version | Purpose |
|---|---|---|
| `pymupdf` | 1.26.7 | PDF parsing |
| `EbookLib` | 0.20 | EPUB parsing |
| `lxml` | 6.0.2 | FB2/XML parsing |
| `beautifulsoup4` | 4.14.3 | HTML/XML utilities |
| `charset-normalizer` | 3.4.4 | Encoding detection for TXT |
| `faiss-cpu` | 1.13.0 | Vector index |
| `numpy` | 1.26.4 | Numerical arrays for FAISS |
| `openai` | 1.47.1 | OpenRouter client (OpenAI-compatible) |
| `python-dotenv` | ≥1.0.1 | Env file loading |
| `python-telegram-bot` | 22.6 | Async Telegram bot framework |
| `pymorphy2` | 0.9.1 | Russian morphological analysis |
| `pymorphy2-dicts-ru` | 2.4.417127.4579844 | Russian morphology dictionaries |
| `razdel` | 0.5.0 | Russian sentence tokenization |
| `watchdog` | ≥4.0.0 | Folder monitoring |
| `pytesseract` | ≥0.3.13 | OCR (PDF fallback) |
| `Pillow` | ≥10.4.0 | Image processing for OCR |
| `lingua-language-detector` | ≥2.0.2 | Language detection |
