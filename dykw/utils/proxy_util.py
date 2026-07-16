from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class ProxyPool:
    proxies: List[str]
    mode: str = "round_robin"
    _cursor: int = field(default=0, init=False, repr=False)

    def pick(self, n: int = 0) -> Optional[str]:
        if not self.proxies:
            return None
        if self.mode == "random":
            import random

            return random.choice(self.proxies)
        idx = self._cursor % len(self.proxies)
        self._cursor += 1
        return self.proxies[idx]


def load_proxy_list(path: str) -> List[str]:
    p = Path(path)
    lines = [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [x for x in lines if not x.startswith("#")]
