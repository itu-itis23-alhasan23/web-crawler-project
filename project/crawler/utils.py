import time
import uuid


def generate_crawler_id() -> str:
    epoch = int(time.time())
    short_id = uuid.uuid4().hex[:8]
    return f"{epoch}_{short_id}"
