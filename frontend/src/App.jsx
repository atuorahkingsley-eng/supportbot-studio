import React, { useState, useEffect, useCallback, createContext, useContext } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import AdminPanel from './components/AdminPanel.jsx'
import ChatWidget from './components/ChatWidget.jsx'
import AnalyticsDashboard from './components/AnalyticsDashboard.jsx'
import WebhookSettings from './components/WebhookSettings.jsx'
import ReportSettings from './components/ReportSettings.jsx'
import SalesPanel from './components/SalesPanel.jsx'
import LoginPage from './components/LoginPage.jsx'
import SuperAdmin from './components/SuperAdmin.jsx'
import EmbedChat from './components/EmbedChat.jsx'

// ── Toast system ──────────────────────────────────────────────────────────────
export const ToastContext = createContext(null)

function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>{t.message}</div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// ── Auth context ──────────────────────────────────────────────────────────────
export const AuthContext = createContext(null)

function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then(data => { setUser(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

// ── Admin TABS ────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'configure', label: 'Configure' },
  { id: 'chat', label: 'Chat Demo' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'sales', label: '💰 Sales' },
  { id: 'integrations', label: 'Integrations' },
]

// ── Client Admin Layout ───────────────────────────────────────────────────────
function ClientAdminLayout() {
  const { user, loading, logout } = useContext(AuthContext)
  const navigate = useNavigate()
  const addToast = useContext(ToastContext)
  const [activeTab, setActiveTab] = useState('configure')
  const [config, setConfig] = useState({
    business_name: 'My Business',
    agent_name: 'SupportBot',
    brand_color: '#6366F1',
    welcome_message: 'Hi! How can I help you today?',
    escalation_email: '',
  })

  useEffect(() => {
    if (!loading && !user) { navigate('/login'); return }
    if (!loading && user && user.role === 'super_admin') { navigate('/super-admin'); return }
    if (user) {
      fetch('/api/config', { credentials: 'include' })
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data) setConfig(data) })
        .catch(() => {})
    }
  }, [user, loading, navigate])

  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', color: 'var(--text-secondary)' }}>Loading…</div>
  if (!user || user.role !== 'client') return null

  const accent = config.brand_color || '#6366F1'

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div style={{ '--accent': accent, minHeight: '100vh', background: 'var(--body-bg)' }}>
      <header style={{ background: 'var(--header-bg)', color: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', gap: '32px', height: 56, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 8, background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16 }}>🤖</div>
          <span style={{ fontWeight: 700, fontSize: 15, fontFamily: 'var(--font-mono)' }}>SupportBot Studio</span>
        </div>
        <nav style={{ display: 'flex', gap: 4 }}>
          {TABS.map(tab => (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: activeTab === tab.id ? accent : 'transparent', color: activeTab === tab.id ? '#fff' : '#A1A1AA', fontWeight: 500, fontSize: 14, cursor: 'pointer', transition: 'all 0.15s' }}>
              {tab.label}
            </button>
          ))}
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 12, color: '#A1A1AA' }}>
            {user.plan?.toUpperCase()} · {(user.messages_used || 0).toLocaleString()}/{(user.message_limit || 0).toLocaleString()} msgs
          </span>
          <span className="status-dot status-dot-green" />
          <span style={{ fontSize: 13, color: '#A1A1AA' }}>{user.company_name}</span>
          <button onClick={handleLogout} style={{ background: 'none', border: '1px solid #52525B', color: '#A1A1AA', padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>
            Logout
          </button>
        </div>
      </header>

      <main style={{ padding: '24px', maxWidth: 1100, margin: '0 auto' }}>
        {activeTab === 'configure' && <AdminPanel config={config} setConfig={setConfig} />}
        {activeTab === 'chat' && <ChatWidget config={config} />}
        {activeTab === 'analytics' && <AnalyticsDashboard />}
        {activeTab === 'sales' && <SalesPanel />}
        {activeTab === 'integrations' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <WebhookSettings />
            <ReportSettings />
          </div>
        )}

        {/* Embed code card */}
        <div className="card" style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>Bot ID</div>
              <code style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{user.bot_id}</code>
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>Embed Code</div>
              <code style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', wordBreak: 'break-all' }}>
                {'<script src="…/widget.js" data-bot-id="' + user.bot_id + '"></script>'}
              </code>
            </div>
          </div>
          <span className={`badge ${user.plan === 'enterprise' ? 'badge-blue' : user.plan === 'pro' ? 'badge-amber' : 'badge-gray'}`} style={{ fontSize: 12, padding: '4px 10px' }}>
            {user.plan?.toUpperCase()} PLAN
          </span>
        </div>
      </main>
    </div>
  )
}

// ── Root App with BrowserRouter + Routes ──────────────────────────────────────
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/embed/:botId" element={<EmbedChat />} />
            <Route path="/super-admin/*" element={<SuperAdmin />} />
            <Route path="/admin/*" element={<ClientAdminLayout />} />
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
