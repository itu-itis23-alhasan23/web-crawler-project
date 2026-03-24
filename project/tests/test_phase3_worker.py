from crawler.models import CrawlerStatus, QueueItem
from crawler.storage import create_crawler_status_file, read_crawler_status, ensure_data_dirs
from crawler.utils import generate_crawler_id
from crawler.worker import run_crawler_job


def test_worker():
    ensure_data_dirs()

    crawler_id = generate_crawler_id()

    status = CrawlerStatus(
        crawler_id=crawler_id,
        origin_url="https://example.com",
        max_depth=0,
        pages_per_second=1,
        queue_capacity=10
    )
    status.queue.append(QueueItem(
        url="https://example.com",
        depth=0,
        origin_url="https://example.com"
    ))
    status.queued_count = 1

    create_crawler_status_file(status)

    run_crawler_job(crawler_id)

    data = read_crawler_status(crawler_id)
    assert data is not None
    assert data["status"] in ("finished", "failed")
    assert len(data["logs"]) > 0

    print("Worker test finished with status:", data["status"])


if __name__ == "__main__":
    test_worker()
