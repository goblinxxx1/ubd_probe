# UBD Public

Vue 3 + Vite public site for the UBD discounts platform. Shows published offers
with a filter panel, pagination, and a detail view. No auth.

## Development

    npm install
    npm run dev        # http://localhost:5174, proxies /api → http://localhost:8000

The backend must be running on port 8000 (see ../backend).

## Tests

    npm run test       # Vitest, no backend required (API is mocked)
