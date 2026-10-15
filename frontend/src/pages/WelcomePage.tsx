import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { BrandMark, SectionIcon } from '../components/icons'

const FEATURES = [
  {
    icon: '/documents',
    title: 'Medical documents, read for you',
    text: 'Upload lab reports, prescriptions, discharge summaries, consultation notes, imaging and ECG reports as PDFs or photos. Healthfolio reads them and shows the values in plain text, with anything unclear marked.',
  },
  {
    icon: '/timeline',
    title: 'Health timeline and search',
    text: 'Every record in date order, filtered by type or date, and a search across your reports, results, medicines and diagnoses.',
  },
  {
    icon: '/medications',
    title: 'Medications',
    text: 'Medicines from your prescriptions in one list. You confirm what you are taking or have stopped, and every change is kept.',
  },
  {
    icon: '/follow-ups',
    title: 'Checkups and follow-ups',
    text: 'Follow-ups written in your documents can be added to your checkup list in one click, with overdue and upcoming ones easy to see.',
  },
  {
    icon: '/alerts',
    title: 'Safety alerts by fixed rules',
    text: 'Results outside the range printed on their own report are flagged for review with your doctor, never by AI guesswork.',
  },
  {
    icon: '/profile',
    title: 'Health profile',
    text: 'Allergies first, conditions, BMI, vital signs, surgeries, hospital stays and family history, in one place.',
  },
  {
    icon: '/summaries',
    title: 'AI summaries with sources',
    text: 'A plain-language summary of your history or of one report, written on request. Every statement links to the record it came from.',
  },
  {
    icon: '/settings',
    title: 'Your data, your choice',
    text: 'Download a PDF health summary, all your data as JSON or CSV, or your original files. Delete your account at any time.',
  },
]

const STEPS = [
  { title: 'Create your account', text: 'Sign up with your email and a password of at least 12 characters.' },
  {
    title: 'Upload a report',
    text: 'Choose the file and add its type, date and hospital. Photos must be clear; a discharge summary should be one page.',
  },
  {
    title: 'Check what was read',
    text: 'Compare the summary with the original side by side. Values a report does not state are shown as “Not mentioned”.',
  },
  {
    title: 'Keep track',
    text: 'Your dashboard, timeline, alerts and summaries update as your records grow.',
  },
]

/** Screenshots of each step, taken from a demo account filled with fictional sample reports. */
const SCREENSHOTS = [
  {
    src: '/welcome/upload.webp',
    title: 'Upload a report',
    text: 'Choose the file, add its type, date and hospital, and say whether it is a digital PDF or a scanned copy.',
    alt: 'The upload form with the document details and the question “Is this a digital PDF or a scanned copy?”',
  },
  {
    src: '/welcome/document.webp',
    title: 'Check what was read',
    text: 'The original sits beside what was read. Scanned copies are read with OCR, and doubtful values are marked for review.',
    alt: 'A lipid profile shown beside its extracted results, grouped into values above, below and within range',
  },
  {
    src: '/welcome/dashboard.webp',
    title: 'See what needs attention',
    text: 'Alerts, items to review, follow-ups and recent documents on one dashboard.',
    alt: 'The dashboard with cards for alerts, items to review, checkups and follow-ups, and recent documents',
  },
  {
    src: '/welcome/timeline.webp',
    title: 'Browse your history',
    text: 'Every record in date order, with filters and a search across all your reports.',
    alt: 'The health timeline listing lab results, a prescription and a hospital stay by date',
  },
  {
    src: '/welcome/medications.webp',
    title: 'Keep your medicines up to date',
    text: 'Medicines from your prescriptions in one list. You confirm what you are taking.',
    alt: 'The medications page with medicines marked as taking and others waiting to be confirmed',
  },
  {
    src: '/welcome/summary.webp',
    title: 'Read a plain-language summary',
    text: 'Written by AI on request. Every statement links to the record it came from.',
    alt: 'An AI summary of the health history with numbered source links after each sentence',
  },
  {
    src: '/welcome/profile.webp',
    title: 'Your health profile',
    text: 'Allergies first, then personal data, BMI for adults, vital signs and history.',
    alt: 'The health profile with allergies, personal data and the BMI indicator',
  },
]

const PRINCIPLES = [
  { title: 'Nothing is guessed', text: 'Values are copied as written; missing ones stay missing.' },
  { title: 'Rules decide, AI explains', text: 'Ranges and alerts come from fixed rules; AI only reads and summarises.' },
  { title: 'Every statement has a source', text: 'Summaries cite your records, and anything unsupported is removed.' },
  { title: 'Private by design', text: 'Only you can see your records, and you can export or delete them at any time.' },
]

/** Public introduction to Healthfolio (no sign-in needed). */
export function WelcomePage() {
  const { status } = useAuth()
  const signedIn = status === 'authenticated'
  const primary = signedIn ? (
    <Link to="/" className="button welcome-cta">
      Open your dashboard
    </Link>
  ) : (
    <Link to="/login" className="button welcome-cta">
      Log in
    </Link>
  )

  return (
    <div className="welcome">
      <header className="welcome-top">
        <span className="welcome-logo">
          <BrandMark size={36} />
          Healthfolio
        </span>
        {signedIn ? (
          <Link to="/" className="button button-small">
            Dashboard
          </Link>
        ) : (
          <Link to="/login" className="button button-small">
            Log in
          </Link>
        )}
      </header>

      <main>
        <section className="welcome-hero" aria-labelledby="welcome-title">
          <BrandMark size={84} />
          <h1 id="welcome-title">Healthfolio</h1>
          <p className="welcome-tagline">Your medical history, organised and explained.</p>
          <p className="welcome-lead">
            Keep every report, prescription and discharge summary in one secure place. Healthfolio reads them, lays out
            your results and medicines clearly, keeps track of your follow-ups, and explains your records in plain language,
            always showing where each fact came from.
          </p>
          <div className="welcome-actions">
            {primary}
            {!signedIn && (
              <Link to="/register" className="button button-secondary welcome-cta">
                Create an account
              </Link>
            )}
          </div>
        </section>

        <section className="welcome-section" aria-labelledby="features-title">
          <h2 id="features-title">What you can do</h2>
          <ul className="welcome-features">
            {FEATURES.map((feature) => (
              <li key={feature.title} className="welcome-feature">
                <span className="welcome-feature-icon">
                  <SectionIcon path={feature.icon} />
                </span>
                <h3>{feature.title}</h3>
                <p>{feature.text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="welcome-section" aria-labelledby="steps-title">
          <h2 id="steps-title">How it works</h2>
          <ol className="welcome-steps">
            {STEPS.map((step, index) => (
              <li key={step.title}>
                <span className="welcome-step-number" aria-hidden="true">
                  {index + 1}
                </span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <ScreenshotTour />

        <section className="welcome-section welcome-access" aria-labelledby="access-title">
          <h2 id="access-title">How to access Healthfolio</h2>
          <ul>
            <li>
              <strong>In your web browser</strong>, on a computer, tablet or phone. There is nothing to install.
            </li>
            <li>
              <strong>Sign in with your email and password.</strong> Password reset by email is not available yet, so keep
              your password safe.
            </li>
            <li>
              <strong>Stay signed in safely:</strong> sessions renew in the background, and changing your password
              signs out your other devices.
            </li>
          </ul>
        </section>

        <section className="welcome-section" aria-labelledby="principles-title">
          <h2 id="principles-title">Built to be trusted</h2>
          <ul className="welcome-principles">
            {PRINCIPLES.map((item) => (
              <li key={item.title}>
                <h3>{item.title}</h3>
                <p>{item.text}</p>
              </li>
            ))}
          </ul>
        </section>

        <nav className="welcome-end" aria-label="End of page">
          <button type="button" className="welcome-top-button" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            ↑ Back to top
          </button>
        </nav>

        <p className="welcome-disclaimer">
          Healthfolio gives information, not medical advice, and does not replace your doctor. In an emergency, call
          your local emergency number. This is a prototype: please use sample documents, not real patient records,
          until its privacy review is complete.
        </p>
      </main>

      <footer className="welcome-footer">
        <span>© Healthfolio</span>
        <Link to="/status">System status</Link>
      </footer>
    </div>
  )
}

/** Each step as a screenshot; a click opens it full size (Escape or a click closes it). */
function ScreenshotTour() {
  const [open, setOpen] = useState<(typeof SCREENSHOTS)[number] | null>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(null)
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [open])

  return (
    <section className="welcome-section" aria-labelledby="tour-title">
      <h2 id="tour-title">See it in action</h2>
      <p className="welcome-tour-note">Screens from a demo account with fictional sample reports.</p>
      <ol className="welcome-tour">
        {SCREENSHOTS.map((shot, index) => (
          <li key={shot.src} className="welcome-shot">
            <button type="button" className="welcome-shot-image" onClick={() => setOpen(shot)}>
              <img src={shot.src} alt={shot.alt} width={1600} height={888} loading="lazy" decoding="async" />
              <span className="visually-hidden">Open full size</span>
            </button>
            <div className="welcome-shot-text">
              <span className="welcome-step-number" aria-hidden="true">
                {index + 1}
              </span>
              <h3>{shot.title}</h3>
              <p>{shot.text}</p>
            </div>
          </li>
        ))}
      </ol>
      {open && (
        <div className="welcome-lightbox" role="dialog" aria-modal="true" aria-label={open.title} onClick={() => setOpen(null)}>
          <img src={open.src} alt={open.alt} />
          <button type="button" className="welcome-lightbox-close" onClick={() => setOpen(null)} autoFocus>
            Close
          </button>
        </div>
      )}
    </section>
  )
}
