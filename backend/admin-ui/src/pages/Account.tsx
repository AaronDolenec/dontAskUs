import { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import QRCode from 'qrcode.react'
import '../styles/Account.css'

export default function Account() {
  const { accessToken, logout } = useAuth()
  const [profile, setProfile] = useState<any>(null)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState('')
  const [loading, setLoading] = useState(true)
  const [totpSecret, setTotpSecret] = useState('')
  const [totpUri, setTotpUri] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [totpError, setTotpError] = useState('')
  const [totpSuccess, setTotpSuccess] = useState('')
  const [settingUpTotp, setSettingUpTotp] = useState(false)

  useEffect(() => {
    if (!accessToken) return

    const fetchProfile = async () => {
      try {
        const data = await api.profile(accessToken)
        setProfile(data)
      } catch (err: any) {
        console.error('Error fetching profile:', err)
      } finally {
        setLoading(false)
      }
    }

    fetchProfile()
  }, [accessToken])

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('🔐 handleChangePassword called')
    setPasswordError('')
    setPasswordSuccess('')

    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match')
      return
    }

    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters')
      return
    }

    try {
      console.log('Calling api.changePassword...')
      const response = await api.changePassword(accessToken!, currentPassword, newPassword)
      console.log('✅ Password change response:', response)
      setPasswordSuccess('Password changed successfully')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: any) {
      console.error('❌ Password change error:', err)
      setPasswordError(err.message)
    }
  }

  const handleInitiateTotpSetup = async () => {
    console.log('🔑 handleInitiateTotpSetup called')
    setSettingUpTotp(true)
    setTotpError('')
    try {
      console.log('Calling api.initiateTotpSetup...')
      const data = await api.initiateTotpSetup(accessToken!)
      console.log('✅ TOTP setup initiated:', data)
      setTotpSecret(data.secret)
      setTotpUri(data.provisioning_uri)
    } catch (err: any) {
      console.error('❌ TOTP initiate error:', err)
      setTotpError(err.message)
      setSettingUpTotp(false)
    }
  }

  const handleVerifyTotp = async (e: React.FormEvent) => {
    e.preventDefault()
    console.log('✅ handleVerifyTotp called with code:', totpCode)
    setTotpError('')
    setTotpSuccess('')

    if (totpCode.length !== 6) {
      setTotpError('Code must be 6 digits')
      return
    }

    try {
      console.log('Calling api.verifyTotpSetup...')
      await api.verifyTotpSetup(accessToken!, totpCode)
      console.log('✅ TOTP verification successful')
      setTotpSuccess('2FA configured successfully!')
      setTotpCode('')
      setTotpSecret('')
      setTotpUri('')
      setSettingUpTotp(false)
      // Refresh profile
      const data = await api.profile(accessToken!)
      setProfile(data)
    } catch (err: any) {
      console.error('❌ TOTP verify error:', err)
      setTotpError(err.message)
    }
  }

  if (loading) return <div className="loading">Loading profile...</div>

  return (
    <div className="account">
      <h1>Account Settings</h1>

      <div className="section">
        <h2>Profile</h2>
        {profile && (
          <div className="profile-info">
            <p><strong>Username:</strong> {profile.username}</p>
            <p><strong>Status:</strong> {profile.is_active ? '✅ Active' : '❌ Inactive'}</p>
            <p><strong>2FA:</strong> {profile.totp_configured ? '✅ Enabled' : '❌ Not configured'}</p>
            <p><strong>Created:</strong> {new Date(profile.created_at).toLocaleString()}</p>
            <p><strong>Last Login IP:</strong> {profile.last_login_ip || 'N/A'}</p>
          </div>
        )}
      </div>

      <div className="section">
        <h2>Change Password</h2>
        <form onSubmit={handleChangePassword}>
          <div className="form-group">
            <label>Current Password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>New Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>Confirm Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          {passwordError && <div className="error">{passwordError}</div>}
          {passwordSuccess && <div className="success">{passwordSuccess}</div>}
          <button type="submit">Change Password</button>
        </form>
      </div>

      <div className="section">
        <h2>Two-Factor Authentication</h2>
        {profile?.totp_configured ? (
          <div className="success">✅ 2FA is enabled on your account</div>
        ) : (
          <>
            {settingUpTotp ? (
              <>
                <p>Scan this QR code with your authenticator app:</p>
                {totpUri && (
                  <div className="qr-container">
                    <QRCode value={totpUri} size={256} />
                  </div>
                )}
                <p>Or enter this secret manually: <code>{totpSecret}</code></p>
                <form onSubmit={handleVerifyTotp}>
                  <div className="form-group">
                    <label>Enter the 6-digit code from your authenticator:</label>
                    <input
                      type="text"
                      maxLength={6}
                      value={totpCode}
                      onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                      placeholder="000000"
                      required
                    />
                  </div>
                  {totpError && <div className="error">{totpError}</div>}
                  {totpSuccess && <div className="success">{totpSuccess}</div>}
                  <button type="submit" disabled={totpCode.length !== 6}>
                    Verify & Enable 2FA
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSettingUpTotp(false)
                      setTotpCode('')
                      setTotpSecret('')
                      setTotpUri('')
                      setTotpError('')
                    }}
                  >
                    Cancel
                  </button>
                </form>
              </>
            ) : (
              <button onClick={handleInitiateTotpSetup}>Set Up 2FA</button>
            )}
          </>
        )}
      </div>

      <div className="section">
        <button onClick={() => logout().then(() => window.location.href = '/')}>
          Logout
        </button>
      </div>
    </div>
  )
}
