import { Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell'
import { ComingSoon, NotFound } from './pages/ComingSoon'
import { StatusPage } from './pages/StatusPage'
import { SECTIONS, STATUS_SECTION } from './sections'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        {SECTIONS.map((section) =>
          section.path === '/' ? (
            <Route key={section.path} index element={<ComingSoon section={section} />} />
          ) : (
            <Route key={section.path} path={section.path} element={<ComingSoon section={section} />} />
          ),
        )}
        <Route path={STATUS_SECTION.path} element={<StatusPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
