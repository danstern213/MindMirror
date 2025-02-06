import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

// Debug environment variables
console.log('Environment Variables Check:', {
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL ? 'Set' : 'Not Set',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ? 'Set' : 'Not Set',
  url: supabaseUrl,
  keyLength: supabaseAnonKey?.length,
  keyStart: supabaseAnonKey?.substring(0, 10),
  keyEnd: supabaseAnonKey?.substring(supabaseAnonKey.length - 10)
})

if (!supabaseUrl || !supabaseAnonKey) {
  console.error('Missing Supabase environment variables:', {
    url: !!supabaseUrl,
    key: !!supabaseAnonKey
  })
  throw new Error('Missing required environment variables for Supabase')
}

// Create Supabase client with minimal configuration
export const supabase = createClient(supabaseUrl, supabaseAnonKey)

// Auth helper functions with better error handling
export const auth = {
  async login(email: string, password: string) {
    try {
      console.log('Starting login process for:', email)
      
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (error) {
        console.error('Login error details:', {
          message: error.message,
          status: error.status,
          name: error.name,
          stack: error.stack
        })
        throw error
      }

      console.log('Login successful. Session details:', {
        userId: data.user?.id,
        email: data.user?.email,
        sessionId: data.session?.access_token?.substring(0, 20) + '...'
      })
      return data
    } catch (error: any) {
      console.error('Login failed with error:', {
        message: error.message,
        status: error.status,
        name: error.name,
        stack: error.stack,
        supabaseError: error.error,
        supabaseErrorDescription: error.error_description
      })
      throw error
    }
  },

  async signup(email: string, password: string) {
    try {
      console.log('Attempting signup for:', email)
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
      })
      if (error) {
        console.error('Signup error:', error)
        throw error
      }
      console.log('Signup successful:', data)
      return data
    } catch (error: any) {
      console.error('Signup failed:', error)
      throw error
    }
  },

  async logout() {
    try {
      const { error } = await supabase.auth.signOut()
      if (error) {
        console.error('Logout error:', error)
        throw error
      }
      console.log('Logout successful')
    } catch (error: any) {
      console.error('Logout failed:', error)
      throw error
    }
  },

  async getSession() {
    try {
      const { data: { session }, error } = await supabase.auth.getSession()
      if (error) {
        console.error('Get session error:', error)
        throw error
      }
      console.log('Session retrieved:', session ? 'Active' : 'None')
      return session
    } catch (error: any) {
      console.error('Get session failed:', error)
      throw error
    }
  },

  onAuthStateChange(callback: (event: string, session: any) => void) {
    return supabase.auth.onAuthStateChange(callback)
  }
} 