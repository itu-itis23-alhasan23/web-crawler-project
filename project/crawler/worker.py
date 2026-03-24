import time
from collections import deque
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse

from crawler.models import QueueItem, WordEntry
from crawler.storage import (
    read_crawler_status,
    update_crawler_fields,
    append_log,
    is_visited,
    mark_visited,
    store_word_entry,
)
from crawler.parser import extract_links_and_word_counts, normalize_url


USER_AGENT = "Mozilla/5.0 (compatible; MiniSearchEngineBot/1.0)"


def fetch_page(url: str, timeout: int = 10):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        status_code = response.getcode()

        if "text/html" not in content_type.lower():
            return status_code, content_type, None

        raw = response.read()
        html = raw.decode("utf-8", errors="ignore")
        return status_code, content_type, html


def _queue_snapshot(queue):
    return [
        {
            "url": item.url,
            "depth": item.depth,
            "origin_url": item.origin_url
        }
        for item in queue
    ]


def _get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _is_same_domain(url: str, origin_domain: str) -> bool:
    return _get_domain(url) == origin_domain.lower()


def _stop_requested(crawler_id: str) -> bool:
    data = read_crawler_status(crawler_id)
    if data is None:
        return True
    return bool(data.get("stop_requested", False))


def run_crawler_job(crawler_id: str):
    data = read_crawler_status(crawler_id)
    if data is None:
        return

    origin_url = normalize_url(data["origin_url"])
    max_depth = data["max_depth"]
    pages_per_second = data.get("pages_per_second", 1)
    queue_capacity = data.get("queue_capacity", 100)
    restrict_to_origin_domain = data.get("restrict_to_origin_domain", True)
    origin_domain = _get_domain(origin_url)

    delay = 1.0 / max(pages_per_second, 1)

    queue = deque()
    queue.append(QueueItem(url=origin_url, depth=0, origin_url=origin_url))

    processed_count = 0
    visited_count = 0

    update_crawler_fields(
        crawler_id,
        origin_url=origin_url,
        origin_domain=origin_domain,
        status="running",
        started_at=int(time.time()),
        queued_count=1,
        processed_count=0,
        visited_count=0,
        current_url=origin_url,
        current_depth=0,
        queue=_queue_snapshot(queue),
        error=None,
        throttle_active=False
    )

    append_log(crawler_id, f"[INFO] crawler started from {origin_url}")
    append_log(crawler_id, f"[INFO] origin domain = {origin_domain}")
    append_log(crawler_id, f"[INFO] restrict_to_origin_domain = {restrict_to_origin_domain}")

    try:
        while queue:
            if _stop_requested(crawler_id):
                update_crawler_fields(
                    crawler_id,
                    status="stopped",
                    ended_at=int(time.time()),
                    queued_count=len(queue),
                    queue=_queue_snapshot(queue),
                    throttle_active=False
                )
                append_log(crawler_id, "[INFO] stop requested by user")
                return

            current_item = queue.popleft()
            current_url = normalize_url(current_item.url)

            update_crawler_fields(
                crawler_id,
                current_url=current_url,
                current_depth=current_item.depth,
                queued_count=len(queue),
                queue=_queue_snapshot(queue)
            )

            if current_item.depth > max_depth:
                append_log(
                    crawler_id,
                    f"[INFO] skipped {current_url} because depth {current_item.depth} > max_depth {max_depth}"
                )
                continue

            if is_visited(current_url):
                append_log(crawler_id, f"[INFO] skipped already visited URL: {current_url}")
                continue

            append_log(crawler_id, f"[INFO] visiting {current_url} at depth {current_item.depth}")

            try:
                status_code, content_type, html = fetch_page(current_url)

                if status_code != 200:
                    append_log(crawler_id, f"[ERROR] HTTP status {status_code} for {current_url}")
                    continue

                if html is None:
                    append_log(
                        crawler_id,
                        f"[INFO] skipped non-HTML content at {current_url} ({content_type})"
                    )
                    continue

            except HTTPError as e:
                append_log(crawler_id, f"[ERROR] HTTPError for {current_url}: {e}")
                continue
            except URLError as e:
                append_log(crawler_id, f"[ERROR] URLError for {current_url}: {e}")
                continue
            except Exception as e:
                append_log(crawler_id, f"[ERROR] Unexpected fetch error for {current_url}: {e}")
                continue

            links, word_counts = extract_links_and_word_counts(html, current_url)

            mark_visited(current_url)
            visited_count += 1
            processed_count += 1

            for word, freq in word_counts.items():
                entry = WordEntry(
                    word=word,
                    origin_url=current_item.origin_url,
                    current_url=current_url,
                    depth=current_item.depth,
                    frequency=freq
                )
                store_word_entry(entry)

            append_log(
                crawler_id,
                f"[INFO] indexed {len(word_counts)} unique words and found {len(links)} links in {current_url}"
            )

            throttled = False
            added_links = 0
            filtered_outside_domain = 0

            if current_item.depth < max_depth:
                for link in links:
                    if _stop_requested(crawler_id):
                        update_crawler_fields(
                            crawler_id,
                            status="stopped",
                            ended_at=int(time.time()),
                            queued_count=len(queue),
                            queue=_queue_snapshot(queue),
                            throttle_active=False
                        )
                        append_log(crawler_id, "[INFO] stop requested by user")
                        return

                    link = normalize_url(link)

                    if restrict_to_origin_domain and not _is_same_domain(link, origin_domain):
                        filtered_outside_domain += 1
                        continue

                    if len(queue) >= queue_capacity:
                        throttled = True
                        append_log(
                            crawler_id,
                            f"[INFO] queue capacity reached ({queue_capacity}), throttling new URLs"
                        )
                        break

                    if not is_visited(link):
                        queue.append(
                            QueueItem(
                                url=link,
                                depth=current_item.depth + 1,
                                origin_url=current_item.origin_url
                            )
                        )
                        added_links += 1

                if added_links:
                    append_log(
                        crawler_id,
                        f"[INFO] added {added_links} new URLs to queue from {current_url}"
                    )

                if filtered_outside_domain:
                    append_log(
                        crawler_id,
                        f"[INFO] filtered {filtered_outside_domain} outside-domain URLs from {current_url}"
                    )

            update_crawler_fields(
                crawler_id,
                processed_count=processed_count,
                visited_count=visited_count,
                queued_count=len(queue),
                queue=_queue_snapshot(queue),
                current_url=current_url,
                current_depth=current_item.depth,
                throttle_active=throttled
            )

            time.sleep(delay)

        update_crawler_fields(
            crawler_id,
            status="finished",
            ended_at=int(time.time()),
            queued_count=0,
            queue=[],
            throttle_active=False
        )
        append_log(crawler_id, "[INFO] crawler finished successfully")

    except Exception as e:
        update_crawler_fields(
            crawler_id,
            status="failed",
            ended_at=int(time.time()),
            error=str(e),
            throttle_active=False
        )
        append_log(crawler_id, f"[ERROR] crawler failed: {e}")