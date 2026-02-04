import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Dashboard from './pages/Dashboard'
import Orders from './pages/Orders'
import OrderDetail from './pages/OrderDetail'
import TestOrders from './pages/TestOrders'
import Layout from './components/Layout'
import './App.css'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="orders" element={<Orders />} />
          <Route path="orders/:jobId" element={<OrderDetail />} />
          <Route path="test" element={<TestOrders />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
