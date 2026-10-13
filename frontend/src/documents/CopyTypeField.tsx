import type { CopyType } from './documentsApi'
import { COPY_TYPE_LABELS } from './format'

const COPY_TYPE_HINTS: Record<CopyType, string> = {
  digital: 'Made on a computer: you can select its text. The text is copied exactly.',
  scanned: 'A scan or photo of paper. The text is read with OCR (text recognition).',
}

interface Props {
  value: CopyType | ''
  onChange: (value: CopyType) => void
  /** Photos are always scanned copies, so "Digital PDF" is not offered. */
  isPhoto?: boolean
  error?: string
}

/** "Is this a digital PDF or a scanned copy?": decides between copying the PDF's text and OCR. */
export function CopyTypeField({ value, onChange, isPhoto = false, error }: Props) {
  return (
    <fieldset className="copy-type" aria-describedby={error ? 'copy-type-error' : undefined}>
      <legend>Is this a digital PDF or a scanned copy? (required)</legend>
      <div className="copy-type-options">
        {(['digital', 'scanned'] as const).map((option) => (
          <label key={option} className={`copy-type-option${value === option ? ' copy-type-option-selected' : ''}`}>
            <input
              type="radio"
              name="copy_type"
              value={option}
              checked={value === option}
              disabled={isPhoto && option === 'digital'}
              onChange={() => onChange(option)}
            />
            <span>
              <strong>{COPY_TYPE_LABELS[option]}</strong>
              <span className="form-hint">{COPY_TYPE_HINTS[option]}</span>
            </span>
          </label>
        ))}
      </div>
      {isPhoto && <p className="form-hint">Photos are always read as scanned copies.</p>}
      {error && (
        <p id="copy-type-error" className="form-error">
          {error}
        </p>
      )}
    </fieldset>
  )
}
