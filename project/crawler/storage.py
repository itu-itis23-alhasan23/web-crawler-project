import json
import os
import threading
import csv
import io
from typing import Optional, List

from crawler.constants import DATA_DIR, CRAWLERS_DIR, STORAGE_DIR, VISITED_FILE
from crawler.models import CrawlerStatus, WordEntry


_dir_lock = threading.Lock()
_visited_lock = threading.Lock()
_crawler_file_locks: dict[str, threading.Lock] = {}
_word_file_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _get_crawler_lock(crawler_id: str) -> threading.Lock:
    with _registry_lock:
        if crawler_id not in _crawler_file_locks:
            _crawler_file_locks[crawler_id] = threading.Lock()
        return _crawler_file_locks[crawler_id]


def _get_word_lock(letter: str) -> threading.Lock:
    with _registry_lock:
        if letter not in _word_file_locks:
            _word_file_locks[letter] = threading.Lock()
        return _word_file_locks[letter]


def ensure_data_dirs() -> None:
    with _dir_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        os.makedirs(CRAWLERS_DIR, exist_ok=True)
        os.makedirs(STORAGE_DIR, exist_ok=True)

        if not os.path.exists(VISITED_FILE):
            with open(VISITED_FILE, "w", encoding="utf-8") as f:
                pass


def get_crawler_file_path(crawler_id: str) -> str:
    return os.path.join(CRAWLERS_DIR, f"{crawler_id}.data")


def create_crawler_status_file(status: CrawlerStatus) -> None:
    ensure_data_dirs()
    path = get_crawler_file_path(status.crawler_id)
    lock = _get_crawler_lock(status.crawler_id)

    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(status.to_dict(), f, indent=2, ensure_ascii=False)


def read_crawler_status(crawler_id: str) -> Optional[dict]:
    path = get_crawler_file_path(crawler_id)
    if not os.path.exists(path):
        return None

    lock = _get_crawler_lock(crawler_id)

    with lock:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def write_crawler_status(data: dict) -> None:
    crawler_id = data["crawler_id"]
    path = get_crawler_file_path(crawler_id)
    lock = _get_crawler_lock(crawler_id)

    with lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def append_log(crawler_id: str, message: str) -> bool:
    lock = _get_crawler_lock(crawler_id)
    path = get_crawler_file_path(crawler_id)

    if not os.path.exists(path):
        return False

    with lock:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("logs", []).append(message)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return True


def update_crawler_fields(crawler_id: str, **kwargs) -> bool:
    lock = _get_crawler_lock(crawler_id)
    path = get_crawler_file_path(crawler_id)

    if not os.path.exists(path):
        return False

    with lock:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for key, value in kwargs.items():
            data[key] = value

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return True


def safe_status_snapshot(crawler_id: str) -> Optional[dict]:
    return read_crawler_status(crawler_id)


def load_visited_urls() -> set[str]:
    ensure_data_dirs()
    visited = set()

    with _visited_lock:
        with open(VISITED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                url = line.strip()
                if url:
                    visited.add(url)

    return visited


def is_visited(url: str) -> bool:
    visited = load_visited_urls()
    return url in visited


def mark_visited(url: str) -> None:
    ensure_data_dirs()

    with _visited_lock:
        existing = set()
        with open(VISITED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                existing.add(line.strip())

        if url in existing:
            return

        with open(VISITED_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")


def get_word_file_path(word: str) -> str:
    first = word[0].casefold()
    if not first.isalpha():
        first = "_"
    return os.path.join(STORAGE_DIR, f"{first}.data")


def _get_word_file_key(word: str) -> str:
    first = word[0].casefold()
    if not first.isalpha():
        first = "_"
    return first


def store_word_entry(entry: WordEntry) -> None:
    ensure_data_dirs()

    if not entry.word:
        return

    letter = _get_word_file_key(entry.word)
    path = get_word_file_path(entry.word)
    lock = _get_word_lock(letter)

    safe_word = entry.word.casefold()

    with lock:
        with open(path, "a", encoding="utf-8") as f:
            # rubric-friendly raw format:
            # word url origin depth frequency
            f.write(
                f"{safe_word} "
                f"{entry.current_url} "
                f"{entry.origin_url} "
                f"{entry.depth} "
                f"{entry.frequency}\n"
            )


def read_word_entries(word: str) -> List[dict]:
    if not word:
        return []

    word = word.casefold()
    path = get_word_file_path(word)
    if not os.path.exists(path):
        return []

    letter = _get_word_file_key(word)
    lock = _get_word_lock(letter)

    results = []
    with lock:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) != 5:
                    continue

                stored_word, current_url, origin_url, depth, frequency = parts

                if stored_word == word:
                    try:
                        results.append({
                            "word": stored_word,
                            "current_url": current_url,
                            "origin_url": origin_url,
                            "depth": int(depth),
                            "frequency": int(frequency),
                        })
                    except ValueError:
                        continue

    return results


def read_letter_file(letter: str) -> List[dict]:
    letter = (letter or "_").casefold()
    path = os.path.join(STORAGE_DIR, f"{letter}.data")
    if not os.path.exists(path):
        return []

    lock = _get_word_lock(letter)
    results = []

    with lock:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return results


def read_all_word_entries() -> List[dict]:
    ensure_data_dirs()
    results = []

    with _dir_lock:
        files = [name for name in os.listdir(STORAGE_DIR) if name.endswith(".data")]

    for name in files:
        letter = name[:-5]
        results.extend(read_letter_file(letter))

    return results


def list_crawler_jobs() -> List[str]:
    ensure_data_dirs()

    with _dir_lock:
        files = []
        for name in os.listdir(CRAWLERS_DIR):
            if name.endswith(".data"):
                files.append(name[:-5])

    files.sort(reverse=True)
    return files


def export_logs_text(crawler_id: str) -> Optional[str]:
    data = safe_status_snapshot(crawler_id)
    if data is None:
        return None

    logs = data.get("logs", [])
    return "\n".join(logs)


def export_results_csv(rows: List[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["current_url", "origin_url", "depth", "score", "matched_words"])

    for row in rows:
        writer.writerow([
            row.get("current_url", ""),
            row.get("origin_url", ""),
            row.get("depth", ""),
            row.get("score", ""),
            ", ".join(row.get("matched_words", [])),
        ])

    return output.getvalue()