import React, { useState, useContext, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { AuthContext } from '../App.jsx'

export default function LoginPage() {
  const { user, setUser, loading } = useContext(AuthContext)
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!loading && user) {
      if (user.role === 'super_admin') navigate('/super-admin')
      else navigate('/admin')
    }
  }, [user, loading, navigate])

  const handleLogin = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ email, password }),
      })
      const data = await r.json()
      if (!r.ok) {
        setError(data.detail || 'Login failed')
        return
      }
      setUser({
          role: 'client',
          bot_id: data.bot_id,
          company_name: data.company_name,
          email: data.email || data.bot_id,
          plan: data.plan ?? 'starter',
          messages_used: data.messages_used ?? 0,
          message_limit: data.monthly_message_limit ?? 500,
          ...data,
      })
      navigate('/admin')
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>Loading…</div>

  return (
    <div style={{ minHeight: '100vh', background: 'var(--body-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div style={{ width: '100%', maxWidth: 400 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ width: 56, height: 56, borderRadius: 14, background: 'var(--color-cta)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, margin: '0 auto 12px' }}>🤖</div>
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>SupportBot Studio</h1>
          <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)', fontSize: 14 }}>Sign in to your account</p>
        </div>

        <form className="card" onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label className="label">Email address</label>
            <input
              className="input"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div>
            <label className="label">Password</label>
            <input
              className="input"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          {error && (
            <div style={{ background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: 6, padding: '8px 12px', color: '#DC2626', fontSize: 13 }}>
              {error}
            </div>
          )}

          <button className="btn btn-primary" type="submit" disabled={submitting} style={{ marginTop: 4 }}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p style={{ textAlign: 'center', marginTop: 16, fontSize: 13, color: 'var(--text-muted)' }}>
          Platform administrator?{' '}
          <Link to="/super-admin" style={{ color: 'var(--color-cta)', textDecoration: 'none' }}>Super Admin →</Link>
        </p>
      </div>
    </div>
  )
}
