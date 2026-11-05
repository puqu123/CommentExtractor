"""Copy installed runtime license texts alongside the portable distribution."""
from importlib import metadata
from pathlib import Path
import shutil

RUNTIME = ["Pillow", "rapidocr-onnxruntime", "onnxruntime", "numpy", "opencv-python",
           "shapely", "pyclipper", "PyYAML", "six", "tqdm", "protobuf", "flatbuffers",
           "coloredlogs", "humanfriendly", "pyreadline3", "sympy", "mpmath", "packaging",
           "colorama"]


def collect(destination):
    destination = Path(destination)
    count = 0
    for name in RUNTIME:
        dist = metadata.distribution(name)
        for item in dist.files or []:
            if not any(word in item.name.lower() for word in ("license", "copying", "notice")):
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file() or source.suffix.lower() in {".py", ".pyc", ".pyd"}:
                continue
            # Preserve package-relative subdirectories for duplicate basenames.
            target = destination / (name + "-" + dist.version) / Path(*item.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            count += 1
    print(f"Copied {count} installed runtime license and notice files.")


if __name__ == "__main__":
    collect(Path(__file__).resolve().parents[1] / "licenses" / "dependencies")
