import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Copy, Download, Share2 } from 'lucide-react'
import axios from 'axios'
import QRCode from 'qrcode'

const API_BASE = 'http://localhost:8000'

export default function CreateGroup({ adminToken }) {
  const navigate = useNavigate()
  const [groupName, setGroupName] = useState('')
  const [loading, setLoading] = useState(false)
  const [createdGroup, setCreatedGroup] = useState(null)
  const [qrImage, setQrImage] = useState(null)

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!groupName.trim()) return

    setLoading(true)
    try {
      const response = await axios.post(
        `${API_BASE}/api/admin/groups`,
        { name: groupName },
        { headers: { 'Authorization': `Bearer ${adminToken}` } }
      )

      const group = response.data
      setCreatedGroup(group)

      // Generate QR code
      const qr = await QRCode.toDataURL(group.invite_code, {
        errorCorrectionLevel: 'H',
        type: 'image/png',
        quality: 0.95,
        margin: 1,
        width: 300,
        color: {
          dark: '#000000',
          light: '#FFFFFF',
        },
      })
      setQrImage(qr)
    } catch (error) {
      console.error('Error creating group:', error)
      alert('Failed to create group')
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    alert('Copied to clipboard!')
  }

  if (createdGroup) {
    return (
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="text-center">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">Group Created!</h1>
          <p className="text-gray-600">Share these details with your group members</p>
        </div>

        <div className="bg-white rounded-lg shadow-lg p-8 border border-gray-200 space-y-6">
          {/* Group Name */}
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-2">Group Name</label>
            <div className="text-2xl font-bold text-indigo-600">{createdGroup.name}</div>
          </div>

          {/* Invite Code */}
          <div>
            <label className="block text-sm font-semibold text-gray-900 mb-2">Invite Code</label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={createdGroup.invite_code}
                readOnly
                className="flex-1 px-4 py-3 bg-gray-100 text-gray-900 font-mono text-lg rounded-lg border border-gray-300"
              />
              <button
                onClick={() => copyToClipboard(createdGroup.invite_code)}
                className="p-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition"
              >
                <Copy size={20} />
              </button>
            </div>
          </div>

          {/* QR Code */}
          <div className="text-center">
            <label className="block text-sm font-semibold text-gray-900 mb-4">QR Code</label>
            {qrImage && (
              <img
                src={qrImage}
                alt="QR Code"
                className="w-64 h-64 mx-auto border-2 border-gray-300 rounded-lg p-2 bg-white"
              />
            )}
            <div className="mt-4 flex gap-2 justify-center">
              <button
                onClick={() => {
                  const link = document.createElement('a')
                  link.href = qrImage
                  link.download = `${createdGroup.name}-qr.png`
                  link.click()
                }}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition"
              >
                <Download size={18} /> Download QR
              </button>
            </div>
          </div>

          {/* Admin Token */}
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <p className="text-sm text-yellow-800 font-semibold mb-2">Admin Token (Keep Secret)</p>
            <input
              type="text"
              value={createdGroup.admin_token}
              readOnly
              className="w-full px-3 py-2 bg-yellow-100 text-yellow-900 font-mono text-sm rounded border border-yellow-300"
            />
          </div>

          {/* Next Steps */}
          <div className="space-y-3">
            <button
              onClick={() => navigate(`/groups/${createdGroup.group_id}/question`)}
              className="w-full px-4 py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition"
            >
              Create First Question
            </button>
            <button
              onClick={() => navigate('/groups')}
              className="w-full px-4 py-3 bg-gray-200 text-gray-900 font-semibold rounded-lg hover:bg-gray-300 transition"
            >
              Back to Groups
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900">Create New Group</h1>
        <p className="text-gray-600 mt-2">Set up a new group for your AskUs questions</p>
      </div>

      <form onSubmit={handleCreate} className="bg-white rounded-lg shadow-lg p-8 border border-gray-200 space-y-6">
        <div>
          <label className="block text-sm font-semibold text-gray-900 mb-2">Group Name</label>
          <input
            type="text"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            placeholder="e.g., Team Alpha, Office Friends"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition"
          />
          <p className="text-sm text-gray-600 mt-1">This will be visible to all group members</p>
        </div>

        <button
          type="submit"
          disabled={loading || !groupName.trim()}
          className="w-full px-4 py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Creating...' : 'Create Group'}
        </button>
      </form>
    </div>
  )
}
