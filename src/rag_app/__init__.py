"""RAnythinG RAG application package."""

__all__ = ["RagAgent", "parse_upload_file"]


def __getattr__(name: str):
    if name == "RagAgent":
        from .core import RagAgent

        return RagAgent
    if name == "parse_upload_file":
        from .parsers import parse_upload_file

        return parse_upload_file
    raise AttributeError(name)
