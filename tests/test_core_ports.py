from __future__ import annotations

import pytest

from samuel.core.ports import (
    IAuditLog,
    IAuditSink,
    IAuthProvider,
    IConfig,
    IDashboardRenderer,
    IExternalEventSink,
    IExternalGate,
    IExternalTrigger,
    ILLMProvider,
    INotificationSink,
    IPatchApplier,
    IProjectRegistry,
    IQualityCheck,
    ISecretsProvider,
    ISkeletonBuilder,
    IVersionControl,
)
from samuel.core.types import LLMResponse


def test_all_ports_are_abstract():
    abcs = [
        IAuditLog, IAuditSink, IAuthProvider, IConfig,
        IDashboardRenderer, IExternalEventSink, IExternalGate,
        IExternalTrigger, ILLMProvider, INotificationSink,
        IPatchApplier, IProjectRegistry, IQualityCheck,
        ISecretsProvider, ISkeletonBuilder, IVersionControl,
    ]
    for abc_cls in abcs:
        with pytest.raises(TypeError):
            abc_cls()


def test_version_control_capabilities_default():
    class DummyVC(IVersionControl):
        def get_issue(self, number): ...
        def get_comments(self, number): ...
        def post_comment(self, number, body): ...
        def create_pr(self, head, base, title, body): ...
        def swap_label(self, number, remove, add): ...
        def list_labels(self): ...
        def create_label(self, name, color, description=""): ...
        def list_issues(self, labels): ...
        def close_issue(self, number): ...
        def merge_pr(self, pr_id): ...
        def issue_url(self, number): ...
        def pr_url(self, pr_id): ...
        def branch_url(self, branch): ...

    vc = DummyVC()
    assert vc.capabilities == set()


def test_llm_provider_capabilities_default():
    class DummyLLM(ILLMProvider):
        def complete(self, messages, **kwargs):
            return LLMResponse(text="", input_tokens=0, output_tokens=0)
        def estimate_tokens(self, text):
            return 0
        @property
        def context_window(self):
            return 100000

    llm = DummyLLM()
    assert llm.capabilities == set()
    assert llm.context_window == 100000
