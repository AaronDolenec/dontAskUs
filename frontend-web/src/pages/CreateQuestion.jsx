import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Lightbulb } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function CreateQuestion({ adminToken }) {
  const { groupId } = useParams()
  const navigate = useNavigate()
  const [templates, setTemplates] = useState([])
  const [question, setQuestion] = useState('')
  const [optionA, setOptionA] = useState('')
  const [optionB, setOptionB] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadTemplates()
  }, [])

  const loadTemplates = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/admin/question-templates`)
      setTemplates(response.data)
    } catch (error) {
      console.error('Error loading templates:', error)
    }
  }

  const applyTemplate = (template) => {
    setQuestion(template.question_text)
    setOptionA(template.option_a_template)
    setOptionB(template.option_b_template)
  }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!question.trim() || !optionA.trim() || !optionB.trim()) return

    setLoading(true)
    try {
      await axios.post(
        `${API_BASE}/api/groups/${groupId}/questions`,
        {
          question_text: question,
          option_a: optionA,
          option_b: optionB,
        }
      )
      alert('Question created successfully!')
      navigate(`/groups/${groupId}`)
    } catch (error) {
      console.error('Error creating question:', error)
      alert('Failed to create question')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-4xl font-bold text-gray-900">Create Today's Question</h1>
        <p className="text-gray-600 mt-2">Write an engaging question and two options</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Form */}
        <div className="lg:col-span-2">
          <form onSubmit={handleCreate} className="bg-white rounded-lg shadow-lg p-8 border border-gray-200 space-y-6">
            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-2">Question</label>
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Who would rather...?"
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"
                maxLength={255}
              />
              <p className="text-xs text-gray-600 mt-1">{question.length}/255 characters</p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">Option A</label>
                <input
                  type="text"
                  value={optionA}
                  onChange={(e) => setOptionA(e.target.value)}
                  placeholder="Option A"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"
                  maxLength={100}
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">Option B</label>
                <input
                  type="text"
                  value={optionB}
                  onChange={(e) => setOptionB(e.target.value)}
                  placeholder="Option B"
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"
                  maxLength={100}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || !question.trim() || !optionA.trim() || !optionB.trim()}
              className="w-full px-4 py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating...' : 'Create Question'}
            </button>
          </form>
        </div>

        {/* Templates */}
        <div>
          <div className="bg-white rounded-lg shadow-lg p-6 border border-gray-200 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <Lightbulb size={20} className="text-indigo-600" />
              <h2 className="font-semibold text-gray-900">Templates</h2>
            </div>

            <div className="space-y-2 max-h-96 overflow-y-auto">
              {templates.map((template) => (
                <button
                  key={template.template_id}
                  onClick={() => applyTemplate(template)}
                  className="w-full text-left p-3 hover:bg-indigo-50 rounded-lg border border-gray-200 transition group"
                >
                  <p className="text-xs font-semibold text-indigo-600 group-hover:text-indigo-700 uppercase">
                    {template.category}
                  </p>
                  <p className="text-sm text-gray-900 font-medium mt-1 line-clamp-2">
                    {template.question_text}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
