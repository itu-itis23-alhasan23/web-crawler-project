# Product Requirements Document

## Product Name
Mini Search Engine / Localhost Web Crawler

## Goal
Build a localhost-runnable crawler and search system that supports:

- indexing from a given origin URL up to depth `k`
- searching indexed content by query
- viewing system state during indexing

## User Stories
- As a user, I want to start a crawl from a URL and set max depth.
- As a user, I want the crawler to avoid revisiting the same page twice.
- As a user, I want indexing to continue in the background.
- As a user, I want to search indexed content while indexing is active.
- As a user, I want to see crawler progress, queue depth, logs, and back pressure state.
- As a user, I want a simple localhost UI to control the system.

## Functional Requirements
### Indexing
- Input:
  - origin URL
  - max depth `k`
- Crawl recursively up to depth `k`
- Avoid duplicate crawling
- Support back pressure
- Run in background thread
- Store crawler status in filesystem
- Store visited URLs in filesystem
- Store indexed words in per-letter storage files

### Search
- Input:
  - query string
- Return relevant indexed pages
- Support querying while indexing is still active
- Return required triples:
  - relevant_url
  - origin_url
  - depth

### UI
- Crawler page
- Crawler status page
- Search page

### API
- `POST /api/index`
- `GET /api/search`

## Non-Functional Requirements
- Localhost runnable
- Single-machine design
- Language-native implementation where possible
- Simple, modular architecture
- Filesystem-based persistence

## Out of Scope
- Distributed crawling
- Production-scale full-text indexing
- Advanced ranking models
- Multi-machine deployment
- Authentication

## Deliverables
- GitHub repository
- `README.md`
- `product_prd.md`
- `recommendation.md`
- localhost-runnable codebase
