import asyncio
from threading import Lock

from .core import RagAgent
from . import store

_agents: dict[str, RagAgent] = {}
_lock = Lock()


def get_agent(notebook_id: str) -> RagAgent:
    with _lock:
        if notebook_id not in _agents:
            agent = RagAgent()
            store.load_index(notebook_id, agent)
            _agents[notebook_id] = agent
        return _agents[notebook_id]


async def async_get_agent(notebook_id: str) -> RagAgent:
    """Non-blocking version: runs load_index in a thread pool if needed."""
    if notebook_id in _agents:
        return _agents[notebook_id]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_agent, notebook_id)


def rebuild_agent(notebook_id: str) -> RagAgent:
    with _lock:
        agent = RagAgent()
        store.build_and_save_index(notebook_id, agent)
        _agents[notebook_id] = agent
        return agent


def _ensure_loaded(notebook_id: str) -> RagAgent:
    agent = _agents.get(notebook_id)
    if agent is None:
        agent = RagAgent()
        store.load_index(notebook_id, agent)
        _agents[notebook_id] = agent
    return agent


def add_document(notebook_id: str, source: str, text: str) -> RagAgent:
    """Incrementally index one new document into an already-built notebook index.

    Much cheaper than ``rebuild_agent`` for notebooks that already have an index —
    only the new document is embedded/mined instead of re-processing every source.
    """
    with _lock:
        agent = _ensure_loaded(notebook_id)
        agent.add_document(source, text)
        store.persist_index(notebook_id, agent)
        return agent


def remove_document(notebook_id: str, source: str) -> RagAgent:
    """Incrementally drop one document from an already-built notebook index."""
    with _lock:
        agent = _ensure_loaded(notebook_id)
        agent.remove_document(source)
        store.persist_index(notebook_id, agent)
        return agent


def invalidate_agent(notebook_id: str) -> None:
    with _lock:
        _agents.pop(notebook_id, None)
