"""Fake-mode eval gate — must stay at 54/54 with false_success=0."""

from __future__ import annotations

import pytest

from terminal_agent.eval.runner import EvalRunner


@pytest.mark.asyncio
async def test_fake_agent_eval_should_pass_all_seeds() -> None:
    runner = EvalRunner.create_standalone()
    report = await runner.run("agent")
    assert report["model_mode"] == "fake"
    assert report["total"] == 54
    failed = int(report["failed"])
    if failed > 0:
        failed_lines = [
            f"{c.get('id')}: {c.get('message')}"
            for c in report["cases"]
            if not c.get("passed")
        ]
        pytest.fail(f"Fake 评测门禁失败 ({failed}):\n" + "\n".join(failed_lines))
    assert int(report["false_success"]) == 0
    assert int(report["passed"]) >= 50
