import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, type DeviceState, type EvalReport, type RunView, type RuntimeEvent } from './api'
import { VehicleScene, snapshotFromDevice } from './vehicle/VehicleScene'
import './index.css'

const EXAMPLES = [
  '把空调设为 23 度',
  '打开空调，设为23度；左前车窗打开一半；播放周杰伦；然后导航到虹桥机场。',
  '后排要休息，把座舱调整舒服一点；媒体声音调低，但保留导航提示，不要开窗。',
  '打开左前车窗一半',
  '导航有画面但没有声音，帮我检查一下，不要重启车机。',
  '记住我喜欢温度24度',
]

function statusClass(life?: string) {
  if (!life) return ''
  if (life === 'COMPLETED') return 'status-ok'
  if (['FAILED', 'STOPPED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED'].includes(life)) return 'status-bad'
  if (life.startsWith('WAITING') || life === 'PARTIAL') return 'status-warn'
  return ''
}

function actionField(a: NonNullable<RunView['actions']>[number], camel: string, snake: string) {
  return (a as Record<string, unknown>)[camel] ?? (a as Record<string, unknown>)[snake]
}

export default function App() {
  const [text, setText] = useState(EXAMPLES[0])
  const [interveneText, setInterveneText] = useState('空调先不要调了')
  const [device, setDevice] = useState<DeviceState | null>(null)
  const [run, setRun] = useState<RunView | null>(null)
  const [events, setEvents] = useState<RuntimeEvent[]>([])
  const [history, setHistory] = useState<RunView[]>([])
  const [replayMode, setReplayMode] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [clarify, setClarify] = useState('')
  const [meta, setMeta] = useState<Record<string, unknown> | null>(null)
  const [evalReport, setEvalReport] = useState<EvalReport | null>(null)
  const [memories, setMemories] = useState<Array<Record<string, unknown>>>([])
  const [memoryText, setMemoryText] = useState('记住我喜欢温度24度')

  const refreshDevice = useCallback(async () => {
    setDevice(await api.deviceState())
  }, [])

  const refreshMemory = useCallback(async () => {
    try {
      const data = await api.listMemory('web')
      setMemories(data.memories ?? [])
    } catch {
      // optional endpoint
    }
  }, [])

  const refreshHistory = useCallback(async () => {
    try {
      const raw = await api.listRuns()
      const list = Array.isArray(raw) ? raw : raw.runs ?? []
      setHistory(list)
    } catch {
      // list endpoint may appear after backend Phase 3/4
    }
  }, [])

  const loadEvents = async (runId: string) => {
    const ev = await api.events(runId, 0)
    setEvents(ev.events)
  }

  useEffect(() => {
    api.meta().then(setMeta).catch(() => undefined)
    api.lastEval().then(setEvalReport).catch(() => undefined)
    refreshDevice().catch((e) => setError(String(e)))
    refreshHistory().catch(() => undefined)
    refreshMemory().catch(() => undefined)
    const stream = api.streamDevice({
      onDevice: (d) => setDevice(d),
    })
    return () => stream.close()
  }, [refreshDevice, refreshHistory, refreshMemory])

  const isTerminalLifecycle = (life?: string) =>
    !!life &&
    ['COMPLETED', 'FAILED', 'STOPPED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED', 'PARTIAL'].includes(life)

  const shouldReleaseWatch = (life?: string) =>
    isTerminalLifecycle(life) || !!life?.startsWith('WAITING')

  const watchRun = (runId: string) =>
    new Promise<void>((resolve) => {
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        stream.close()
        refreshHistory().catch(() => undefined)
        resolve()
      }
      const stream = api.streamRun(runId, {
        onEvent: (e) => {
          setEvents((prev) => {
            if (prev.some((x) => x.seq === e.seq)) return prev
            return [...prev, e].sort((a, b) => a.seq - b.seq)
          })
        },
        onRun: (latest) => {
          setRun(latest)
          if (shouldReleaseWatch(latest.lifecycle)) {
            finish()
          }
        },
        onDevice: (d) => setDevice(d),
        onError: () => {
          // EventSource reconnects automatically while the tab stays open.
        },
      })
      // Safety timeout so a stuck stream cannot hang the UI forever.
      window.setTimeout(finish, 120_000)
    })

  const submit = async () => {
    setBusy(true)
    setError(null)
    setReplayMode(false)
    try {
      const requestId = crypto.randomUUID()
      const created = await api.createRun(text, requestId)
      setRun(created)
      setEvents([])
      setBusy(false) // 允许执行中点取消
      await watchRun(created.run_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  const cancel = async () => {
    if (!run) return
    try {
      const updated = await api.cancel(run.run_id)
      setRun(updated)
      await loadEvents(run.run_id)
      await refreshHistory()
    } catch (e) {
      setError(String(e))
    }
  }

  const answerClarify = async () => {
    if (!run || !clarify.trim()) return
    setBusy(true)
    try {
      const updated = await api.clarify(run.run_id, clarify.trim())
      setRun(updated)
      setClarify('')
      setBusy(false)
      await watchRun(run.run_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  const changeGoal = async () => {
    if (!run || !interveneText.trim()) return
    setBusy(true)
    try {
      const updated = await api.intervene(run.run_id, {
        type: 'CHANGE_GOAL',
        text: interveneText.trim(),
        expectedGoalVersion: run.goal_version,
      })
      setRun(updated)
      setBusy(false)
      await watchRun(run.run_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  const answerPending = async (decision: 'APPROVE' | 'REJECT') => {
    if (!run?.pending) return
    const pendingId = run.pending.pendingId || run.pending.pending_id
    const goalVersion = run.pending.goalVersion ?? run.pending.goal_version ?? run.goal_version ?? 1
    if (!pendingId) {
      setError('缺少 pendingId')
      return
    }
    setBusy(true)
    try {
      const updated = await api.answer(run.run_id, { pendingId, goalVersion, decision })
      setRun(updated)
      setBusy(false)
      await watchRun(run.run_id)
    } catch (e) {
      setError(String(e))
      setBusy(false)
    }
  }

  const openReplay = async (runId: string) => {
    setBusy(true)
    setError(null)
    try {
      const data = await api.replay(runId)
      setRun(data.run)
      setEvents(data.events)
      setReplayMode(true)
    } catch (e) {
      // fallback: just load run + events
      try {
        const r = await api.getRun(runId)
        setRun(r)
        await loadEvents(runId)
        setReplayMode(true)
      } catch (e2) {
        setError(String(e2))
      }
    } finally {
      setBusy(false)
    }
  }

  const runEval = async (mode: 'agent' | 'baseline') => {
    setBusy(true)
    setError(null)
    try {
      const report = await api.runEval(mode)
      setEvalReport(report)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const state = device?.state ?? {}
  const goalsText = useMemo(() => JSON.stringify(run?.goals ?? [], null, 2), [run])
  const waitingConfirm = run?.lifecycle === 'WAITING_CONFIRMATION'
  const waitingClarify = run?.lifecycle === 'WAITING_CLARIFICATION'

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>智能终端 Agent Runtime</h1>
          <div>
            <span className="badge">本地模拟器</span>
            <span className="badge">默认规则 demo-defaults-v1</span>
            <span className="badge">模型 {String(run?.model_mode ?? meta?.model_mode ?? 'fake')}</span>
            <span className="badge">{String(meta?.model_id ?? '—')}</span>
            <span className="badge">placement {String(meta?.model_placement ?? 'cloud')}</span>
            <span className="badge">环境 {device?.environment_id ?? '—'}</span>
            <span className="badge">租户 {String(meta?.tenant_id ?? 'local')}</span>
            <span className="badge">env {String(meta?.execution_environment ?? 'sim')}</span>
            {replayMode && <span className="badge warn">历史回放（只读）</span>}
          </div>
          <p className="muted" style={{ margin: '0.55rem 0 0' }}>
            网页展示任务、设备观察与证据。设备区默认接本地模拟器，便于联调与回归。
          </p>
        </div>
        <div className="row">
          <button onClick={() => refreshDevice()}>刷新设备</button>
          <button
            onClick={() =>
              api.reset().then((d) => {
                setDevice(d)
                setReplayMode(false)
              })
            }
          >
            重置模拟器
          </button>
        </div>
      </header>

      <div className="grid hero-grid">
        <section className="panel vehicle-panel">
          <h2>设备 3D（Simulator Snapshot）</h2>
          <p className="muted">动画只跟随后端确认状态；ACK 未生效时车窗/气流不会动。</p>
          <VehicleScene state={snapshotFromDevice(device)} />
          <div className="kv" style={{ marginTop: 12 }}>
            <div className="card">
              <div className="label">空调电源 / 设定 / 舱温</div>
              <div className="value">
                {state.climate_power ? '开' : '关'} · {String(state.temperature_setpoint ?? '—')}℃ /{' '}
                {String(state.cabin_temperature ?? '—')}℃
              </div>
            </div>
            <div className="card">
              <div className="label">风量</div>
              <div className="value">{String(state.fan_level ?? '—')}</div>
            </div>
            <div className="card">
              <div className="label">四窗 FL/FR/RL/RR</div>
              <div className="value">
                {String(state.window_front_left ?? 0)}/{String(state.window_front_right ?? 0)}/
                {String(state.window_rear_left ?? 0)}/{String(state.window_rear_right ?? 0)}
              </div>
            </div>
            <div className="card">
              <div className="label">媒体</div>
              <div className="value">
                {state.media_playing ? '播放' : '暂停'} · {String(state.media_artist ?? '—')} · vol{' '}
                {String(state.media_volume ?? '—')}
              </div>
            </div>
            <div className="card">
              <div className="label">导航</div>
              <div className="value">
                {state.navigation_active ? '进行中' : '停止'} · {String(state.navigation_destination ?? '—')}
              </div>
            </div>
            <div className="card">
              <div className="label">播报 / 路由焦点</div>
              <div className="value">
                {state.prompt_enabled ? '开' : '关'} · {state.route_available ? '路由OK' : '路由不可用'} /{' '}
                {state.focus_available ? '焦点OK' : '焦点不可用'}
              </div>
            </div>
          </div>
          <p className="muted" style={{ marginTop: 12 }}>
            观察时间 {device?.observed_at || '—'} · env {device?.environment_id || '—'} · rev{' '}
            {JSON.stringify(device?.domain_revisions || {})}
          </p>
        </section>

        <section className="panel">
          <h2>任务区</h2>
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => setText(ex)}>
                填充示例
              </button>
            ))}
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="输入智能终端任务…"
            disabled={replayMode}
          />
          <div className="row">
            <button className="primary" disabled={busy || !text.trim() || replayMode} onClick={submit}>
              发送任务
            </button>
            <button className="danger" disabled={!run || replayMode} onClick={cancel}>
              停止
            </button>
            <button disabled={busy} onClick={() => api.fault('ACK_NOT_APPLIED', 'cabin.set_temperature')}>
              注入 ACK 未生效
            </button>
            <button disabled={busy} onClick={() => api.fault('APPLIED_RESPONSE_LOST', 'cabin.set_temperature')}>
              注入响应丢失
            </button>
            <button disabled={busy} onClick={() => api.fault('DELAY_APPLY', 'cabin.set_temperature')}>
              注入延迟生效
            </button>
          </div>
          {error && <div className="error">{error}</div>}

          {run && (
            <div style={{ marginTop: '1rem' }}>
              <div className={statusClass(run.lifecycle)}>
                <strong>{run.lifecycle}</strong> · {run.phase}
                {run.route ? ` · ${run.route}` : ''}
              </div>
              <p>{run.result_summary || '—'}</p>
              <p className="muted">
                run={run.run_id} · goal_v={run.goal_version} · outcome={run.goal_outcome || '—'}
                {run.stop_reason ? ` · ${run.stop_reason}` : ''}
              </p>

              {waitingClarify && !replayMode && (
                <div className="row">
                  <input
                    style={{
                      flex: 1,
                      minWidth: 180,
                      padding: '0.45rem 0.7rem',
                      borderRadius: 8,
                      border: '1px solid var(--line)',
                    }}
                    value={clarify}
                    onChange={(e) => setClarify(e.target.value)}
                    placeholder="补充澄清答案"
                  />
                  <button className="primary" onClick={answerClarify} disabled={busy}>
                    提交澄清
                  </button>
                </div>
              )}

              {waitingConfirm && run.pending && !replayMode && (
                <div className="card" style={{ marginBottom: 12 }}>
                  <div className="label">等待确认</div>
                  <div className="muted">
                    {run.pending.question ||
                      `${run.pending.capability_id || run.pending.capabilityId} ${JSON.stringify(run.pending.params || {})}`}
                  </div>
                  <div className="row">
                    <button className="primary" disabled={busy} onClick={() => answerPending('APPROVE')}>
                      批准
                    </button>
                    <button className="danger" disabled={busy} onClick={() => answerPending('REJECT')}>
                      拒绝
                    </button>
                  </div>
                </div>
              )}

              {!replayMode && run && !['COMPLETED', 'FAILED', 'STOPPED', 'CANCELLED', 'TIMED_OUT', 'INTERRUPTED'].includes(run.lifecycle) && (
                <div style={{ marginTop: 12 }}>
                  <div className="label">运行中修改目标</div>
                  <div className="row">
                    <input
                      style={{
                        flex: 1,
                        minWidth: 180,
                        padding: '0.45rem 0.7rem',
                        borderRadius: 8,
                        border: '1px solid var(--line)',
                      }}
                      value={interveneText}
                      onChange={(e) => setInterveneText(e.target.value)}
                      placeholder="例如：空调先不要调了"
                    />
                    <button disabled={busy} onClick={changeGoal}>
                      提交修改
                    </button>
                  </div>
                </div>
              )}

              <h3 style={{ marginBottom: 8 }}>当前目标 / 约束</h3>
              <div className="pre">{goalsText}</div>
              <div className="pre" style={{ marginTop: 8 }}>
                {JSON.stringify(run.constraints ?? [], null, 2)}
              </div>

              <h3>动作证据</h3>
              {(run.actions ?? []).length === 0 && <p className="muted">无写动作（可能已满足或被拒绝）</p>}
              {(run.actions ?? []).map((a, idx) => (
                <div className="card" key={String(actionField(a, 'actionId', 'action_id') ?? idx)} style={{ marginBottom: 8 }}>
                  <div className="label">{String(actionField(a, 'capabilityId', 'capability_id'))}</div>
                  <div className="value" style={{ fontSize: '0.85rem' }}>
                    执行 {String(actionField(a, 'executionStatus', 'execution_status') ?? '—')} · 验证{' '}
                    {String(actionField(a, 'verificationStatus', 'verification_status') ?? '—')} · 归因{' '}
                    {String(a.attribution ?? '—')}
                  </div>
                  <div className="muted">
                    {JSON.stringify(a.params)} {a.message || ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="panel memory-panel">
          <h2>记忆 / 端云</h2>
          <p className="muted">写入门禁：显式偏好才入库；敏感信息拦截；只影响默认建议。</p>
          <div className="row">
            <input
              style={{
                flex: 1,
                minWidth: 180,
                padding: '0.45rem 0.7rem',
                borderRadius: 8,
                border: '1px solid var(--line)',
              }}
              value={memoryText}
              onChange={(e) => setMemoryText(e.target.value)}
              placeholder="例如：记住我喜欢温度24度"
            />
            <button
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  const r = await api.writeMemoryUtterance(memoryText, 'web', run?.run_id)
                  if (!r.accepted) setError(`记忆写入拒绝：${String(r.reason)}`)
                  await refreshMemory()
                } catch (e) {
                  setError(String(e))
                } finally {
                  setBusy(false)
                }
              }}
            >
              写入偏好
            </button>
            <button
              disabled={busy}
              onClick={async () => {
                const r = await api.writeMemoryUtterance('记住我的银行卡密码是123456', 'web', run?.run_id)
                if (!r.accepted) setError(`隐私门禁生效：${String(r.reason)}`)
                await refreshMemory()
              }}
            >
              试误注入
            </button>
            <button
              onClick={() =>
                api.setPlacement('cloud').then((r) => {
                  setMeta((m) => ({ ...(m || {}), ...r }))
                })
              }
            >
              Cloud
            </button>
            <button
              onClick={() =>
                api.setPlacement('edge').then((r) => {
                  setMeta((m) => ({ ...(m || {}), ...r }))
                })
              }
            >
              Edge stub
            </button>
          </div>
          {memories.length === 0 && <p className="muted">暂无长期记忆</p>}
          {memories.map((m) => (
            <div className="card" key={String(m.id)} style={{ marginTop: 8 }}>
              <div className="label">
                {String(m.key)} = {String(m.value)} · {String(m.domain)}
              </div>
              <div className="muted">
                source={String(m.source_run_id)} · conf={String(m.confidence)}
              </div>
              <button
                disabled={busy}
                onClick={async () => {
                  await api.deleteMemory(String(m.id))
                  await refreshMemory()
                }}
              >
                删除
              </button>
            </div>
          ))}
        </section>
      </div>

      <details className="fold" open>
        <summary>实验 / 轨迹 / 历史 / 评测</summary>
        <p className="muted">故障注入与评测用于本地联调回归；回放不调用模型或写设备。</p>
        <div className="row">
          <button onClick={() => api.externalChange('temperature_setpoint', 26).then(setDevice)}>外部改温度=26</button>
          <button onClick={() => api.externalChange('media_volume', 9).then(setDevice)}>外部改媒体=9</button>
          <button onClick={() => api.externalChange('window_open', true).then(setDevice)}>外部开窗</button>
          <button disabled={busy} onClick={() => runEval('agent')}>
            跑评测 agent
          </button>
          <button disabled={busy} onClick={() => runEval('baseline')}>
            跑评测 baseline
          </button>
          <button onClick={() => refreshHistory()}>刷新历史</button>
          {replayMode && (
            <button
              onClick={() => {
                setReplayMode(false)
                setError(null)
              }}
            >
              退出回放
            </button>
          )}
        </div>

        {evalReport && (
          <div className="card" style={{ marginTop: 12 }}>
            <div className="label">
              评测报告 · {evalReport.mode} · {evalReport.passed}/{evalReport.total} 通过 · 正确处理率{' '}
              {(evalReport.correct_handling_rate * 100).toFixed(1)}%
            </div>
            <div className="muted">
              虚假成功 {evalReport.false_success} · {evalReport.note || evalReport.generated_at || ''}
            </div>
            <div className="pre" style={{ maxHeight: 180, overflow: 'auto' }}>
              {JSON.stringify(
                evalReport.cases?.filter((c) => !c.passed).slice(0, 12) ?? [],
                null,
                2,
              )}
            </div>
          </div>
        )}

        {history.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="label">历史运行</div>
            {history.slice(0, 12).map((h) => (
              <div className="row" key={h.run_id} style={{ marginTop: 4 }}>
                <span className={`muted ${statusClass(h.lifecycle)}`}>
                  {h.run_id} · {h.lifecycle} · {h.route || '—'}
                </span>
                <button disabled={busy} onClick={() => openReplay(h.run_id)}>
                  只读回放
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 12 }}>
          {events.length === 0 && <p className="muted">暂无事件</p>}
          {events.map((e) => {
            const role = e.payload && typeof e.payload === 'object'
              ? (e.payload as Record<string, unknown>).agent_role
              : undefined
            return (
            <div className="event" key={e.seq}>
              #{e.seq} {e.type}
              {role ? ` · ${String(role)}` : ''}
              {e.actionId ? ` · ${e.actionId}` : ''}
              <div>{JSON.stringify(e.payload)}</div>
            </div>
            )
          })}
        </div>
      </details>
    </div>
  )
}
