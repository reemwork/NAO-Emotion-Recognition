
"""Image validation and storage utilities for NAO camera uploads."""

from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000


async def read_image(frame: UploadFile) -> Image.Image:
    """Read, validate, and decode an uploaded image."""
    data = await frame.read(MAX_IMAGE_BYTES + 1)

    if not data or len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="Image must be non-empty and at most 10 MB."
        )

    try:
        with Image.open(BytesIO(data)) as uploaded:
            if uploaded.width * uploaded.height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions are too large.")

            image = uploaded.convert("RGB")
            image.load()
            return image

    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid image file."
        ) from error


def save_image(
    image: Image.Image,
    folder: Path,
    filename: str,
    root: Path
) -> str:
    """Save a JPEG and return its path relative to project root."""
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / filename
    image.save(path, format="JPEG", quality=90)

    return path.relative_to(root).as_posix()
