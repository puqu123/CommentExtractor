"""Create demonstrator files from fictional content, separate from real user data."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.samples import create_samples

if __name__ == "__main__":
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("local_data/demo")
    create_samples(output)
    print(output.resolve())
