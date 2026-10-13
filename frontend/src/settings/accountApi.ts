/** Exports of the signed-in user's data (api_contract_spec.md Section 6.13). */
import { apiGetBlob } from '../api/client'

export type ExportKind = 'pdf' | 'json' | 'csv' | 'documents'

export const EXPORTS: { kind: ExportKind; label: string; description: string; filename: string }[] = [
  {
    kind: 'pdf',
    label: 'PDF health summary',
    description:
      'A readable summary: personal data, allergies, conditions, current medicines, follow-ups, results outside the printed range, vital signs, and your documents. Built by fixed rules, without AI.',
    filename: 'health-summary.pdf',
  },
  {
    kind: 'json',
    label: 'All data (JSON)',
    description: 'Every record in one structured file, for keeping or moving to another service.',
    filename: 'health-data.json',
  },
  {
    kind: 'csv',
    label: 'All data (CSV)',
    description: 'The same records as spreadsheet files, one per record type, in a ZIP.',
    filename: 'health-data-csv.zip',
  },
  {
    kind: 'documents',
    label: 'Original documents',
    description: 'Every file you uploaded, as uploaded, in a ZIP.',
    filename: 'health-documents.zip',
  },
]

export const accountApi = {
  export: (kind: ExportKind) => apiGetBlob(`/account/export/${kind}`),
}
