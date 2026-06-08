# sim2l Web Dashboard

A modern React-based web dashboard for monitoring and managing sim2l microservices (Cache, Results, Catalog).

## Features

- **Real-time Service Monitoring** - Health checks and status monitoring for all services
- **Cache Management** - View cache entries, statistics, and invalidate cached results
- **Results Browser** - Search and explore simulation execution results
- **Catalog Explorer** - Browse simulations, view execution statistics
- **Modern UI** - Built with Material-UI for a clean, responsive interface

## Project Structure

```
web-ui/
├── src/
│   ├── api/               # API client layer
│   │   ├── client.ts      # Base HTTP client
│   │   ├── cacheService.ts
│   │   ├── resultsService.ts
│   │   └── catalogService.ts
│   ├── components/        # Reusable components
│   ├── pages/             # Page components
│   │   └── Dashboard.tsx  # Main dashboard
│   ├── types/             # TypeScript type definitions
│   ├── config.ts          # Service configuration
│   ├── App.tsx            # Main app component
│   └── main.tsx           # Entry point
├── public/
├── package.json
├── vite.config.ts
└── tsconfig.json
```

## Prerequisites

- Node.js 18+ and npm
- Running sim2l services (Cache, Results, Catalog)

## Installation

```bash
cd web-ui
npm install
```

## Deployment topology

The web-UI is a static SPA. It is **not** meant to talk to each
microservice on a different origin from the browser — the bundled
defaults assume a single origin where `/api/cache`, `/api/catalog`, and
`/api/results` are reverse-proxied to the corresponding backend.

```
                       ┌───────────────────────────┐
   browser  ────HTTPS──►   reverse proxy (nginx,   │
                       │   Caddy, Vite dev server) │
                       └──────┬───┬────────┬───────┘
                              │   │        │
                  /api/cache  │   │        │  /api/catalog
                              ▼   ▼        ▼
                       cache_service  catalog_service  results_service
                       (8001)         (8002)           (8003)
```

In development, [`vite.config.ts`](./vite.config.ts) is the reverse
proxy: requests to `/api/{cache,catalog,results}` from `npm run dev`
(port 3000) are forwarded to the three Flask services on 8001/8002/8003.
In production, **bring your own** reverse proxy with the three
locations. Example nginx snippet:

```nginx
location /api/cache/   { proxy_pass http://127.0.0.1:8001/; }
location /api/catalog/ { proxy_pass http://127.0.0.1:8002/; }
location /api/results/ { proxy_pass http://127.0.0.1:8003/; }
```

The proxy is what lets login persist across services: the browser only
ever sees the single front-door origin, so cookies and session-id
storage (`localStorage`) Just Work. Pointing the SPA directly at the
three service ports requires CORS configuration on every backend and is
explicitly not supported.

### Overrides

The defaults can be overridden with a `.env` file when you really do
need direct cross-origin access (e.g. local IDE development against a
remote backend cluster):

```env
VITE_CACHE_SERVICE_URL=http://localhost:8001
VITE_RESULTS_SERVICE_URL=http://localhost:8003
VITE_CATALOG_SERVICE_URL=http://localhost:8002
VITE_SESSION_ID=demo-session
```

Setting these makes each axios client target the absolute URL — the
backend services then need CORS allowing `http://localhost:3000`.

## Development

Start the development server:

```bash
npm run dev
```

The dashboard will be available at [http://localhost:3000](http://localhost:3000)

## Building for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

## Technology Stack

- **React 18** - UI framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Fast build tool
- **Material-UI (MUI)** - Component library
- **Axios** - HTTP client
- **React Router** - Routing
- **Recharts** - Data visualization

## API Endpoints Used

### Cache Service (port 8001)
- `GET /health` - Health check
- `GET /cache/entries` - List cache entries
- `GET /cache/stats` - Get cache statistics
- `POST /cache/invalidate` - Invalidate cache entries

### Results Service (port 8003)
- `GET /health` - Health check
- `POST /search` - Search results
- `GET /results/<id>` - Get specific result
- `GET /stats/<simulation>/<param>` - Get parameter statistics

### Catalog Service (port 8002)
- `GET /health` - Health check
- `GET /simulations/search` - Search simulations
- `GET /simulations/<name>` - Get simulation details
- `GET /simulations/<id>/stats` - Get execution statistics

## Development Roadmap

- [x] Project setup with Vite + React + TypeScript
- [x] API client layer
- [x] Main dashboard with service health monitoring
- [ ] Cache service dashboard
- [ ] Results browser and search
- [ ] Catalog explorer
- [ ] Advanced visualizations (charts, graphs)
- [ ] Real-time updates (WebSocket/polling)
- [ ] Dark mode support
- [ ] Export functionality

## Contributing

See [SIM2L_WEB_UI_IMPLEMENTATION.md](../SIM2L_WEB_UI_IMPLEMENTATION.md) for detailed implementation guide and missing endpoints that need to be added to the backend services.

## License

Same as sim2l project
