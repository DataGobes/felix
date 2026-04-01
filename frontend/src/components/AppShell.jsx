import { Link, Outlet, useLocation } from 'react-router-dom'
import Footer from './Footer'

const NAV_ITEMS = [
  { to: '/documents', label: 'Documents' },
  { to: '/search', label: 'Search' },
  { to: '/chat', label: 'Chat' },
]

function AppShell() {
  const location = useLocation()

  return (
    <div className="h-screen flex flex-col bg-warm-bg">
      <header className="bg-white border-b border-warm-200 px-6 h-14 flex-shrink-0 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
            <img src="/felix-logo.svg" alt="Felix" className="w-7 h-7" />
            <span className="text-sm font-semibold text-warm-900">Felix</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map(item => (
              <Link
                key={item.to}
                to={item.to}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                  location.pathname.startsWith(item.to)
                    ? 'text-ember bg-ember/[0.08]'
                    : 'text-warm-500 hover:text-warm-900'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
        <Link
          to="/settings"
          className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
            location.pathname === '/settings'
              ? 'text-ember bg-ember/[0.08]'
              : 'text-warm-500 hover:text-warm-900'
          }`}
        >
          Settings
        </Link>
      </header>

      <main className="flex-1 min-h-0 overflow-auto">
        <Outlet />
      </main>

      <Footer />
    </div>
  )
}

export default AppShell
