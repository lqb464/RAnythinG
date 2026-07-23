"""Select storage backend: PostgreSQL (DATABASE_URL) or local files."""

import os

USE_POSTGRES = bool(os.getenv("DATABASE_URL"))

if USE_POSTGRES:
    from . import postgres_store as _backend
else:
    from . import workspace_store as _backend

list_notebooks = _backend.list_notebooks
create_notebook = _backend.create_notebook
get_notebook = _backend.get_notebook
update_notebook_name = _backend.update_notebook_name
delete_notebook = _backend.delete_notebook
load_notes = _backend.load_notes
save_notes = _backend.save_notes
load_chat_history = _backend.load_chat_history
save_chat_history = _backend.save_chat_history
list_source_files = _backend.list_source_files
save_upload_bytes = _backend.save_upload_bytes
save_uploaded_file = _backend.save_uploaded_file
remove_source = _backend.remove_source
collect_documents = _backend.collect_documents
build_and_save_index = _backend.build_and_save_index
persist_index = _backend.persist_index
load_index = _backend.load_index

append_chat_message = getattr(_backend, "append_chat_message", None)
load_studio_outputs = getattr(_backend, "load_studio_outputs", lambda *a: [])
save_studio_output = getattr(_backend, "save_studio_output", lambda *a, **k: {})
delete_studio_output = getattr(_backend, "delete_studio_output", lambda *a: False)
load_assembly_board = getattr(_backend, "load_assembly_board", lambda *a: None)
save_assembly_board = getattr(_backend, "save_assembly_board", lambda *a, **k: {})

backend_name = "postgresql" if USE_POSTGRES else "filesystem"
