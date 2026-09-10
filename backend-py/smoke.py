import asyncio
import tempfile

from terminal_agent.capability.core import CapabilityRegistry
from terminal_agent.device.simulator import DeviceSimulator
from terminal_agent.model.fake import FakeModelAdapter
from terminal_agent.persistence.sqlite import SqlitePersistence
from terminal_agent.persistence.store import InMemoryRunStore
from terminal_agent.policy.engine import PolicyEngine
from terminal_agent.runtime.executor import CapabilityExecutor
from terminal_agent.runtime.harness import HarnessService
from terminal_agent.runtime.support import RuntimeSettings, TaskBinder
from terminal_agent.runtime.verifier import Verifier


async def main() -> None:
    tmp = tempfile.mkdtemp()
    registry = CapabilityRegistry()
    sim = DeviceSimulator(registry)
    store = InMemoryRunStore(tmp)
    policy = PolicyEngine(registry, False)
    executor = CapabilityExecutor(sim, registry, policy, store)
    verifier = Verifier(sim)
    persistence = SqlitePersistence(store, sim, tmp + "/db.sqlite", enabled=False)
    harness = HarnessService(
        store, sim, FakeModelAdapter(), TaskBinder(registry), executor, verifier, persistence, RuntimeSettings()
    )
    run = await harness.create_run(None, "把空调设为 23 度", "eval", True)
    print(run.lifecycle, run.route_type, run.stop_reason, run.result_summary)
    print((await sim.read_state(None)).state["temperature_setpoint"])
    print([(a.capability_id, a.execution_status) for a in run.actions])

    # multi-agent case
    rest = "后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。"
    await sim.force_new_environment()
    await sim.reset_to_defaults()
    for r in store.list():
        r.lifecycle = r.lifecycle.__class__.CANCELLED
    run2 = await harness.create_run(None, rest, "eval", True)
    print(run2.lifecycle, run2.route_type, run2.stop_reason)
    print(run2.result_summary)
    s = (await sim.read_state(None)).state
    print({k: s[k] for k in ("temperature_setpoint", "fan_level", "media_volume", "window_open")})


asyncio.run(main())
