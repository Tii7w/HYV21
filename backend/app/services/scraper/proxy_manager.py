# proxy_manager.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import random
import threading
from enum import Enum


class ProxyStatus(Enum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    DEAD = "dead"
    UNCHECKED = "unchecked"


class RotationStrategy(Enum):
    STICKY = "sticky"
    ON_BLOCK = "on_block"
    WEIGHTED_RANDOM = "weighted_random"
    ROUND_ROBIN = "round_robin"


@dataclass
class Proxy:
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    protocol: str = "http"  # http, https, socks5
    status: ProxyStatus = ProxyStatus.UNCHECKED
    success_count: int = 0
    fail_count: int = 0
    last_used: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    total_requests: int = 0
    sticky_requests_left: int = 0

    @property
    def url(self) -> str:
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"{self.protocol}://{auth}{self.host}:{self.port}"

    def is_available(self) -> bool:
        if self.status == ProxyStatus.DEAD:
            return False
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return False
        return True


class ProxyManager:
    def __init__(
        self,
        strategy: RotationStrategy = RotationStrategy.ON_BLOCK,
        sticky_duration_minutes: int = 15,
        sticky_max_requests: int = 30,
        cooldown_minutes: int = 45,
        max_fails_before_dead: int = 5,
    ):
        self.proxies: List[Proxy] = []
        self.strategy = strategy
        self.sticky_duration = 