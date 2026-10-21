"""Read and split the single, free-text input file."""

import re
from dataclasses import dataclass
from pathlib import Path

MAX_INPUT_BYTES = 100_000
MAX_SUPPLIERS = 8
SEPARATOR = re.compile(r"^\s*===\s*PACKET\s*===\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Packet:
    buyer: str
    suppliers: tuple[str, ...]

    @property
    def sources(self) -> dict[str, str]:
        return {"buyer": self.buyer, **{
            f"supplier_{index}": text
            for index, text in enumerate(self.suppliers, 1)
        }}


def parse_packet(text: str) -> Packet:
    if not text.strip():
        raise ValueError("Quote packet is empty.")
    if len(text.encode("utf-8")) > MAX_INPUT_BYTES:
        raise ValueError(f"Quote packet exceeds {MAX_INPUT_BYTES:,} UTF-8 bytes.")
    blocks = [block.strip() for block in SEPARATOR.split(text.lstrip("\ufeff"))]
    if len(blocks) < 2 or any(not block for block in blocks):
        raise ValueError(
            "Put buyer requirements first, then separate each supplier reply "
            "with a line containing ===PACKET===. Blocks must not be empty."
        )
    if len(blocks) - 1 > MAX_SUPPLIERS:
        raise ValueError(f"At most {MAX_SUPPLIERS} supplier replies are supported.")
    return Packet(blocks[0], tuple(blocks[1:]))


def read_packet(path: Path) -> str:
    with path.open("rb") as stream:
        content = stream.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError(f"Quote packet exceeds {MAX_INPUT_BYTES:,} UTF-8 bytes.")
    text = content.decode("utf-8-sig")
    parse_packet(text)
    return text
