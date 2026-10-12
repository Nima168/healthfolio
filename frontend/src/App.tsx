import { Route, Routes } from 'react-router-dom'

import { AuthLayout } from './auth/AuthLayout'
import { ProtectedRoute } from './auth/ProtectedRoute'
import { AppShell } from './components/AppShell'
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage'
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage'
import { DocumentDetailPage } from './documents/DocumentDetailPage'
import { DocumentsPage } from './documents/DocumentsPage'
import { FollowUpsPage } from './followUps/FollowUpsPage'
import { MedicationsPage } from './medications/MedicationsPage'
import { ComingSoon, NotFound } from './pages/ComingSoon'
import { StatusPage } from './pages/StatusPage'
import { SECTIONS, STATUS_SECTION } from './sections'

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
      </Route>

      <Route element={<AppShell />}>
        <Route element={<ProtectedRoute />}>
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:documentId" element={<DocumentDetailPage />} />
          <Route path="/medications" element={<MedicationsPage />} />
          <Route path="/follow-ups" element={<FollowUpsPage />} />
          {SECTIONS.filter((section) => !section.available).map((section) =>
            section.path === '/' ? (
              <Route key={section.path} index element={<ComingSoon section={section} />} />
            ) : (
              <Route key={section.path} path={section.path} element={<ComingSoon section={section} />} />
            ),
          )}
        </Route>
        <Route path={STATUS_SECTION.path} element={<StatusPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
