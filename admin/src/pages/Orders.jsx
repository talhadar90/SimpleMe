import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, RefreshCw, Filter } from 'lucide-react'
import { supabase } from '../lib/supabase'

export default function Orders() {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  const fetchOrders = async () => {
    setLoading(true)
    try {
      let query = supabase
        .from('orders')
        .select('*')
        .order('created_at', { ascending: false })

      if (statusFilter !== 'all') {
        query = query.eq('status', statusFilter)
      }

      const { data, error } = await query

      if (error) throw error
      setOrders(data || [])

    } catch (err) {
      console.error('Error fetching orders:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOrders()
  }, [statusFilter])

  const filteredOrders = orders.filter(order => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return (
      order.customer_name?.toLowerCase().includes(q) ||
      order.customer_email?.toLowerCase().includes(q) ||
      order.order_number?.toLowerCase().includes(q) ||
      order.job_id?.toLowerCase().includes(q) ||
      order.title?.toLowerCase().includes(q)
    )
  })

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
    <div className="orders-page">
      <div className="page-header">
        <h1>Orders</h1>
        <button className="btn btn-secondary" onClick={fetchOrders} disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
      </div>

      <div className="filters-bar">
        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search by customer, email, order #..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="filter-group">
          <Filter size={18} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">All Status</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </div>

      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Order #</th>
              <th>Job ID</th>
              <th>Customer</th>
              <th>Email</th>
              <th>Title</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="8" className="loading-state">Loading...</td>
              </tr>
            ) : filteredOrders.length === 0 ? (
              <tr>
                <td colSpan="8" className="empty-state">No orders found</td>
              </tr>
            ) : (
              filteredOrders.map(order => (
                <tr key={order.id}>
                  <td>
                    {order.order_number || '-'}
                    {order.is_test && <span className="order-test-badge">TEST</span>}
                  </td>
                  <td className="job-id">{order.job_id?.slice(0, 8)}</td>
                  <td>{order.customer_name || '-'}</td>
                  <td>{order.customer_email || '-'}</td>
                  <td>{order.title || '-'}</td>
                  <td>{getStatusBadge(order.status)}</td>
                  <td>{new Date(order.created_at).toLocaleDateString()}</td>
                  <td>
                    <Link to={`/orders/${order.job_id}`} className="btn btn-small">
                      View
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="table-footer">
        Showing {filteredOrders.length} of {orders.length} orders
      </div>
    </div>
  )
}
