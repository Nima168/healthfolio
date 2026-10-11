import { useState } from 'react'

import { FormField } from '../components/FormField'
import { SelectField } from '../components/SelectField'
import { CATEGORIES, DATE_PRECISIONS, type Category, type DatePrecision } from './documentsApi'
import { CATEGORY_LABELS, PRECISION_LABELS } from './format'
import type { MetadataValues } from './metadata'

interface Props {
  values: MetadataValues
  onChange: (values: MetadataValues) => void
  errors?: Record<string, string>
}

/** Category, document date (with how exact it is), and provider; shared by upload and edit. */
export function MetadataFields({ values, onChange, errors = {} }: Props) {
  // Today's date for the picker's upper limit, computed once (not on every render).
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const set = <K extends keyof MetadataValues>(key: K, value: MetadataValues[K]) => onChange({ ...values, [key]: value })

  return (
    <div className="metadata-grid">
      <SelectField
        label="Document type"
        value={values.category}
        onChange={(e) => set('category', e.target.value as Category | '')}
        options={[
          { value: '', label: 'Not set' },
          ...CATEGORIES.filter((c) => c !== 'unknown').map((c) => ({ value: c, label: CATEGORY_LABELS[c] })),
        ]}
        error={errors.category}
      />
      <FormField
        label="Document date"
        type="date"
        value={values.document_date}
        max={today}
        onChange={(e) => set('document_date', e.target.value)}
        error={errors.document_date}
      />
      <SelectField
        label="How exact is the date?"
        value={values.document_date_precision}
        disabled={!values.document_date}
        onChange={(e) => set('document_date_precision', e.target.value as DatePrecision | '')}
        options={[
          { value: '', label: 'Exact day' },
          ...DATE_PRECISIONS.filter((p) => p !== 'day').map((p) => ({ value: p, label: PRECISION_LABELS[p] })),
        ]}
        error={errors.document_date_precision}
      />
      <FormField
        label="Hospital, lab, or clinic"
        maxLength={200}
        value={values.provider_name}
        onChange={(e) => set('provider_name', e.target.value)}
        error={errors.provider_name}
      />
    </div>
  )
}
