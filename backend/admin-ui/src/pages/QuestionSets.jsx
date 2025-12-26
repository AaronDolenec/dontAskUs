import React, { useEffect, useState } from 'react'
import { api } from '../lib/api'
import '../styles/Management.css'

export default function QuestionSets() {
  const [sets, setSets] = useState([])
  const [total, setTotal] = useState(0)
  const [expandedId, setExpandedId] = useState(null)
  const [questions, setQuestions] = useState({})
  const [newQuestionText, setNewQuestionText] = useState('')
  const [newQuestionType, setNewQuestionType] = useState('member_choice')
  const [loading, setLoading] = useState(true)
  const [showNewSetForm, setShowNewSetForm] = useState(false)
  const [newSetName, setNewSetName] = useState('')
  const [newSetPublic, setNewSetPublic] = useState(true)

  async function load() {
    setLoading(true)
    try {
      const res = await api('/api/admin/question-sets?limit=50&offset=0')
      if (res.ok) {
        const data = await res.json()
        setSets(data.sets)
        setTotal(data.total)
      } else {
        const errData = await res.json()
        console.error('Error loading question sets:', errData)
        alert('Error loading question sets: ' + (errData.detail || 'Unknown error'))
      }
    } catch (err) {
      console.error('Exception loading question sets:', err)
      alert('Error: ' + err.message)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  async function loadQuestions(setId) {
    try {
      const res = await api(`/api/admin/question-sets/${setId}/questions`)
      if (res.ok) {
        const data = await res.json()
        console.log('Loaded questions:', data)
        setQuestions(prev => ({ ...prev, [setId]: data.questions || [] }))
      } else {
        console.error('Failed to load questions:', res.status, await res.text())
      }
    } catch (err) {
      console.error('Error loading questions:', err)
    }
  }

  async function toggleExpanded(s) {
    if (expandedId === s.id) {
      setExpandedId(null)
    } else {
      setExpandedId(s.id)
      await loadQuestions(s.id)
    }
  }

  async function createSet() {
    if (!newSetName.trim()) {
      alert('Please enter a name')
      return
    }
    try {
      const res = await api('/api/admin/question-sets', {
        method: 'POST',
        body: JSON.stringify({ name: newSetName, is_public: newSetPublic })
      })
      if (res.ok) {
        const data = await res.json()
        console.log('Created set:', data)
        setNewSetName('')
        setShowNewSetForm(false)
        await load()
      } else {
        const errData = await res.json()
        console.error('Error creating set:', errData)
        alert('Error: ' + (errData.detail || 'Failed to create set'))
      }
    } catch (err) {
      console.error('Exception creating set:', err)
      alert('Error: ' + err.message)
    }
  }

  async function deleteSet(setId) {
    if (!confirm('Delete this question set? This cannot be undone.')) return
    try {
      const res = await api(`/api/admin/question-sets/${setId}`, { method: 'DELETE' })
      if (res.ok) {
        console.log('Set deleted successfully')
        await load()
      } else {
        const errData = await res.json()
        console.error('Error deleting set:', errData)
        alert('Error: ' + (errData.detail || 'Failed to delete set'))
      }
    } catch (err) {
      console.error('Exception deleting set:', err)
      alert('Error: ' + err.message)
    }
  }

  async function deleteQuestion(setId, questionId) {
    if (!confirm('Delete this question?')) return
    try {
      const res = await api(`/api/admin/question-sets/${setId}/questions/${questionId}`, { method: 'DELETE' })
      if (res.ok) {
        console.log('Question deleted successfully')
        await loadQuestions(setId)
      } else {
        const errData = await res.json()
        console.error('Error deleting question:', errData)
        alert('Error: ' + (errData.detail || 'Failed to delete question'))
      }
    } catch (err) {
      console.error('Exception deleting question:', err)
      alert('Error: ' + err.message)
    }
  }

  async function addQuestion(setId) {
    if (!newQuestionText.trim()) {
      alert('Please enter a question')
      return
    }
    const payload = {
      question_text: newQuestionText,
      question_type: newQuestionType,
      options: []
    }
    const res = await api(`/api/admin/question-sets/${setId}/questions`, {
      method: 'POST',
      body: JSON.stringify(payload)
    })
    if (res.ok) {
      setNewQuestionText('')
      setNewQuestionType('member_choice')
      await loadQuestions(setId)
    } else {
      const errData = await res.json()
      alert('Error adding question: ' + (errData.detail || 'Unknown error'))
    }
  }

  if (loading) return <div style={{ padding: 16 }}>Loading question sets...</div>

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2>Question Sets ({total})</h2>
        <button onClick={() => setShowNewSetForm(!showNewSetForm)} style={{ padding: '8px 16px' }}>
          {showNewSetForm ? 'Cancel' : 'New Question Set'}
        </button>
      </div>

      {total === 0 && !showNewSetForm && (
        <div style={{ padding: 20, backgroundColor: 'var(--bg-secondary)', borderRadius: 4, textAlign: 'center', color: 'var(--text-secondary)' }}>
          <p>No question sets found. Create one to get started!</p>
        </div>
      )}

      {showNewSetForm && (
        <div style={{ marginBottom: 16, padding: 12, border: '1px solid var(--border-color)', borderRadius: 4, backgroundColor: 'var(--bg-primary)' }}>
          <input
            type="text"
            placeholder="Set name"
            value={newSetName}
            onChange={e => setNewSetName(e.target.value)}
            style={{ marginRight: 8, padding: 6 }}
          />
          <label style={{ marginRight: 16 }}>
            <input
              type="checkbox"
              checked={newSetPublic}
              onChange={e => setNewSetPublic(e.target.checked)}
            />
            Public
          </label>
          <button onClick={createSet} style={{ padding: '6px 12px' }}>Create</button>
        </div>
      )}

      <table className="management-table">
        <thead>
          <tr>
            <th>ID</th><th>Name</th><th>Questions</th><th>Public</th><th>Usage</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {sets.map(s => (
            <React.Fragment key={s.id}>
              <tr>
                <td>{s.id}</td>
                <td>{s.name}</td>
                <td>{s.question_count}</td>
                <td>{String(s.is_public)}</td>
                <td>{s.usage_count}</td>
                <td>
                  <button onClick={() => toggleExpanded(s)} style={{ marginRight: 8 }}>
                    {expandedId === s.id ? 'Hide' : 'View'}
                  </button>
                  <button onClick={() => deleteSet(s.id)} style={{ marginRight: 8, color: 'red' }}>Delete</button>
                </td>
              </tr>
              {expandedId === s.id && (
                <tr className="expanded-row">
                  <td colSpan="6" className="expanded-content">
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                        <h4 style={{ margin: 0 }}>Questions in "{s.name}"</h4>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <input
                            type="text"
                            placeholder="Enter question text"
                            value={newQuestionText}
                            onChange={e => setNewQuestionText(e.target.value)}
                            style={{ padding: 6, minWidth: 240 }}
                          />
                          <select
                            value={newQuestionType}
                            onChange={e => setNewQuestionType(e.target.value)}
                            style={{ padding: 6 }}
                          >
                            <option value="member_choice">Member Choice</option>
                            <option value="duo_choice">Duo Vote</option>
                            <option value="free_text">Free Text</option>
                          </select>
                          <button onClick={() => addQuestion(s.id)} style={{ padding: '6px 12px' }}>+ Add Question</button>
                        </div>
                      </div>
                      {(questions[s.id] || []).length === 0 ? (
                        <div style={{ padding: 12, backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: 4, textAlign: 'center', color: 'var(--text-secondary)' }}>
                          No questions in this set yet. Click "Add Question" to create one.
                        </div>
                      ) : (
                        <div>
                          {(questions[s.id] || []).map((q, idx) => (
                            <div key={q.id} style={{ marginBottom: 8, padding: 12, backgroundColor: 'var(--bg-primary)', border: '1px solid var(--border-color)', borderRadius: 4 }}>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                <div style={{ flex: 1 }}>
                                  <div style={{ fontWeight: 'bold', marginBottom: 4 }}>
                                    #{idx + 1}: {q.text || q.question_text}
                                  </div>
                                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                    Type: <code style={{ backgroundColor: 'var(--bg-tertiary)', padding: '2px 4px', borderRadius: 2, color: 'var(--text-primary)' }}>{q.type}</code>
                                  </div>
                                  {q.options && q.options.length > 0 && (
                                    <div style={{ marginTop: 6, fontSize: '12px' }}>
                                      Options: {q.options.map((opt, i) => (
                                        <span key={i} style={{ 
                                          display: 'inline-block',
                                          backgroundColor: 'var(--chip-bg)', 
                                          padding: '2px 6px', 
                                          borderRadius: 3,
                                          marginRight: 4,
                                          marginTop: 2,
                                          color: 'var(--text-primary)',
                                          border: '1px solid var(--chip-border)'
                                        }}>
                                          {opt}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                                <button 
                                  onClick={() => deleteQuestion(s.id, q.id)} 
                                  style={{ color: 'red', padding: '4px 8px', fontSize: 12, marginLeft: 12 }}
                                >
                                  Delete
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
