from __future__ import annotations

from pathlib import Path

from samuel.core.bus import Bus
from samuel.core.commands import VerifyACCommand
from samuel.slices.ac_verification.handler import ACVerificationHandler


class TestDiffCheck:
    def test_diff_passes_when_file_exists(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] handler.py"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True
        assert result["results"][0]["tag"] == "DIFF"

    def test_diff_fails_when_file_missing(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] nonexistent.py"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False


class TestExistsCheck:
    def test_exists_passes_when_file_present(self, tmp_path: Path):
        (tmp_path / "config.yaml").write_text("key: value\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] config.yaml"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_exists_fails_when_missing(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] missing.yaml"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False


class TestImportCheck:
    def test_import_passes_for_safe_stdlib(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [IMPORT] json"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_import_fails_for_nonexistent_module(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [IMPORT] nonexistent_module_xyz_123"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert "import failed" in result["results"][0]["reason"]

    def test_import_blocks_injection(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = '- [ ] [IMPORT] os; os.system("rm -rf /")'
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "rejected" in result["results"][0]["reason"]

    def test_import_blocks_dangerous_modules(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        for module in ["os", "sys", "subprocess", "shutil"]:
            plan = f"- [ ] [IMPORT] {module}"
            cmd = VerifyACCommand(payload={"plan_text": plan})
            result = handler.handle(cmd)
            assert result["results"][0]["passed"] is False
            assert "blocked module" in result["results"][0]["reason"]


class TestPathTraversal:
    def test_path_traversal_blocked(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [DIFF] ../../../etc/passwd"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "traversal blocked" in result["results"][0]["reason"]

    def test_exists_traversal_blocked(self, tmp_path: Path):
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [EXISTS] ../../etc/shadow"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["results"][0]["passed"] is False
        assert "traversal blocked" in result["results"][0]["reason"]


class TestGrepCheck:
    def test_grep_finds_pattern(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("class MyHandler:\n    pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP] class MyHandler"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_grep_fails_when_pattern_absent(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def something(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP] class MissingClass"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False


class TestGrepNotCheck:
    def test_grep_not_passes_when_absent(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def clean_code(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP:NOT] deprecated_function"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["results"][0]["passed"] is True

    def test_grep_not_fails_when_present(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("def deprecated_function(): pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = "- [ ] [GREP:NOT] deprecated_function"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False


class TestManualCheck:
    def test_manual_always_fails_with_flag(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [MANUAL] Check the UI visually"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert result["results"][0]["manual"] is True
        assert result["manual"] == 1


class TestUnknownTag:
    def test_unknown_tag_fails_gracefully(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        plan = "- [ ] [FOOBAR] something"
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is False
        assert result["results"][0]["passed"] is False
        assert "unknown tag" in result["results"][0]["reason"]


class TestMixedACs:
    def test_mixed_auto_checks(self, tmp_path: Path):
        (tmp_path / "handler.py").write_text("class Handler:\n    pass\n")
        bus = Bus()
        handler = ACVerificationHandler(bus, project_root=tmp_path)

        plan = (
            "- [ ] [EXISTS] handler.py\n"
            "- [ ] [GREP] class Handler\n"
        )
        cmd = VerifyACCommand(payload={"plan_text": plan})
        result = handler.handle(cmd)

        assert result["verified"] is True
        assert result["total"] == 2
        assert result["passed"] == 2

    def test_empty_plan_not_verified(self):
        bus = Bus()
        handler = ACVerificationHandler(bus)

        cmd = VerifyACCommand(payload={"plan_text": ""})
        result = handler.handle(cmd)

        assert result["verified"] is False
