import { useState } from 'react'
import { Send, Loader2, CheckCircle, XCircle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../lib/supabase'

export default function TestOrders() {
  const [submitting, setSubmitting] = useState(false)
  const [lastSubmission, setLastSubmission] = useState(null) // { success, job_id, error }

  const [formData, setFormData] = useState({
    user_image: null,
    accessory_1: '',
    accessory_2: '',
    accessory_3: '',
    title: '',
    subtitle: '',
    text_color: 'red',
    background_type: 'transparent',
    background_color: 'white',
    background_image: null,
    background_description: ''
  })

  const textColors = ['red', 'blue', 'green', 'white', 'black', 'yellow', 'orange', 'purple', 'pink', 'gold']
  const bgColors = ['white', 'black', 'red', 'blue', 'green', 'yellow', 'orange', 'purple', 'pink', 'gray', 'navy', 'teal']

  const handleInputChange = (e) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleFileChange = (e) => {
    const { name, files } = e.target
    setFormData(prev => ({ ...prev, [name]: files[0] || null }))
  }

  const resetForm = () => {
    setFormData({
      user_image: null,
      accessory_1: '',
      accessory_2: '',
      accessory_3: '',
      title: '',
      subtitle: '',
      text_color: 'red',
      background_type: 'transparent',
      background_color: 'white',
      background_image: null,
      background_description: ''
    })
    // Reset file inputs
    const fileInputs = document.querySelectorAll('input[type="file"]')
    fileInputs.forEach(input => input.value = '')
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setLastSubmission(null)

    const data = new FormData()

    if (formData.user_image) {
      data.append('user_image', formData.user_image)
    }
    data.append('accessory_1', formData.accessory_1)
    data.append('accessory_2', formData.accessory_2)
    data.append('accessory_3', formData.accessory_3)
    data.append('title', formData.title)
    data.append('subtitle', formData.subtitle || '')
    data.append('text_color', formData.text_color)
    data.append('background_type', formData.background_type)
    data.append('background_color', formData.background_color)
    data.append('is_test', 'true')

    if (formData.background_image) {
      data.append('background_image', formData.background_image)
    }
    if (formData.background_description) {
      data.append('background_description', formData.background_description)
    }

    try {
      const response = await fetch(`${API_BASE_URL}/starter-pack/submit`, {
        method: 'POST',
        body: data
      })

      const json = await response.json()

      if (json.success && json.job_id) {
        setLastSubmission({
          success: true,
          job_id: json.job_id,
          queue_position: json.queue_position
        })
        resetForm()
      } else {
        setLastSubmission({
          success: false,
          error: json.error || 'Failed to submit order'
        })
      }
    } catch (error) {
      setLastSubmission({
        success: false,
        error: error.message
      })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="test-orders-page">
      <div className="page-header">
        <h1>Create Test Order</h1>
        <span className="test-badge">Test Mode</span>
        <Link to="/orders" className="btn btn-secondary" style={{ marginLeft: 'auto' }}>
          View All Orders
        </Link>
      </div>

      {/* Submission Result */}
      {lastSubmission && (
        <div className={`submission-alert ${lastSubmission.success ? 'success' : 'error'}`}>
          {lastSubmission.success ? (
            <>
              <CheckCircle size={20} />
              <div>
                <strong>Order Queued Successfully!</strong>
                <p>Job ID: <code>{lastSubmission.job_id}</code> (Queue position: {lastSubmission.queue_position})</p>
                <Link to="/orders" className="alert-link">View in Orders →</Link>
              </div>
            </>
          ) : (
            <>
              <XCircle size={20} />
              <div>
                <strong>Failed to Submit Order</strong>
                <p>{lastSubmission.error}</p>
              </div>
            </>
          )}
          <button className="alert-close" onClick={() => setLastSubmission(null)}>×</button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="test-form">
        {/* User Photo */}
        <div className="form-section">
          <h3>1. User Photo (for Figure)</h3>
          <div className="form-group">
            <label>Upload photo *</label>
            <input
              type="file"
              name="user_image"
              accept="image/*"
              onChange={handleFileChange}
              required
            />
          </div>
        </div>

        {/* Accessories */}
        <div className="form-section">
          <h3>2. Accessories</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Accessory 1 *</label>
              <input
                type="text"
                name="accessory_1"
                placeholder="e.g., samurai sword"
                value={formData.accessory_1}
                onChange={handleInputChange}
                required
              />
            </div>
            <div className="form-group">
              <label>Accessory 2 *</label>
              <input
                type="text"
                name="accessory_2"
                placeholder="e.g., shield"
                value={formData.accessory_2}
                onChange={handleInputChange}
                required
              />
            </div>
            <div className="form-group">
              <label>Accessory 3 *</label>
              <input
                type="text"
                name="accessory_3"
                placeholder="e.g., helmet"
                value={formData.accessory_3}
                onChange={handleInputChange}
                required
              />
            </div>
          </div>
        </div>

        {/* Title & Subtitle */}
        <div className="form-section">
          <h3>3. Title & Subtitle</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Title *</label>
              <input
                type="text"
                name="title"
                placeholder="e.g., John Doe"
                value={formData.title}
                onChange={handleInputChange}
                required
              />
            </div>
            <div className="form-group">
              <label>Subtitle</label>
              <input
                type="text"
                name="subtitle"
                placeholder="e.g., The Hero"
                value={formData.subtitle}
                onChange={handleInputChange}
              />
            </div>
            <div className="form-group">
              <label>Text Color</label>
              <select
                name="text_color"
                value={formData.text_color}
                onChange={handleInputChange}
              >
                {textColors.map(color => (
                  <option key={color} value={color}>{color.charAt(0).toUpperCase() + color.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Background */}
        <div className="form-section">
          <h3>4. Background</h3>
          <div className="form-group">
            <label>Background Type</label>
            <select
              name="background_type"
              value={formData.background_type}
              onChange={handleInputChange}
            >
              <option value="transparent">Transparent (no background)</option>
              <option value="solid">Solid Color</option>
              <option value="image">Image (upload or describe)</option>
            </select>
          </div>

          {formData.background_type === 'solid' && (
            <div className="form-group">
              <label>Background Color</label>
              <select
                name="background_color"
                value={formData.background_color}
                onChange={handleInputChange}
              >
                {bgColors.map(color => (
                  <option key={color} value={color}>{color.charAt(0).toUpperCase() + color.slice(1)}</option>
                ))}
              </select>
            </div>
          )}

          {formData.background_type === 'image' && (
            <>
              <div className="form-group">
                <label>Option A: Upload reference image</label>
                <input
                  type="file"
                  name="background_image"
                  accept="image/*"
                  onChange={handleFileChange}
                />
              </div>
              <div className="form-group">
                <label>Option B: Describe the background</label>
                <textarea
                  name="background_description"
                  placeholder="e.g., galaxy background with stars, or wooden texture"
                  value={formData.background_description}
                  onChange={handleInputChange}
                  rows={2}
                />
              </div>
              <p className="form-hint">Note: If you upload an image, description will be ignored.</p>
            </>
          )}
        </div>

        <button type="submit" className="btn btn-primary btn-large" disabled={submitting}>
          {submitting ? (
            <>
              <Loader2 size={20} className="spinning" />
              Submitting...
            </>
          ) : (
            <>
              <Send size={20} />
              Submit Test Order
            </>
          )}
        </button>
      </form>
    </div>
  )
}
