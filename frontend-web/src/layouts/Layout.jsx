import { Link, useLocation } from 'react-router-dom'
import { 
  BarChart3, 
  Settings, 
  Users, 
  HelpCircle, 
  LogOut,
  Menu,
  X 
} from 'lucide-react'
import { useState } from 'react'

export default function Layout({ children, setAdminToken }) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const location = useLocation()

  const navItems = [
    { path: '/', label: 'Dashboard', icon: BarChart3 },
    { path: '/groups', label: 'Groups', icon: Users },
    { path: '/templates', label: 'Templates', icon: HelpCircle },
  ]

  const isActive = (path) => location.pathname === path

  return (
    <div className="flex h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      {/* Sidebar */}
      <div className={`${sidebarOpen ? 'w-64' : 'w-20'} bg-gradient-to-b from-indigo-600 to-indigo-700 text-white transition-all duration-300 flex flex-col shadow-lg`}>
        {/* Logo */}
        <div className="p-4 border-b border-indigo-500 flex items-center justify-between">
          {sidebarOpen && <h1 className="text-2xl font-bold">AskUs</h1>}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1 hover:bg-indigo-500 rounded-lg transition"
          >
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        {/* Nav Items */}
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive(item.path)
                    ? 'bg-indigo-500 text-white'
                    : 'text-indigo-100 hover:bg-indigo-500 hover:bg-opacity-50'
                }`}
              >
                <Icon size={20} />
                {sidebarOpen && <span>{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        {/* Logout */}
        <div className="p-4 border-t border-indigo-500">
          <button
            onClick={() => {
              localStorage.removeItem('adminToken')
              setAdminToken(null)
            }}
            className="flex items-center space-x-3 w-full px-4 py-3 rounded-lg text-indigo-100 hover:bg-indigo-500 hover:bg-opacity-50 transition-colors"
          >
            <LogOut size={20} />
            {sidebarOpen && <span>Logout</span>}
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </div>
    </div>
  )
}
