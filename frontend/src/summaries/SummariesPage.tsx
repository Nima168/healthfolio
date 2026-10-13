import { HelperNote } from '../components/HelperNote'
import { AiSummaryPanel } from './AiSummaryPanel'
import { summariesApi } from './summariesApi'

/** AI Summaries and Insights (frontend_spec.md Section 11). */
export function SummariesPage() {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title">AI Summaries and Insights</h1>
      <HelperNote>
        A plain-language summary of your records, written by AI on request. Every statement links to its source;
        anything that cannot be matched to your records is left out.
      </HelperNote>
      <AiSummaryPanel
        title="Your health history"
        load={summariesApi.history}
        create={summariesApi.createHistory}
        emptyText="There are no records to summarise yet. Upload and read a document first."
      />
      <p className="document-meta">
        For one report on its own, open it in Medical Documents and use its plain-language summary.
      </p>
    </section>
  )
}
