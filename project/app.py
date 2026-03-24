from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
import threading
import math
from collections import defaultdict
from urllib.parse import urlparse
from difflib import SequenceMatcher

from crawler.models import CrawlerStatus, QueueItem
from crawler.storage import (
    ensure_data_dirs,
    create_crawler_status_file,
    read_crawler_status,
    safe_status_snapshot,
    list_crawler_jobs,
    read_word_entries,
    read_letter_file,
    export_logs_text,
    export_results_csv,
    update_crawler_fields,
)
from crawler.utils import generate_crawler_id
from crawler.worker import run_crawler_job

app = Flask(__name__)

RESULTS_PER_PAGE = 10
FUZZY_THRESHOLD = 0.75


def _get_domain(url: str) -> str:
    return urlparse(url).netloc.casefold()


def create_real_crawler_job(
    origin_url: str,
    max_depth: int,
    pages_per_second: int,
    queue_capacity: int,
    restrict_to_origin_domain: bool
) -> str:
    crawler_id = generate_crawler_id()
    origin_domain = _get_domain(origin_url)

    status = CrawlerStatus(
        crawler_id=crawler_id,
        origin_url=origin_url,
        max_depth=max_depth,
        pages_per_second=pages_per_second,
        queue_capacity=queue_capacity,
        status="created",
        restrict_to_origin_domain=restrict_to_origin_domain,
        origin_domain=origin_domain,
        stop_requested=False,
    )

    status.queue.append(
        QueueItem(
            url=origin_url,
            depth=0,
            origin_url=origin_url
        )
    )
    status.queued_count = 1
    status.current_url = origin_url
    status.current_depth = 0
    status.logs.append("[INFO] crawler job created")
    status.logs.append(f"[INFO] origin URL set to {origin_url}")
    status.logs.append(f"[INFO] origin domain set to {origin_domain}")
    status.logs.append(f"[INFO] max depth set to {max_depth}")
    status.logs.append(f"[INFO] pages_per_second set to {pages_per_second}")
    status.logs.append(f"[INFO] queue_capacity set to {queue_capacity}")
    status.logs.append(f"[INFO] restrict_to_origin_domain set to {restrict_to_origin_domain}")

    create_crawler_status_file(status)

    worker_thread = threading.Thread(
        target=run_crawler_job,
        args=(crawler_id,),
        daemon=True
    )
    worker_thread.start()

    return crawler_id


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.casefold(), b.casefold()).ratio()


def compute_relevance_score(frequency: int, depth: int) -> int:
    return (frequency * 10) + 1000 - (depth * 5)


def search_required_format(query: str):
    query = query.strip().casefold()
    rows = read_word_entries(query)

    grouped = {}

    for row in rows:
        url = row["current_url"]
        score = compute_relevance_score(row["frequency"], row["depth"])

        if url not in grouped or score > grouped[url]["relevance_score"]:
            grouped[url] = {
                "url": row["current_url"],
                "origin_url": row["origin_url"],
                "depth": row["depth"],
                "frequency": row["frequency"],
                "relevance_score": score,
            }

    results = list(grouped.values())
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    return results


@app.route("/")
def home():
    return redirect(url_for("crawler_page"))


@app.route("/crawler", methods=["GET", "POST"])
def crawler_page():
    ensure_data_dirs()
    error = None

    if request.method == "POST":
        origin_url = request.form.get("origin_url", "").strip()
        max_depth_raw = request.form.get("max_depth", "0").strip()
        pages_per_second_raw = request.form.get("pages_per_second", "1").strip()
        queue_capacity_raw = request.form.get("queue_capacity", "100").strip()
        restrict_to_origin_domain = request.form.get("restrict_to_origin_domain") == "on"

        if not origin_url:
            error = "Origin URL is required."
        else:
            try:
                max_depth = int(max_depth_raw)
                pages_per_second = int(pages_per_second_raw)
                queue_capacity = int(queue_capacity_raw)

                if max_depth < 0:
                    raise ValueError("Max depth must be >= 0")
                if pages_per_second < 1:
                    raise ValueError("Pages per second must be >= 1")
                if queue_capacity < 1:
                    raise ValueError("Queue capacity must be >= 1")

                crawler_id = create_real_crawler_job(
                    origin_url=origin_url,
                    max_depth=max_depth,
                    pages_per_second=pages_per_second,
                    queue_capacity=queue_capacity,
                    restrict_to_origin_domain=restrict_to_origin_domain
                )
                return redirect(url_for("status_page", crawler_id=crawler_id))

            except ValueError as e:
                error = str(e)

    jobs = list_crawler_jobs()
    jobs_with_data = []

    for crawler_id in jobs:
        data = read_crawler_status(crawler_id)
        if data:
            jobs_with_data.append(data)

    return render_template("crawler.html", jobs=jobs_with_data, error=error)


@app.route("/crawler/<crawler_id>")
def status_page(crawler_id):
    data = safe_status_snapshot(crawler_id)
    if data is None:
        return render_template("status.html", crawler=None, error="Crawler job not found.")
    return render_template("status.html", crawler=data, error=None)


@app.route("/crawler/<crawler_id>/poll")
def poll_status(crawler_id):
    data = safe_status_snapshot(crawler_id)
    if data is None:
        return jsonify({"error": "Crawler job not found"}), 404
    return jsonify(data)


@app.route("/crawler/<crawler_id>/stop", methods=["POST"])
def stop_crawler(crawler_id):
    data = safe_status_snapshot(crawler_id)
    if data is None:
        return jsonify({"ok": False, "error": "Crawler job not found"}), 404

    if data.get("status") not in ("created", "running"):
        return jsonify({"ok": False, "error": f"Cannot stop crawler in status '{data.get('status')}'"}), 400

    update_crawler_fields(crawler_id, stop_requested=True)
    return jsonify({"ok": True})


@app.route("/crawler/<crawler_id>/export-logs")
def export_crawler_logs(crawler_id):
    text = export_logs_text(crawler_id)
    if text is None:
        return "Crawler job not found.", 404

    return Response(
        text,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename={crawler_id}_logs.txt"
        }
    )


@app.route("/search", methods=["GET"])
def search_api():
    query = request.args.get("query", "").strip()
    sort_by = request.args.get("sortBy", "relevance").strip().lower()

    if not query:
        return jsonify({
            "ok": False,
            "error": "query is required"
        }), 400

    results = search_required_format(query)

    if sort_by == "relevance":
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

    return jsonify({
        "ok": True,
        "query": query,
        "results": results
    })


@app.route("/search-ui", methods=["GET"])
def search_page():
    query = request.args.get("q", "").strip()
    results = []

    if query:
        results = search_required_format(query)

    return render_template("search.html", query=query, results=results)


def aggregate_required_triples(query: str):
    """
    Required-format search output:
    (relevant_url, origin_url, depth)

    We keep the internal ranking logic simple:
    exact word match, grouped by current_url.
    """
    words = [w.strip().casefold() for w in query.split() if w.strip()]
    grouped = {}

    for word in words:
        rows = read_word_entries(word)
        for row in rows:
            relevant_url = row.get("current_url", "")
            if not relevant_url:
                continue

            if relevant_url not in grouped:
                grouped[relevant_url] = {
                    "relevant_url": relevant_url,
                    "origin_url": row.get("origin_url", ""),
                    "depth": row.get("depth", 0),
                    "score": 0
                }

            grouped[relevant_url]["score"] += row.get("frequency", 0)

    results = list(grouped.values())
    results.sort(key=lambda x: x["score"], reverse=True)

    # return only the required triple fields
    return [
        {
            "relevant_url": row["relevant_url"],
            "origin_url": row["origin_url"],
            "depth": row["depth"]
        }
        for row in results
    ]

@app.route("/api/index", methods=["POST"])
def api_index():
    data = request.get_json(silent=True) or {}

    origin_url = str(data.get("origin", "")).strip()
    k_raw = data.get("k", 0)
    pages_per_second_raw = data.get("pages_per_second", 1)
    queue_capacity_raw = data.get("queue_capacity", 100)
    restrict_to_origin_domain = bool(data.get("restrict_to_origin_domain", True))

    if not origin_url:
        return jsonify({"ok": False, "error": "origin is required"}), 400

    try:
        k = int(k_raw)
        pages_per_second = int(pages_per_second_raw)
        queue_capacity = int(queue_capacity_raw)

        if k < 0:
            raise ValueError("k must be >= 0")
        if pages_per_second < 1:
            raise ValueError("pages_per_second must be >= 1")
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be >= 1")

        crawler_id = create_real_crawler_job(
            origin_url=origin_url,
            max_depth=k,
            pages_per_second=pages_per_second,
            queue_capacity=queue_capacity,
            restrict_to_origin_domain=restrict_to_origin_domain
        )

        return jsonify({
            "ok": True,
            "crawler_id": crawler_id,
            "origin": origin_url,
            "k": k,
            "status_url": url_for("status_page", crawler_id=crawler_id, _external=False),
            "poll_url": url_for("poll_status", crawler_id=crawler_id, _external=False)
        })

    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/api/search", methods=["GET"])
def api_search():
    query = request.args.get("query", "").strip()

    if not query:
        return jsonify({
            "ok": False,
            "error": "query is required"
        }), 400

    triples = aggregate_required_triples(query)

    return jsonify({
        "ok": True,
        "query": query,
        "results": triples
    })

if __name__ == "__main__":
    ensure_data_dirs()
    app.run(debug=True, threaded=True, port=5000)
