export type DeviceState = {
  device_id: string
  environment_id: string
  observed_at: string
  domain_revisions: Record<string, number>
  state: Record<string, unknown>
  simulation: boolean
  note: string
}

export type PendingInteraction = {
  pendingId?: string
  pending_id?: string
  type: string
  goalVersion?: number
  goal_version?: number
  capabilityId?: string
  capability_id?: string
  params?: Record<string, unknown>
  question?: string
  expiresAt?: string
  expires_at?: string
}

export type RunView = {
  run_id: string
  lifecycle: string
  phase: string
  route?: string
  stop_reason?: string
  result_summary?: string
  goal_outcome?: string
  goal_version?: number
  raw_text?: string
  defaults_rule_id?: string
  goals?: unknown[]
  constraints?: unknown[]
  criteria?: unknown[]
  pending?: PendingInteraction | null
  actions?: Array<{
    actionId?: string
    action_id?: string
    capabilityId?: string
    capability_id?: string
    params: Record<string, unknown>
    executionStatus?: string
    execution_status?: string
    verificationStatus?: string
    verification_status?: string
    attribution?: string
    message?: string
  }>
  budget?: Record<string, unknown>
  evaluation_snapshot?: Record<string, unknown>
  model_mode?: string
  event_count?: number
  persistence?: string
}

export type RuntimeEvent = {
  seq: number
  type: string
  at: string
  goalVersion?: number
  actionId?: string
  payload: Record<string, unknown>
}

export type EvalReport = {
  mode: string
  dataset_version: string
  model_mode: string
  total: number
  passed: number
  failed: number
  correct_handling_rate: number
  false_success: number
  cases: Array<{
    id: string
    passed: boolean
    lifecycle?: string
    message?: string
    details?: unknown
  }>
  generated_at?: string
  note?: string
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json() as Promise<T>
}

export const api = {
  meta: () => fetch('/api/v1/meta').then((r) => json<Record<string, unknown>>(r)),
  deviceState: () => fetch('/api/v1/device/state').then((r) => json<DeviceState>(r)),
  createRun: (text: string, requestId: string) =>
    fetch('/api/v1/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, requestId, sessionId: 'web' }),
    }).then((r) => json<RunView>(r)),
  getRun: (runId: string) => fetch(`/api/v1/runs/${runId}`).then((r) => json<RunView>(r)),
  listRuns: () =>
    fetch('/api/v1/runs').then((r) => json<{ runs: RunView[] } | RunView[]>(r)),
  events: (runId: string, afterSeq = 0) =>
    fetch(`/api/v1/runs/${runId}/events?afterSeq=${afterSeq}`).then((r) =>
      json<{ events: RuntimeEvent[]; latest_seq: number }>(r),
    ),
  /**
   * Server-Sent Events for a run: named events `event` | `run` | `device` | `ping`.
   * Falls back to polling only if EventSource is unavailable.
   */
  streamRun(
    runId: string,
    handlers: {
      onEvent?: (e: RuntimeEvent) => void
      onRun?: (run: RunView) => void
      onDevice?: (device: DeviceState) => void
      onError?: (err: Event) => void
    },
    afterSeq = 0,
  ): { close: () => void } {
    const url = `/api/v1/runs/${runId}/events/stream?afterSeq=${afterSeq}`
    const es = new EventSource(url)
    const parse = <T,>(raw: MessageEvent): T | null => {
      try {
        return JSON.parse(String(raw.data)) as T
      } catch {
        return null
      }
    }
    es.addEventListener('event', (msg) => {
      const data = parse<RuntimeEvent>(msg as MessageEvent)
      if (data) handlers.onEvent?.(data)
    })
    es.addEventListener('run', (msg) => {
      const data = parse<RunView>(msg as MessageEvent)
      if (data) handlers.onRun?.(data)
    })
    es.addEventListener('device', (msg) => {
      const data = parse<DeviceState>(msg as MessageEvent)
      if (data) handlers.onDevice?.(data)
    })
    es.onerror = (err) => handlers.onError?.(err)
    return { close: () => es.close() }
  },
  streamDevice(handlers: {
    onDevice?: (device: DeviceState) => void
    onError?: (err: Event) => void
  }): { close: () => void } {
    const es = new EventSource('/api/v1/device/state/stream')
    es.addEventListener('device', (msg) => {
      try {
        handlers.onDevice?.(JSON.parse(String((msg as MessageEvent).data)) as DeviceState)
      } catch {
        // ignore malformed
      }
    })
    es.onerror = (err) => handlers.onError?.(err)
    return { close: () => es.close() }
  },
  cancel: (runId: string) =>
    fetch(`/api/v1/runs/${runId}/cancel`, { method: 'POST' }).then((r) => json<RunView>(r)),
  clarify: (runId: string, answer: string) =>
    fetch(`/api/v1/runs/${runId}/clarify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answer }),
    }).then((r) => json<RunView>(r)),
  intervene: (runId: string, body: { type: string; text?: string; expectedGoalVersion?: number }) =>
    fetch(`/api/v1/runs/${runId}/intervene`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<RunView>(r)),
  answer: (
    runId: string,
    body: { pendingId: string; goalVersion: number; decision: string; answer?: string },
  ) =>
    fetch(`/api/v1/runs/${runId}/answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => json<RunView>(r)),
  replay: (runId: string) =>
    fetch(`/api/v1/runs/${runId}/replay`).then((r) =>
      json<{ run: RunView; events: RuntimeEvent[]; mode: string }>(r),
    ),
  reset: () => fetch('/api/v1/experiment/reset', { method: 'POST' }).then((r) => json<DeviceState>(r)),
  fault: (type: string, capabilityId: string, times = 1) =>
    fetch('/api/v1/experiment/fault', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, capabilityId, times }),
    }).then((r) => json<Record<string, unknown>>(r)),
  externalChange: (field: string, value: unknown) =>
    fetch('/api/v1/experiment/external-change', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ field, value }),
    }).then((r) => json<DeviceState>(r)),
  runEval: (mode: 'agent' | 'baseline' = 'agent') =>
    fetch(`/api/v1/evals/run?mode=${mode}`, { method: 'POST' }).then((r) => json<EvalReport>(r)),
  lastEval: () => fetch('/api/v1/evals/last').then((r) => json<EvalReport>(r)),
  listMemory: (sessionId = 'web') =>
    fetch(`/api/v1/memory?sessionId=${encodeURIComponent(sessionId)}`).then((r) =>
      json<{ session_id: string; memories: Array<Record<string, unknown>>; note?: string }>(r),
    ),
  writeMemoryUtterance: (utterance: string, sessionId = 'web', sourceRunId?: string) =>
    fetch('/api/v1/memory', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ utterance, sessionId, sourceRunId }),
    }).then((r) => json<Record<string, unknown>>(r)),
  deleteMemory: (id: string) =>
    fetch(`/api/v1/memory/${id}`, { method: 'DELETE' }).then((r) => json<Record<string, unknown>>(r)),
  setPlacement: (placement: 'cloud' | 'edge') =>
    fetch('/api/v1/model/placement', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ placement }),
    }).then((r) => json<Record<string, unknown>>(r)),
}
