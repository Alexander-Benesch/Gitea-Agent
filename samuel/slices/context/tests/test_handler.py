from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from samuel.core.bus import Bus
from samuel.core.commands import BuildContextCommand
from samuel.core.ports import ISkeletonBuilder
from samuel.core.types import SkeletonEntry
from samuel.slices.context.handler import ContextHandler


class StubSkeletonBuilder(ISkeletonBuilder):
    supported_extensions = {".py"}

    def extract(self, file: Path) -> list[SkeletonEntry]:
        return [
            SkeletonEntry(
                name="my_func",
                kind="function",
                file=str(file),
                line_start=1,
                line_end=5,
            )
        ]


class TestBuildSkeleton:
    def test_build_skeleton_returns_files(self, tmp_path: Path):
        (tmp_path / "mod.py").write_text("def my_func():\n    pass\n")
        bus = Bus()
        handler = ContextHandler(
            bus,
            project_root=tmp_path,
            skeleton_builders=[StubSkeletonBuilder()],
        )

        cmd = BuildContextCommand(payload={})
        result = handler.handle(cmd)

        assert result["files"] == 1
        assert "mod.py" in result["skeleton"]
        assert result["skeleton"]["mod.py"][0]["name"] == "my_func"

    def test_build_skeleton_empty_directory(self, tmp_path: Path):
        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path, skeleton_builders=[StubSkeletonBuilder()])

        result = handler.handle(BuildContextCommand(payload={}))

        assert result["files"] == 0
        assert result["skeleton"] == {}


class TestGetSlice:
    def test_get_slice_returns_content(self, tmp_path: Path):
        f = tmp_path / "hello.py"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")

        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path)

        cmd = BuildContextCommand(payload={"file": "hello.py", "start": 2, "end": 4})
        result = handler.handle(cmd)

        assert result["file"] == "hello.py"
        assert result["start"] == 2
        assert result["end"] == 4
        assert result["content"] == "line2\nline3\nline4"
        assert result["line_count"] == 3

    def test_get_slice_file_not_found(self, tmp_path: Path):
        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path)

        cmd = BuildContextCommand(payload={"file": "missing.py", "start": 1, "end": 5})
        result = handler.handle(cmd)

        assert "error" in result
        assert "not found" in result["error"]

    def test_get_slice_clamps_line_range(self, tmp_path: Path):
        f = tmp_path / "short.py"
        f.write_text("a\nb\n")

        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path)

        cmd = BuildContextCommand(payload={"file": "short.py", "start": 1, "end": 100})
        result = handler.handle(cmd)

        assert result["line_count"] == 2


class TestHMACSignature:
    def test_signature_present_when_key_set(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("line1\nline2\nline3\n")

        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path, hmac_key="my-secret")

        cmd = BuildContextCommand(payload={"file": "code.py", "start": 1, "end": 2})
        result = handler.handle(cmd)

        assert "signature" in result
        expected = hmac.new(
            b"my-secret",
            b"code.py:1:2",
            hashlib.sha256,
        ).hexdigest()[:16]
        assert result["signature"] == expected

    def test_no_signature_without_key(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("line1\nline2\n")

        bus = Bus()
        handler = ContextHandler(bus, project_root=tmp_path)

        cmd = BuildContextCommand(payload={"file": "code.py", "start": 1, "end": 2})
        result = handler.handle(cmd)

        assert "signature" not in result
