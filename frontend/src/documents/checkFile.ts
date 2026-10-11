import { ACCEPTED_TYPES, MAX_UPLOAD_MB } from './documentsApi'

/** Quick checks before uploading; the server repeats them (it checks the real file content). */
export function checkFile(file: File): string | null {
  if (!ACCEPTED_TYPES.includes(file.type) && !/\.(pdf|jpe?g|png)$/i.test(file.name)) {
    return 'Only PDF, JPEG, and PNG files can be uploaded.'
  }
  if (file.size === 0) return 'This file is empty.'
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return `Files must be ${MAX_UPLOAD_MB} MB or smaller.`
  return null
}
