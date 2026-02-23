# Librar

Local-first Telegram bot for searching a personal book library (PDF, EPUB, FB2, TXT) with:

- text search (SQLite FTS5 + Russian morphology)
- semantic search (OpenRouter embeddings + FAISS)
- hybrid ranking (text + semantic)
- auto-ingestion via folder watcher and Telegram file uploads

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

### 7) Run bot

```powershell
python -m librar.bot.main
```

In BotFather, enable inline mode (`/setinline`) for your bot.

## Optional: folder watcher only

```powershell
python -m librar.cli.watch_folder --watch-dir books
```

## Security

- `.env.example` must contain **template placeholders only** and must never include real secrets/tokens.
- Store real credentials only in local `.env` (which is git-ignored).
- If any secret is exposed, rotate it immediately (Telegram BotFather/OpenRouter) and invalidate old tokens.

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
