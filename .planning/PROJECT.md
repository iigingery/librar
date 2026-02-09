# Librar — Telegram-бот для поиска по личной библиотеке

## What This Is

Локальный Telegram-бот с инлайн-поиском по личной библиотеке (PDF, EPUB, FB2, TXT).  
Поддерживает точный, семантический и гибридный поиск, возвращает релевантные отрывки с источником, и автоматически пополняет библиотеку через папку `books/` и загрузки файлов в боте.

## Core Value

По любому запросу — мгновенно находить и выдавать нужные отрывки из всех книг в библиотеке.

## Current State

- **Shipped version:** v1.0 MVP (2026-02-09)
- **Milestone archive:** `.planning/milestones/v1.0-ROADMAP.md`
- **Requirements archive:** `.planning/milestones/v1.0-REQUIREMENTS.md`
- **Audit archive:** `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- **Status:** v1 functional scope shipped; remaining items are non-blocking tech debt and deferred validation.

## Requirements

### Validated (v1.0)

- ✓ Парсинг книг в форматах PDF, EPUB, FB2, TXT с извлечением текста и метаданных
- ✓ Индексация текста для точного поиска по словам и фразам
- ✓ Семантическая индексация (embeddings) для смыслового поиска
- ✓ Telegram-бот с инлайн-поиском
- ✓ Результаты в формате: «Название книги» — страница/позиция — отрывок
- ✓ Настраиваемый размер отрывка в результатах
- ✓ Добавление книг через папку books/ (автоподхват)
- ✓ Добавление книг через отправку файла боту в Telegram

### Active (next milestone discovery)

- [ ] Определить цели следующего milestone через `/gsd-new-milestone`
- [ ] Решить, включать ли устранение текущего tech debt в scope следующего milestone

### Out of Scope

- Веб-интерфейс — Telegram достаточно для v1
- Редактирование текста в боте — пользователь редактирует вручную после получения
- Мультиязычный интерфейс — бот на русском
- Облачное хранилище книг — всё локально

## Next Milestone Goals

Через `/gsd-new-milestone` определить:

1. Какие v2-возможности входят в ближайший релиз (например SRCH-07/08/09, LIB-03/04/05)
2. Какие технические долги v1 должны быть закрыты сразу
3. Критерии качества и проверки для следующего цикла

## Context

- Текущий стек: Python, SQLite FTS5, FAISS, OpenRouter, python-telegram-bot.
- Рабочая модель: локальный запуск на Windows.
- Проверенное поведение: end-to-end поиск и пополнение библиотеки.

## Constraints

- **API**: OpenRouter API для embeddings
- **Форматы**: PDF, EPUB, FB2, TXT
- **Хостинг**: локальный запуск (Windows)
- **Интерфейс**: Telegram Bot API с инлайн-режимом

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python как язык | Лучшая экосистема для текста, AI и Telegram-бота | ✓ Good |
| OpenRouter для embeddings | Поддержка недорогой/бесплатной модели и простая интеграция | ✓ Good |
| Telegram инлайн-бот | Быстрый доступ из любого чата | ✓ Good |
| Общий async ingestion pipeline | Один контракт для watcher и upload flow | ✓ Good |

---
*Last updated: 2026-02-10 after v1.0 milestone completion*
