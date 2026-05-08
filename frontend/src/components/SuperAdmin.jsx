import React, { useState, useEffect, useContext } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthContext, ToastContext } from '../App.jsx'

// ── Super Admin Login ──────────────────────────────────────────────────────────
function SuperAdminLogin({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const r = await fetch('/api/auth/super/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Login failed'); return }
      onLogin({ role: 'super_admin', username })
    } catch {
      setError('Network error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--body-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ width: '100%', maxWidth: 380 }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🛡️</div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Super Admin</h1>
          <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)', fontSize: 13 }}>Platform management</p>
        </div>
        <form className="card" onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label className="label">Username</label>
            <input className="input" value={username} onChange={e => setUsername(e.target.value)} required autoFocus />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
          </div>
          {error && <div style={{ color: '#DC2626', fontSize: 13, background: '#FEF2F2', padding: '8px 12px', borderRadius: 6 }}>{error}</div>}
          <button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign in'}</button>
        </form>
      </div>
    </div>
  )
}

// ── Tenant Row ─────────────────────────────────────────────────────────────────
function TenantRow({ t, onEdit, onToggle, onResetPassword, onDelete }) {
  const usagePct = t.monthly_message_limit > 0 ? Math.min(100, Math.round(t.messages_used_this_month / t.monthly_message_limit * 100)) : 0
  return (
    <tr style={{ borderBottom: '1px solid var(--border)' }}>
      <td style={{ padding: '10px 12px', fontWeight: 600 }}>{t.company_name}</td>
      <td style={{ padding: '10px 12px' }}><code style={{ fontSize: 11 }}>{t.bot_id}</code></td>
      <td style={{ padding: '10px 12px' }}>
        <span className={`badge ${t.plan === 'enterprise' ? 'badge-blue' : t.plan === 'pro' ? 'badge-amber' : 'badge-gray'}`}>{t.plan}</span>
      </td>
      <td style={{ padding: '10px 12px', fontSize: 13 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 80, height: 6, background: 'var(--border)', borderRadius: 99 }}>
            <div style={{ width: usagePct + '%', height: '100%', background: usagePct > 80 ? '#EF4444' : '#6366F1', borderRadius: 99 }} />
          </div>
          <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{t.messages_used_this_month}/{t.monthly_message_limit}</span>
        </div>
      </td>
      <td style={{ padding: '10px 12px', fontSize: 12, color: 'var(--text-secondary)' }}>{t.faq_count} FAQs · {t.conversation_count} convos · {t.lead_count} leads</td>
      <td style={{ padding: '10px 12px' }}>
        <span className={`badge ${t.is_active ? 'badge-green' : 'badge-gray'}`}>{t.is_active ? '✓ Active' : '✗ Inactive'}</span>
      </td>
      <td style={{ padding: '10px 12px' }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => onEdit(t)}>Edit</button>
          <button className="btn btn-secondary" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => onResetPassword(t)}>Reset PW</button>
          <button className="btn btn-secondary" style={{ padding: '3px 8px', fontSize: 11, color: t.is_active ? '#DC2626' : '#16A34A' }} onClick={() => onToggle(t)}>
            {t.is_active ? 'Disable' : 'Enable'}
          </button>
          <button className="btn btn-danger" style={{ padding: '3px 8px', fontSize: 11 }} onClick={() => onDelete(t)}>
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Confirm Delete Modal ───────────────────────────────────────────────────────
// Hard delete is irreversible — modal forces an explicit confirm click before
// the DELETE fires. Toast feedback is owned by the parent dashboard so the
// modal can close cleanly on either success or failure.
function ConfirmDeleteModal({ tenant, onClose, onConfirmed }) {
  const [submitting, setSubmitting] = useState(false)

  const handleConfirm = async () => {
    setSubmitting(true)
    try {
      await onConfirmed(tenant)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }}>
      <div className="card" style={{ maxWidth: 440, width: '100%' }}>
        <h2 className="section-title" style={{ color: '#DC2626' }}>⚠️ Permanent Deletion</h2>
        <p style={{ fontSize: 14, marginBottom: 8 }}>
          Are you sure you want to delete <strong>{tenant.company_name}</strong>?
        </p>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
          This will permanently remove all their data — conversations, messages, leads,
          FAQs, webhooks, and visitor history. This cannot be undone.
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
          <button className="btn btn-danger" onClick={handleConfirm} disabled={submitting}>
            {submitting ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Create / Edit Tenant Modal ─────────────────────────────────────────────────
function TenantModal({ tenant, onClose, onSaved }) {
  const isEdit = !!tenant?.bot_id
  const [form, setForm] = useState({
    owner_name: tenant?.owner_name || '',
    owner_email: tenant?.owner_email || '',
    company_name: tenant?.company_name || '',
    password: '',
    plan: tenant?.plan || 'basic',
    monthly_message_limit: tenant?.monthly_message_limit || 1000,
    is_active: tenant?.is_active ?? true,
    // telegram_handle lives on BotConfig (per-tenant override). Only meaningful
    // in edit mode — on create there's no BotConfig row yet. Empty string
    // round-trips through admin.py as "" -> NULL to clear the override.
    telegram_handle: tenant?.telegram_handle || '',
  })
  const [saving, setSaving] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const handleSave = async () => {
    setSaving(true)
    setError('')
    try {
      const url = isEdit ? `/api/admin/tenants/${tenant.bot_id}` : '/api/admin/tenants'
      const method = isEdit ? 'PUT' : 'POST'
      const body = isEdit
        ? { plan: form.plan, monthly_message_limit: form.monthly_message_limit, is_active: form.is_active, owner_name: form.owner_name, company_name: form.company_name, telegram_handle: form.telegram_handle }
        : form
      const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify(body) })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Failed'); return }
      if (!isEdit) setResult(data)
      else onSaved()
    } catch { setError('Network error') }
    finally { setSaving(false) }
  }

  if (result) {
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }}>
        <div className="card" style={{ maxWidth: 480, width: '100%' }}>
          <h2 className="section-title" style={{ color: '#16A34A' }}>✅ Tenant Created!</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20 }}>
            <div><strong>Bot ID:</strong> <code>{result.bot_id}</code></div>
            <div><strong>API Key:</strong> <code style={{ fontSize: 11, wordBreak: 'break-all' }}>{result.api_key}</code></div>
            <div><strong>Login URL:</strong> <code>{window.location.origin}/login</code></div>
            <div>
              <strong>Embed Code:</strong>
              <pre style={{ background: 'var(--card-bg)', padding: 10, borderRadius: 6, fontSize: 11, overflowX: 'auto', marginTop: 4 }}>{result.embed_code}</pre>
            </div>
          </div>
          <button className="btn btn-primary" onClick={() => { onSaved(); onClose() }}>Done</button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }}>
      <div className="card" style={{ maxWidth: 460, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}>
        <h2 className="section-title">{isEdit ? 'Edit Tenant' : 'Create New Tenant'}</h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {!isEdit && (
            <>
              <div><label className="label">Owner Name</label><input className="input" value={form.owner_name} onChange={e => setForm(p => ({ ...p, owner_name: e.target.value }))} /></div>
              <div><label className="label">Owner Email</label><input className="input" type="email" value={form.owner_email} onChange={e => setForm(p => ({ ...p, owner_email: e.target.value }))} /></div>
              <div><label className="label">Password</label><input className="input" type="password" value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} /></div>
            </>
          )}
          <div><label className="label">Company Name</label><input className="input" value={form.company_name} onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))} /></div>
          <div><label className="label">Plan</label>
            <select className="input" value={form.plan} onChange={e => setForm(p => ({ ...p, plan: e.target.value }))}>
              <option value="basic">Basic ($100/mo · 1,000 msgs)</option>
              <option value="pro">Pro ($200/mo · 5,000 msgs)</option>
              <option value="enterprise">Enterprise ($400/mo · 20,000 msgs)</option>
            </select>
          </div>
          {isEdit && (
            <>
              <div><label className="label">Monthly Message Limit</label><input className="input" type="number" value={form.monthly_message_limit} onChange={e => setForm(p => ({ ...p, monthly_message_limit: Number(e.target.value) }))} /></div>
              <div>
                <label className="label">Telegram Handle (optional)</label>
                <input
                  className="input"
                  value={form.telegram_handle}
                  onChange={e => setForm(p => ({ ...p, telegram_handle: e.target.value }))}
                  placeholder="@handle  or  123456789"
                />
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>
                  Per-tenant escalation ping. Sent in addition to the platform-wide chat. Empty clears.
                </div>
              </div>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={form.is_active} onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))} />
                <span style={{ fontSize: 14 }}>Account Active</span>
              </label>
            </>
          )}
          {error && <div style={{ color: '#DC2626', fontSize: 13 }}>{error}</div>}
        </div>
        <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
          <button className="btn btn-primary" onClick={handleSave} disabled={saving}>{saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Create Tenant'}</button>
          <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ── Reset Password Modal ───────────────────────────────────────────────────────
// Super-admin override: sets a tenant's password to whatever the operator
// chooses. Server enforces an 8-char min — we mirror that here so the
// operator gets immediate feedback. No "current password" field, by design:
// this is the recovery path for tenants who've lost theirs.
function ResetPasswordModal({ tenant, onClose, onDone }) {
  const [pw, setPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async () => {
    setError('')
    if (pw.length < 8) { setError('New password must be at least 8 characters'); return }
    if (pw !== confirm) { setError('Passwords do not match'); return }
    setSubmitting(true)
    try {
      const r = await fetch(`/api/admin/tenants/${tenant.bot_id}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ new_password: pw }),
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        setError(data.detail || 'Reset failed')
        return
      }
      onDone()
    } catch {
      setError('Network error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24 }}>
      <div className="card" style={{ maxWidth: 420, width: '100%' }}>
        <h2 className="section-title">Reset Password</h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 16 }}>
          Set a new login password for <strong>{tenant.company_name}</strong> (<code style={{ fontSize: 11 }}>{tenant.owner_email}</code>).
          Minimum 8 characters. The tenant is not notified — you'll need to share the new password out-of-band.
        </p>
        <div style={{ marginBottom: 12 }}>
          <label className="label">New password</label>
          <input className="input" type="password" value={pw} onChange={e => setPw(e.target.value)} autoFocus autoComplete="new-password" />
        </div>
        <div style={{ marginBottom: 12 }}>
          <label className="label">Confirm new password</label>
          <input className="input" type="password" value={confirm} onChange={e => setConfirm(e.target.value)} autoComplete="new-password" />
        </div>
        {error && <div style={{ color: '#DC2626', fontSize: 13, background: '#FEF2F2', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>{error}</div>}
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={submitting || !pw || !confirm}>
            {submitting ? 'Resetting…' : 'Reset Password'}
          </button>
          <button className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
        </div>
      </div>
    </div>
  )
}

// ── Super Admin Dashboard ──────────────────────────────────────────────────────
function SuperAdminDashboard({ onLogout }) {
  const addToast = useContext(ToastContext)
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [tenants, setTenants] = useState([])
  const [system, setSystem] = useState(null)
  const [billing, setBilling] = useState(null)
  const [health, setHealth] = useState(null)
  const [errors, setErrors] = useState(null)
  const [errorStats, setErrorStats] = useState(null)
  const [errFilter, setErrFilter] = useState({ status: '', error_type: '' })
  const [search, setSearch] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [editTenant, setEditTenant] = useState(null)
  const [resetPwTenant, setResetPwTenant] = useState(null)
  const [deleteTenant, setDeleteTenant] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)

  const load = () => {
    fetch('/api/admin/overview', { credentials: 'include' }).then(r => r.json()).then(setOverview).catch(() => {})
    fetch('/api/admin/tenants', { credentials: 'include' }).then(r => r.json()).then(setTenants).catch(() => {})
    fetch('/api/admin/system', { credentials: 'include' }).then(r => r.json()).then(setSystem).catch(() => {})
    fetch('/api/admin/billing', { credentials: 'include' }).then(r => r.json()).then(setBilling).catch(() => {})
  }

  const loadHealth = () => {
    setHealthLoading(true)
    const params = new URLSearchParams()
    if (errFilter.status) params.set('status', errFilter.status)
    if (errFilter.error_type) params.set('error_type', errFilter.error_type)
    Promise.all([
      fetch('/api/admin/health', { credentials: 'include' }).then(r => r.json()).catch(() => null),
      fetch(`/api/admin/errors?limit=50&${params}`, { credentials: 'include' }).then(r => r.json()).catch(() => null),
      fetch('/api/admin/errors/stats', { credentials: 'include' }).then(r => r.json()).catch(() => null),
    ]).then(([h, e, s]) => {
      setHealth(h)
      setErrors(e)
      setErrorStats(s)
      setHealthLoading(false)
    })
  }

  useEffect(() => { load() }, [])
  useEffect(() => { if (tab === 'health') loadHealth() }, [tab, errFilter])

  const handleToggle = async (t) => {
    const r = await fetch(`/api/admin/tenants/${t.bot_id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ is_active: !t.is_active }) })
    if (r.ok) load()
  }

  // Hard-delete a tenant. On success: optimistically drop from local state +
  // toast. On error: leave the tenant in the list and toast the message.
  // Modal closes either way; user can re-open to retry on failure.
  const handleDelete = async (t) => {
    try {
      const r = await fetch(`/api/admin/tenants/${t.bot_id}/permanent`, {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!r.ok) {
        const data = await r.json().catch(() => ({}))
        addToast(data.detail || 'Failed to delete tenant', 'error')
        return
      }
      setTenants(prev => prev.filter(x => x.bot_id !== t.bot_id))
      addToast(`Tenant '${t.company_name}' deleted`, 'success')
    } catch {
      addToast('Network error — tenant not deleted', 'error')
    } finally {
      setDeleteTenant(null)
    }
  }

  const filtered = tenants.filter(t => !search || t.company_name.toLowerCase().includes(search.toLowerCase()) || t.bot_id.includes(search.toLowerCase()))

  const handleResolveError = async (id) => {
    await fetch(`/api/admin/errors/${id}/resolve`, { method: 'POST', credentials: 'include' })
    loadHealth()
  }

  const handleRetryError = async (id) => {
    await fetch(`/api/admin/errors/${id}/retry`, { method: 'POST', credentials: 'include' })
    loadHealth()
  }

  const TABS = [['overview', '📊 Overview'], ['tenants', '🏢 Tenants'], ['billing', '💳 Billing'], ['system', '⚙️ System'], ['health', '🏥 Health']]

  return (
    <div style={{ '--accent': '#6366F1', minHeight: '100vh', background: 'var(--body-bg)' }}>
      <header style={{ background: 'var(--header-bg)', color: '#fff', padding: '0 24px', display: 'flex', alignItems: 'center', gap: '32px', height: 56, position: 'sticky', top: 0, zIndex: 100 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 22 }}>🛡️</span>
          <span style={{ fontWeight: 700, fontSize: 15, fontFamily: 'var(--font-mono)' }}>SupportBot · Super Admin</span>
        </div>
        <nav style={{ display: 'flex', gap: 4 }}>
          {TABS.map(([id, label]) => (
            <button key={id} onClick={() => setTab(id)} style={{ padding: '6px 14px', borderRadius: 6, border: 'none', background: tab === id ? '#6366F1' : 'transparent', color: tab === id ? '#fff' : '#A1A1AA', fontWeight: 500, fontSize: 14, cursor: 'pointer' }}>
              {label}
            </button>
          ))}
        </nav>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button onClick={onLogout} style={{ background: 'none', border: '1px solid #52525B', color: '#A1A1AA', padding: '4px 10px', borderRadius: 4, cursor: 'pointer', fontSize: 12 }}>Logout</button>
        </div>
      </header>

      <main style={{ padding: '24px', maxWidth: 1200, margin: '0 auto' }}>

        {/* Overview */}
        {tab === 'overview' && overview && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
              {[
                { label: 'Active Tenants', value: overview.active_tenants, icon: '🏢' },
                { label: 'Messages This Month', value: overview.total_messages_this_month?.toLocaleString(), icon: '💬' },
                { label: 'Revenue Estimate', value: '$' + overview.revenue_estimate, icon: '💰' },
                { label: 'API Cost Estimate', value: '$' + overview.api_cost_estimate, icon: '⚡' },
              ].map(({ label, value, icon }) => (
                <div key={label} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
                    <span style={{ fontSize: 20 }}>{icon}</span>
                  </div>
                  <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>{value}</div>
                </div>
              ))}
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div className="card">
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>Conversations Today</div>
                <div style={{ fontSize: 28, fontWeight: 700 }}>{overview.conversations_today}</div>
              </div>
              <div className="card">
                <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 8 }}>Total Leads</div>
                <div style={{ fontSize: 28, fontWeight: 700 }}>{overview.total_leads}</div>
              </div>
            </div>
          </div>
        )}

        {/* Tenants */}
        {tab === 'tenants' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <input className="input" placeholder="Search tenants…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: 240 }} />
              <button className="btn btn-primary" onClick={() => { setEditTenant(null); setShowModal(true) }}>+ Create Tenant</button>
            </div>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border)' }}>
                      {['Company', 'Bot ID', 'Plan', 'Usage', 'Stats', 'Status', 'Actions'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(t => (
                      <TenantRow
                        key={t.bot_id}
                        t={t}
                        onEdit={t => { setEditTenant(t); setShowModal(true) }}
                        onToggle={handleToggle}
                        onResetPassword={t => setResetPwTenant(t)}
                        onDelete={t => setDeleteTenant(t)}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* Billing */}
        {tab === 'billing' && billing && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
              {[
                { label: 'Total Revenue', value: '$' + billing.totals.revenue },
                { label: 'API Costs', value: '$' + billing.totals.api_costs },
                { label: 'Profit', value: '$' + billing.totals.profit, green: true },
              ].map(({ label, value, green }) => (
                <div key={label} className="card">
                  <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
                  <div style={{ fontSize: 26, fontWeight: 700, color: green ? '#16A34A' : undefined }}>{value}</div>
                </div>
              ))}
            </div>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border)' }}>
                      {['Company', 'Plan', 'Price', 'AI Msgs', 'API Cost', 'Profit'].map(h => (
                        <th key={h} style={{ padding: '10px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {billing.tenants.map(t => (
                      <tr key={t.bot_id} style={{ borderBottom: '1px solid var(--border)' }}>
                        <td style={{ padding: '10px 12px', fontWeight: 500 }}>{t.company_name}</td>
                        <td style={{ padding: '10px 12px' }}><span className={`badge ${t.plan === 'enterprise' ? 'badge-blue' : t.plan === 'pro' ? 'badge-amber' : 'badge-gray'}`}>{t.plan}</span></td>
                        <td style={{ padding: '10px 12px' }}>${t.plan_price}</td>
                        <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)' }}>{t.ai_messages}</td>
                        <td style={{ padding: '10px 12px', color: '#DC2626' }}>${t.estimated_api_cost}</td>
                        <td style={{ padding: '10px 12px', color: '#16A34A', fontWeight: 600 }}>${t.profit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* System */}
        {tab === 'system' && system && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="card">
              <h3 className="section-title">Database</h3>
              {[
                ['DB Size', system.db_size_mb + ' MB'],
                ['Tenants', system.tenants],
                ['Total FAQs', system.total_faqs],
                ['Conversations', system.total_conversations],
                ['Messages', system.total_messages],
                ['Leads', system.total_leads],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 14 }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{k}</span>
                  <span style={{ fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
            <div className="card">
              <h3 className="section-title">Environment</h3>
              {Object.entries(system.env_status).map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border)', fontSize: 14 }}>
                  <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>{k}</span>
                  <span style={{ color: v ? '#16A34A' : '#DC2626', fontWeight: 600 }}>{v ? '✓ Set' : '✗ Missing'}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Health Dashboard */}
        {tab === 'health' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>System Health</h2>
              <button className="btn btn-secondary" onClick={loadHealth} disabled={healthLoading}>{healthLoading ? 'Checking…' : 'Refresh'}</button>
            </div>

            {/* Status Cards */}
            {health && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {health.checks && Object.entries(health.checks).map(([key, check]) => {
                  const color = check.status === 'ok' ? '#16A34A' : check.status === 'warning' ? '#D97706' : check.status === 'not_configured' ? '#6B7280' : '#DC2626'
                  const icon = check.status === 'ok' ? '✅' : check.status === 'warning' ? '⚠️' : check.status === 'not_configured' ? '—' : '❌'
                  const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
                  return (
                    <div key={key} className="card" style={{ borderLeft: `3px solid ${color}` }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                        <span style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</span>
                        <span style={{ fontSize: 18 }}>{icon}</span>
                      </div>
                      <div style={{ fontSize: 13, color }}>
                        {check.status === 'ok' ? 'Healthy' : check.status === 'not_configured' ? 'Not configured' : check.message || check.status}
                      </div>
                      {check.free_percent !== undefined && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{check.free_percent}% free ({check.free_gb} GB)</div>}
                      {check.errors_last_hour !== undefined && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{check.errors_last_hour} errors / hour ({check.failed_last_hour} failed)</div>}
                      {check.active !== undefined && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{check.active} active tenants</div>}
                    </div>
                  )
                })}
              </div>
            )}

            {/* Healing Stats */}
            {errorStats && (
              <div className="card">
                <h3 className="section-title">Healing Stats (Last 24h)</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
                  {[
                    { label: 'Total Errors', value: errorStats.total_24h, color: undefined },
                    { label: 'Auto-Healed', value: `${errorStats.auto_healed} (${errorStats.heal_rate}%)`, color: '#16A34A' },
                    { label: 'Failed', value: errorStats.failed, color: errorStats.failed > 0 ? '#DC2626' : undefined },
                    { label: 'Avg Heal Time', value: `${errorStats.avg_heal_time_seconds}s`, color: undefined },
                  ].map(({ label, value, color }) => (
                    <div key={label}>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 2 }}>{label}</div>
                      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}</div>
                    </div>
                  ))}
                </div>
                {errorStats.by_type && Object.keys(errorStats.by_type).length > 0 && (
                  <div style={{ marginTop: 16 }}>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8, fontWeight: 600 }}>BY ERROR TYPE</div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {Object.entries(errorStats.by_type).map(([type, s]) => (
                        <div key={type} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <span style={{ width: 160, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{type}</span>
                          <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 99 }}>
                            <div style={{ width: `${Math.min(100, (s.healed / Math.max(s.total, 1)) * 100)}%`, height: '100%', background: '#6366F1', borderRadius: 99 }} />
                          </div>
                          <span style={{ fontSize: 11, color: 'var(--text-secondary)', width: 80, textAlign: 'right' }}>{s.healed}/{s.total} healed</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Filters + Errors Table */}
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Recent Errors</span>
                <select className="input" style={{ width: 160, height: 32, fontSize: 12 }} value={errFilter.status} onChange={e => setErrFilter(p => ({ ...p, status: e.target.value }))}>
                  <option value="">All statuses</option>
                  <option value="new">New</option>
                  <option value="healing">Healing</option>
                  <option value="healed">Healed</option>
                  <option value="failed">Failed</option>
                  <option value="resolved_manually">Resolved manually</option>
                </select>
                <select className="input" style={{ width: 180, height: 32, fontSize: 12 }} value={errFilter.error_type} onChange={e => setErrFilter(p => ({ ...p, error_type: e.target.value }))}>
                  <option value="">All types</option>
                  <option value="api_error">API Error</option>
                  <option value="db_error">DB Error</option>
                  <option value="connection_error">Connection Error</option>
                  <option value="notification_error">Notification Error</option>
                  <option value="auth_error">Auth Error</option>
                  <option value="upload_error">Upload Error</option>
                  <option value="unknown_error">Unknown</option>
                </select>
                <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-secondary)' }}>{errors?.total || 0} total</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border)' }}>
                      {['Time', 'Type', 'Bot', 'Endpoint', 'Message', 'Status', 'Heal Action', ''].map(h => (
                        <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-secondary)', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(errors?.errors || []).map(e => {
                      const statusColor = { healed: '#16A34A', failed: '#DC2626', healing: '#D97706', new: '#6B7280', resolved_manually: '#6366F1' }[e.status] || '#6B7280'
                      const ago = e.created_at ? (() => { const d = (Date.now() - new Date(e.created_at)) / 1000; return d < 60 ? `${Math.round(d)}s ago` : d < 3600 ? `${Math.round(d/60)}m ago` : `${Math.round(d/3600)}h ago` })() : ''
                      return (
                        <tr key={e.id} style={{ borderBottom: '1px solid var(--border)' }}>
                          <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{ago}</td>
                          <td style={{ padding: '8px 12px' }}><code style={{ fontSize: 11, background: 'var(--card-bg)', padding: '1px 5px', borderRadius: 3 }}>{e.error_type}</code></td>
                          <td style={{ padding: '8px 12px' }}><code style={{ fontSize: 10 }}>{e.bot_id || 'system'}</code></td>
                          <td style={{ padding: '8px 12px', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.endpoint}</td>
                          <td style={{ padding: '8px 12px', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={e.error_message}>{e.error_message}</td>
                          <td style={{ padding: '8px 12px' }}><span style={{ color: statusColor, fontWeight: 600 }}>{e.status}</span></td>
                          <td style={{ padding: '8px 12px', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{e.heal_action || '—'}</td>
                          <td style={{ padding: '8px 12px' }}>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {e.status === 'failed' && <button className="btn btn-secondary" style={{ padding: '2px 8px', fontSize: 10 }} onClick={() => handleRetryError(e.id)}>Retry</button>}
                              {e.status !== 'resolved_manually' && e.status !== 'healed' && <button className="btn btn-secondary" style={{ padding: '2px 8px', fontSize: 10 }} onClick={() => handleResolveError(e.id)}>Resolve</button>}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                    {(!errors?.errors || errors.errors.length === 0) && (
                      <tr><td colSpan={8} style={{ padding: 24, textAlign: 'center', color: 'var(--text-secondary)' }}>No errors found</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {showModal && (
        <TenantModal
          tenant={editTenant}
          onClose={() => { setShowModal(false); setEditTenant(null) }}
          onSaved={() => { load(); setShowModal(false); setEditTenant(null) }}
        />
      )}

      {resetPwTenant && (
        <ResetPasswordModal
          tenant={resetPwTenant}
          onClose={() => setResetPwTenant(null)}
          onDone={() => setResetPwTenant(null)}
        />
      )}

      {deleteTenant && (
        <ConfirmDeleteModal
          tenant={deleteTenant}
          onClose={() => setDeleteTenant(null)}
          onConfirmed={handleDelete}
        />
      )}
    </div>
  )
}

// ── Entry point: check auth or show login ──────────────────────────────────────
export default function SuperAdmin() {
  const { user, setUser, loading, logout } = useContext(AuthContext)
  const navigate = useNavigate()

  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>Loading…</div>

  if (!user || user.role !== 'super_admin') {
    return <SuperAdminLogin onLogin={(u) => setUser(u)} />
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return <SuperAdminDashboard onLogout={handleLogout} />
}
