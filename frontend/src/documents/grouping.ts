/** Filtering and grouping the documents list (frontend side of api_contract_spec.md Section 6.1.1). */
import { CATEGORIES, NO_PROVIDER, type DocumentFilters, type MedicalDocument } from './documentsApi'
import { CATEGORY_LABELS } from './format'

export const GROUPINGS = ['none', 'type', 'date', 'hospital'] as const
export type Grouping = (typeof GROUPINGS)[number]

export const GROUPING_LABELS: Record<Grouping, string> = {
  none: 'None',
  type: 'Type',
  date: 'Date (month)',
  hospital: 'Hospital or clinic',
}

export interface DocumentGroup {
  key: string
  title: string
  documents: MedicalDocument[]
}

/** The comparison form of a hospital or clinic name: lower case, single spaces (same rule as the server). */
export function providerKey(name: string): string {
  return name.toLowerCase().split(/\s+/).filter(Boolean).join(' ')
}

export const hasFilters = (filters: DocumentFilters) =>
  Boolean(filters.category || filters.dateFrom || filters.dateTo || filters.provider)

/** Whether a document belongs in the filtered list (used for a document just uploaded). */
export function matchesFilters(document: MedicalDocument, filters: DocumentFilters): boolean {
  if (filters.category && document.category !== filters.category) return false
  if (filters.dateFrom && (!document.document_date || document.document_date < filters.dateFrom)) return false
  if (filters.dateTo && (!document.document_date || document.document_date > filters.dateTo)) return false
  const provider = document.provider_name?.trim() ? providerKey(document.provider_name) : null
  if (filters.provider === NO_PROVIDER) return provider === null
  if (filters.provider) return provider === providerKey(filters.provider)
  return true
}

/** Newest report date first; undated last; then newest upload first. */
function byReportDate(a: MedicalDocument, b: MedicalDocument): number {
  if (a.document_date !== b.document_date) {
    if (!a.document_date) return 1
    if (!b.document_date) return -1
    return b.document_date.localeCompare(a.document_date)
  }
  return b.created_at.localeCompare(a.created_at)
}

const MONTH = new Intl.DateTimeFormat('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })

function dateGroup(document: MedicalDocument): { key: string; title: string } {
  if (!document.document_date) return { key: 'none', title: 'No date' }
  const [year, month] = document.document_date.split('-')
  // A year-only date sorts after that year's months ("00" is below every month).
  if (document.document_date_precision === 'year') return { key: `${year}-00`, title: `${year} (month not given)` }
  return { key: `${year}-${month}`, title: MONTH.format(new Date(Date.UTC(Number(year), Number(month) - 1, 1))) }
}

export function groupDocuments(documents: MedicalDocument[], grouping: Grouping): DocumentGroup[] {
  // Ungrouped keeps the server's order (newest upload first), so "Load more" continues it.
  if (grouping === 'none') return [{ key: 'all', title: 'Your documents', documents }]
  const sorted = [...documents].sort(byReportDate)

  const groups = new Map<string, DocumentGroup>()
  for (const document of sorted) {
    let key: string
    let title: string
    if (grouping === 'type') {
      key = document.category
      title = CATEGORY_LABELS[document.category]
    } else if (grouping === 'date') {
      ;({ key, title } = dateGroup(document))
    } else {
      const name = document.provider_name?.trim()
      key = name ? `h:${providerKey(name)}` : 'none' // prefixed, so a clinic called "None" stays its own group
      title = name ? name.split(/\s+/).join(' ') : 'No hospital given'
    }
    if (!groups.has(key)) groups.set(key, { key, title, documents: [] })
    groups.get(key)?.documents.push(document)
  }

  const order = (group: DocumentGroup): [number, string] => {
    if (grouping === 'type') return [CATEGORIES.indexOf(group.key as (typeof CATEGORIES)[number]), '']
    return [group.key === 'none' ? 1 : 0, group.key]
  }
  return [...groups.values()].sort((a, b) => {
    const [rankA, keyA] = order(a)
    const [rankB, keyB] = order(b)
    if (rankA !== rankB) return rankA - rankB
    // Dates newest first; hospitals A to Z.
    return grouping === 'date' ? keyB.localeCompare(keyA) : keyA.localeCompare(keyB)
  })
}
