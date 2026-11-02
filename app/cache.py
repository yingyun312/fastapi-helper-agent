import time
from dataclasses import dataclass
from typing import Any


@dataclass
class Node:
    key: str = ""
    value: Any = None
    expires_at: float = 0.0
    previous: "Node | None" = None
    next: "Node | None" = None


class LRUCache:
    """Hash table + doubly linked list. Call from a single event-loop thread."""

    def __init__(self, capacity: int, ttl: float, clock=time.monotonic):
        if capacity < 0 or ttl <= 0:
            raise ValueError("Invalid cache capacity or TTL")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.nodes: dict[str, Node] = {}
        self.head, self.tail = Node(), Node()
        self.head.next, self.tail.previous = self.tail, self.head

    def _detach(self, node: Node):
        node.previous.next = node.next
        node.next.previous = node.previous

    def _promote(self, node: Node):
        node.previous, node.next = self.head, self.head.next
        self.head.next.previous = node
        self.head.next = node

    def get(self, key: str):
        node = self.nodes.get(key)
        if node is None:
            return None
        self._detach(node)
        if node.expires_at <= self.clock():
            del self.nodes[key]
            return None
        self._promote(node)
        return node.value

    def put(self, key: str, value: Any):
        if self.capacity == 0:
            return
        node = self.nodes.get(key)
        if node is not None:
            self._detach(node)
        else:
            node = Node(key=key)
            self.nodes[key] = node
        node.value, node.expires_at = value, self.clock() + self.ttl
        self._promote(node)
        if len(self.nodes) > self.capacity:
            oldest = self.tail.previous
            self._detach(oldest)
            del self.nodes[oldest.key]

    def __len__(self):
        return len(self.nodes)
