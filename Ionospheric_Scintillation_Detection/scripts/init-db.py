from pathlib import Path

from isd.application.bootstrap import bootstrap

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parents[1] / "src" / "isd"
    bootstrap(base_dir)
    print("Database initialized.")
