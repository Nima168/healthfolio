import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { toFormErrors } from '../auth/formErrors'
import { formatDayMonthYear, formatTimestamp } from '../documents/format'
import type { AiSummary, SummaryState } from './summariesApi'

const TRUST_LABELS: Record<string, string> = {
  from_document: 'read from a document, not checked by you',
  confirmed_by_you: 'confirmed by you',
  edited_by_you: 'changed by you',
  added_by_you: 'added by you',
}

/** Sources numbered in the order the summary first cites them. */
function numberSources(summary: AiSummary): Map<string, number> {
  const numbers = new Map<string, number>()
  const cite = (ids: string[]) => ids.forEach((id) => numbers.has(id) || numbers.set(id, numbers.size + 1))
  summary.sections.forEach((section) => section.sentences.forEach((sentence) => cite(sentence.fact_ids)))
  summary.explanations.forEach((explanation) => cite(explanation.fact_ids))
  return numbers
}

function Citations({ ids, numbers }: { ids: string[]; numbers: Map<string, number> }) {
  return (
    <span className="summary-cites">
      {ids.map((id) => (
        <a key={id} href={`#source-${id}`} className="summary-cite" aria-label={`Source ${numbers.get(id)}`}>
          {numbers.get(id)}
        </a>
      ))}
    </span>
  )
}

function SummaryBody({ summary }: { summary: AiSummary }) {
  const numbers = numberSources(summary)
  const cited = [...numbers.entries()].sort((a, b) => a[1] - b[1])
  return (
    <>
      {summary.sections.map((section) => (
        <div key={section.key} className="ai-summary-section">
          <h3>{section.title}</h3>
          <ul>
            {section.sentences.map((sentence, index) => (
              <li key={index} className={sentence.kind === 'interpretation' ? 'ai-interpretation' : undefined}>
                {sentence.kind === 'interpretation' && <span className="ai-kind">AI interpretation</span>}
                {sentence.text}
                <Citations ids={sentence.fact_ids} numbers={numbers} />
              </li>
            ))}
          </ul>
        </div>
      ))}

      {summary.explanations.length > 0 && (
        <aside className="general-info" aria-labelledby={`general-${summary.id}`}>
          <h3 id={`general-${summary.id}`}>General information, not from your records</h3>
          <dl>
            {summary.explanations.map((explanation) => (
              <div key={explanation.term}>
                <dt>{explanation.term}</dt>
                <dd>
                  {explanation.text}
                  <Citations ids={explanation.fact_ids} numbers={numbers} />
                </dd>
              </div>
            ))}
          </dl>
          <p className="general-info-note">
            This is general medical information. Please ask your doctor what it means for you.
          </p>
        </aside>
      )}

      {summary.insights.length > 0 && (
        <div className="ai-summary-section summary-checks">
          <h3>Things to check</h3>
          <p className="document-meta">Found by fixed rules in the app, not by the AI.</p>
          <ul>
            {summary.insights.map((insight) => (
              <li key={insight.id}>
                {insight.link ? <Link to={insight.link}>{insight.text}</Link> : insight.text}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ai-summary-section summary-sources">
        <h3>Sources</h3>
        <ol>
          {cited.map(([id]) => {
            const source = summary.sources[id]
            if (!source) return null
            return (
              <li key={id} id={`source-${id}`}>
                {source.link ? <Link to={source.link}>{source.title}</Link> : source.title}
                {source.date && <span className="mono"> · {formatDayMonthYear(source.date)}</span>}
                {source.source_document_title && source.source_document_id && (
                  <span className="document-meta">
                    {' '}
                    · From <Link to={`/documents/${source.source_document_id}`}>{source.source_document_title}</Link>
                  </span>
                )}
                {source.trust && TRUST_LABELS[source.trust] && (
                  <span className="document-meta"> ({TRUST_LABELS[source.trust]})</span>
                )}
              </li>
            )
          })}
        </ol>
      </div>

      {summary.dropped_count > 0 && (
        <p className="document-meta">
          {summary.dropped_count} AI statement{summary.dropped_count === 1 ? ' was' : 's were'} left out because{' '}
          {summary.dropped_count === 1 ? 'it' : 'they'} could not be matched to your records.
        </p>
      )}
    </>
  )
}

interface Props {
  title: string
  load: () => Promise<SummaryState>
  create: () => Promise<SummaryState>
  /** Shown when there is nothing to summarise yet. */
  emptyText: string
}

/**
 * An AI summary with its sources (frontend_spec.md Section 11). Written only when the user asks: nothing is
 * sent to the AI service otherwise.
 */
export function AiSummaryPanel({ title, load, create, emptyText }: Props) {
  const [state, setState] = useState<SummaryState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [writing, setWriting] = useState(false)

  useEffect(() => {
    let active = true
    load()
      .then((loaded) => active && setState(loaded))
      .catch((e: unknown) => active && setError(toFormErrors(e, 'The summary could not be loaded.').general ?? null))
    return () => {
      active = false
    }
  }, [load])

  async function write() {
    setWriting(true)
    setError(null)
    try {
      setState(await create())
    } catch (e) {
      setError(toFormErrors(e, 'The summary could not be written. Please try again.').general ?? null)
    } finally {
      setWriting(false)
    }
  }

  const summary = state?.summary
  const button = (label: string) => (
    <button type="button" className="button button-small" onClick={() => void write()} disabled={writing}>
      {writing ? 'Writing…' : label}
    </button>
  )

  return (
    <section className="card ai-summary" aria-labelledby="ai-summary-title" aria-busy={writing}>
      <div className="ai-summary-head">
        <h2 id="ai-summary-title">{title}</h2>
        {summary && <span className="ai-badge">AI-generated</span>}
      </div>

      {error && (
        <p role="alert" className="form-alert">
          {error}
        </p>
      )}
      {!state && !error && <p role="status">Loading…</p>}

      {state && !state.enabled && !summary && (
        <p>AI summaries are turned off on this server, so no summary can be written yet.</p>
      )}
      {state?.enabled && !summary && !state.can_create && <p>{emptyText}</p>}
      {state?.enabled && !summary && state.can_create && !writing && (
        <div>
          <p>
            Get a plain-language summary written by AI from your records, with a source for every statement. Your
            records (not your name or email) are sent to the AI service only when you ask.
          </p>
          {button('Create summary')}
        </div>
      )}
      {writing && (
        <p role="status" className="processing-note">
          <span className="spinner" aria-hidden="true" />
          Writing your summary… This can take up to a minute.
        </p>
      )}

      {summary && (
        <>
          <p className="ai-summary-meta">
            Written {formatTimestamp(summary.created_at)}. AI can make mistakes: check each statement against its
            source. This is not medical advice.
          </p>
          {state.stale && (
            <p className="summary-stale" role="status">
              Your records changed after this summary was written.{' '}
              {state.enabled && state.can_create && button('Refresh summary')}
            </p>
          )}
          <SummaryBody summary={summary} />
          {!state.stale && state.enabled && state.can_create && (
            <p className="read-again">
              {button('Write again')}
              <span className="form-hint">AI writing varies, so a new summary may read differently.</span>
            </p>
          )}
        </>
      )}
    </section>
  )
}
