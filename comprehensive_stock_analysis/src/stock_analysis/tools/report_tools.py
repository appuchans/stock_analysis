"""Tools for generating structured investment reports."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from crewai.tools import BaseTool

from ..config.settings import settings

_logger = logging.getLogger(__name__)

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Investment Report — {{ symbol }}</title>
<style>
  body { font-family: Arial, sans-serif; max-width: 960px; margin: 40px auto; color: #222; line-height: 1.6; }
  h1 { border-bottom: 2px solid #2c5282; padding-bottom: 8px; }
  h2 { color: #2c5282; margin-top: 32px; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { border: 1px solid #ccc; padding: 8px 12px; text-align: left; }
  th { background: #edf2f7; font-weight: 600; }
  tr:nth-child(even) { background: #f7fafc; }
  .badge { display: inline-block; padding: 3px 12px; border-radius: 12px; font-weight: bold; font-size: 0.95em; }
  .buy  { background: #c6f6d5; color: #276749; }
  .hold { background: #fefcbf; color: #744210; }
  .sell { background: #fed7d7; color: #822727; }
  .meta { color: #666; font-size: 0.875em; }
  .card { background: #f7fafc; border-left: 4px solid #4299e1; padding: 14px 18px; margin: 16px 0; border-radius: 0 4px 4px 0; }
  pre { background: #f1f5f9; padding: 16px; overflow: auto; font-size: 0.8em; border-radius: 4px; }
  hr { border: none; border-top: 1px solid #e2e8f0; margin: 32px 0; }
</style>
</head>
<body>

<h1>Investment Report: {{ symbol }}</h1>
<p class="meta">Generated {{ generated_at }} &nbsp;&bull;&nbsp; Analysis timeframe: {{ timeframe }}</p>

{% if recommendation %}
<div class="card">
  <h2 style="margin-top:0">Recommendation</h2>
  <p>
    <span class="badge {{ rec_class }}">{{ recommendation.get("recommendation", "N/A") }}</span>
    &nbsp;&nbsp;
    Target price: <strong>{{ recommendation.get("target_price", "—") }}</strong>
    &nbsp;&nbsp;
    Stop-loss: <strong>{{ recommendation.get("stop_loss", "—") }}</strong>
    &nbsp;&nbsp;
    Time horizon: <strong>{{ recommendation.get("time_horizon", "—") }}</strong>
  </p>
  {% if recommendation.get("reasoning") %}
  <p>{{ recommendation["reasoning"] }}</p>
  {% endif %}
  {% if recommendation.get("risks") %}
  <p><strong>Key risks:</strong> {{ recommendation["risks"] | join(", ") }}</p>
  {% endif %}
  {% if recommendation.get("opportunities") %}
  <p><strong>Opportunities:</strong> {{ recommendation["opportunities"] | join(", ") }}</p>
  {% endif %}
</div>
{% endif %}

{% if market_data %}
<h2>Market Data</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {% for k, v in market_data.items() %}
  <tr><td>{{ k | replace("_", " ") | title }}</td><td>{{ v }}</td></tr>
  {% endfor %}
</table>
{% endif %}

{% if technical %}
<h2>Technical Analysis</h2>
<div class="card">{{ technical }}</div>
{% endif %}

{% if fundamental %}
<h2>Fundamental Analysis</h2>
<div class="card">{{ fundamental }}</div>
{% endif %}

{% if risk %}
<h2>Risk Assessment</h2>
<div class="card">{{ risk }}</div>
{% endif %}

{% if sentiment %}
<h2>Sentiment Analysis</h2>
<div class="card">{{ sentiment }}</div>
{% endif %}

{% if economic %}
<h2>Economic Context</h2>
<div class="card">{{ economic }}</div>
{% endif %}

<h2>Full Analysis Data</h2>
<pre>{{ raw_json }}</pre>

<hr>
<p class="meta">
  This report is generated automatically and is for informational purposes only.
  It does not constitute financial advice.
</p>

</body>
</html>
"""


class ReportGeneratorTool(BaseTool):
    """Generates an HTML investment report from structured analysis data."""

    name: str = "Report Generator Tool"
    description: str = (
        "Generates a formatted HTML investment report from analysis results "
        "and saves it to the configured reports directory. "
        "Falls back to JSON when jinja2 is not installed."
    )

    def _run(
        self,
        symbol: str,
        analysis_data: Dict[str, Any],
        timeframe: str = "1y",
    ) -> Dict[str, Any]:
        try:
            return self._render_html(symbol, analysis_data, timeframe)
        except ImportError:
            _logger.warning("jinja2 not installed; falling back to JSON report")
            return self._render_json(symbol, analysis_data)
        except Exception as exc:
            return {"error": f"Report generation failed: {exc}"}

    def _render_html(
        self, symbol: str, analysis_data: Dict[str, Any], timeframe: str
    ) -> Dict[str, Any]:
        from jinja2 import Environment

        env = Environment(autoescape=True)
        template = env.from_string(_HTML_TEMPLATE)

        rec = analysis_data.get("recommendation") or {}
        rec_str = str(rec.get("recommendation", "")).upper()
        if "BUY" in rec_str:
            rec_class = "buy"
        elif "SELL" in rec_str:
            rec_class = "sell"
        else:
            rec_class = "hold"

        html = template.render(
            symbol=symbol.upper(),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            timeframe=timeframe,
            recommendation=rec or None,
            rec_class=rec_class,
            market_data=analysis_data.get("market_data"),
            technical=analysis_data.get("technical_summary"),
            fundamental=analysis_data.get("fundamental_summary"),
            risk=analysis_data.get("risk_summary"),
            sentiment=analysis_data.get("sentiment_summary"),
            economic=analysis_data.get("economic_summary"),
            raw_json=json.dumps(analysis_data, indent=2, default=str),
        )

        path = self._output_path(symbol, "html")
        path.write_text(html, encoding="utf-8")

        return {
            "status": "success",
            "symbol": symbol.upper(),
            "report_path": str(path),
            "format": "html",
        }

    def _render_json(self, symbol: str, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        path = self._output_path(symbol, "json")
        path.write_text(json.dumps(analysis_data, indent=2, default=str), encoding="utf-8")
        return {
            "status": "success",
            "symbol": symbol.upper(),
            "report_path": str(path),
            "format": "json",
        }

    def _output_path(self, symbol: str, ext: str) -> Path:
        output_dir = Path(settings.report_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return output_dir / f"{symbol.upper()}_{ts}_report.{ext}"
