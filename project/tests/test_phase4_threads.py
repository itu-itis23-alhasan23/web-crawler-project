import time
from app import create_real_crawler_job
from crawler.storage import ensure_data_dirs, safe_status_snapshot


def test_phase4_threads():
    ensure_data_dirs()

    crawler1 = create_real_crawler_job("https://example.com", 0, 1, 10, True)
    crawler2 = create_real_crawler_job("https://example.com", 0, 1, 10, True)

    print("Started jobs:", crawler1, crawler2)

    # wait a bit so both threads can run
    time.sleep(5)

    data1 = safe_status_snapshot(crawler1)
    data2 = safe_status_snapshot(crawler2)

    assert data1 is not None
    assert data2 is not None

    assert "status" in data1
    assert "status" in data2

    assert isinstance(data1.get("logs", []), list)
    assert isinstance(data2.get("logs", []), list)

    print("Crawler 1 status:", data1["status"])
    print("Crawler 2 status:", data2["status"])
    print("Phase 4 thread-safety test passed.")


if __name__ == "__main__":
    test_phase4_threads()
