"""
HKY Estates V2 - Gerçek zamanlı olay yolu
Agent iş parçacıklarından gelen olayları SSE bağlantılarına iletir.
"""

import asyncio
import threading
from typing import Any, Dict, List, Optional, Tuple

QUEUE_LIMIT = 200


class EventBus:
    def __init__(self) -> None:
        self._subscribers: List[Tuple[asyncio.AbstractEventLoop, asyncio.Queue, int, bool]] = []
        self._lock = threading.Lock()

    def subscribe(self, user_id: int, is_admin: bool) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_LIMIT)
        with self._lock:
            self._subscribers.append((asyncio.get_running_loop(), queue, user_id, is_admin))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [item for item in self._subscribers if item[1] is not queue]

    def publish(self, event: str, data: Dict[str, Any], user_id: Optional[int] = None) -> None:
        """user_id verilirse olay yalnızca o kullanıcıya gider."""
        message = {"event": event, "data": data}
        with self._lock:
            targets = [item for item in self._subscribers if user_id is None or item[2] == user_id]
        for loop, queue, _user, _admin in targets:
            try:
                loop.call_soon_threadsafe(self._offer, queue, message)
            except RuntimeError:
                self.unsubscribe(queue)

    @staticmethod
    def _offer(queue: asyncio.Queue, message: Dict[str, Any]) -> None:
        # Yavaş istemci sunucuyu bloke etmesin; en eski olay düşürülür.
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(message)


bus = EventBus()
