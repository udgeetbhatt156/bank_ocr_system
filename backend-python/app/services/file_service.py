from pathlib import Path
from typing import Any

import aiofiles


async def write_file(upload_file: Any, destination: Path) -> Path:
    """Save an uploaded file to disk asynchronously."""
    async with aiofiles.open(destination, "wb") as f:
        while chunk := await upload_file.read(65536):
            await f.write(chunk)
    return destination
