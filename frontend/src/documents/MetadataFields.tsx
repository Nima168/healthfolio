import { useState } from 'react'

import { FormField } from '../components/FormField'
import { SelectField } from '../components/SelectField'
import { DATE_PRECISIONS, SUBTYPE_MAX_LENGTH, type Category, type DatePrecision } from './documentsApi'
import { CATEGORY_LABELS, PRECISION_LABELS, REPORT_TYPE_OPTIONS } from './format'
import type { MetadataValues } from './metadata'

interface Props {
  values: MetadataValues
  onChange: (values: MetadataValues) => void
  errors?: Record<string, string>
  /** On upload every detail is required; editing later keeps them optional. */
  required?: boolean
}

/** Report type and sub-type, document date (with how exact it is), and provider; shared by upload and edit. */
export function MetadataFields({ values, onChange, errors = {}, required = false }: Props) {
  // Today's date for the picker's upper limit, computed once (not on every render).
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const mark = (label: string) => (required ? `${label} (required)` : label)
  const set = <K extends keyof MetadataValues>(key: K, value: MetadataValues[K]) => onChange({ ...values, [key]: value })

  return (
    <div className="metadata-grid">
      <div>
        <SelectField
          label={mark('Report type')}
          required={required}
          value={values.category}
          onChange={(e) => set('category', e.target.value as Category | '')}
          options={[
            { value: '', label: required ? 'Choose a type' : 'Not set' },
            ...REPORT_TYPE_OPTIONS,
            // "Other" is no longer offered, but a document that has it still shows it when edited.
            ...(values.category === 'other' ? [{ value: 'other', label: CATEGORY_LABELS.other }] : []),
          ]}
          error={errors.category}
          aria-describedby={values.category === 'discharge_summary' ? 'discharge-page-note' : undefined}
        />
        {values.category === 'discharge_summary' && (
          <p id="discharge-page-note" className="field-note">
            <strong>Note:</strong> Please upload only one page of the discharge summary (the page with the
            diagnosis and discharge medicines), due to AI reading limits.
          </p>
        )}
      </div>
      <FormField
        label="Report sub-type (optional)"
        maxLength={SUBTYPE_MAX_LENGTH}
        placeholder="e.g. Lipid profile"
        value={values.report_subtype}
        onChange={(e) => set('report_subtype', e.target.value)}
        error={errors.report_subtype}
      />
      <FormField
        label={mark('Document date')}
        required={required}
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
        label={mark('Hospital, lab, or clinic')}
        required={required}
        maxLength={200}
        value={values.provider_name}
        onChange={(e) => set('provider_name', e.target.value)}
        error={errors.provider_name}
      />
    </div>
  )
}
