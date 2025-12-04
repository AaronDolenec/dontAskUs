export default function StatCard({ title, value, icon: Icon, color, trend }) {
  const colorClasses = {
    indigo: 'bg-indigo-50 text-indigo-600 border-indigo-200',
    blue: 'bg-blue-50 text-blue-600 border-blue-200',
    purple: 'bg-purple-50 text-purple-600 border-purple-200',
    pink: 'bg-pink-50 text-pink-600 border-pink-200',
  }

  return (
    <div className={`p-6 rounded-lg border ${colorClasses[color]} shadow-sm hover:shadow-md transition`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-semibold text-gray-900 uppercase tracking-wide">{title}</p>
          <p className="text-3xl font-bold mt-2">{value}</p>
          <p className="text-xs text-gray-600 mt-2">{trend}</p>
        </div>
        <Icon size={28} className="opacity-50" />
      </div>
    </div>
  )
}
