import React, { useState, useEffect, useCallback } from 'react'
import AdminPanel from './components/AdminPanel.jsx'
import ChatWidget from './components/ChatWidget.jsx'
import AnalyticsDashboard from './components/AnalyticsDashboard.jsx'
import WebhookSettings from './components/WebhookSettings.jsx'
import ReportSettings from './components/ReportSettings.jsx'

const TABS = [
  { id: 'configure', label: 'Configure' },
  { id: 'chat', label: 'Chat Demo' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'integrations', label: 'Integrations' },
]

export function useToast() {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now()
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  return { toasts, addToast }
}

export const ToastContext = React.createContext(null)

export default function App() {
  const [activeTab, setActiveTab] = useState('configure')
  const [config, setConfig] = useState({
    business_name: 'My Business',
    agent_name: 'SupportBot',
    brand_color: '#6366F1',
    welcome_message: 'Hi! How can I help you today?',
    escalation_email: '',
  })
  const { toasts, addToast } = useToast()

  useEffect(() => {
    fetch('/api/config')
      .then(r => r.json())
      .then(data => setConfig(data))
      .catch(() => {})
  }, [])

  const accent = config.brand_color || '#6366F1'

  return (
    <ToastContext.Provider value={addToast}>
      <div style={{ '--accent': accent, minHeight: '100vh', background: 'var(--body-bg)' }}>
        {/* Header */}
        <header style={{
          background: 'var(--header-bg)',
          color: '#fff',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          gap: '32px',
          height: 56,
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: accent, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 16,
            }}>🤖</div>
            <span style={{ fontWeight: 700, fontSize: 15, fontFamily: 'var(--font-mono)' }}>
              SupportBot Studio
            </span>
          </div>

          <nav style={{ display: 'flex', gap: 4 }}>
            {TABS.map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: '6px 14px',
                  borderRadius: 6,
                  border: 'none',
                  background: activeTab === tab.id ? accent : 'transparent',
                  color: activeTab === tab.id ? '#fff' : '#A1A1AA',
                  fontWeight: 500,
                  fontSize: 14,
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="status-dot status-dot-green" />
            <span style={{ fontSize: 13, color: '#A1A1AA' }}>Online</span>
          </div>
        </header>

        {/* Content */}
        <main style={{ padding: '24px', maxWidth: 1100, margin: '0 auto' }}>
          {activeTab === 'configure' && (
            <AdminPanel config={config} setConfig={setConfig} />
          )}
          {activeTab === 'chat' && (
            <ChatWidget config={config} />
          )}
          {activeTab === 'analytics' && (
            <AnalyticsDashboard />
          )}
          {activeTab === 'integrations' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <WebhookSettings />
              <ReportSettings />
            </div>
          )}
        </main>

        {/* Toasts */}
        <div className="toast-container">
          {toasts.map(t => (
            <div key={t.id} className={`toast toast-${t.type}`}>{t.message}</div>
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  )
}
