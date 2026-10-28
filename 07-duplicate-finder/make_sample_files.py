"""Create a sample folder with duplicate photos and documents in sample/.

Example: python make_sample_files.py
"""
import os
import random
import shutil
from pathlib import Path

HERE = Path(__file__).parent
SAMPLE = HERE / "sample"


def main():
    shutil.rmtree(SAMPLE, ignore_errors=True)
    rng = random.Random(42)
    photos = {f"IMG_{i:04d}.jpg": rng.randbytes(rng.randint(150_000, 900_000)) for i in range(1, 7)}
    for name, data in photos.items():
        (SAMPLE / "Photos" / "2025").mkdir(parents=True, exist_ok=True)
        (SAMPLE / "Photos" / "2025" / name).write_bytes(data)
    # The usual mess: a phone backup and a "to sort" folder holding copies of the same pictures.
    for folder, names in {"Phone backup": ["IMG_0001.jpg", "IMG_0002.jpg", "IMG_0005.jpg"],
                          "To sort": ["IMG_0002.jpg", "IMG_0006.jpg"]}.items():
        (SAMPLE / folder).mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy2(SAMPLE / "Photos" / "2025" / name, SAMPLE / folder / name)
    (SAMPLE / "Documents").mkdir()
    invoice = b"Invoice 2025-104\nTotal: 1,250.00 $\n" * 200
    (SAMPLE / "Documents" / "invoice-104.txt").write_bytes(invoice)
    (SAMPLE / "Documents" / "invoice-104 (1).txt").write_bytes(invoice)
    (SAMPLE / "Documents" / "notes.txt").write_bytes(b"Meeting notes\n" * 80)
    # Make the originals the oldest files, so they are the ones kept by default.
    for path in (SAMPLE / "Photos" / "2025").iterdir():
        os.utime(path, (1_700_000_000, 1_700_000_000))
    print(f"Sample files created in {SAMPLE}")


if __name__ == "__main__":
    main()
