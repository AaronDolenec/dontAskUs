import { ReactNode } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import '../styles/Layout.css'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = async () => {
    await logout()
    navigate('/')
  }

  const isActive = (path: string) => location.pathname === path

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="logo">
          <h2>dontAskUs</h2>
          <span className="admin-badge">Admin</span>
        </div>

        <button className="theme-toggle" onClick={toggleTheme}>
          {theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode'}
        </button>

        <ul className="nav-links">
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/dashboard')
              }}
              className={isActive('/dashboard') ? 'active' : ''}
            >
              📊 Dashboard
            </a>
          </li>
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/users')
              }}
              className={isActive('/users') ? 'active' : ''}
            >
              👥 Users
            </a>
          </li>
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/groups')
              }}
              className={isActive('/groups') ? 'active' : ''}
            >
              👫 Groups
            </a>
          </li>
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/question-sets')
              }}
              className={isActive('/question-sets') ? 'active' : ''}
            >
              ❓ Question Sets
            </a>
          </li>
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/audit-logs')
              }}
              className={isActive('/audit-logs') ? 'active' : ''}
            >
              📋 Audit Logs
            </a>
          </li>
          <li>
            <a
              href="#"
              onClick={e => {
                e.preventDefault()
                navigate('/account')
              }}
              className={isActive('/account') ? 'active' : ''}
            >
              ⚙️ Account
            </a>
          </li>
        </ul>

        <button className="logout-btn" onClick={handleLogout}>
          🚪 Logout
        </button>
      </nav>

      <main className="content">
        {children}
      </main>
    </div>
  )
}
