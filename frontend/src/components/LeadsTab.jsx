import React, { useState, useEffect, useContext, useCallback, useRef } from 'react'
import { ToastContext } from '../App.jsx'

// ── Constants ─────────────────────────────────────────────────────────────────
// Status values mirror the backend Lead.status enum. Single source of truth
// for both the dropdown options AND the label-pill colour map below.
const STATUS_OPTIONS = ['new', 'contacted', 'qualified', 'lost']

// Status → token. Tokens (not hex) so the palette can be retuned globally
// without touching this file.
const STATUS_COLORS = {
  new: 'var(--color-cta)',
  contacted: 'var(--color-warning)',
  qualified: 'var(--color-success)',
  lost: 'var(--color-muted)',
}

const TYPE_LABEL = {
  lead: 'Lead',
  escalation: 'Escalation',
}

const PER_PAGE = 20

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function truncate(s, n = 80) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n - 1) + '…' : s
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function SummaryCard({ label, value, hint }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 180 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: 'var(--text-primary)' }}>
        {value.toLocaleString()}
      </div>
      {hint && (
        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{hint}</div>
      )}
    </div>
  )
}

function TypePill({ type }) {
  const isEsc = type === 'escalation'
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 999,
        fontSize: 11,
        fontWeight: 500,
        background: isEsc ? 'var(--color-warning-bg, #FEF3C7)' : 'var(--color-cta-bg, #E0F2FE)',
        color: isEsc ? 'var(--color-warning, #92400E)' : 'var(--color-cta, #0369A1)',
      }}
    >
      {TYPE_LABEL[type] || type}
    </span>
  )
}

function StatusSelect({ value, onChange }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        padding: '4px 8px',
        borderRadius: 6,
        border: '1px solid var(--border)',
        background: '#fff',
        fontSize: 12,
        color: STATUS_COLORS[value] || 'var(--text-primary)',
        fontWeight: 500,
        cursor: 'pointer',
      }}
    >
      {STATUS_OPTIONS.map(s => (
        <option key={s} value={s}>{s}</option>
      ))}
    </select>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function LeadsTab() {
  const addToast = useContext(ToastContext)

  // Hold addToast in a ref so callbacks below can call the latest version
  // without listing it in their dep arrays. Pre-fix: addToast was a direct
  // dep of fetchList's useCallback, and an unstable Toast provider (or any
  // refactor that drops the App.jsx useCallback wrap) would re-create
  // fetchList every render. fetchList is itself the dep of a useEffect, so
  // the result was an infinite fetch loop hammering /api/leads. The ref
  // pattern breaks that chain: identity of addToastRef itself never
  // changes, but addToastRef.current always points at the latest fn.
  const addToastRef = useRef(addToast)
  useEffect(() => { addToastRef.current = addToast }, [addToast])

  // Filters — initialised to "all" so the first page-load shows everything.
  // Kept in component state (not URL) to match the rest of the dashboard's
  // shallow-routing approach.
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [rangeFilter, setRangeFilter] = useState('all')
  const [page, setPage] = useState(1)

  const [summary, setSummary] = useState(null)
  const [data, setData] = useState({ items: [], total: 0, total_pages: 0, page: 1 })
  const [loading, setLoading] = useState(false)

  // Build the filter query-string once per render. Empty values are omitted
  // so the URL stays readable in network logs.
  const buildParams = useCallback(() => {
    const p = new URLSearchParams()
    if (typeFilter && typeFilter !== 'all') p.set('type', typeFilter)
    if (statusFilter && statusFilter !== 'all') p.set('status', statusFilter)
    if (rangeFilter && rangeFilter !== 'all') p.set('range', rangeFilter)
    return p
  }, [typeFilter, statusFilter, rangeFilter])

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const params = buildParams()
      params.set('page', page)
      params.set('per_page', PER_PAGE)
      const r = await fetch(`/api/leads?${params.toString()}`, { credentials: 'include' })
      if (r.ok) setData(await r.json())
    } catch {
      addToastRef.current?.('Failed to load leads', 'error')
    } finally {
      setLoading(false)
    }
    // addToast is intentionally accessed via the ref above so it does not
    // need to be in this dep array.
  }, [buildParams, page])

  const fetchSummary = useCallback(async () => {
    try {
      const r = await fetch('/api/leads/summary', { credentials: 'include' })
      if (r.ok) setSummary(await r.json())
    } catch {}
  }, [])

  useEffect(() => { fetchSummary() }, [fetchSummary])
  useEffect(() => { fetchList() }, [fetchList])

  // Filter changes reset pagination — otherwise you can land on a now-empty
  // page 4 and see "no results" when there are 3 pages of data.
  useEffect(() => { setPage(1) }, [typeFilter, statusFilter, rangeFilter])

  const updateStatus = async (id, newStatus) => {
    try {
      const r = await fetch(`/api/leads/${id}/status`, {
        method: 'PATCH',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })
      if (!r.ok) throw new Error()
      // Optimistic update keeps the table responsive. Server is the source
      // of truth — a background refetch would be safer but more flicker.
      setData(prev => ({
        ...prev,
        items: prev.items.map(it => it.id === id ? { ...it, status: newStatus } : it),
      }))
    } catch {
      addToastRef.current?.('Failed to update status', 'error')
    }
  }

  const exportCsv = () => {
    const params = buildParams()
    // Cookies carry the session — using a plain link keeps the streaming
    // download free, no need to fetch+blob+revoke.
    window.location.href = `/api/leads/export?${params.toString()}`
  }

  const empty = !loading && data.items.length === 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* ── Summary cards ────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <SummaryCard label="Total leads" value={summary?.total_all_time ?? 0} hint="All time" />
        <SummaryCard label="This month" value={summary?.total_this_month ?? 0} hint="Last 30 days" />
        <SummaryCard label="With contact info" value={summary?.with_contact ?? 0} hint="Email or phone provided" />
        <SummaryCard label="Escalations" value={summary?.escalations_this_month ?? 0} hint="This month" />
      </div>

      {/* ── Filter bar + Export ──────────────────────────────────────── */}
      <div className="card" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Type:</span>
          <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} className="input" style={{ padding: '4px 8px', fontSize: 13 }}>
            <option value="all">All</option>
            <option value="lead">Leads</option>
            <option value="escalation">Escalations</option>
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Status:</span>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="input" style={{ padding: '4px 8px', fontSize: 13 }}>
            <option value="all">All</option>
            {STATUS_OPTIONS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}>
          <span style={{ color: 'var(--text-secondary)' }}>Range:</span>
          <select value={rangeFilter} onChange={e => setRangeFilter(e.target.value)} className="input" style={{ padding: '4px 8px', fontSize: 13 }}>
            <option value="all">All time</option>
            <option value="today">Today</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </label>
        <button
          className="btn btn-secondary"
          onClick={exportCsv}
          style={{ marginLeft: 'auto', fontSize: 13 }}
          disabled={empty}
        >
          ⬇ Export CSV
        </button>
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading && (
          <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13 }}>
            Loading…
          </div>
        )}

        {empty && (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🎯</div>
            <div style={{ fontWeight: 500, marginBottom: 4 }}>No leads yet</div>
            <div style={{ fontSize: 13 }}>
              Leads and escalations from your chat will appear here.
            </div>
          </div>
        )}

        {!loading && !empty && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: 'var(--body-bg)', textAlign: 'left' }}>
                  <th style={thStyle}>Date</th>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Email</th>
                  <th style={thStyle}>Phone</th>
                  <th style={thStyle}>Type</th>
                  <th style={thStyle}>Message</th>
                  <th style={thStyle}>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(row => (
                  <tr key={row.id} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={tdStyle}>{formatDate(row.created_at)}</td>
                    <td style={tdStyle}>{row.name || <span style={muted}>—</span>}</td>
                    <td style={tdStyle}>{row.email || <span style={muted}>—</span>}</td>
                    <td style={tdStyle}>{row.phone || <span style={muted}>—</span>}</td>
                    <td style={tdStyle}><TypePill type={row.type} /></td>
                    <td style={tdStyle} title={row.message || ''}>
                      {row.message ? truncate(row.message, 60) : <span style={muted}>—</span>}
                    </td>
                    <td style={tdStyle}>
                      <StatusSelect
                        value={row.status}
                        onChange={(v) => updateStatus(row.id, v)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* ── Pagination ──────────────────────────────────────────── */}
        {!empty && data.total_pages > 1 && (
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 16px', borderTop: '1px solid var(--border)',
            background: 'var(--body-bg)', fontSize: 13,
          }}>
            <span style={{ color: 'var(--text-secondary)' }}>
              Page {data.page} of {data.total_pages} · {data.total} total
            </span>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className="btn btn-secondary"
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                style={{ fontSize: 13, padding: '4px 10px' }}
              >← Prev</button>
              <button
                className="btn btn-secondary"
                onClick={() => setPage(p => Math.min(data.total_pages, p + 1))}
                disabled={page >= data.total_pages}
                style={{ fontSize: 13, padding: '4px 10px' }}
              >Next →</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Inline style fragments (avoid restyling the whole table on every render) ──
const thStyle = {
  padding: '10px 12px',
  fontSize: 11,
  fontWeight: 600,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  color: 'var(--text-muted)',
  borderBottom: '1px solid var(--border)',
}
const tdStyle = {
  padding: '10px 12px',
  verticalAlign: 'middle',
  color: 'var(--text-primary)',
}
const muted = { color: 'var(--text-muted)' }
