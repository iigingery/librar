# Librar

Local-first Telegram bot for searching a personal book library (PDF, EPUB, FB2, TXT) with:

- text search (SQLite FTS5 + Russian morphology)
- semantic search (OpenRouter embeddings + FAISS)
- hybrid ranking (text + semantic)
- auto-ingestion via folder watcher and Telegram file uploads

## Architecture

Librar consists of four main layers:

1. **Ingestion layer** (`librar.cli.ingest_books`): parses books and stores normalized chunks/metadata.
2. **Index layer**:
   - Text index in SQLite FTS5 (`librar.cli.index_books`).
   - Semantic vectors in FAISS (`librar.cli.index_semantic`).
3. **Query layer**:
   - Text search (`librar.cli.search_text`).
   - Semantic search (`librar.cli.search_semantic`).
   - Hybrid ranking (`librar.cli.search_hybrid`).
4. **Runtime layer**:
   - Telegram bot (`librar.bot.main`) for inline and command-based search.
   - Folder watcher (`librar.cli.watch_folder`) for continuous ingestion/index refresh.

Data flow (high level):

`Books folder / Telegram uploads -> Ingestion -> SQLite + FAISS indexes -> Bot/CLI search`.

## Run on a clean Windows PC

### 1) Prerequisites

- Windows 10/11
- Python 3.12 (64-bit)
- Git
- Telegram bot token (from BotFather)
- OpenRouter API key

### 2) Clone and install

```powershell
git clone <YOUR_REPO_URL>
cd librar

py -3.12 -m venv .venv
.\.venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -e .
```

### 3) Configure environment

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set at minimum:

- `TELEGRAM_BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `OPENROUTER_EMBEDDING_MODEL` (default in template is fine)

### 4) Add books

Create `books\` and put your files there (`.pdf`, `.epub`, `.fb2`, `.txt`).

### 5) Build indexes

```powershell
python -m librar.cli.ingest_books --path books --cache-file .librar-ingestion-cache.json
python -m librar.cli.index_books --books-path books --db-path .librar-search.db
python -m librar.cli.index_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss
```

### 6) Smoke-test search

```powershell
python -m librar.cli.search_text --db-path .librar-search.db --query "книга"
python -m librar.cli.search_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss --query "spiritual growth"
python -m librar.cli.search_hybrid --db-path .librar-search.db --index-path .librar-semantic.faiss --query "духовный рост"
```

## Run scenarios

### Scenario A: CLI only (no bot)

Use this mode for local diagnostics and scripts.

```powershell
python -m librar.cli.search_text --db-path .librar-search.db --query "книга"
python -m librar.cli.search_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss --query "духовный рост"
python -m librar.cli.search_hybrid --db-path .librar-search.db --index-path .librar-semantic.faiss --query "духовный рост"
```

### Scenario B: Bot only

Use this mode when indexes are already built and updates are manual.

```powershell
python -m librar.bot.main
```

In BotFather, enable inline mode (`/setinline`) for your bot.

### Scenario C: Watcher + bot

Use two terminals: one for continuous ingestion, one for Telegram runtime.

**Terminal 1 (watcher):**

```powershell
python -m librar.cli.watch_folder --watch-dir books
```

**Terminal 2 (bot):**

```powershell
python -m librar.bot.main
```

## Configuration Table

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes (for bot) | — | Telegram Bot API token from BotFather. |
| `OPENROUTER_API_KEY` | Yes (for semantic) | — | API key for embeddings generation. |
| `OPENROUTER_EMBEDDING_MODEL` | No | `openai/text-embedding-3-small` | Embedding model used by semantic indexing/search. |
| `OPENROUTER_BASE_URL` | No | `https://openrouter.ai/api/v1` | OpenRouter-compatible API base URL. |
| `LIBRAR_DB_PATH` | No | `.librar-search.db` | Path to SQLite text index/database. |
| `LIBRAR_INDEX_PATH` | No | `.librar-semantic.faiss` | Path to FAISS semantic index. |
| `LIBRAR_WATCH_DIR` | No | `books` | Default directory used by watcher. |
| `TELEGRAM_INLINE_TIMEOUT_SECONDS` | No | `25.0` | Inline query timeout limit. |
| `TELEGRAM_INLINE_RESULT_LIMIT` | No | `20` | Max inline results per request. |
| `TELEGRAM_COMMAND_RESULT_LIMIT` | No | `10` | Max results for bot commands. |
| `TELEGRAM_PAGE_SIZE` | No | `5` | Pagination size for bot result pages. |

### Required environment variables

Must be set for relevant runtime mode:

- `TELEGRAM_BOT_TOKEN` — required for any bot run (`librar.bot.main`).
- `OPENROUTER_API_KEY` — required for semantic indexing/search.

### Optional environment variables (with defaults)

- `OPENROUTER_EMBEDDING_MODEL` = `openai/text-embedding-3-small`
- `OPENROUTER_BASE_URL` = `https://openrouter.ai/api/v1`
- `LIBRAR_DB_PATH` = `.librar-search.db`
- `LIBRAR_INDEX_PATH` = `.librar-semantic.faiss`
- `LIBRAR_WATCH_DIR` = `books`
- `TELEGRAM_INLINE_TIMEOUT_SECONDS` = `25.0`
- `TELEGRAM_INLINE_RESULT_LIMIT` = `20`
- `TELEGRAM_COMMAND_RESULT_LIMIT` = `10`
- `TELEGRAM_PAGE_SIZE` = `5`

## Security

- `.env.example` must contain **template placeholders only** and must never include real secrets/tokens.
- Store real credentials only in local `.env` (which is git-ignored).
- Keep indexes and caches local unless explicitly needed in CI/distribution.
- If any secret is exposed, rotate it immediately (Telegram BotFather/OpenRouter) and invalidate old tokens.

## Troubleshooting

- **Bot does not respond inline:** ensure inline mode is enabled via BotFather `/setinline`, and verify `TELEGRAM_BOT_TOKEN`.
- **Semantic commands fail with auth errors:** verify `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL`.
- **No semantic results:** rebuild semantic index:
  `python -m librar.cli.index_semantic --db-path .librar-search.db --index-path .librar-semantic.faiss`.
- **Watcher does not pick up files:** verify watched folder path (`--watch-dir` or `LIBRAR_WATCH_DIR`) and supported file formats.
- **Bad/empty text matches:** rebuild ingestion and text index:
  1) `python -m librar.cli.ingest_books --path books --cache-file .librar-ingestion-cache.json`
  2) `python -m librar.cli.index_books --books-path books --db-path .librar-search.db`

## Tests

```powershell
python -m pytest tests -q
```

## Safe GitHub push defaults

`.gitignore` now excludes local secrets and machine artifacts:

- `.env*` (except `.env.example`)
- local DB/FAISS files
- `books/`
- virtual envs and `__pycache__`

Still, rotate any token that was ever exposed locally or shared accidentally.
