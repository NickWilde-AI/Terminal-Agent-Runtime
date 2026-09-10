from terminal_agent.agent.contracts import StateSnapshot
from terminal_agent.runtime.goal_compiler import GoalCompiler
from terminal_agent.runtime.task_binder import TaskBinder


def test_complex_request_covers_every_detected_domain() -> None:
    candidate = GoalCompiler.compile(
        "打开空调，设为23度；左前车窗打开一半；播放周杰伦；然后导航到虹桥机场。",
        None,
        [],
    )
    assert candidate.route_hint == "MULTI_AGENT"
    assert {goal["type"] for goal in candidate.goals} == {
        "climate_power",
        "cabin_temperature",
        "window_position",
        "media_play",
        "nav_start",
    }
    assert "coverage_missing" not in candidate.raw


def test_rest_defaults_keep_constraints_and_muted_media() -> None:
    candidate = GoalCompiler.compile(
        "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。",
        StateSnapshot(state={"media_muted": True}),
        [],
    )
    assert candidate.route_hint == "MULTI_AGENT"
    assert {"type": "no_window", "source": "user"} in candidate.constraints
    assert any(goal["type"] == "media_keep_muted" for goal in candidate.goals)
    assert not any(goal["type"] == "window_position" for goal in candidate.goals)


def test_navigation_waypoint_does_not_steal_destination() -> None:
    candidate = GoalCompiler.compile("导航到东方明珠途经一个加油站", None, [])
    assert candidate.route_hint == "MULTI_AGENT"
    assert any(
        goal["type"] == "nav_start" and goal["destination"] == "东方明珠"
        for goal in candidate.goals
    )
    assert any(
        goal["type"] == "nav_add_waypoint" and goal["name"] == "加油站"
        for goal in candidate.goals
    )


def test_life_checkout_is_not_navigation() -> None:
    candidate = GoalCompiler.compile("去结算", None, [])
    assert candidate.route_hint == "FAST"
    assert candidate.fast_action == {"capability_id": "life.go_to_checkout", "params": {}}


def test_waypoint_requires_existing_destination() -> None:
    candidate = GoalCompiler.compile(
        "加个途经点星巴克",
        StateSnapshot(state={"navigation_active": True, "navigation_destination": None}),
        [],
    )
    assert candidate.route_hint == "CLARIFY"


def test_binder_uses_product_effects_not_candidate_criteria() -> None:
    candidate = GoalCompiler.compile("把空调设为 23 度", None, [])
    candidate.criteria.clear()
    task = TaskBinder().bind("run-1", "把空调设为 23 度", "demo-defaults-v1", candidate)
    assert task.criteria[0].template_id == "field_eq"
    assert task.criteria[0].params == {"field": "temperature_setpoint", "value": 23}
