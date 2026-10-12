/** Primary sections from frontend_spec.md Section 4. `available` flips as features ship. */
export interface Section {
  path: string
  label: string
  description: string
  available: boolean
}

export const SECTIONS: Section[] = [
  { path: '/', label: 'Dashboard', description: 'An overview of your records, follow-ups, and items to review.', available: false },
  { path: '/timeline', label: 'Health Timeline', description: 'Your records in date order, with filters and search.', available: false },
  { path: '/documents', label: 'Medical Documents', description: 'Upload and view reports, prescriptions, and summaries.', available: true },
  { path: '/medications', label: 'Medications and Prescriptions', description: 'Add, edit, and review your medication records.', available: false },
  { path: '/follow-ups', label: 'Checkups and Follow-ups', description: 'Record checkups and see what is upcoming or overdue.', available: true },
  { path: '/summaries', label: 'AI Summaries and Insights', description: 'Plain-language summaries of your records, with sources.', available: false },
  { path: '/alerts', label: 'Alerts', description: 'Safety alerts from validated rules, to review and acknowledge.', available: false },
  { path: '/profile', label: 'Health Profile', description: 'Your conditions, allergies, and other health details.', available: false },
  { path: '/settings', label: 'Account and Privacy Settings', description: 'Account, export, and deletion options.', available: false },
]

export const STATUS_SECTION: Section = {
  path: '/status',
  label: 'System Status',
  description: 'Whether the application and its database are reachable.',
  available: true,
}
