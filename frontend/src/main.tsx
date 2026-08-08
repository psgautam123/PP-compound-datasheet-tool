import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ReviewApp from './ReviewApp.tsx'

const isReviewRoute = window.location.pathname.startsWith('/review')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isReviewRoute ? <ReviewApp /> : <App />}
  </StrictMode>,
)
