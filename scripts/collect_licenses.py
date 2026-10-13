"""Copy installed Python distribution notices into the portable build."""
import argparse
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    for dist in distributions():
        name = dist.metadata["Name"] or "unnamed"
        for file in dist.files or ():
            if any(word in file.name.lower() for word in ("license", "copying", "copyright", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    output = args.destination / name / str(file).replace("..", "_")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, output)
    for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if candidate.is_file():
            shutil.copy2(candidate, args.destination / "PYTHON-LICENSE.txt")
            break


if __name__ == "__main__":
    main()
