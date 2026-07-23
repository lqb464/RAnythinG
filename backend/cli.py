import argparse
from pathlib import Path
from typing import List, Tuple

from .core import RagAgent
from .parsers import parse_text_file


def parse_document_file(path: Path) -> Tuple[str, str]:
    text = parse_text_file(path.read_bytes())
    return path.name, text


def load_documents_from_folder(folder: Path, extensions: List[str]) -> List[Tuple[str, str]]:
    docs = []
    for path in folder.rglob("*"):
        if path.suffix.lower() in extensions:
            name, text = parse_document_file(path)
            if text.strip():
                docs.append((name, text))
    return docs


def build_index_command(args: argparse.Namespace) -> None:
    source_folder = Path(args.source_folder)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    docs = load_documents_from_folder(source_folder, [".txt", ".md", ".csv", ".pdf", ".docx"])

    agent = RagAgent()
    agent.add_documents(docs)
    agent.save_index(output_dir / args.index_name)
    agent.save_metadata(output_dir / (args.index_name + ".json"))
    print(f"Index built and saved to {output_dir / args.index_name}")


def query_command(args: argparse.Namespace) -> None:
    agent = RagAgent()
    agent.load_index(args.index_path)
    agent.load_metadata(args.metadata_path)
    answer, relevant = agent.answer(args.query, top_k=args.top_k)
    print("Answer:\n", answer)
    print("\nSources:")
    for idx, chunk in enumerate(relevant, start=1):
        print(f"{idx}. {chunk.source}: {chunk.text}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("rag_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Build a FAISS index from document folder")
    build_parser.add_argument("--source-folder", required=True)
    build_parser.add_argument("--output-dir", default="./data")
    build_parser.add_argument("--index-name", default="rag_index.faiss")
    build_parser.set_defaults(func=build_index_command)

    query_parser = subparsers.add_parser("query", help="Query a saved FAISS index")
    query_parser.add_argument("--index-path", required=True)
    query_parser.add_argument("--metadata-path", required=True)
    query_parser.add_argument("--query", required=True)
    query_parser.add_argument("--top-k", type=int, default=3)
    query_parser.set_defaults(func=query_command)

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
