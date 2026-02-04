import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Package, CheckCircle, Clock, AlertCircle, RefreshCw } from 'lucide-react'
import { supabase } from '../lib/supabase'

export default function Dashboard() {
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    processing: 0,
    completed: 0,
    failed: 0
  })
  const [recentOrders, setRecentOrders] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      // Fetch all orders for stats
      const { data: orders, error } = await supabase
        .from('orders')
        .select('*')
        .order('created_at', { ascending: false })

      if (error) throw error

      // Calculate stats
      const newStats = {
        total: orders.length,
        pending: orders.filter(o => o.status === 'pending').length,
        processing: orders.filter(o => o.status === 'processing').length,
        completed: orders.filter(o => o.status === 'completed').length,
        failed: orders.filter(o => o.status === 'failed').length
      }
      setStats(newStats)
      setRecentOrders(orders.slice(0, 5))

    } catch (err) {
      console.error('Error fetching data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()

    // Subscribe to realtime updates
    const subscription = supabase
      .channel('orders')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'orders' }, () => {
        fetchData()
      })
      .subscribe()

    return () => {
      subscription.unsubscribe()
    }
  }, [])

  const statCards = [
    { label: 'Total Orders', value: stats.total, icon: Package, color: '#6366f1' },
    { label: 'Pending', value: stats.pending, icon: Clock, color: '#f59e0b' },
    { label: 'Processing', value: stats.processing, icon: RefreshCw, color: '#3b82f6' },
    { label: 'Completed', value: stats.completed, icon: CheckCircle, color: '#10b981' },
    { label: 'Failed', value: stats.failed, icon: AlertCircle, color: '#ef4444' },
  ]

  const getStatusBadge = (status) => {
    const styles = {
      pending: { bg: '#fef3c7', color: '#92400e' },
      processing: { bg: '#dbeafe', color: '#1e40af' },
      completed: { bg: '#d1fae5', color: '#065f46' },
      failed: { bg: '#fee2e2', color: '#991b1b' }
    }
    const s = styles[status] || styles.pending
    return (
      <span className="status-badge" style={{ backgroundColor: s.bg, color: s.color }}>
        {status}
      </span>
    )
  }

  return (
    <div className="dashboard">
      <div className="page-header">
        <h1>Dashboard</h1>
        <button className="btn btn-secondary" onClick={fetchData} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </div>

      <div className="stats-grid">
        {statCards.map(stat => (
          <div key={stat.label} className="stat-card">
            <div className="stat-icon" style={{ backgroundColor: stat.color + '20', color: stat.color }}>
              <stat.icon size={24} />
            </div>
            <div className="stat-info">
              <span className="stat-value">{stat.value}</span>
              <span className="stat-label">{stat.label}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section">
        <div className="section-header">
          <h2>Recent Orders</h2>
          <Link to="/orders" className="btn btn-link">View all →</Link>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Order #</th>
                <th>Customer</th>
                <th>Title</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {recentOrders.length === 0 ? (
                <tr>
                  <td colSpan="5" className="empty-state">No orders yet</td>
                </tr>
              ) : (
                recentOrders.map(order => (
                  <tr key={order.id}>
                    <td>
                      <Link to={`/orders/${order.job_id}`} className="order-link">
                        {order.order_number || order.job_id.slice(0, 8)}
                      </Link>
                      {order.is_test && <span className="order-test-badge">TEST</span>}
                    </td>
                    <td>{order.customer_name || 'N/A'}</td>
                    <td>{order.title || 'N/A'}</td>
                    <td>{getStatusBadge(order.status)}</td>
                    <td>{new Date(order.created_at).toLocaleDateString()}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
