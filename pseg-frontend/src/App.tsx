import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { Loader2, Zap, TrendingUp, DollarSign, Eye, EyeOff } from 'lucide-react'
import './App.css'

interface UsageData {
  date: string
  usage_kwh: number
  cost?: number
  billing_period?: string
}

interface PSEGUsageResponse {
  success: boolean
  data: UsageData[]
  message: string
  total_usage: number
  average_monthly_usage: number
}

function App() {
  const [credentials, setCredentials] = useState({ username: '', password: '' })
  const [usageData, setUsageData] = useState<UsageData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [totalUsage, setTotalUsage] = useState(0)
  const [averageUsage, setAverageUsage] = useState(0)
  const [activeTab, setActiveTab] = useState('auth')

  const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  const handleInputChange = (field: string, value: string) => {
    setCredentials(prev => ({ ...prev, [field]: value }))
    setError('')
  }

  const testLogin = async () => {
    if (!credentials.username || !credentials.password) {
      setError('Please enter both username and password')
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/pseg/login-test`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      })

      const result = await response.json()

      if (result.success) {
        setSuccess('Login successful! You can now retrieve your usage data.')
      } else {
        setError(result.message || 'Login failed')
      }
    } catch (err) {
      setError('Failed to connect to the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const fetchUsageData = async () => {
    if (!credentials.username || !credentials.password) {
      setError('Please enter your PSE&G credentials first')
      return
    }

    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/pseg/usage`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      })

      const result: PSEGUsageResponse = await response.json()

      if (result.success) {
        setUsageData(result.data)
        setTotalUsage(result.total_usage)
        setAverageUsage(result.average_monthly_usage)
        setSuccess(result.message)
        setActiveTab('data')
      } else {
        setError(result.message || 'Failed to retrieve usage data')
      }
    } catch (err) {
      setError('Failed to connect to the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const loadSampleData = async () => {
    setLoading(true)
    setError('')
    setSuccess('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/pseg/sample-data`)
      const result: PSEGUsageResponse = await response.json()

      if (result.success) {
        setUsageData(result.data)
        setTotalUsage(result.total_usage)
        setAverageUsage(result.average_monthly_usage)
        setSuccess('Sample data loaded for demonstration')
        setActiveTab('data')
      } else {
        setError('Failed to load sample data')
      }
    } catch (err) {
      setError('Failed to connect to the server. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const formatChartData = () => {
    return usageData.map(item => ({
      month: new Date(item.date).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      usage: item.usage_kwh,
      cost: item.cost || 0,
      date: item.date
    })).reverse()
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD'
    }).format(amount)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-green-50 p-4">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-4">
            <Zap className="h-8 w-8 text-blue-600" />
            <h1 className="text-4xl font-bold text-gray-900">PSE&amp;G Usage Interface</h1>
          </div>
          <p className="text-lg text-gray-600">
            Access your historical electric usage data for the last 12 months
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="auth">Authentication</TabsTrigger>
            <TabsTrigger value="data" disabled={usageData.length === 0}>Usage Data</TabsTrigger>
          </TabsList>

          <TabsContent value="auth" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="h-5 w-5" />
                  PSE&amp;G Account Login
                </CardTitle>
                <CardDescription>
                  Enter your PSE&amp;G account credentials to retrieve your historical usage data.
                  Your credentials are used only for this session and are not stored.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">Username/Email</Label>
                  <Input
                    id="username"
                    type="text"
                    placeholder="Enter your PSE&amp;G username or email"
                    value={credentials.username}
                    onChange={(e) => handleInputChange('username', e.target.value)}
                    disabled={loading}
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      placeholder="Enter your PSE&amp;G password"
                      value={credentials.password}
                      onChange={(e) => handleInputChange('password', e.target.value)}
                      disabled={loading}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                      onClick={() => setShowPassword(!showPassword)}
                      disabled={loading}
                    >
                      {showPassword ? (
                        <EyeOff className="h-4 w-4" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>

                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                {success && (
                  <Alert>
                    <AlertDescription>{success}</AlertDescription>
                  </Alert>
                )}

                <div className="flex gap-3">
                  <Button 
                    onClick={testLogin} 
                    disabled={loading || !credentials.username || !credentials.password}
                    variant="outline"
                    className="flex-1"
                  >
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Test Login
                  </Button>
                  
                  <Button 
                    onClick={fetchUsageData} 
                    disabled={loading || !credentials.username || !credentials.password}
                    className="flex-1"
                  >
                    {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                    Get Usage Data
                  </Button>
                </div>

                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <span className="w-full border-t" />
                  </div>
                  <div className="relative flex justify-center text-xs uppercase">
                    <span className="bg-background px-2 text-muted-foreground">Or</span>
                  </div>
                </div>

                <Button 
                  onClick={loadSampleData} 
                  disabled={loading}
                  variant="secondary"
                  className="w-full"
                >
                  {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Load Sample Data (Demo)
                </Button>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="data" className="space-y-6">
            {usageData.length > 0 && (
              <>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Total Usage (12 months)</CardTitle>
                      <Zap className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{totalUsage.toLocaleString()} kWh</div>
                    </CardContent>
                  </Card>
                  
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Average Monthly Usage</CardTitle>
                      <TrendingUp className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">{Math.round(averageUsage).toLocaleString()} kWh</div>
                    </CardContent>
                  </Card>
                  
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">Total Cost (Est.)</CardTitle>
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {formatCurrency(usageData.reduce((sum, item) => sum + (item.cost || 0), 0))}
                      </div>
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle>Monthly Usage Trend</CardTitle>
                    <CardDescription>Your electricity usage over the last 12 months</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={formatChartData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis />
                        <Tooltip 
                          formatter={(value: number, name: string) => [
                            name === 'usage' ? `${value.toLocaleString()} kWh` : formatCurrency(value),
                            name === 'usage' ? 'Usage' : 'Cost'
                          ]}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="usage" 
                          stroke="#2563eb" 
                          strokeWidth={2}
                          dot={{ fill: '#2563eb' }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Monthly Usage Comparison</CardTitle>
                    <CardDescription>Bar chart view of your monthly electricity consumption</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={formatChartData()}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="month" />
                        <YAxis />
                        <Tooltip 
                          formatter={(value: number) => [`${value.toLocaleString()} kWh`, 'Usage']}
                        />
                        <Bar dataKey="usage" fill="#10b981" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Detailed Usage Data</CardTitle>
                    <CardDescription>Complete breakdown of your monthly usage and costs</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="overflow-x-auto">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="border-b">
                            <th className="text-left p-2">Billing Period</th>
                            <th className="text-left p-2">Date</th>
                            <th className="text-right p-2">Usage (kWh)</th>
                            <th className="text-right p-2">Cost</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usageData.map((item, index) => (
                            <tr key={index} className="border-b hover:bg-gray-50">
                              <td className="p-2">{item.billing_period || 'N/A'}</td>
                              <td className="p-2">{new Date(item.date).toLocaleDateString()}</td>
                              <td className="p-2 text-right font-mono">{item.usage_kwh.toLocaleString()}</td>
                              <td className="p-2 text-right font-mono">
                                {item.cost ? formatCurrency(item.cost) : 'N/A'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default App
