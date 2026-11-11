"""Persist received payloads and build ACKs only after successful writes."""

import json
from pathlib import Path

import cv2
import numpy as np

from protocol import digest, transfer_id


def save_text(output: Path, identifier: str, text: str) -> dict:
    identifier = transfer_id(identifier)
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    payload = text.encode("utf-8")
    (output / f"{identifier}.txt").write_bytes(payload)
    return {"id": identifier, "kind": "text", "ok": True, "sha256": digest(payload)}


def save_image(output: Path, identifier: str, image: np.ndarray) -> dict:
    identifier = transfer_id(identifier)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        raise ValueError("Expected a nonempty uint8 BGR image with 3 channels")
    path = output / f"{identifier}.png"
    if not cv2.imwrite(str(path), image):
        raise OSError(f"Cannot save {path}")
    # Confirm lossless disk persistence before acknowledging the pixels.
    saved = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if saved is None or saved.shape != image.shape or digest(saved.tobytes()) != digest(image.tobytes()):
        raise OSError("Saved PNG does not match received pixels")
    result = {"id": identifier, "kind": "image", "ok": True,
              "sha256": digest(saved.tobytes()), "shape": list(saved.shape),
              "bytes": saved.nbytes, "file": path.name}
    (output / f"{identifier}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
