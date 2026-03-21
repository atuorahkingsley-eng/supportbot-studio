import React, { useState, useEffect, useContext, useRef } from 'react'
import { ToastContext } from '../App.jsx'

export default function AdminPanel({ config, setConfig }) {
  const addToast = useContext(ToastContext)
  const [form, setForm] = useState(config)
  const [faqs, setFaqs] = useState([])
  const [newQ, setNewQ] = useState('')
  const [newA, setNewA] = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  useEffect(() => { setForm(config) }, [config])

  useEffect(() => {
    fetch('/api/knowledge').then(r => r.json()).then(setFaqs).catch(() => {})
  }, [])

  const saveConfig = async () => {
    try {
      const r = await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await r.json()
      setConfig(data)
      addToast('Configuration saved!', 'success')
    } catch {
      addToast('Failed to save config', 'error')
    }
  }

  const addFaq = async () => {
    if (!newQ.trim() || !newA.trim()) return
    try {
      const r = await fetch('/api/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: newQ, answer: newA }),
      })
      const faq = await r.json()
      setFaqs(prev => [faq, ...prev])
      setNewQ('')
      setNewA('')
      addToast('FAQ added!', 'success')
    } catch {
      addToast('Failed to add FAQ', 'error')
    }
  }

  const deleteFaq = async (id) => {
    try {
      await fetch(`/api/knowledge/${id}`, { method: 'DELETE' })
      setFaqs(prev => prev.filter(f => f.id !== id))
      addToast('FAQ removed', 'info')
    } catch {
      addToast('Failed to delete FAQ', 'error')
    }
  }

  const handleUpload = async (file) => {
    if (!file) return
    const allowed = ['.pdf', '.docx', '.csv', '.txt']
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!allowed.includes(ext)) {
      addToast('Unsupported file type. Use PDF, DOCX, CSV, or TXT', 'error')
      return
    }
    setUploading(true)
    setUploadResult(null)
    const fd = new FormData()
    fd.append('file', file)
    try {
      const r = await fetch('/api/knowledge/upload', { method: 'POST', body: fd })
      const data = await r.json()
      setUploadResult(data)
      fetch('/api/knowledge').then(r => r.json()).then(setFaqs)
      addToast(`Extracted ${data.added} Q&A pairs from ${file.name}`, 'success')
    } catch {
      addToast('Upload failed', 'error')
    } finally {
      setUploading(false)
    }
  }

  const field = (label, key, type = 'text', extra = {}) => (
    <div style={{ marginBottom: 16 }}>
      <label className="label">{label}</label>
      <input
        className="input"
        type={type}
        value={form[key] || ''}
        onChange={e => setForm(prev => ({ ...prev, [key]: e.target.value }))}
        {...extra}
      />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Bot Configuration */}
      <div className="card">
        <h2 className="section-title">Bot Configuration</h2>
        <div className="grid-2">
          {field('Business Name', 'business_name', 'text', { placeholder: 'Acme Corp' })}
          {field('Agent Name', 'agent_name', 'text', { placeholder: 'SupportBot' })}
        </div>
        <div className="grid-2">
          <div style={{ marginBottom: 16 }}>
            <label className="label">Brand Color</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="color"
                value={form.brand_color || '#6366F1'}
                onChange={e => setForm(prev => ({ ...prev, brand_color: e.target.value }))}
                style={{ width: 40, height: 36, border: '1px solid var(--border)', borderRadius: 8, cursor: 'pointer', padding: 2 }}
              />
              <input
                className="input"
                value={form.brand_color || ''}
                onChange={e => setForm(prev => ({ ...prev, brand_color: e.target.value }))}
                placeholder="#6366F1"
                style={{ flex: 1 }}
              />
            </div>
          </div>
          {field('Escalation Email', 'escalation_email', 'email', { placeholder: 'support@yourcompany.com' })}
        </div>
        <div style={{ marginBottom: 16 }}>
          <label className="label">Welcome Message</label>
          <textarea
            className="input"
            rows={2}
            value={form.welcome_message || ''}
            onChange={e => setForm(prev => ({ ...prev, welcome_message: e.target.value }))}
            placeholder="Hi! How can I help you today?"
            style={{ resize: 'vertical' }}
          />
        </div>
        <button className="btn btn-primary" onClick={saveConfig}>Save Configuration</button>
      </div>

      {/* Document Upload */}
      <div className="card">
        <h2 className="section-title">Upload Knowledge Document</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: 16, fontSize: 13 }}>
          Upload a PDF, DOCX, CSV, or TXT file — the bot will automatically extract FAQ pairs from it.
        </p>
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault()
            setDragOver(false)
            handleUpload(e.dataTransfer.files[0])
          }}
          onClick={() => fileRef.current?.click()}
          style={{
            border: `2px dashed ${dragOver ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 'var(--radius)',
            padding: '32px',
            textAlign: 'center',
            cursor: 'pointer',
            background: dragOver ? '#F5F3FF' : 'var(--body-bg)',
            transition: 'all 0.15s',
          }}
        >
          <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>
            {uploading ? 'Processing...' : 'Drop file here or click to browse'}
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>PDF · DOCX · CSV · TXT</div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.csv,.txt"
            style={{ display: 'none' }}
            onChange={e => handleUpload(e.target.files[0])}
          />
        </div>

        {uploading && (
          <div style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: 13 }}>
            ⏳ Extracting Q&A pairs with AI...
          </div>
        )}

        {uploadResult && !uploading && (
          <div style={{ marginTop: 12, padding: '12px 16px', background: '#F0FDF4', borderRadius: 8, border: '1px solid #BBF7D0' }}>
            <strong style={{ color: '#16A34A' }}>✅ Upload complete!</strong>
            <div style={{ fontSize: 13, color: '#166534', marginTop: 4 }}>
              Extracted {uploadResult.extracted} pairs · Added {uploadResult.added} to knowledge base from <em>{uploadResult.filename}</em>
            </div>
          </div>
        )}
      </div>

      {/* Knowledge Base */}
      <div className="card">
        <h2 className="section-title">Knowledge Base ({faqs.length} entries)</h2>

        {/* Add FAQ */}
        <div style={{ background: 'var(--body-bg)', borderRadius: 8, padding: 16, marginBottom: 20, border: '1px solid var(--border)' }}>
          <div style={{ marginBottom: 10 }}>
            <label className="label">Question</label>
            <input
              className="input"
              value={newQ}
              onChange={e => setNewQ(e.target.value)}
              placeholder="How do I reset my password?"
              onKeyDown={e => e.key === 'Enter' && addFaq()}
            />
          </div>
          <div style={{ marginBottom: 10 }}>
            <label className="label">Answer</label>
            <textarea
              className="input"
              rows={2}
              value={newA}
              onChange={e => setNewA(e.target.value)}
              placeholder="To reset your password, click..."
              style={{ resize: 'vertical' }}
            />
          </div>
          <button className="btn btn-primary" onClick={addFaq} disabled={!newQ.trim() || !newA.trim()}>
            + Add FAQ
          </button>
        </div>

        {/* FAQ List */}
        {faqs.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '24px 0', fontSize: 13 }}>
            No FAQs yet. Add one above or upload a document.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {faqs.map(faq => (
              <div key={faq.id} style={{
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '12px 14px',
                display: 'flex',
                gap: 12,
                alignItems: 'flex-start',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, marginBottom: 4 }}>{faq.question}</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 13 }}>{faq.answer}</div>
                  <div style={{ marginTop: 6, display: 'flex', gap: 6 }}>
                    <span className={`badge ${faq.source === 'manual' ? 'badge-blue' : 'badge-green'}`}>
                      {faq.source === 'manual' ? 'Manual' : `📄 ${faq.source_filename || 'Uploaded'}`}
                    </span>
                  </div>
                </div>
                <button
                  className="btn btn-danger"
                  style={{ padding: '4px 10px', fontSize: 12 }}
                  onClick={() => deleteFaq(faq.id)}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
