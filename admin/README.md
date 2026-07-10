# UBD Admin

Vue 3 + Vite admin panel for the UBD discounts platform.

## Development

    npm install
    npm run dev        # http://localhost:5173, proxies /api → http://localhost:8000

The backend must be running on port 8000 (see ../backend). Log in with a seeded
admin account.

## Tests

    npm run test       # Vitest, no backend required (API is mocked)
