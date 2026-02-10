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

## Configuration

Create a `.env` file in the `web-ui` directory:

```env
VITE_CACHE_SERVICE_URL=http://localhost:8001
VITE_RESULTS_SERVICE_URL=http://localhost:8003
VITE_CATALOG_SERVICE_URL=http://localhost:8002
VITE_SESSION_ID=demo-session
```

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
