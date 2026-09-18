"""Read members out of a ZIP archive on a web server, without downloading the archive.

A ZIP file keeps its table of contents (the central directory) at its end, and every host this product
fetches vision data from answers HTTP range requests. So an archive is listed with a few small requests at
its tail, and each chosen member is fetched with one request covering its local header and its compressed
bytes. Every member is inflated in memory and checked against the CRC32 its archive records before a byte
is written, then written atomically, so a partial or corrupted member never lands on disk under its name.

This is what makes the selection a rule over members (environment, trajectory, frames) rather than a
choice among archives: the TartanAir front camera alone is 1.87 TB as archives, and the canonical selection
is about 5 percent of it.
"""

from __future__ import annotations

import io
import os
import struct
import threading
import zipfile
import zlib
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")  # the 30-byte fixed part of a local file header
LOCAL_HEADER_SIGNATURE = 0x04034B50
TIMEOUT = (20, 180)  # connect, read (seconds)

_sessions = threading.local()


def session() -> requests.Session:
    """One keep-alive session per thread, retrying transient server errors with backoff."""
    s = getattr(_sessions, "session", None)
    if s is None:
        s = requests.Session()
        retry = Retry(total=8, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "HEAD"))
        s.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4))
        s.mount("http://", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4))
        _sessions.session = s
    return s


def get_range(url: str, start: int, end: int) -> bytes:
    """Bytes [start, end] of a remote file; fails unless the server honoured the range."""
    response = session().get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=TIMEOUT)
    if response.status_code != 206:
        raise OSError(f"{url}: range {start}-{end} answered {response.status_code}, not 206")
    data = response.content
    if len(data) != end - start + 1:
        raise OSError(f"{url}: range {start}-{end} returned {len(data)} bytes")
    return data


class _HttpFile(io.RawIOBase):
    """A read-only, seekable view of a remote file, used only to parse the central directory."""

    def __init__(self, url: str, size: int):
        self.url, self.size, self.pos = url, size, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def readinto(self, buffer) -> int:
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        data = get_range(self.url, self.pos, end)
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


@dataclass(frozen=True)
class Member:
    name: str
    header_offset: int
    compress_size: int
    file_size: int
    compress_type: int
    crc: int


class RemoteZip:
    """The members of a remote ZIP archive, listed from its central directory."""

    def __init__(self, url: str):
        # The size comes from a one-byte ranged GET, not a HEAD: some hosts (DaRUS) redirect to a presigned
        # URL whose signature covers GET only, and answer HEAD with 403. The URL after redirects is kept, so
        # every member read goes straight to the storage and skips the redirect.
        probe = session().get(url, headers={"Range": "bytes=0-0"}, timeout=TIMEOUT, allow_redirects=True)
        if probe.status_code != 206 or "Content-Range" not in probe.headers:
            raise OSError(f"{url}: does not answer range requests (status {probe.status_code})")
        self.url = probe.url
        self.size = int(probe.headers["Content-Range"].rsplit("/", 1)[1])
        # a large read buffer turns the central directory into a handful of range requests
        with zipfile.ZipFile(io.BufferedReader(_HttpFile(url, self.size), buffer_size=1 << 20)) as archive:
            self.members = {
                info.filename: Member(info.filename, info.header_offset, info.compress_size, info.file_size,
                                      info.compress_type, info.CRC)
                for info in archive.infolist()
                if not info.is_dir()
            }

    def names(self) -> list[str]:
        return sorted(self.members)

    def read(self, name: str) -> bytes:
        """One member, inflated and checked against its recorded CRC32."""
        member = self.members[name]
        # the local header's name and extra fields can differ in length from the central directory's, so
        # fetch generously, then read the true lengths from the local header itself
        slack = 30 + len(name.encode("utf-8")) + 1024
        blob = get_range(self.url, member.header_offset,
                         min(member.header_offset + slack + member.compress_size, self.size) - 1)
        signature, *_, name_length, extra_length = LOCAL_HEADER.unpack_from(blob, 0)
        if signature != LOCAL_HEADER_SIGNATURE:
            raise OSError(f"{self.url}:{name}: no local file header at offset {member.header_offset}")
        start = 30 + name_length + extra_length
        if start + member.compress_size > len(blob):
            blob += get_range(self.url, member.header_offset + len(blob),
                              member.header_offset + start + member.compress_size - 1)
        payload = blob[start: start + member.compress_size]
        if member.compress_type == zipfile.ZIP_STORED:
            data = payload
        elif member.compress_type == zipfile.ZIP_DEFLATED:
            data = zlib.decompress(payload, -15)
        else:
            raise OSError(f"{self.url}:{name}: compression method {member.compress_type} is not supported")
        if len(data) != member.file_size or (zlib.crc32(data) & 0xFFFFFFFF) != member.crc:
            raise OSError(f"{self.url}:{name}: CRC32 or size mismatch, the member is corrupt or truncated")
        return data

    def fetch(self, name: str, destination: Path) -> int:
        """Write one member to disk atomically; returns the bytes written."""
        data = self.read(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        partial.write_bytes(data)
        os.replace(partial, destination)
        return len(data)


def fetch_members(archive: RemoteZip, names: Iterable[str], destination_of: Callable[[str], Path],
                  workers: int = 12, done: set[str] | None = None,
                  on_member: Callable[[str, int], None] | None = None) -> dict:
    """Fetch many members in parallel; members already done (by name) are skipped, failures are reported."""
    done = done or set()
    todo = [n for n in names if n not in done]
    written, failed = 0, {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(archive.fetch, name, destination_of(name)): name for name in todo}
        for future in as_completed(futures):
            name = futures[future]
            try:
                size = future.result()
            except Exception as error:  # a member failing is recorded, the others continue
                failed[name] = str(error)
                continue
            written += size
            if on_member:
                on_member(name, size)
    return {"requested": len(todo), "skipped": len(done), "bytes": written, "failed": failed}
