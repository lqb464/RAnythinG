"""API entrypoint: python -m backend"""

from dotenv import load_dotenv

load_dotenv()

from backend.server import run

if __name__ == "__main__":
    run()
