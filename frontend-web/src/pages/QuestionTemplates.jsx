import { useState, useEffect } from 'react'
import axios from 'axios'
import { Plus, Edit, Trash2 } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function QuestionTemplates() {
  const [templates, setTemplates] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadTemplates()
  }, [])

  const loadTemplates = async () => {
    try {
      const response = await axios.get(`${API_BASE}/api/admin/question-templates`)
      setTemplates(response.data)
    } catch (error) {
      console.error('Error loading templates:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div>Loading...</div>

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Question Templates</h1>
        <button
          onClick={() => navigate('/templates/create')}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
        >
          <Plus size={20} />
          Create Template
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {templates.map((template) => (
          <div key={template.template_id} className="bg-white rounded-lg shadow-md p-6 border border-gray-200">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="px-2 py-1 bg-indigo-100 text-indigo-700 text-xs rounded">
                  {template.category}
                </span>
                <div className="flex items-center gap-2">
                  <button className="p-1 hover:bg-gray-200 rounded">
                    <Edit size={16} />
                  </button>
                  <button className="p-1 hover:bg-gray-200 rounded">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              <p className="font-medium text-gray-900">{template.question_text}</p>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Option A</span>
                <span className="font-medium">{template.option_a_template}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-600">Option B</span>
                <span className="font-medium">{template.option_b_template}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
