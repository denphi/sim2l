#!/usr/bin/env python3
"""
HTML Report Generator for Complete Workflow

Generates a comprehensive HTML report with:
- Service health status
- Simulation deployment details
- Execution results with parameters
- Cache statistics
- Results database queries
- Performance metrics
- Visualizations
"""

import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class HTMLReportGenerator:
    """Generate comprehensive HTML reports for sim2l workflow"""

    def __init__(self, output_file: str = "sim2l_workflow_report.html"):
        self.output_file = output_file
        self.sections = []
        self.start_time = datetime.now()

    def add_header(self):
        """Add HTML header with CSS styling"""
        header = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sim2l Complete Workflow Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }

        .header .subtitle {
            font-size: 1.2em;
            opacity: 0.9;
        }

        .header .timestamp {
            margin-top: 20px;
            font-size: 0.9em;
            opacity: 0.8;
        }

        .content {
            padding: 40px;
        }

        .section {
            margin-bottom: 40px;
            border-left: 4px solid #667eea;
            padding-left: 20px;
        }

        .section h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
        }

        .section h3 {
            color: #764ba2;
            margin: 15px 0 10px 0;
            font-size: 1.3em;
        }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }

        .status-card {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 20px;
            border-left: 4px solid #28a745;
        }

        .status-card.warning {
            border-left-color: #ffc107;
        }

        .status-card.error {
            border-left-color: #dc3545;
        }

        .status-card .title {
            font-weight: bold;
            color: #495057;
            margin-bottom: 10px;
        }

        .status-card .value {
            font-size: 1.5em;
            color: #212529;
        }

        .status-card .detail {
            font-size: 0.9em;
            color: #6c757d;
            margin-top: 5px;
        }

        .code-block {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            overflow-x: auto;
            margin: 10px 0;
        }

        .json-view {
            background: #2d2d2d;
            color: #f8f8f2;
            border-radius: 5px;
            padding: 15px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            overflow-x: auto;
            margin: 10px 0;
        }

        .json-key {
            color: #66d9ef;
        }

        .json-string {
            color: #a6e22e;
        }

        .json-number {
            color: #ae81ff;
        }

        .json-boolean {
            color: #fd971f;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }

        th {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }

        td {
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
        }

        tr:hover {
            background: #f8f9fa;
        }

        .badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }

        .badge-success {
            background: #d4edda;
            color: #155724;
        }

        .badge-warning {
            background: #fff3cd;
            color: #856404;
        }

        .badge-danger {
            background: #f8d7da;
            color: #721c24;
        }

        .badge-info {
            background: #d1ecf1;
            color: #0c5460;
        }

        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #e9ecef;
        }

        .metric-row:last-child {
            border-bottom: none;
        }

        .metric-label {
            font-weight: 600;
            color: #495057;
        }

        .metric-value {
            color: #212529;
        }

        .highlight {
            background: #fff3cd;
            padding: 2px 6px;
            border-radius: 3px;
        }

        .success-text {
            color: #28a745;
            font-weight: 600;
        }

        .error-text {
            color: #dc3545;
            font-weight: 600;
        }

        .footer {
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            color: #6c757d;
            border-top: 1px solid #dee2e6;
        }

        .progress-bar {
            width: 100%;
            height: 30px;
            background: #e9ecef;
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 600;
            transition: width 0.3s ease;
        }

        .timeline {
            position: relative;
            padding: 20px 0;
        }

        .timeline-item {
            position: relative;
            padding-left: 40px;
            margin-bottom: 30px;
        }

        .timeline-item::before {
            content: '';
            position: absolute;
            left: 10px;
            top: 0;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #667eea;
        }

        .timeline-item::after {
            content: '';
            position: absolute;
            left: 19px;
            top: 20px;
            width: 2px;
            height: calc(100% + 30px);
            background: #dee2e6;
        }

        .timeline-item:last-child::after {
            display: none;
        }

        .timeline-time {
            font-size: 0.85em;
            color: #6c757d;
            margin-bottom: 5px;
        }

        .timeline-title {
            font-weight: 600;
            color: #212529;
            margin-bottom: 5px;
        }

        .timeline-content {
            color: #495057;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Sim2l Complete Workflow Report</h1>
            <div class="subtitle">Comprehensive Analysis of Service Integration and Performance</div>
            <div class="timestamp">Generated: """ + self.start_time.strftime("%Y-%m-%d %H:%M:%S") + """</div>
        </div>
        <div class="content">
"""
        self.sections.append(header)

    def add_section(self, title: str, content: str):
        """Add a content section"""
        section = f"""
        <div class="section">
            <h2>{title}</h2>
            {content}
        </div>
"""
        self.sections.append(section)

    def add_service_status(self, services: Dict[str, Dict[str, Any]]):
        """Add service status section"""
        cards_html = ""
        for name, info in services.items():
            status_class = "" if info['healthy'] else "error"
            status_text = "✓ Healthy" if info['healthy'] else "✗ Unhealthy"

            cards_html += f"""
            <div class="status-card {status_class}">
                <div class="title">{name.upper()} Service</div>
                <div class="value">{status_text}</div>
                <div class="detail">Port: {info['port']}</div>
                <div class="detail">URL: {info['url']}</div>
                <div class="detail">Response Time: {info.get('response_time', 'N/A')}ms</div>
            </div>
"""

        self.add_section("Service Health Status", f'<div class="status-grid">{cards_html}</div>')

    def add_deployment_info(self, deployment: Dict[str, Any]):
        """Add deployment information"""
        content = f"""
        <div class="metric-row">
            <span class="metric-label">Simulation Name:</span>
            <span class="metric-value">{deployment['name']}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Version:</span>
            <span class="metric-value">{deployment['version']}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Simulation ID:</span>
            <span class="metric-value highlight">{deployment['sim_id']}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Notebook:</span>
            <span class="metric-value">{deployment['notebook']}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Description:</span>
            <span class="metric-value">{deployment.get('description', 'N/A')}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Author:</span>
            <span class="metric-value">{deployment.get('author', 'N/A')}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Deployment Time:</span>
            <span class="metric-value">{deployment.get('timestamp', 'N/A')}</span>
        </div>
"""
        self.add_section("Simulation Deployment", content)

    def add_execution_results(self, results: List[Dict[str, Any]]):
        """Add execution results table"""
        table_rows = ""
        for i, result in enumerate(results, 1):
            cache_badge = '<span class="badge badge-success">CACHED</span>' if result['cached'] else '<span class="badge badge-info">NEW RUN</span>'

            params_html = "<br>".join([f"{k}: {v}" for k, v in result['parameters'].items()])
            outputs_html = "<br>".join([f"{k}: {v:.2f}" if isinstance(v, (int, float)) else f"{k}: {v}"
                                       for k, v in result.get('outputs', {}).items() if k in ['max_temperature', 'avg_temperature', 'converged']])

            table_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{params_html}</td>
                <td>{outputs_html}</td>
                <td>{result['execution_time']:.3f}s</td>
                <td>{cache_badge}</td>
                <td><code>{result.get('squid_id', 'N/A')[:16]}...</code></td>
            </tr>
"""

        content = f"""
        <table>
            <thead>
                <tr>
                    <th>Run #</th>
                    <th>Parameters</th>
                    <th>Key Outputs</th>
                    <th>Time</th>
                    <th>Cache</th>
                    <th>SQUID ID</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
"""
        self.add_section("Execution Results", content)

    def add_cache_statistics(self, cache_stats: Dict[str, Any]):
        """Add cache statistics"""
        total_runs = cache_stats.get('total_runs', 0)
        cache_hits = cache_stats.get('cache_hits', 0)
        cache_misses = total_runs - cache_hits
        hit_rate = (cache_hits / total_runs * 100) if total_runs > 0 else 0

        content = f"""
        <div class="status-grid">
            <div class="status-card">
                <div class="title">Total Runs</div>
                <div class="value">{total_runs}</div>
                <div class="detail">All executions</div>
            </div>
            <div class="status-card">
                <div class="title">Cache Hits</div>
                <div class="value success-text">{cache_hits}</div>
                <div class="detail">Instant results</div>
            </div>
            <div class="status-card">
                <div class="title">Cache Misses</div>
                <div class="value">{cache_misses}</div>
                <div class="detail">New computations</div>
            </div>
            <div class="status-card">
                <div class="title">Hit Rate</div>
                <div class="value">{hit_rate:.1f}%</div>
                <div class="detail">Efficiency metric</div>
            </div>
        </div>

        <h3>Cache Performance</h3>
        <div class="progress-bar">
            <div class="progress-fill" style="width: {hit_rate}%">
                {hit_rate:.1f}% Cache Hit Rate
            </div>
        </div>

        <div class="metric-row">
            <span class="metric-label">Total Cached Entries:</span>
            <span class="metric-value">{cache_stats.get('total_entries', 0)}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Cache Size:</span>
            <span class="metric-value">{cache_stats.get('total_size', 0)} bytes</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Average Speedup:</span>
            <span class="metric-value highlight">{cache_stats.get('avg_speedup', 0):.1f}x faster</span>
        </div>
"""
        self.add_section("Cache Statistics", content)

    def add_database_queries(self, db_results: Dict[str, Any]):
        """Add database query results"""
        content = ""

        # Results database
        if 'results' in db_results:
            results = db_results['results']
            content += f"""
            <h3>Results Database</h3>
            <div class="metric-row">
                <span class="metric-label">Total Simulation Runs:</span>
                <span class="metric-value">{results.get('count', 0)}</span>
            </div>
            <div class="json-view">
{json.dumps(results.get('sample', {}), indent=2)}
            </div>
"""

        # Parameter statistics
        if 'param_stats' in db_results:
            stats = db_results['param_stats']
            content += """
            <h3>Parameter Statistics</h3>
            <table>
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Min</th>
                        <th>Max</th>
                        <th>Average</th>
                        <th>Count</th>
                    </tr>
                </thead>
                <tbody>
"""
            for param, values in stats.items():
                avg_val = values.get('avg')
                avg_str = f"{avg_val:.2f}" if isinstance(avg_val, (int, float)) else 'N/A'
                content += f"""
                    <tr>
                        <td><strong>{param}</strong></td>
                        <td>{values.get('min', 'N/A')}</td>
                        <td>{values.get('max', 'N/A')}</td>
                        <td>{avg_str}</td>
                        <td>{values.get('count', 0)}</td>
                    </tr>
"""
            content += """
                </tbody>
            </table>
"""

        self.add_section("Database Query Results", content)

    def add_performance_analysis(self, performance: Dict[str, Any]):
        """Add performance analysis"""
        content = f"""
        <div class="status-grid">
            <div class="status-card">
                <div class="title">Avg New Run Time</div>
                <div class="value">{performance.get('avg_new_time', 0):.2f}s</div>
                <div class="detail">Uncached executions</div>
            </div>
            <div class="status-card">
                <div class="title">Avg Cached Time</div>
                <div class="value success-text">{performance.get('avg_cached_time', 0):.3f}s</div>
                <div class="detail">Cached retrievals</div>
            </div>
            <div class="status-card">
                <div class="title">Speedup Factor</div>
                <div class="value highlight">{performance.get('speedup', 0):.1f}x</div>
                <div class="detail">Cache advantage</div>
            </div>
            <div class="status-card">
                <div class="title">Time Saved</div>
                <div class="value">{performance.get('time_saved', 0):.2f}s</div>
                <div class="detail">By caching</div>
            </div>
        </div>

        <h3>Execution Timeline</h3>
        <div class="timeline">
"""

        for event in performance.get('timeline', []):
            content += f"""
            <div class="timeline-item">
                <div class="timeline-time">{event['time']}</div>
                <div class="timeline-title">{event['title']}</div>
                <div class="timeline-content">{event['description']}</div>
            </div>
"""

        content += "</div>"

        self.add_section("Performance Analysis", content)

    def add_service_interactions(self, interactions: List[Dict[str, Any]]):
        """Add service interaction log"""
        content = """
        <table>
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Service</th>
                    <th>Operation</th>
                    <th>Status</th>
                    <th>Response Time</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
"""

        for interaction in interactions:
            status_badge = '<span class="badge badge-success">SUCCESS</span>' if interaction['status'] == 'success' else '<span class="badge badge-danger">FAILED</span>'

            content += f"""
            <tr>
                <td>{interaction['timestamp']}</td>
                <td><strong>{interaction['service']}</strong></td>
                <td>{interaction['operation']}</td>
                <td>{status_badge}</td>
                <td>{interaction.get('response_time', 'N/A')}ms</td>
                <td><small>{interaction.get('details', '')}</small></td>
            </tr>
"""

        content += """
            </tbody>
        </table>
"""
        self.add_section("Service Interaction Log", content)

    def add_footer(self):
        """Add footer"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        footer = f"""
        </div>
        <div class="footer">
            <p><strong>Report Generated by Sim2l Complete Workflow Example</strong></p>
            <p>Generation Time: {duration:.2f} seconds</p>
            <p>Timestamp: {end_time.strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p style="margin-top: 20px;">
                <a href="https://github.com/denphi/sim2l" style="color: #667eea; text-decoration: none;">
                    github.com/denphi/sim2l
                </a>
            </p>
        </div>
    </div>
</body>
</html>
"""
        self.sections.append(footer)

    def generate(self):
        """Generate and save the HTML report"""
        self.add_header()
        # Content sections are added via other methods
        self.add_footer()

        html_content = "\n".join(self.sections)

        with open(self.output_file, 'w') as f:
            f.write(html_content)

        return Path(self.output_file).absolute()
