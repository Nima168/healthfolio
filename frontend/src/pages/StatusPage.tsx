import { useCallback, useEffect, useState } from 'react'

import { ApiError, apiGet } from '../api/client'

type State = 'checking' | 'ok' | 'problem'

interface CheckResult {
  state: State
  label: string
  requestId?: string | null
}

const CHECKING: CheckResult = { state: 'checking', label: 'Checking…' }

function describeFailure(error: unknown, unavailableLabel: string): CheckResult {
  if (error instanceof ApiError) {
    if (error.code === 'NETWORK_ERROR') return { state: 'problem', label: 'Unreachable' }
    return { state: 'problem', label: unavailableLabel, requestId: error.requestId }
  }
  return { state: 'problem', label: 'Unknown error' }
}

/** Shows whether the backend process and its database are reachable (observability spec Section 6). */
export function StatusPage() {
  const [backend, setBackend] = useState<CheckResult>(CHECKING)
  const [database, setDatabase] = useState<CheckResult>(CHECKING)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const [isChecking, setIsChecking] = useState(true)

  // State starts as "checking", so the first run needs no reset; re-checks reset in recheck().
  const runChecks = useCallback(async (signal?: AbortSignal) => {
    const [live, ready] = await Promise.allSettled([
      apiGet<{ status: string }>('/health/live', { signal }),
      apiGet<{ status: string }>('/health/ready', { signal }),
    ])
    if (signal?.aborted) return

    setBackend(live.status === 'fulfilled' ? { state: 'ok', label: 'Running' } : describeFailure(live.reason, 'Not running'))
    if (ready.status === 'fulfilled') {
      setDatabase({ state: 'ok', label: 'Ready' })
    } else if (live.status === 'rejected') {
      // If the backend itself is down, the database state is unknown, not "down".
      setDatabase({ state: 'problem', label: 'Unknown (backend unreachable)' })
    } else {
      setDatabase(describeFailure(ready.reason, 'Not ready'))
    }
    setCheckedAt(new Date())
    setIsChecking(false)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    // Fetching from the backend is an external sync; state is only set after the requests resolve.
    // oxlint-disable-next-line react/set-state-in-effect
    void runChecks(controller.signal)
    return () => controller.abort()
  }, [runChecks])

  function recheck() {
    setIsChecking(true)
    setBackend(CHECKING)
    setDatabase(CHECKING)
    void runChecks()
  }

  const rows: { name: string; result: CheckResult }[] = [
    { name: 'Backend service', result: backend },
    { name: 'Database', result: database },
  ]

  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">System Status</h1>
      <p className="page-intro">Whether the application and its database are reachable right now.</p>

      <div className="card">
        <ul className="status-list" aria-live="polite" aria-busy={isChecking}>
          {rows.map(({ name, result }) => (
            <li key={name} className="status-row">
              <span className="status-name">{name}</span>
              <span className="status-badge" data-state={result.state}>
                {result.label}
              </span>
              {result.requestId && (
                <span className="status-meta status-request-id">Request ID: {result.requestId}</span>
              )}
            </li>
          ))}
        </ul>
        {checkedAt && <p className="status-meta">Last checked: {checkedAt.toLocaleTimeString()}</p>}
        <button type="button" className="button" onClick={recheck} disabled={isChecking}>
          {isChecking ? 'Checking…' : 'Check again'}
        </button>
      </div>
    </section>
  )
}
