import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button.jsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card.jsx'
import { Input } from '@/components/ui/input.jsx'
import { Badge } from '@/components/ui/badge.jsx'
import { 
  Monitor, 
  Plus, 
  Play, 
  Square, 
  Settings, 
  Activity,
  Users,
  Server,
  Cpu,
  HardDrive,
  MemoryStick,
  Wifi,
  WifiOff,
  MessageSquare,
  Wand2
} from 'lucide-react'
import './App.css'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [user, setUser] = useState(null)
  const [environments, setEnvironments] = useState([])
  const [currentView, setCurrentView] = useState('dashboard')
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  // Mock authentication for demo
  useEffect(() => {
    const token = localStorage.getItem('genos_token')
    if (token) {
      setIsAuthenticated(true)
      setUser({ id: 1, username: 'demo_user', email: 'demo@genos.dev' })
      loadMockEnvironments()
    }
  }, [])

  const loadMockEnvironments = () => {
    const mockEnvironments = [
      {
        id: 1,
        name: "Ubuntu Development",
        description: "Ubuntu 22.04 with development tools",
        status: "running",
        os: "ubuntu_22.04",
        apps: ["vscode", "git", "nodejs"],
        created_at: new Date().toISOString(),
        last_accessed: new Date().toISOString(),
        cpu_cores: 2,
        memory_mb: 4096,
        disk_gb: 20
      },
      {
        id: 2,
        name: "Secure Browsing",
        description: "Isolated environment with Tor browser",
        status: "suspended",
        os: "ubuntu_22.04",
        apps: ["tor_browser", "firefox"],
        created_at: new Date(Date.now() - 86400000).toISOString(),
        last_accessed: new Date(Date.now() - 3600000).toISOString(),
        cpu_cores: 1,
        memory_mb: 2048,
        disk_gb: 10
      },
      {
        id: 3,
        name: "Windows Office",
        description: "Windows 10 with Office suite",
        status: "provisioning",
        os: "windows_10",
        apps: ["office", "chrome"],
        created_at: new Date(Date.now() - 1800000).toISOString(),
        last_accessed: null,
        cpu_cores: 2,
        memory_mb: 8192,
        disk_gb: 40
      }
    ]
    setEnvironments(mockEnvironments)
  }

  const handleLogin = async (credentials) => {
    localStorage.setItem('genos_token', 'demo_token')
    setIsAuthenticated(true)
    setUser({ id: 1, username: credentials.username, email: 'demo@genos.dev' })
    loadMockEnvironments()
  }

  const handleLogout = () => {
    localStorage.removeItem('genos_token')
    setIsAuthenticated(false)
    setUser(null)
    setEnvironments([])
  }

  const handleStartEnvironment = async (envId) => {
    setEnvironments(envs => 
      envs.map(env => 
        env.id === envId 
          ? { ...env, status: 'provisioning' }
          : env
      )
    )

    setTimeout(() => {
      setEnvironments(envs => 
        envs.map(env => 
          env.id === envId 
            ? { ...env, status: 'running', last_accessed: new Date().toISOString() }
            : env
        )
      )
    }, 3000)
  }

  const handleStopEnvironment = async (envId) => {
    setEnvironments(envs => 
      envs.map(env => 
        env.id === envId 
          ? { ...env, status: 'suspended' }
          : env
      )
    )
  }

  if (!isAuthenticated) {
    return <LoginScreen onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen bg-background">
      <Header 
        user={user} 
        onLogout={handleLogout}
        connectionStatus={connectionStatus}
        currentView={currentView}
        setCurrentView={setCurrentView}
      />
      
      <main className="container mx-auto px-4 py-6">
        {currentView === 'dashboard' && (
          <Dashboard 
            environments={environments}
            onStartEnvironment={handleStartEnvironment}
            onStopEnvironment={handleStopEnvironment}
            setCurrentView={setCurrentView}
          />
        )}
        {currentView === 'create' && (
          <EnvironmentCreator 
            onBack={() => setCurrentView('dashboard')}
            onEnvironmentCreated={(env) => {
              setEnvironments([...environments, env])
              setCurrentView('dashboard')
            }}
          />
        )}
        {currentView === 'environments' && (
          <EnvironmentManager 
            environments={environments}
            onStartEnvironment={handleStartEnvironment}
            onStopEnvironment={handleStopEnvironment}
            onBack={() => setCurrentView('dashboard')}
          />
        )}
      </main>
    </div>
  )
}

// Login Screen Component
function LoginScreen({ onLogin }) {
  const [credentials, setCredentials] = useState({ username: '', password: '' })
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsLoading(true)
    
    await new Promise(resolve => setTimeout(resolve, 1000))
    await onLogin(credentials)
    setIsLoading(false)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-4">
            <div className="p-3 bg-primary rounded-full">
              <Monitor className="h-8 w-8 text-primary-foreground" />
            </div>
          </div>
          <CardTitle className="text-2xl font-bold">Welcome to GenOS</CardTitle>
          <CardDescription>
            Access your dynamic virtual environments
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              type="text"
              placeholder="Username"
              value={credentials.username}
              onChange={(e) => setCredentials({...credentials, username: e.target.value})}
              required
            />
            <Input
              type="password"
              placeholder="Password"
              value={credentials.password}
              onChange={(e) => setCredentials({...credentials, password: e.target.value})}
              required
            />
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
          
          <div className="mt-6 text-center text-sm text-muted-foreground">
            <p>Demo credentials: any username/password</p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Header Component
function Header({ user, onLogout, connectionStatus, currentView, setCurrentView }) {
  const getConnectionIcon = () => {
    switch (connectionStatus) {
      case 'connected':
        return <Wifi className="h-4 w-4 text-green-500" />
      case 'connecting':
        return <Activity className="h-4 w-4 text-yellow-500 animate-pulse" />
      default:
        return <WifiOff className="h-4 w-4 text-red-500" />
    }
  }

  return (
    <header className="border-b bg-card">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <Monitor className="h-6 w-6 text-primary" />
              <span className="text-xl font-bold">GenOS</span>
            </div>
            
            <nav className="hidden md:flex space-x-4">
              <Button 
                variant={currentView === 'dashboard' ? 'default' : 'ghost'} 
                size="sm"
                onClick={() => setCurrentView('dashboard')}
              >
                Dashboard
              </Button>
              <Button 
                variant={currentView === 'environments' ? 'default' : 'ghost'} 
                size="sm"
                onClick={() => setCurrentView('environments')}
              >
                Environments
              </Button>
              <Button 
                variant={currentView === 'create' ? 'default' : 'ghost'} 
                size="sm"
                onClick={() => setCurrentView('create')}
              >
                Create
              </Button>
            </nav>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              {getConnectionIcon()}
              <span className="text-sm text-muted-foreground">
                {connectionStatus === 'connected' ? 'Connected' : 
                 connectionStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
              </span>
            </div>
            
            <Badge variant="outline" className="hidden sm:flex">
              {user?.username}
            </Badge>
            
            <Button variant="outline" size="sm" onClick={onLogout}>
              Sign Out
            </Button>
          </div>
        </div>
      </div>
    </header>
  )
}

// Dashboard Component
function Dashboard({ environments, onStartEnvironment, onStopEnvironment, setCurrentView }) {
  const getStatusColor = (status) => {
    switch (status) {
      case 'running': return 'bg-green-500'
      case 'suspended': return 'bg-yellow-500'
      case 'provisioning': return 'bg-blue-500'
      case 'error': return 'bg-red-500'
      default: return 'bg-gray-500'
    }
  }

  const getStatusText = (status) => {
    switch (status) {
      case 'running': return 'Running'
      case 'suspended': return 'Suspended'
      case 'provisioning': return 'Starting...'
      case 'error': return 'Error'
      default: return 'Unknown'
    }
  }

  const runningCount = environments.filter(env => env.status === 'running').length

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">Manage your virtual environments</p>
        </div>
        <Button onClick={() => setCurrentView('create')} className="flex items-center space-x-2">
          <Plus className="h-4 w-4" />
          <span>Create Environment</span>
        </Button>
      </div>

      {/* System Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Environments</CardTitle>
            <Server className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{environments.length}</div>
            <p className="text-xs text-muted-foreground">{runningCount} running</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">45%</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div className="bg-blue-600 h-2 rounded-full" style={{width: '45%'}}></div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
            <MemoryStick className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">62%</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div className="bg-green-600 h-2 rounded-full" style={{width: '62%'}}></div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Disk Usage</CardTitle>
            <HardDrive className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">38%</div>
            <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
              <div className="bg-yellow-600 h-2 rounded-full" style={{width: '38%'}}></div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Environments */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Environments</CardTitle>
          <CardDescription>Your most recently accessed virtual environments</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {environments.map((env) => (
              <div key={env.id} className="flex items-center justify-between p-4 border rounded-lg">
                <div className="flex items-center space-x-4">
                  <div className="flex items-center space-x-2">
                    <div className={`w-3 h-3 rounded-full ${getStatusColor(env.status)}`} />
                    <Monitor className="h-5 w-5 text-muted-foreground" />
                  </div>
                  
                  <div>
                    <h3 className="font-medium">{env.name}</h3>
                    <p className="text-sm text-muted-foreground">{env.description}</p>
                    <div className="flex items-center space-x-2 mt-1">
                      <Badge variant="outline" className="text-xs">
                        {env.os.replace('_', ' ')}
                      </Badge>
                      <Badge variant="outline" className="text-xs">
                        {env.cpu_cores} CPU, {env.memory_mb}MB RAM
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Badge variant={env.status === 'running' ? 'default' : 'secondary'}>
                    {getStatusText(env.status)}
                  </Badge>
                  
                  {env.status === 'running' ? (
                    <>
                      <Button size="sm" variant="outline">
                        <Monitor className="h-4 w-4 mr-1" />
                        Connect
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => onStopEnvironment(env.id)}
                      >
                        <Square className="h-4 w-4" />
                      </Button>
                    </>
                  ) : env.status === 'suspended' ? (
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => onStartEnvironment(env.id)}
                    >
                      <Play className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" disabled>
                      <Activity className="h-4 w-4 animate-pulse" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>

          {environments.length === 0 && (
            <div className="text-center py-8">
              <Monitor className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium mb-2">No environments yet</h3>
              <p className="text-muted-foreground mb-4">
                Create your first virtual environment to get started
              </p>
              <Button onClick={() => setCurrentView('create')}>
                <Plus className="h-4 w-4 mr-2" />
                Create Environment
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// Environment Creator Component
function EnvironmentCreator({ onBack, onEnvironmentCreated }) {
  const [command, setCommand] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  const handleCreateFromCommand = async () => {
    if (!command.trim()) return

    setIsCreating(true)
    
    // Simulate parsing and creation
    await new Promise(resolve => setTimeout(resolve, 2000))
    
    const newEnvironment = {
      id: Date.now(),
      name: command.split(' ').slice(0, 3).join(' ') || 'Custom Environment',
      description: `Environment created from: "${command}"`,
      status: 'provisioning',
      os: command.toLowerCase().includes('windows') ? 'windows_10' : 'ubuntu_22.04',
      apps: [
        ...(command.toLowerCase().includes('tor') ? ['tor_browser'] : []),
        ...(command.toLowerCase().includes('firefox') ? ['firefox'] : []),
        ...(command.toLowerCase().includes('code') ? ['vscode', 'git'] : [])
      ],
      cpu_cores: 2,
      memory_mb: 4096,
      disk_gb: 20,
      created_at: new Date().toISOString(),
      last_accessed: null
    }

    onEnvironmentCreated(newEnvironment)
    setIsCreating(false)
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center space-x-4">
        <Button variant="outline" size="sm" onClick={onBack}>
          ← Back
        </Button>
        <div>
          <h1 className="text-3xl font-bold">Create Environment</h1>
          <p className="text-muted-foreground">
            Set up a new virtual environment using natural language
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Wand2 className="h-5 w-5" />
            <span>Describe Your Environment</span>
          </CardTitle>
          <CardDescription>
            Tell us what you need in plain English, and we'll configure everything for you
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Environment Description</label>
            <textarea
              placeholder="e.g., 'I need a Linux environment with Tor browser for secure browsing' or 'Create a Windows development environment with Visual Studio Code'"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              rows={4}
              className="w-full mt-2 p-3 border rounded-md"
            />
          </div>
          
          <Button 
            onClick={handleCreateFromCommand}
            disabled={!command.trim() || isCreating}
            className="flex items-center space-x-2"
          >
            <Wand2 className="h-4 w-4" />
            <span>{isCreating ? 'Creating...' : 'Create Environment'}</span>
          </Button>

          <div className="mt-6">
            <label className="text-sm font-medium">Example Commands:</label>
            <div className="mt-2 space-y-2">
              {[
                "Ubuntu desktop with Firefox and development tools",
                "Isolated Windows environment for testing",
                "Secure browsing environment with Tor browser",
                "Powerful Linux workstation with Docker and VS Code"
              ].map((example, index) => (
                <Button
                  key={index}
                  variant="outline"
                  size="sm"
                  className="mr-2 mb-2"
                  onClick={() => setCommand(example)}
                >
                  {example}
                </Button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

// Environment Manager Component
function EnvironmentManager({ environments, onStartEnvironment, onStopEnvironment, onBack }) {
  const getStatusColor = (status) => {
    switch (status) {
      case 'running': return 'bg-green-500'
      case 'suspended': return 'bg-yellow-500'
      case 'provisioning': return 'bg-blue-500'
      case 'error': return 'bg-red-500'
      default: return 'bg-gray-500'
    }
  }

  const getStatusText = (status) => {
    switch (status) {
      case 'running': return 'Running'
      case 'suspended': return 'Suspended'
      case 'provisioning': return 'Starting...'
      case 'error': return 'Error'
      default: return 'Unknown'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-4">
        <Button variant="outline" size="sm" onClick={onBack}>
          ← Back
        </Button>
        <div>
          <h1 className="text-3xl font-bold">Environment Manager</h1>
          <p className="text-muted-foreground">Manage all your virtual environments</p>
        </div>
      </div>

      <div className="space-y-4">
        {environments.map((env) => (
          <Card key={env.id}>
            <CardContent className="pt-6">
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-4 flex-1">
                  <div className="flex items-center space-x-2 mt-1">
                    <div className={`w-3 h-3 rounded-full ${getStatusColor(env.status)}`} />
                    <span className="text-2xl">
                      {env.os.includes('ubuntu') ? '🐧' : env.os.includes('windows') ? '🪟' : '💻'}
                    </span>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-2">
                      <h3 className="text-lg font-medium">{env.name}</h3>
                      <Badge variant={env.status === 'running' ? 'default' : 'secondary'}>
                        {getStatusText(env.status)}
                      </Badge>
                    </div>
                    
                    <p className="text-sm text-muted-foreground mb-3">{env.description}</p>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div>
                        <span className="text-muted-foreground">OS:</span>
                        <span className="ml-2 font-medium">
                          {env.os.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>
                      </div>
                      <div className="flex items-center space-x-1">
                        <Cpu className="h-3 w-3 text-muted-foreground" />
                        <span>{env.cpu_cores} cores</span>
                      </div>
                      <div className="flex items-center space-x-1">
                        <MemoryStick className="h-3 w-3 text-muted-foreground" />
                        <span>{env.memory_mb}MB</span>
                      </div>
                      <div className="flex items-center space-x-1">
                        <HardDrive className="h-3 w-3 text-muted-foreground" />
                        <span>{env.disk_gb}GB</span>
                      </div>
                    </div>

                    {env.apps && env.apps.length > 0 && (
                      <div className="mt-3">
                        <span className="text-sm text-muted-foreground">Apps: </span>
                        <div className="inline-flex flex-wrap gap-1 mt-1">
                          {env.apps.slice(0, 3).map((app) => (
                            <Badge key={app} variant="outline" className="text-xs">
                              {app.replace('_', ' ')}
                            </Badge>
                          ))}
                          {env.apps.length > 3 && (
                            <Badge variant="outline" className="text-xs">
                              +{env.apps.length - 3} more
                            </Badge>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center space-x-2 ml-4">
                  {env.status === 'running' ? (
                    <>
                      <Button size="sm">
                        <Monitor className="h-4 w-4 mr-1" />
                        Connect
                      </Button>
                      <Button 
                        size="sm" 
                        variant="outline"
                        onClick={() => onStopEnvironment(env.id)}
                      >
                        <Square className="h-4 w-4" />
                      </Button>
                    </>
                  ) : env.status === 'suspended' ? (
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => onStartEnvironment(env.id)}
                    >
                      <Play className="h-4 w-4 mr-1" />
                      Start
                    </Button>
                  ) : env.status === 'provisioning' ? (
                    <Button size="sm" variant="outline" disabled>
                      <Activity className="h-4 w-4 animate-pulse mr-1" />
                      Starting...
                    </Button>
                  ) : (
                    <Button 
                      size="sm" 
                      variant="outline"
                      onClick={() => onStartEnvironment(env.id)}
                    >
                      <Play className="h-4 w-4 mr-1" />
                      Retry
                    </Button>
                  )}

                  <Button size="sm" variant="outline">
                    <Settings className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {environments.length === 0 && (
        <Card>
          <CardContent className="text-center py-12">
            <Monitor className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium mb-2">No environments found</h3>
            <p className="text-muted-foreground mb-4">
              Create your first environment to get started
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default App

