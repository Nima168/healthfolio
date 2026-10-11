import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// The first render in each test file is slow while modules load in parallel runs;
// the default 1 s wait for findBy* queries is too tight for that.
configure({ asyncUtilTimeout: 3000 })

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
