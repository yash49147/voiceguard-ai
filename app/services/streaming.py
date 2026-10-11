from dataclasses import dataclass, field


SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2  # PCM 16-bit
CHUNK_DURATION_SECONDS = 5
CHUNK_DURATION_MS = CHUNK_DURATION_SECONDS * 1000

BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES
CHUNK_SIZE_BYTES = BYTES_PER_SECOND * CHUNK_DURATION_SECONDS


@dataclass
class StreamingSession:
    call_id: int
    user_id: int
    buffer: bytearray = field(default_factory=bytearray)
    frame_count: int = 0
    chunk_sequence: int = 0

    def add_frame(self, data: bytes) -> list[bytes]:
        if not data:
            raise ValueError("Audio frame cannot be empty")

        self.buffer.extend(data)
        self.frame_count += 1

        completed_chunks: list[bytes] = []

        while len(self.buffer) >= CHUNK_SIZE_BYTES:
            chunk = bytes(self.buffer[:CHUNK_SIZE_BYTES])
            del self.buffer[:CHUNK_SIZE_BYTES]

            self.chunk_sequence += 1
            completed_chunks.append(chunk)

        return completed_chunks

    @property
    def buffered_bytes(self) -> int:
        return len(self.buffer)

    @property
    def buffered_seconds(self) -> float:
        return self.buffered_bytes / BYTES_PER_SECOND