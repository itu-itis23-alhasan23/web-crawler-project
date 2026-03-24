from app import app
from crawler.storage import ensure_data_dirs


def test_phase2():
    ensure_data_dirs()
    client = app.test_client()

    response = client.get("/crawler")
    assert response.status_code == 200

    response = client.get("/search")
    assert response.status_code == 400

    response = client.post("/crawler", data={
        "origin_url": "https://example.com",
        "max_depth": "1",
        "pages_per_second": "1",
        "queue_capacity": "10"
    }, follow_redirects=False)

    assert response.status_code in (302, 303)
    location = response.headers.get("Location", "")
    assert "/crawler/" in location

    print("Phase 2 test passed.")


if __name__ == "__main__":
    test_phase2()
