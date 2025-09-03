import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import './index.css';
import LoginPage from './pages/LoginPage';
import Dashboard from './pages/Dashboard';


const router = createBrowserRouter([
  {
    path: '/',
    element: <LoginPage/>
  },
  {
    path: '/dashboard',
    element: <Dashboard/>
  }
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
