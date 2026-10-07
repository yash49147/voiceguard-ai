from dataclasses import dataclass, field


@dataclass
class StreamingSession:
    call_id: int
    user_id: int
    buffer: bytearray = field(default_factory=bytearray)
    frame_count: int = 0

    def add_frame(self, data: bytes) -> int:
        if not data:
            raise ValueError("Audio frame cannot be empty")

        self.buffer.extend(data)
        self.frame_count += 1

        return len(self.buffer)

    @property
    def buffered_bytes(self) -> int:
        return len(self.buffer)