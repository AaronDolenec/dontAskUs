import { useState, useEffect, useCallback } from 'react'
import { useApi } from '../api/client'
import '../styles/DatabaseBrowser.css'

interface TableInfo {
  name: string
  row_count: number
}

interface ColumnSchema {
  name: string
  type: string
  nullable: boolean
  default: string | null
}

export default function DatabaseBrowser() {
  const { request } = useApi()
  const [tables, setTables] = useState<TableInfo[]>([])
  const [selectedTable, setSelectedTable] = useState('')
  const [columns, setColumns] = useState<string[]>([])
  const [rows, setRows] = useState<Record<string, any>[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [pageSize] = useState(50)
  const [sortColumn, setSortColumn] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [schema, setSchema] = useState<ColumnSchema[]>([])
  const [showSchema, setShowSchema] = useState(false)
  const [expandedRow, setExpandedRow] = useState<number | null>(null)

  // Fetch table list
  useEffect(() => {
    const fetchTables = async () => {
      try {
        const res = await request('/api/admin/db/tables')
        if (res.ok) {
          const data = await res.json()
          setTables(data.tables)
        }
      } catch (err: any) {
        setError(err.message)
      }
    }
    fetchTables()
  }, [request])

  // Fetch rows when table/page/sort/search changes
  const fetchRows = useCallback(async () => {
    if (!selectedTable) return
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams({
        limit: String(pageSize),
        offset: String(page * pageSize),
      })
      if (sortColumn) {
        params.set('sort_column', sortColumn)
        params.set('sort_dir', sortDir)
      }
      if (search) {
        params.set('search', search)
      }
      const res = await request(`/api/admin/db/tables/${selectedTable}/rows?${params}`)
      if (res.ok) {
        const data = await res.json()
        setColumns(data.columns)
        setRows(data.rows)
        setTotal(data.total)
      } else {
        setError('Failed to load rows')
      }
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [request, selectedTable, page, pageSize, sortColumn, sortDir, search])

  useEffect(() => {
    fetchRows()
  }, [fetchRows])

  // Fetch schema
  const fetchSchema = async (tableName: string) => {
    try {
      const res = await request(`/api/admin/db/tables/${tableName}/schema`)
      if (res.ok) {
        const data = await res.json()
        setSchema(data.columns)
      }
    } catch {}
  }

  const handleTableSelect = (tableName: string) => {
    setSelectedTable(tableName)
    setPage(0)
    setSortColumn(null)
    setSortDir('asc')
    setSearch('')
    setSearchInput('')
    setShowSchema(false)
    setExpandedRow(null)
    fetchSchema(tableName)
  }

  const handleSort = (col: string) => {
    if (sortColumn === col) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortColumn(col)
      setSortDir('asc')
    }
    setPage(0)
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSearch(searchInput)
    setPage(0)
  }

  const truncate = (val: any, max = 120): string => {
    if (val === null || val === undefined) return '∅'
    const s = String(val)
    return s.length > max ? s.slice(0, max) + '…' : s
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="management db-browser">
      <div className="db-header">
        <h1>🗄️ Database Browser</h1>
        <span className="db-badge">Read-Only</span>
      </div>

      <div className="db-layout">
        {/* Sidebar: table list */}
        <div className="db-sidebar">
          <h3>Tables</h3>
          <ul className="table-list">
            {tables.map(t => (
              <li
                key={t.name}
                className={selectedTable === t.name ? 'active' : ''}
                onClick={() => handleTableSelect(t.name)}
              >
                <span className="table-name">{t.name}</span>
                <span className="row-count">{t.row_count.toLocaleString()}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Main content */}
        <div className="db-main">
          {!selectedTable ? (
            <div className="db-empty">
              <div className="db-empty-icon">📋</div>
              <p>Select a table from the sidebar to browse its contents.</p>
            </div>
          ) : (
            <>
              {/* Toolbar */}
              <div className="db-toolbar">
                <div className="db-toolbar-left">
                  <h2>{selectedTable}</h2>
                  <span className="db-row-total">{total.toLocaleString()} rows</span>
                  <button
                    className={`schema-toggle ${showSchema ? 'active' : ''}`}
                    onClick={() => setShowSchema(!showSchema)}
                  >
                    {showSchema ? '📖 Hide Schema' : '📖 Schema'}
                  </button>
                </div>
                <form className="db-search" onSubmit={handleSearch}>
                  <input
                    type="text"
                    placeholder="Search across text columns…"
                    value={searchInput}
                    onChange={e => setSearchInput(e.target.value)}
                  />
                  <button type="submit">🔍</button>
                  {search && (
                    <button
                      type="button"
                      className="clear-search"
                      onClick={() => {
                        setSearch('')
                        setSearchInput('')
                        setPage(0)
                      }}
                    >
                      ✕
                    </button>
                  )}
                </form>
              </div>

              {/* Schema panel */}
              {showSchema && schema.length > 0 && (
                <div className="schema-panel">
                  <table className="schema-table">
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Nullable</th>
                        <th>Default</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schema.map(col => (
                        <tr key={col.name}>
                          <td className="col-name">{col.name}</td>
                          <td className="col-type">{col.type}</td>
                          <td>{col.nullable ? '✓' : '✗'}</td>
                          <td className="col-default">{truncate(col.default, 60)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Error */}
              {error && <div className="error">Error: {error}</div>}

              {/* Data table */}
              {loading ? (
                <div className="loading-text">Loading rows…</div>
              ) : (
                <>
                  <div className="db-table-wrapper">
                    <table className="db-data-table">
                      <thead>
                        <tr>
                          {columns.map(col => (
                            <th
                              key={col}
                              onClick={() => handleSort(col)}
                              className="sortable"
                            >
                              {col}
                              {sortColumn === col && (
                                <span className="sort-arrow">
                                  {sortDir === 'asc' ? ' ↑' : ' ↓'}
                                </span>
                              )}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.length === 0 ? (
                          <tr>
                            <td colSpan={columns.length} className="no-data">
                              No rows found
                            </td>
                          </tr>
                        ) : (
                          rows.map((row, idx) => (
                            <>
                              <tr
                                key={idx}
                                className={expandedRow === idx ? 'expanded-row' : ''}
                                onClick={() =>
                                  setExpandedRow(expandedRow === idx ? null : idx)
                                }
                              >
                                {columns.map(col => (
                                  <td key={col} title={row[col] !== null ? String(row[col]) : ''}>
                                    {truncate(row[col])}
                                  </td>
                                ))}
                              </tr>
                              {expandedRow === idx && (
                                <tr key={`${idx}-exp`} className="detail-row">
                                  <td colSpan={columns.length}>
                                    <div className="row-detail">
                                      {columns.map(col => (
                                        <div key={col} className="detail-field">
                                          <span className="detail-label">{col}</span>
                                          <span className="detail-value">
                                            {row[col] !== null && row[col] !== undefined
                                              ? String(row[col])
                                              : <em className="null-value">NULL</em>}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  <div className="pagination">
                    <button
                      onClick={() => setPage(0)}
                      disabled={page === 0}
                    >
                      ⏮ First
                    </button>
                    <button
                      onClick={() => setPage(p => Math.max(0, p - 1))}
                      disabled={page === 0}
                    >
                      ← Prev
                    </button>
                    <span>
                      Page {page + 1} of {totalPages || 1}
                    </span>
                    <button
                      onClick={() => setPage(p => p + 1)}
                      disabled={(page + 1) * pageSize >= total}
                    >
                      Next →
                    </button>
                    <button
                      onClick={() => setPage(totalPages - 1)}
                      disabled={(page + 1) * pageSize >= total}
                    >
                      Last ⏭
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
