from dataclasses import dataclass, field, asdict
from typing import Optional, List
import time


@dataclass
class QueueItem:
    url: str
    depth: int
    origin_url: str


@dataclass
class WordEntry:
    word: str
    origin_url: str
    current_url: str
    depth: int
    frequency: int


@dataclass
class CrawlerStatus:
    crawler_id: str
    origin_url: str
    max_depth: int
    status: str = "created"

    created_at: int = field(default_factory=lambda: int(time.time()))
    started_at: Optional[int] = None
    ended_at: Optional[int] = None

    pages_per_second: int = 1
    queue_capacity: int = 100

    processed_count: int = 0
    queued_count: int = 0
    visited_count: int = 0

    current_url: Optional[str] = None
    current_depth: Optional[int] = None
    throttle_active: bool = False

    restrict_to_origin_domain: bool = True
    origin_domain: Optional[str] = None

    stop_requested: bool = False

    queue: List[QueueItem] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)

    error: Optional[str] = None

    def to_dict(self):
        return asdict(self)