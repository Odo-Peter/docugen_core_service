"""Helpers and payload catalogues for the renderer security tests."""

import io
import socket
import struct
import threading
import time
import zlib

from pypdf import PdfReader

MARKER = "LEAKMARKER7F3A"

# Sandbox escape attempts. Each must fail as a template error.
ESCAPES = {
    "dunder-class": "{{ ''.__class__ }}",
    "mro-subclasses": "{{ ''.__class__.__mro__[1].__subclasses__() }}",
    "cycler-globals": "{{ cycler.__init__.__globals__ }}",
    "joiner-globals": "{{ joiner.__init__.__globals__ }}",
    "namespace-globals": "{{ namespace.__init__.__globals__ }}",
    "lipsum-globals": "{{ lipsum.__globals__ }}",
    "self-dict": "{{ self.__dict__ }}",
    "attr-filter": "{{ customer|attr('__class__') }}",
    "format-string": "{{ '{0.__class__}'.format(customer) }}",
    "open-builtin": "{{ open('/etc/passwd').read() }}",
    "import-builtin": "{{ __import__('os').popen('id').read() }}",
    "getattr-builtin": "{{ getattr(customer, '__class__') }}",
    "config-object": "{{ config.items() }}",
}

# Broken or abusive templates. Each must surface as a template error, never as
# a bare exception (which the API would turn into a 500).
BROKEN = {
    "syntax-unclosed-expression": "{{ customer.name ",
    "syntax-unclosed-block": "{% if customer %}",
    "syntax-stray-endfor": "{% endfor %}",
    "unknown-filter": "{{ customer.name | nope }}",
    "unknown-test": "{% if customer is nope %}x{% endif %}",
    "undefined-variable": "{{ missing }}",
    "undefined-attribute": "{{ customer.missing }}",
    "include-absolute": '{% include "/etc/passwd" %}',
    "include-relative": '{% include "../../../etc/passwd" %}',
    "extends": '{% extends "/etc/passwd" %}',
    "import": '{% import "/etc/passwd" as p %}',
    "from-import": '{% from "/etc/passwd" import x %}',
    "range-bomb": "{% for i in range(100000000) %}x{% endfor %}",
    "infinite-recursion": "{% macro m() %}{{ m() }}{% endmacro %}{{ m() }}",
    "division-by-zero": "{{ 1 / 0 }}",
    "call-a-string": "{{ customer.name() }}",
}


class TcpCanary:
    """Listens on a free 127.0.0.1 port and counts connection attempts.

    Any scheme that tries to reach it (http, https, ftp, ...) is recorded.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(16)
        self._sock.settimeout(0.05)
        self.port = self._sock.getsockname()[1]
        self.host = f"127.0.0.1:{self.port}"
        self._count = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._count += 1
            conn.close()

    @property
    def connections(self) -> int:
        time.sleep(0.1)  # let the accept loop record in-flight connections
        return self._count

    def __enter__(self) -> "TcpCanary":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self._sock.close()


def tiny_png() -> bytes:
    """A valid 1x1 grayscale PNG, built by hand so there is no Pillow dependency."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x80")  # filter byte + one gray pixel
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "".join(page.extract_text() or "" for page in reader.pages)


def squash(text: str) -> str:
    """Remove all whitespace so PDF text-extraction spacing can't break a match."""
    return "".join(text.split())


def _resolve(obj):
    return obj.get_object() if hasattr(obj, "get_object") else obj


def _count_images(resources) -> int:
    resources = _resolve(resources) or {}
    xobjects = _resolve(resources.get("/XObject")) or {}
    total = 0
    for ref in xobjects.values():
        obj = _resolve(ref)
        subtype = obj.get("/Subtype")
        if subtype == "/Image":
            total += 1
        elif subtype == "/Form":
            total += _count_images(obj.get("/Resources"))
    return total


def pdf_image_count(content: bytes) -> int:
    reader = PdfReader(io.BytesIO(content))
    return sum(_count_images(page.get("/Resources")) for page in reader.pages)