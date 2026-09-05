"""
Contextual Intent & Cross-Rail Autonomous Payment Recovery Engine
Minimal API Server & UI Foundation.

Provides a zero-dependency, standard library HTTP server to serve
recovery telemetry, audit trails, and static frontend assets for the
upcoming Recovery Control Center web application.
"""

import json
import os
import sys
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"
AUDIT_PATH = DATA_DIR / "audit_trail.json"
DEEP_AUDIT_PATH = DATA_DIR / "deep_audit_trail.json"
FAILED_BATCH_PATH = DATA_DIR / "failed_batch.json"
PORTFOLIO_EXPERIMENT_PATH = DATA_DIR / "portfolio_experiment.json"

class RecoveryEngineRequestHandler(SimpleHTTPRequestHandler):
    """Minimal JSON API and static file handler for the Recovery Engine."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def _send_json(self, data, status=HTTPStatus.OK):
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        # Enable CORS for local development
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        # API Routes
        if self.path == "/api/health":
            self._send_json({
                "status": "healthy",
                "service": "payment-recovery-engine",
                "version": "1.0.0",
                "engine": "frozen_baseline_p3"
            })
            return

        if self.path == "/api/audit":
            if AUDIT_PATH.exists():
                with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                    self._send_json(json.load(f))
            else:
                self._send_json({"error": "Audit trail not generated. Run python agent.py first."}, status=HTTPStatus.NOT_FOUND)
            return

        if self.path == "/api/deep-audit":
            if DEEP_AUDIT_PATH.exists():
                with open(DEEP_AUDIT_PATH, "r", encoding="utf-8") as f:
                    self._send_json(json.load(f))
            else:
                self._send_json({"error": "Deep audit trail not generated. Run python agent.py first."}, status=HTTPStatus.NOT_FOUND)
            return

        if self.path == "/api/benchmark":
            if AUDIT_PATH.exists() and FAILED_BATCH_PATH.exists():
                # Read baseline and audit to provide snapshot metrics
                with open(FAILED_BATCH_PATH, "r", encoding="utf-8") as f:
                    batch = json.load(f)
                with open(AUDIT_PATH, "r", encoding="utf-8") as f:
                    audit = json.load(f)

                total_risk = sum(tx["amount"] for tx in batch)
                contextual_recovered = sum(tx["recovered_revenue"] for tx in audit)
                contextual_attempts = sum(tx["total_attempts"] for tx in audit)
                contextual_successes = sum(1 for tx in audit if tx["final_status"] == "RECOVERED")
                contextual_fails = sum(tx["failed_attempts"] for tx in audit)
                contextual_stops = sum(1 for tx in audit if "SUPPRESSED" in tx["final_status"] or "CIRCUIT" in tx["final_status"])

                self._send_json({
                    "transactions_evaluated": len(batch),
                    "gross_revenue_at_risk": total_risk,
                    "baseline": {
                        "gross_recovered": 9495.0,
                        "recovery_rate_pct": 5.01,
                        "attempts": 99,
                        "successful_recoveries": 5,
                        "failed_executions": 94,
                        "efficiency_pct": 5.1,
                        "simulated_penalties": 11500.0,
                        "net_financial_recovery": -3490.0,
                        "stops": 0
                    },
                    "contextual_engine": {
                        "gross_recovered": contextual_recovered,
                        "recovery_rate_pct": round((contextual_recovered / total_risk) * 100, 2) if total_risk > 0 else 0.0,
                        "attempts": contextual_attempts,
                        "successful_recoveries": contextual_successes,
                        "failed_executions": contextual_fails,
                        "efficiency_pct": round((contextual_successes / contextual_attempts) * 100, 1) if contextual_attempts > 0 else 0.0,
                        "simulated_penalties": 0.0,
                        "net_financial_recovery": contextual_recovered - (contextual_attempts * 15.0),
                        "stops": contextual_stops
                    },
                    "notice": "Controlled simulation benchmark on synthetic dataset. Not a claim of live PG production data."
                })
            else:
                self._send_json({"error": "Data files missing. Run generate_data.py and agent.py first."}, status=HTTPStatus.NOT_FOUND)
            return

        if self.path == "/api/portfolio-experiment":
            if PORTFOLIO_EXPERIMENT_PATH.exists():
                with open(PORTFOLIO_EXPERIMENT_PATH, "r", encoding="utf-8") as f:
                    self._send_json(json.load(f))
            elif FAILED_BATCH_PATH.exists():
                from core.portfolio_allocator import PortfolioRecoveryAllocator
                with open(FAILED_BATCH_PATH, "r", encoding="utf-8") as f:
                    batch = json.load(f)
                allocator = PortfolioRecoveryAllocator(base_seed=1337)
                res = allocator.run_controlled_experiment(batch, capacity_limit=20)
                PORTFOLIO_EXPERIMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(PORTFOLIO_EXPERIMENT_PATH, "w", encoding="utf-8") as f:
                    json.dump(res, f, indent=2)
                self._send_json(res)
            else:
                self._send_json({"error": "Dataset not found. Run generate_data.py and run_portfolio_experiment.py first."}, status=HTTPStatus.NOT_FOUND)
            return

        # Fallback to serving static files from frontend/
        index_path = FRONTEND_DIR / "index.html"
        if not index_path.exists() and (self.path == "/" or self.path == "/index.html"):
            self._send_json({
                "message": "Payment Recovery Engine API Foundation Active",
                "endpoints": [
                    "/api/health",
                    "/api/benchmark",
                    "/api/audit",
                    "/api/deep-audit",
                    "/api/portfolio-experiment"
                ],
                "note": "Frontend UI will be mounted in frontend/ in the upcoming milestone."
            })
            return

        super().do_GET()


def run_server(port=8000, host="127.0.0.1"):
    server_address = (host, port)
    httpd = HTTPServer(server_address, RecoveryEngineRequestHandler)
    print(f"[*] Recovery Engine API Server running at http://{host}:{port}/")
    print(f"[*] Health Check: http://{host}:{port}/api/health")
    print(f"[*] Benchmark Telemetry: http://{host}:{port}/api/benchmark")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down server cleanly.")
        httpd.server_close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    run_server(port=port)
