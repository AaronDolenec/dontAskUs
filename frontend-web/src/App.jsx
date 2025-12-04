import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Layout from './layouts/Layout'
import Dashboard from './pages/Dashboard'
import GroupManagement from './pages/GroupManagement'
import CreateGroup from './pages/CreateGroup'
import GroupDetails from './pages/GroupDetails'
import Analytics from './pages/Analytics'
import QuestionTemplates from './pages/QuestionTemplates'
import CreateQuestion from './pages/CreateQuestion'
import Login from './pages/Login'

function App() {
  const [adminToken, setAdminToken] = useState(localStorage.getItem('adminToken'))

  useEffect(() => {
    localStorage.setItem('adminToken', adminToken || '')
  }, [adminToken])

  if (!adminToken) {
    return <Login setAdminToken={setAdminToken} />
  }

  return (
    <Layout adminToken={adminToken} setAdminToken={setAdminToken}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/groups" element={<GroupManagement adminToken={adminToken} />} />
        <Route path="/groups/create" element={<CreateGroup adminToken={adminToken} />} />
        <Route path="/groups/:groupId" element={<GroupDetails adminToken={adminToken} />} />
        <Route path="/groups/:groupId/analytics" element={<Analytics adminToken={adminToken} />} />
        <Route path="/groups/:groupId/question" element={<CreateQuestion adminToken={adminToken} />} />
        <Route path="/templates" element={<QuestionTemplates />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default App
