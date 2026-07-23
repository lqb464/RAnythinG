import type { NextConfig } from 'next'

const apiOrigin = process.env.API_ORIGIN || 'http://127.0.0.1:8000'

const nextConfig: NextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiOrigin}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
