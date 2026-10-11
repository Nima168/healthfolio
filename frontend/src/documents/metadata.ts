import type { Category, DatePrecision } from './documentsApi'

export interface MetadataValues {
  category: Category | ''
  document_date: string
  document_date_precision: DatePrecision | ''
  provider_name: string
}

export const EMPTY_METADATA: MetadataValues = {
  category: '',
  document_date: '',
  document_date_precision: '',
  provider_name: '',
}
