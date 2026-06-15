"""Tools for generating structured investment reports."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from crewai.tools import BaseTool

from ..config.settings import settings

_logger = logging.getLogger(__name__)

# Order and labels for the specialist markdown files — stock path
_MD_SECTIONS: List[Tuple[str, str]] = [
    ("technical_analysis",      "Technical Analysis"),
    ("fundamental_analysis",    "Fundamental Analysis"),
    ("ownership_analysis",      "Ownership & Capital Allocation"),
    ("risk_analysis",           "Risk Analysis"),
    ("sentiment_analysis",      "Sentiment Analysis"),
    ("market_analysis",         "Market Analysis"),
    ("industry_analysis",       "Industry Analysis"),
    ("competitor_analysis",     "Competitor Analysis"),
    ("economic_analysis",       "Economic Analysis"),
    ("investment_recommendation", "Investment Recommendation"),
]

# ETF path — technical_analysis omitted; three sections replaced by ETF variants
_ETF_MD_SECTIONS: List[Tuple[str, str]] = [
    ("etf_fundamental_analysis", "ETF Profile & Cost Analysis"),
    ("etf_holdings_analysis",    "Holdings & Sector Allocation"),
    ("etf_peer_analysis",        "Peer ETF Comparison"),
    ("risk_analysis",            "Risk Analysis"),
    ("sentiment_analysis",       "Sentiment Analysis"),
    ("market_analysis",          "Market Analysis"),
    ("economic_analysis",        "Economic Analysis"),
    ("investment_recommendation", "Investment Recommendation"),
]

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ symbol }} — Equity Research Report</title>
<style>
  :root {
    --ink: #1a202c; --ink-soft: #4a5568; --ink-faint: #718096;
    --brand: #1a365d; --accent: #2b6cb0; --line: #e2e8f0; --bg-soft: #f7fafc;
    --green: #276749; --green-bg: #c6f6d5; --amber: #744210; --amber-bg: #fefcbf;
    --red: #822727; --red-bg: #fed7d7;
  }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
         max-width: 1000px; margin: 0 auto; color: var(--ink); line-height: 1.65; padding: 0 24px 48px;
         font-size: 15.5px; -webkit-font-smoothing: antialiased; }
  .report-header { display: flex; align-items: center; gap: 18px; padding: 28px 0 18px;
                   border-bottom: 3px solid var(--brand); margin-bottom: 6px; }
  .logo { width: 56px; height: 56px; border-radius: 12px; background: var(--bg-soft);
          display: flex; align-items: center; justify-content: center; border: 1px solid var(--line);
          overflow: hidden; flex-shrink: 0; }
  .logo img { width: 40px; height: 40px; }
  .logo-fallback { font-size: 1.5em; font-weight: 700; color: var(--brand); }
  .title-block h1 { margin: 0; font-size: 1.65em; color: var(--brand); line-height: 1.2; }
  .title-block .subtitle { color: var(--ink-soft); font-size: 0.95em; margin-top: 2px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 4px; }
  .chip { background: var(--bg-soft); border: 1px solid var(--line); border-radius: 14px;
          padding: 3px 12px; font-size: 0.82em; color: var(--ink-soft); }
  h2 { color: var(--brand); margin-top: 40px; font-size: 1.25em;
       border-bottom: 1px solid var(--line); padding-bottom: 8px; }
  h3 { color: #2d3748; margin: 22px 0 8px; font-size: 1.05em; }
  h4 { color: var(--ink-soft); margin: 16px 0 6px; }
  table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 0.93em; }
  th, td { border: 1px solid var(--line); padding: 8px 12px; text-align: left; }
  th { background: var(--bg-soft); font-weight: 600; color: var(--ink-soft);
       text-transform: uppercase; font-size: 0.8em; letter-spacing: 0.4px; }
  tr:nth-child(even) td { background: #fbfdfe; }
  .badge { display: inline-block; padding: 6px 20px; border-radius: 20px; font-weight: 700;
           font-size: 1.05em; letter-spacing: 1.2px; }
  .buy  { background: var(--green-bg); color: var(--green); }
  .hold { background: var(--amber-bg); color: var(--amber); }
  .sell { background: var(--red-bg); color: var(--red); }
  .meta { color: var(--ink-faint); font-size: 0.85em; }
  .card { background: var(--bg-soft); border-left: 4px solid #4299e1; padding: 16px 20px;
          margin: 12px 0; border-radius: 0 8px 8px 0; }
  .rec-card { background: #ebf8ff; border: 1px solid #bee3f8; border-left: 5px solid var(--accent);
              padding: 22px 26px; margin: 24px 0; border-radius: 10px; }
  .exec-card { background: #f0fff4; border-left: 4px solid #38a169; padding: 16px 20px;
               margin: 12px 0; border-radius: 0 8px 8px 0; }
  .chart { background: #fff; border: 1px solid var(--line); border-radius: 10px;
           padding: 16px 12px 8px; margin: 14px 0; }
  .chart svg { width: 100%; height: auto; display: block; }
  .stat-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
               gap: 12px; margin: 16px 0; }
  .stat { background: var(--bg-soft); border: 1px solid var(--line); border-radius: 10px;
          padding: 12px 14px; }
  .stat .label { font-size: 0.74em; text-transform: uppercase; letter-spacing: 0.5px;
                 color: var(--ink-faint); margin-bottom: 2px; }
  .stat .value { font-size: 1.15em; font-weight: 650; color: var(--ink); }
  .detail-section { background: #fff; border: 1px solid var(--line); border-radius: 10px;
                    padding: 24px 28px; margin: 24px 0; }
  .detail-section h2 { margin-top: 0; border: none; }
  .toc { background: var(--bg-soft); border: 1px solid var(--line); border-radius: 10px;
         padding: 16px 24px; margin: 24px 0; }
  .toc ul { margin: 6px 0; columns: 2; }
  .toc a { color: var(--accent); text-decoration: none; }
  .toc a:hover { text-decoration: underline; }
  hr { border: none; border-top: 1px solid var(--line); margin: 36px 0; }
  ul { margin: 6px 0; padding-left: 24px; }
  li { margin: 4px 0; }
  .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media (max-width: 640px) { .two-col, .toc ul { grid-template-columns: 1fr; columns: 1; } }
  .md-content p { margin: 10px 0; }
  .md-content ul, .md-content ol { padding-left: 24px; }
  .md-content h1 { font-size: 1.3em; color: var(--brand); }
  .md-content h2 { font-size: 1.15em; color: var(--accent); border-bottom: 1px solid var(--line); }
  .md-content h3 { font-size: 1.02em; }
  .md-content code { background: #edf2f7; padding: 2px 5px; border-radius: 3px; font-size: 0.88em; }
  .md-content pre { background: #f1f5f9; padding: 14px; border-radius: 6px; overflow: auto; }
  .md-content blockquote { border-left: 3px solid #4299e1; margin: 10px 0; padding-left: 14px; color: #555; }
  details.detail-section summary { cursor: pointer; font-size: 1.05em; color: var(--brand);
    padding: 4px 0; list-style-position: outside; }
  details.detail-section summary:hover { color: var(--accent); }
  details.detail-section[open] summary { margin-bottom: 12px; border-bottom: 1px solid var(--line);
    padding-bottom: 10px; }
  .narrative > h2:first-child { margin-top: 12px; }
  /* Within the synthesized narrative, render any sub-headings the writer slips
     in as run-in (inline) lead-ins rather than block section breaks — this is
     what keeps the body reading as continuous prose, not a stack of sections. */
  .narrative h3, .narrative h4 {
    display: inline; font-size: 1em; color: var(--ink); font-weight: 700;
    border: none; margin: 0; padding: 0;
  }
  .narrative h3::after, .narrative h4::after { content: ". "; font-weight: 700; }
  .narrative h3 + p, .narrative h4 + p { display: inline; }
  @media print { .toc { display: none; } body { font-size: 12px; }
    details.detail-section { page-break-inside: avoid; } }
  html { scroll-behavior: smooth; }
  .to-top { position: fixed; right: 22px; bottom: 22px; width: 42px; height: 42px;
    border-radius: 50%; background: var(--brand); color: #fff; display: flex;
    align-items: center; justify-content: center; font-size: 20px; line-height: 1;
    text-decoration: none; box-shadow: 0 2px 10px rgba(16,24,40,.28); opacity: 0;
    pointer-events: none; transition: opacity .2s ease; z-index: 50; }
  .to-top.show { opacity: .92; pointer-events: auto; }
  .to-top:hover { opacity: 1; }
  @media print { .to-top { display: none; } }
</style>
</head>
<body>

<div class="report-header" id="top">
  <div class="logo">
    {% if logo_url %}<img src="{{ logo_url }}" alt="" onerror="this.parentElement.innerHTML='<span class=&quot;logo-fallback&quot;>{{ symbol[0] }}</span>'">
    {% else %}<span class="logo-fallback">{{ symbol[0] }}</span>{% endif %}
  </div>
  <div class="title-block">
    <h1>{{ company_name or symbol }} <span style="color:var(--ink-faint); font-weight:400">({{ symbol }})</span></h1>
    <div class="subtitle">{{ "ETF Research Report" if asset_type == "etf" else "Equity Research Report" }} &bull; Generated {{ generated_at }}</div>
  </div>
</div>
<div class="chips">
  {% if meta.get('exchange') %}<span class="chip">{{ meta['exchange'] }}</span>{% endif %}
  {% if meta.get('sector') %}<span class="chip">{{ meta['sector'] }}</span>{% endif %}
  {% if meta.get('industry') %}<span class="chip">{{ meta['industry'] }}</span>{% endif %}
  <span class="chip">Timeframe: {{ timeframe }}</span>
  <span class="chip">{{ "ETF" if asset_type == "etf" else "Stock" }}</span>
</div>

{% if key_stats %}
<div class="stat-grid" style="margin-top:18px">
  {% for label, value in key_stats %}
  <div class="stat"><div class="label">{{ label }}</div><div class="value">{{ value }}</div></div>
  {% endfor %}
</div>
{% endif %}

{% if catalysts %}
<div class="stat-grid" style="margin-top:4px">
  {% for label, value in catalysts %}
  <div class="stat" style="border-left:3px solid var(--accent)"><div class="label">📅 {{ label }}</div><div class="value" style="font-size:0.98em">{{ value }}</div></div>
  {% endfor %}
</div>
{% endif %}

{% if inv_rec %}
<div class="rec-card" id="recommendation">
  <h2 style="margin-top:0; border:none; color:var(--brand)">
    Recommendation:
    <span class="badge {{ rec_class }}">{{ rating }}</span>
  </h2>
  <div class="stat-grid">
    {% if inv_rec.get('target_price') %}<div class="stat"><div class="label">Target Price</div><div class="value">${{ inv_rec['target_price'] }}</div></div>{% endif %}
    {% if inv_rec.get('stop_loss') %}<div class="stat"><div class="label">Stop Loss</div><div class="value">${{ inv_rec['stop_loss'] }}</div></div>{% endif %}
    {% if inv_rec.get('time_horizon') %}<div class="stat"><div class="label">Time Horizon</div><div class="value">{{ inv_rec['time_horizon'] }}</div></div>{% endif %}
    {% if inv_rec.get('risk_level') %}<div class="stat"><div class="label">Risk Level</div><div class="value">{{ inv_rec['risk_level'] }}</div></div>{% endif %}
    {% if inv_rec.get('confidence') is not none %}<div class="stat"><div class="label">Confidence</div><div class="value">{{ "%.0f%%"|format(inv_rec['confidence']|float * 100) }}</div></div>{% endif %}
  </div>
  {% if inv_rec.get('rationale') %}
  <h3 style="margin-top:12px">Rationale</h3>
  <ul>{% for r in inv_rec['rationale'] %}<li>{{ r | md }}</li>{% endfor %}</ul>
  {% elif inv_rec.get('reasoning') %}
  <div>{{ inv_rec['reasoning'] | md }}</div>
  {% endif %}
  <div class="two-col">
    {% if inv_rec.get('upside_drivers') or inv_rec.get('opportunities') %}
    <div>
      <h3>Upside Drivers</h3>
      <ul>{% for d in (inv_rec.get('upside_drivers') or inv_rec.get('opportunities') or []) %}<li>{{ d }}</li>{% endfor %}</ul>
    </div>
    {% endif %}
    {% if inv_rec.get('downside_risks') or inv_rec.get('risks') %}
    <div>
      <h3>Downside Risks</h3>
      <ul>{% for r in (inv_rec.get('downside_risks') or inv_rec.get('risks') or []) %}<li>{{ r }}</li>{% endfor %}</ul>
    </div>
    {% endif %}
  </div>
</div>
{% endif %}

<div class="toc">
  <strong>Contents</strong>
  <ul>
    {% if inv_rec %}<li><a href="#recommendation">Recommendation</a></li>{% endif %}
    {% if exec_sum and not narrative_html %}<li><a href="#executive-summary">Executive Summary</a></li>{% endif %}
    {% for sec in narrative_sections %}
    <li><a href="#{{ sec.anchor }}">{{ sec.title }}</a></li>
    {% endfor %}
    {% if standalone.get('consensus') %}<li><a href="#analyst-consensus">Analyst Consensus</a></li>{% endif %}
    {% if standalone.get('peers') %}<li><a href="#peer-comparison">Peer Comparison</a></li>{% endif %}
    {% if standalone.get('valuation') %}<li><a href="#valuation-scenarios">Valuation Scenarios</a></li>{% endif %}
    {% if standalone.get('price') %}<li><a href="#price-chart">Price History</a></li>{% endif %}
    {% if market_snap %}<li><a href="#market-snapshot">Market Snapshot</a></li>{% endif %}
    {% if asset_type == "etf" %}
    {% if etf_profile %}<li><a href="#etf-profile">ETF Profile &amp; Cost</a></li>{% endif %}
    {% if sector_chart_svg %}<li><a href="#sector-allocation">Sector Allocation</a></li>{% endif %}
    {% else %}
    {% if technical %}<li><a href="#technical-analysis">Technical Analysis</a></li>{% endif %}
    {% if fundamental %}<li><a href="#fundamental-analysis">Fundamental Analysis</a></li>{% endif %}
    {% endif %}
    {% if risk %}<li><a href="#risk-assessment">Risk Assessment</a></li>{% endif %}
    {% if sentiment %}<li><a href="#sentiment-analysis">Sentiment Analysis</a></li>{% endif %}
    {% if market_ctx %}<li><a href="#market-context">Market &amp; Economic Context</a></li>{% endif %}
    {% if asset_type != "etf" %}
    {% if industry %}<li><a href="#industry-analysis">Industry Analysis</a></li>{% endif %}
    {% if competitive %}<li><a href="#competitive-analysis">Competitive Analysis</a></li>{% endif %}
    {% endif %}
    {% for slug, title, _ in detail_sections %}
    <li><a href="#detail-{{ slug }}">Appendix {{ loop.index }}: {{ title }}</a></li>
    {% endfor %}
    {% if consolidated_gaps %}<li><a href="#data-sources-gaps">Appendix: Data Sources &amp; Gaps</a></li>{% endif %}
  </ul>
</div>

{% if exec_sum and not narrative_html %}
<h2 id="executive-summary">Executive Summary</h2>
{% if exec_sum.get('headline') %}
<div class="exec-card"><strong>{{ exec_sum['headline'] | md }}</strong></div>
{% endif %}
{% if exec_sum.get('investment_thesis') %}
<div class="exec-card">{{ exec_sum['investment_thesis'] | md }}</div>
{% endif %}
{% if exec_sum.get('key_findings') %}
<h3>Key Findings</h3>
<ul>{% for f in exec_sum['key_findings'] %}<li>{{ f | md }}</li>{% endfor %}</ul>
{% endif %}
{% endif %}

{# Visuals whose narrative section is absent render as front matter #}
{% if standalone.get('price') %}
<h2>Price History</h2>
{{ standalone['price'] }}
{% endif %}
{% if standalone.get('range52w') %}{{ standalone['range52w'] }}{% endif %}
{% if standalone.get('consensus') %}
<h2>Analyst Consensus &amp; Positioning</h2>
{{ standalone['consensus'] }}
{% endif %}
{% if standalone.get('peers') %}
<h2>Competitive Standing</h2>
{{ standalone['peers'] }}
{% endif %}
{% if standalone.get('valuation') %}
<h2>Valuation</h2>
{{ standalone['valuation'] }}
{% endif %}
{% if standalone.get('revenue') %}
<h2>Revenue Trend</h2>
{{ standalone['revenue'] }}
{% endif %}

{% if narrative_sections %}
<div id="analysis">
{% for sec in narrative_sections %}
<h2 id="{{ sec.anchor }}">{{ sec.title }}</h2>
<div class="md-content narrative">{{ sec.html | safe }}</div>
{% for visual in sec.visuals %}{{ visual }}{% endfor %}
{% endfor %}
</div>
{% elif narrative_html %}
<h2 id="analysis">Analysis</h2>
<div class="md-content narrative">{{ narrative_html }}</div>
{% endif %}

{% if market_snap %}
<h2 id="market-snapshot">Market Snapshot</h2>
<div class="stat-grid">
  {% for k, v in market_snap.items() %}
  <div class="stat"><div class="label">{{ k | replace('_', ' ') | title }}</div><div class="value">{{ v }}</div></div>
  {% endfor %}
</div>
{% endif %}

{% if asset_type == "etf" %}

{% if etf_profile %}
<h2 id="etf-profile">ETF Profile &amp; Cost Analysis</h2>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {% if etf_profile.get('fund_family') %}<tr><td>Fund Family</td><td>{{ etf_profile['fund_family'] }}</td></tr>{% endif %}
  {% if etf_profile.get('category') %}<tr><td>Category</td><td>{{ etf_profile['category'] }}</td></tr>{% endif %}
  {% if etf_profile.get('total_assets_bn') is not none %}<tr><td>AUM (bn)</td><td>${{ etf_profile['total_assets_bn'] }}B</td></tr>{% endif %}
  {% if etf_profile.get('expense_ratio') is not none %}<tr><td>Expense Ratio</td><td>{{ "%.2f%%"|format(etf_profile['expense_ratio'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('distribution_yield') is not none %}<tr><td>Distribution Yield</td><td>{{ "%.2f%%"|format(etf_profile['distribution_yield'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('ytd_return') is not none %}<tr><td>YTD Return</td><td>{{ "%.2f%%"|format(etf_profile['ytd_return'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('three_year_return') is not none %}<tr><td>3Y Return (ann.)</td><td>{{ "%.2f%%"|format(etf_profile['three_year_return'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('five_year_return') is not none %}<tr><td>5Y Return (ann.)</td><td>{{ "%.2f%%"|format(etf_profile['five_year_return'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('turnover_ratio') is not none %}<tr><td>Turnover Ratio</td><td>{{ "%.0f%%"|format(etf_profile['turnover_ratio'] * 100) }}</td></tr>{% endif %}
  {% if etf_profile.get('index_tracked') %}<tr><td>Index / Benchmark</td><td>{{ etf_profile['index_tracked'] }}</td></tr>{% endif %}
</table>
{% if etf_profile.get('top_holdings') %}
<h3>Top Holdings</h3>
<table>
  <tr><th>Symbol</th><th>Name</th><th>Weight</th></tr>
  {% for h in etf_profile['top_holdings'] %}
  <tr>
    <td>{{ h.get('Symbol') or h.get('symbol') or '—' }}</td>
    <td>{{ h.get('Name') or h.get('name') or '—' }}</td>
    <td>{{ h.get('% of Net Assets') or h.get('Holding Percent') or h.get('weight_pct') or '—' }}</td>
  </tr>
  {% endfor %}
</table>
{% endif %}
{% endif %}

{% if sector_chart_svg %}
<h2 id="sector-allocation">Sector Allocation</h2>
<div class="chart">{{ sector_chart_svg }}</div>
{% endif %}

{% else %}


{% if technical %}
<h2 id="technical-analysis">Technical Analysis — Summary</h2>
{% if technical.get('summary') %}<div class="card">{{ technical['summary'] | md }}</div>{% endif %}
{% if technical.get('key_observations') %}
<h3>Key Observations</h3>
<ul>{% for o in technical['key_observations'] %}<li>{{ o | md }}</li>{% endfor %}</ul>
{% endif %}
{% if technical.get('support_levels') or technical.get('resistance_levels') %}
<div class="two-col">
  {% if technical.get('support_levels') %}
  <div>
    <h3>Support Levels</h3>
    <ul>{% for s in technical['support_levels'] %}<li>${{ s }}</li>{% endfor %}</ul>
  </div>
  {% endif %}
  {% if technical.get('resistance_levels') %}
  <div>
    <h3>Resistance Levels</h3>
    <ul>{% for r in technical['resistance_levels'] %}<li>{{ r }}</li>{% endfor %}</ul>
  </div>
  {% endif %}
</div>
{% endif %}
{% if technical.get('technical_bias') %}<p><strong>Technical Bias:</strong> {{ technical['technical_bias'] }}</p>{% endif %}
{% endif %}

{% if fundamental %}
<h2 id="fundamental-analysis">Fundamental Analysis — Summary</h2>
{% if fundamental.get('summary') %}<div class="card">{{ fundamental['summary'] | md }}</div>{% endif %}
{% if fundamental.get('key_metrics') %}
<h3>Key Metrics</h3>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  {% for k, v in fundamental['key_metrics'].items() %}
  <tr><td>{{ k | replace('_', ' ') | title }}</td><td>{{ v }}</td></tr>
  {% endfor %}
</table>
{% endif %}
{% if fundamental.get('interpretation') %}
<h3>Interpretation</h3>
<ul>{% for i in fundamental['interpretation'] %}<li>{{ i | md }}</li>{% endfor %}</ul>
{% endif %}
{% if fundamental.get('valuation_view') %}<p><strong>Valuation View:</strong> {{ fundamental['valuation_view'] }}</p>{% endif %}
{% if fundamental.get('investment_quality_score') is not none %}<p><strong>Investment Quality Score:</strong> {{ fundamental['investment_quality_score'] }}/100</p>{% endif %}
{% endif %}

{% endif %}

{% if risk %}
<h2 id="risk-assessment">Risk Assessment — Summary</h2>
{% if risk.get('summary') %}<div class="card">{{ risk['summary'] | md }}</div>{% endif %}
{% if risk.get('overall_risk_score') is not none %}<p><strong>Overall Risk Score:</strong> {{ risk['overall_risk_score'] }}/100</p>{% endif %}
{% if risk.get('risk_categories') %}
<table>
  <tr><th>Risk Category</th><th>Score</th><th>Level</th></tr>
  {% for cat, info in risk['risk_categories'].items() %}
  <tr>
    <td>{{ cat | replace('_', ' ') | title }}</td>
    <td>{{ info.get('score', '—') }}</td>
    <td>{{ info.get('level', '—') }}</td>
  </tr>
  {% endfor %}
</table>
{% endif %}
{% if risk.get('key_risks') %}
<h3>Key Risks</h3>
<ul>{% for r in risk['key_risks'] %}<li>{{ r | md }}</li>{% endfor %}</ul>
{% endif %}
{% if risk.get('mitigation_strategies') %}
<h3>Mitigation Strategies</h3>
<ul>{% for m in risk['mitigation_strategies'] %}<li>{{ m | md }}</li>{% endfor %}</ul>
{% endif %}
{% endif %}

{% if sentiment %}
<h2 id="sentiment-analysis">Sentiment Analysis — Summary</h2>
{% if sentiment.get('summary') %}<div class="card">{{ sentiment['summary'] | md }}</div>{% endif %}
{% if sentiment.get('overall_sentiment') %}<p><strong>Overall Sentiment:</strong> {{ sentiment['overall_sentiment'] }}</p>{% endif %}
{% if sentiment.get('analyst_sentiment') %}<p><strong>Analyst Sentiment:</strong> {{ sentiment['analyst_sentiment'] }}</p>{% endif %}
{% if sentiment.get('market_sentiment') %}<p><strong>Market Sentiment:</strong> {{ sentiment['market_sentiment'] }}</p>{% endif %}
{% endif %}

{% if market_ctx %}
<h2 id="market-context">Market &amp; Economic Context — Summary</h2>
{% if market_ctx.get('summary') %}<div class="card">{{ market_ctx['summary'] | md }}</div>{% endif %}
{% if market_ctx.get('macro_metrics') %}
<table>
  <tr><th>Indicator</th><th>Value</th></tr>
  {% for k, v in market_ctx['macro_metrics'].items() %}
  <tr><td>{{ k | replace('_', ' ') | title }}</td><td>{{ v }}</td></tr>
  {% endfor %}
</table>
{% endif %}
{% if market_ctx.get('interpretation') %}
<ul>{% for i in market_ctx['interpretation'] %}<li>{{ i }}</li>{% endfor %}</ul>
{% endif %}
{% endif %}

{% if asset_type != "etf" %}

{% if industry %}
<h2 id="industry-analysis">Industry Analysis — Summary</h2>
{% if industry.get('summary') %}<div class="card">{{ industry['summary'] | md }}</div>{% endif %}
{% if industry.get('industry_trends') %}
<h3>Industry Trends</h3>
<ul>{% for t in industry['industry_trends'] %}<li>{{ t | md }}</li>{% endfor %}</ul>
{% endif %}
{% if industry.get('growth_prospects') %}
<h3>Growth Prospects</h3>
<ul>{% for g in industry['growth_prospects'] %}<li>{{ g | md }}</li>{% endfor %}</ul>
{% endif %}
{% if industry.get('industry_positioning') %}<p><strong>Positioning:</strong> {{ industry['industry_positioning'] }}</p>{% endif %}
{% endif %}

{% if competitive %}
<h2 id="competitive-analysis">Competitive Analysis — Summary</h2>
{% if competitive.get('summary') %}<div class="card">{{ competitive['summary'] | md }}</div>{% endif %}
{% if competitive.get('peer_set') %}<p><strong>Key Peers:</strong> {{ competitive['peer_set'] | join(', ') }}</p>{% endif %}
<div class="two-col">
  {% if competitive.get('competitive_advantages') %}
  <div>
    <h3>Competitive Advantages</h3>
    <ul>{% for a in competitive['competitive_advantages'] %}<li>{{ a | md }}</li>{% endfor %}</ul>
  </div>
  {% endif %}
  {% if competitive.get('competitive_disadvantages') %}
  <div>
    <h3>Competitive Disadvantages</h3>
    <ul>{% for d in competitive['competitive_disadvantages'] %}<li>{{ d | md }}</li>{% endfor %}</ul>
  </div>
  {% endif %}
</div>
{% endif %}

{% endif %}

{% if detail_sections %}
<hr>
<h2 style="border:none; font-size:1.35em">Appendices — Specialist Workpapers</h2>
<p class="meta">Full underlying analyses. Click a section to expand.</p>
{% for slug, title, html_content in detail_sections %}
<details class="detail-section" id="detail-{{ slug }}">
  <summary><strong>Appendix {{ loop.index }}: {{ title }}</strong></summary>
  <div class="md-content">{{ html_content }}</div>
</details>
{% endfor %}
{% endif %}

{% if consolidated_gaps %}
<details class="detail-section" id="data-sources-gaps">
  <summary><strong>Appendix: Data Sources &amp; Gaps</strong></summary>
  {% for title, gaps_html in consolidated_gaps %}
  <h3>{{ title }}</h3>
  <div class="md-content">{{ gaps_html }}</div>
  {% endfor %}
</details>
{% endif %}

<script>
  window.addEventListener("beforeprint", function () {
    document.querySelectorAll("details").forEach(function (d) { d.setAttribute("open", ""); });
  });
</script>

<hr>
<p class="meta">
  Generated {{ generated_at }} from free public data sources (Yahoo Finance, SEC EDGAR, FRED,
  Stocktwits, Google News). This report is generated automatically and is for informational
  purposes only. It does not constitute financial advice.
</p>

<a href="#top" class="to-top" id="to-top" aria-label="Back to top" title="Back to top">&uarr;</a>
<script>
  (function () {
    var btn = document.getElementById('to-top');
    if (!btn) return;
    var scroller = document.scrollingElement || document.documentElement;
    function onScroll() {
      var y = scroller.scrollTop || window.pageYOffset || 0;
      btn.classList.toggle('show', y > 400);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    // Scroll via JS so it works every time — an href="#top" only scrolls when
    // the hash actually changes (a second click would otherwise do nothing).
    // Force instant scroll-behavior for the jump so it lands reliably even where
    // smooth-scrolling is unsupported; restore the CSS smooth afterwards (which
    // still applies to the table-of-contents anchor links).
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var prev = scroller.style.scrollBehavior;
      scroller.style.scrollBehavior = 'auto';
      scroller.scrollTop = 0;
      window.scrollTo(0, 0);  // belt-and-suspenders for body-scrolling layouts
      scroller.style.scrollBehavior = prev;
    });
    onScroll();
  })();
</script>

</body>
</html>
"""


def _md_to_html(text: str) -> str:
    """Convert markdown to HTML."""
    try:
        import markdown
        return markdown.markdown(
            text,
            extensions=[
                "tables",
                "fenced_code",
                "nl2br",
                "sane_lists",
                "attr_list",
                "pymdownx.superfences",
            ],
        )
    except ImportError:
        pass
    # Pure-Python fallback — handles the most common markdown patterns so the
    # report is still readable when the markdown library isn't installed.
    import html as _html
    import re

    text = _html.escape(text)

    # Headings
    for level in (4, 3, 2, 1):
        hashes = "#" * level
        text = re.sub(
            rf"^{re.escape(hashes)}\s+(.+)$",
            rf"<h{level}>\1</h{level}>",
            text,
            flags=re.MULTILINE,
        )

    # Bold / italic
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)

    # Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Bullet lists (- or *)
    def _list_block(m: re.Match) -> str:
        items = re.sub(r"^[*\-]\s+(.+)$", r"<li>\1</li>", m.group(0), flags=re.MULTILINE)
        return f"<ul>{items}</ul>"

    text = re.sub(r"(?:^[*\-] .+\n?)+", _list_block, text, flags=re.MULTILINE)

    # Simple tables: | col | col |
    def _table_block(m: re.Match) -> str:
        rows = [r.strip() for r in m.group(0).strip().splitlines() if r.strip()]
        out = ["<table>"]
        for i, row in enumerate(rows):
            if re.match(r"^\|[-| :]+\|$", row):
                continue  # separator row
            cells = [c.strip() for c in row.strip("|").split("|")]
            tag = "th" if i == 0 else "td"
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
        out.append("</table>")
        return "\n".join(out)

    text = re.sub(r"(?:^\|.+\|\n?)+", _table_block, text, flags=re.MULTILINE)

    # Paragraphs (double newline → <p>)
    paragraphs = text.split("\n\n")
    parts = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith(("<h", "<ul", "<table", "<pre")):
            parts.append(p)
        else:
            parts.append(f"<p>{p.replace(chr(10), ' ')}</p>")
    return "\n".join(parts)


def _strip_leading_title(md_text: str) -> str:
    """Drop a leading markdown title — the template already renders the section header."""
    stripped = md_text.lstrip()
    if stripped.startswith("#"):
        first_break = stripped.find("\n")
        if first_break > 0:
            return stripped[first_break + 1:].lstrip()
    return md_text


def _split_gaps(md_text: str) -> Tuple[str, str]:
    """Excise a 'Data Sources & Gaps' section; return (cleaned_md, gaps_md).

    Per-section gap footers are consolidated into one appendix so the report
    doesn't repeat the same boilerplate after every section.
    """
    import re

    m = re.search(
        r"^(#{1,4})\s*Data Sources?\s*(?:&(?:amp;)?|and)\s*Gaps[^\n]*$",
        md_text, re.IGNORECASE | re.MULTILINE,
    )
    if not m:
        return md_text, ""
    level = len(m.group(1))
    nxt = re.search(rf"^#{{1,{level}}}\s", md_text[m.end():], re.MULTILINE)
    end = m.end() + nxt.start() if nxt else len(md_text)
    gaps = md_text[m.end():end].strip()
    cleaned = (md_text[:m.start()] + md_text[end:]).strip()
    return cleaned, gaps


def _load_narrative(symbol: str) -> str:
    """Load the synthesized comprehensive narrative markdown, if present."""
    path = (
        Path(settings.report_output_dir) / symbol.upper()
        / f"{symbol.upper()}_comprehensive_report.md"
    )
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    # Strip only a duplicate H1 title line — the narrative's own '## ' section
    # headings (starting with '## Investment Thesis') must survive
    stripped = text.lstrip()
    if stripped.startswith("# ") and not stripped.startswith("## "):
        first_break = stripped.find("\n")
        if first_break > 0:
            text = stripped[first_break + 1:]
    text, _ = _split_gaps(text)
    # A valid narrative has the mandated '## ' sections; a status summary or
    # fragment must not be embedded as the report body.
    if text.count("## ") < 3:
        _logger.warning("Narrative file %s looks malformed; skipping body embed", path.name)
        return ""
    return text


def _build_narrative_sections(
    narrative_md: str, visual_groups: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], set]:
    """Split the narrative into its '## ' sections and attach each visual group
    to the section that discusses it — charts appear inside the argument, not
    stacked in front of it.

    visual_groups maps a section keyword → Markup block. Returns the section
    list and the set of consumed group keys (unmatched groups render in their
    standalone fallback positions).
    """
    import re

    matches = list(re.finditer(r"^##\s+(.+)$", narrative_md, re.MULTILINE))
    if not matches:
        return [], set()

    # keywords → which visual group belongs in that section (first match wins;
    # synonyms cover narratives that don't follow the canonical headings)
    section_map = [
        (("thesis", "bottom line", "summary"), "price"),
        (("business", "overview", "selling", "what "), "peers"),
        (("financial", "income statement", "revenue", "margin"), "revenue"),
        (("sentiment", "positioning"), "consensus"),
        (("valuation", "recommendation"), "valuation"),
        (("timing", "technical"), "range52w"),
    ]
    sections: List[Dict[str, Any]] = []
    consumed: set = set()
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(narrative_md)
        body_md = narrative_md[m.end():body_end].strip()
        visuals = []
        lowered = title.lower()
        # Appendix-style sections never receive visuals
        if not lowered.startswith("appendix"):
            for keywords, group in section_map:
                if (any(k in lowered for k in keywords)
                        and group in visual_groups and group not in consumed):
                    visuals.append(visual_groups[group])
                    consumed.add(group)
        sections.append({
            "anchor": "sec-" + re.sub(r"[^a-z0-9]+", "-", lowered).strip("-"),
            "title": title,
            "html": _md_to_html(body_md),
            "visuals": visuals,
        })
    return sections, consumed


def _peers_table_html(peers: List[Dict[str, Any]]) -> str:
    """Peer comparison table (subject row highlighted)."""
    if not peers:
        return ""
    rows = []
    for p in peers:
        style = ' style="font-weight:700; background:#ebf8ff"' if p.get("is_subject") else ""
        def cell(v, suffix=""):
            return f"{v}{suffix}" if v is not None else "—"
        rows.append(
            f"<tr{style}><td>{p.get('symbol', '')} — {p.get('name', '')}</td>"
            f"<td>{cell(p.get('market_cap_b'))}</td>"
            f"<td>{cell(p.get('pe_ttm'))}</td>"
            f"<td>{cell(p.get('fwd_pe'))}</td>"
            f"<td>{cell(p.get('revenue_growth_pct'), '%')}</td>"
            f"<td>{cell(p.get('operating_margin_pct'), '%')}</td></tr>"
        )
    return (
        '<div id="peer-comparison"><h3>Peer Comparison</h3><table>'
        "<tr><th>Company</th><th>Mkt Cap ($B)</th><th>P/E (TTM)</th><th>Fwd P/E</th>"
        "<th>Rev Growth</th><th>Op Margin</th></tr>"
        + "".join(rows)
        + '</table><p class="meta">Peers from Yahoo Finance similarity data; '
        "metrics as of report generation.</p></div>"
    )


def _scenarios_table_html(scenarios: List[Dict[str, Any]]) -> str:
    """Bear/base/bull DCF grid with disclosed assumptions."""
    if not scenarios:
        return ""
    rows = []
    for sc in scenarios:
        upside = (
            f"{sc['upside_pct']:+.1f}%" if sc.get("upside_pct") is not None else "—"
        )
        rows.append(
            f"<tr><td><strong>{sc['scenario']}</strong></td>"
            f"<td>{sc['growth_pct']}%</td><td>{sc['discount_pct']}%</td>"
            f"<td>{sc['terminal_pct']}%</td>"
            f"<td>${sc['intrinsic_per_share']}</td><td>{upside}</td></tr>"
        )
    return (
        '<div id="valuation-scenarios"><h3>Valuation Scenarios</h3><table>'
        "<tr><th>Scenario</th><th>EPS Growth (3y)</th><th>Discount Rate</th>"
        "<th>Terminal Growth</th><th>Intrinsic Value / Share</th><th>vs Current Price</th></tr>"
        + "".join(rows)
        + '</table><p class="meta">Two-stage DCF on consensus current-year EPS: '
        "3 years at scenario growth, 2 years fading to terminal, Gordon terminal "
        "value. Illustrative — sensitive to assumptions shown.</p></div>"
    )


def _load_chart_data(symbol: str) -> Dict[str, Any]:
    """Load chart data written during collection, or build it live as fallback.

    The live fallback is fully guarded — when offline (or in tests) it simply
    returns {} and the report renders without charts.
    """
    sym = symbol.upper()
    path = Path(settings.report_output_dir) / sym / f"{sym}_chart_data.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            _logger.warning("Could not read chart data %s: %s", path, exc)

    try:
        import yfinance as yf

        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1y", interval="1wk")
        chart: Dict[str, Any] = {}
        info = {}
        try:
            info = ticker.info or {}
        except Exception:
            pass
        chart["company"] = {
            "name": info.get("longName"),
            "website": info.get("website"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "exchange": info.get("exchange"),
        }
        if hist is not None and not hist.empty:
            chart["price_history"] = [
                {"date": idx.date().isoformat(), "close": round(float(row["Close"]), 2)}
                for idx, row in hist.iterrows()
                if row["Close"] == row["Close"]
            ]
        try:
            qis = ticker.quarterly_income_stmt
            if qis is not None and not qis.empty and "Total Revenue" in qis.index:
                rev = qis.loc["Total Revenue"]
                chart["quarterly_revenue_m"] = {
                    (c.date().isoformat() if hasattr(c, "date") else str(c)[:10]):
                        round(float(v) / 1e6, 1)
                    for c, v in sorted(rev.items())
                    if v == v and v is not None
                }
        except Exception:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(chart, indent=2), encoding="utf-8")
        return chart
    except Exception as exc:
        _logger.debug("Live chart-data fallback failed for %s: %s", sym, exc)
        return {}


def _logo_url(company: Dict[str, Any]) -> str:
    """Keyless company logo via Google's favicon service from the company domain."""
    website = (company or {}).get("website") or ""
    if not website:
        return ""
    domain = website.split("//")[-1].split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    if not domain or "." not in domain:
        return ""
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=64"


def render_html_report(
    symbol: str, asset_type: str = "stock", timeframe: str = "1y"
) -> Dict[str, Any]:
    """Render the HTML report directly from the specialist files already on disk.

    Deterministic, LLM-free entry point used by the crews after a run completes,
    so a report is always produced even when the report-generator agent did not
    invoke the tool itself. The tool pulls the recommendation and all specialist
    sections from reports/{SYMBOL}/, so empty analysis_data is sufficient.
    """
    return ReportGeneratorTool()._run(
        symbol=symbol, analysis_data="{}", timeframe=timeframe, asset_type=asset_type
    )


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
        analysis_data: str,
        timeframe: str = "1y",
        asset_type: str = "stock",
    ) -> Dict[str, Any]:
        """Generate a report. analysis_data is a JSON object of analysis results."""
        if isinstance(analysis_data, dict):
            data: Dict[str, Any] = analysis_data
        else:
            v = (analysis_data or "").strip()
            try:
                data = json.loads(v) if v and v != "null" else {}
            except Exception:
                data = {}
        # Auto-detect ETF by checking for ETF-specific output files when not specified
        if asset_type == "stock":
            etf_check = Path(settings.report_output_dir) / symbol.upper() / f"{symbol.upper()}_etf_fundamental_analysis.md"
            if etf_check.exists():
                asset_type = "etf"
        try:
            return self._render_html(symbol, data, timeframe, asset_type)
        except ImportError:
            _logger.warning("jinja2 not installed; falling back to JSON report")
            return self._render_json(symbol, data)
        except Exception as exc:
            return {"error": f"Report generation failed: {exc}"}

    def _extract_rec_from_md(self, symbol: str) -> Dict[str, Any]:
        """Extract investment recommendation — tries JSON file first, then markdown fallback."""
        import re

        report_dir = Path(settings.report_output_dir) / symbol.upper()

        # ── Primary: structured JSON written by output_pydantic ──────────────────
        json_path = report_dir / f"{symbol.upper()}_investment_recommendation.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                # Normalise field names to what the template expects
                rec = data.get("recommendation", data.get("rating", ""))
                return {
                    "rating": str(rec).upper(),
                    "recommendation": rec,
                    "target_price": data.get("target_price"),
                    "stop_loss": data.get("stop_loss"),
                    "time_horizon": data.get("time_horizon"),
                    "risk_level": data.get("risk_level"),
                    "confidence": data.get("confidence"),
                    "reasoning": data.get("reasoning", ""),
                    "key_factors": data.get("key_factors", []),
                    "risks": data.get("risks", []),
                    "opportunities": data.get("opportunities", []),
                }
            except Exception:
                pass

        # ── Fallback: parse markdown file ─────────────────────────────────────────
        md_path = report_dir / f"{symbol.upper()}_investment_recommendation.md"
        if not md_path.exists():
            return {}
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception:
            return {}

        # Prefer the rating stated on a "Recommendation:" line — a whole-text scan
        # can latch onto incidental words (e.g. "HOLD (with a Buy-on-confirmation
        # plan)" must read as HOLD, not BUY).
        rating = ""
        m = re.search(
            r"recommendation[^A-Za-z]*((?:STRONG\s+)?(?:BUY|SELL)|HOLD)\b",
            text,
            re.IGNORECASE,
        )
        if m:
            rating = re.sub(r"\s+", " ", m.group(1)).upper()
        else:
            for candidate in ("STRONG BUY", "STRONG SELL", "BUY", "SELL", "HOLD"):
                if re.search(rf"\b{re.escape(candidate)}\b", text, re.IGNORECASE):
                    rating = candidate
                    break

        target_price = None
        m = re.search(r"[Tt]arget\s+[Pp]rice[:\s]+\$?([\d,]+(?:\.\d+)?)", text)
        if m:
            target_price = m.group(1)

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        reasoning = paragraphs[0] if paragraphs else text[:400].strip()

        result: Dict[str, Any] = {"rating": rating or "N/A", "reasoning": reasoning}
        if target_price:
            result["target_price"] = target_price
        return result

    # ── executive-summary helpers ─────────────────────────────────────────────

    @staticmethod
    def _extract_bullets(text: str, max_bullets: int = 6) -> List[str]:
        """Pull the first `max_bullets` substantive bullet-point lines from markdown text."""
        bullets: List[str] = []
        # Metadata lines to skip (bold key: value patterns at the top of files)
        _SKIP_PREFIXES = ("**as of", "**instrument", "**current price", "**52-week",
                          "**data timestamp", "**exchange", "**source")
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped.startswith(("- ", "* ")):
                continue
            content = stripped[2:].strip()
            if len(content) < 15:
                continue
            if any(content.lower().startswith(p) for p in _SKIP_PREFIXES):
                continue
            bullets.append(content)
            if len(bullets) >= max_bullets:
                break
        return bullets

    @staticmethod
    def _first_paragraph(text: str, max_chars: int = 350) -> str:
        """Return the first non-header, non-blank paragraph of a markdown file."""
        for block in text.split("\n\n"):
            block = block.strip()
            if not block or block.startswith("#") or block.startswith("---"):
                continue
            # Skip pure-metadata blocks (all lines are **Key:** Value)
            lines = block.splitlines()
            if all(l.strip().startswith("**") for l in lines if l.strip()):
                continue
            return block[:max_chars] + ("…" if len(block) > max_chars else "")
        return ""

    def _build_exec_summary(
        self, symbol: str, inv_rec: Dict[str, Any], asset_type: str = "stock"
    ) -> Dict[str, Any]:
        """Build an executive summary from the specialist analysis files.

        Key findings are drawn from the analyst reports (fundamental, risk, sentiment)
        — NOT from the investment recommendation, which has its own dedicated section
        and would otherwise just repeat itself here.
        """
        report_dir = Path(settings.report_output_dir) / symbol.upper()
        key_findings: List[str] = []

        # Pull one leading insight from each specialist report.
        # Order: fundamental → risk → sentiment (most important first).
        section_slugs = (
            [
                ("fundamental_analysis", "Business & Fundamentals"),
                ("risk_analysis",        "Risk"),
                ("sentiment_analysis",   "Market Sentiment"),
                ("market_analysis",      "Market Context"),
                ("industry_analysis",    "Industry"),
            ]
            if asset_type != "etf"
            else [
                ("etf_fundamental_analysis", "ETF Profile"),
                ("risk_analysis",            "Risk"),
                ("sentiment_analysis",       "Market Sentiment"),
            ]
        )

        for slug, label in section_slugs:
            path = report_dir / f"{symbol.upper()}_{slug}.md"
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
                # First paragraph is preferred — narrative reports open with an analytical
                # summary sentence, while bullets are often product/item enumerations.
                para = self._first_paragraph(text, max_chars=280)
                if para:
                    key_findings.append(f"**{label}:** {para}")
                else:
                    # Fall back to the first substantive bullet if no good paragraph exists
                    bullets = self._extract_bullets(text, max_bullets=1)
                    if bullets:
                        key_findings.append(f"**{label}:** {bullets[0]}")
            except Exception:
                pass
            if len(key_findings) >= 5:
                break

        return {"key_findings": key_findings} if key_findings else {}

    @staticmethod
    def _rec_json_to_md(data: Dict[str, Any]) -> str:
        """Convert a structured InvestmentRecommendation JSON dict to readable markdown."""
        lines = [f"## Investment Recommendation: {data.get('recommendation', 'N/A')}"]
        fields = [
            ("Target Price", data.get("target_price")),
            ("Stop Loss",    data.get("stop_loss")),
            ("Time Horizon", data.get("time_horizon")),
            ("Risk Level",   data.get("risk_level")),
            ("Confidence",   f"{int(float(data['confidence']) * 100)}%" if data.get("confidence") is not None else None),
        ]
        for label, val in fields:
            if val is not None:
                lines.append(f"- **{label}:** {val}")
        if data.get("reasoning"):
            lines += ["", "### Reasoning", data["reasoning"]]
        for section, key in [("Key Factors", "key_factors"), ("Risks", "risks"), ("Opportunities", "opportunities")]:
            items = data.get(key) or []
            if items:
                lines += [f"", f"### {section}"]
                lines += [f"- {item}" for item in items]
        return "\n".join(lines)

    def _load_detail_sections(
        self, symbol: str, asset_type: str = "stock"
    ) -> Tuple[List[Tuple[str, str, Any]], List[Tuple[str, Any]]]:
        """Read specialist .md files; return (appendix_sections, consolidated_gaps).

        Each section's own title line is stripped (the template renders the
        header) and its 'Data Sources & Gaps' footer is excised — the gaps are
        consolidated into a single appendix instead of repeating per section.
        """
        try:
            from markupsafe import Markup
        except ImportError:
            from jinja2 import Markup  # type: ignore[no-redef]

        report_dir = Path(settings.report_output_dir) / symbol.upper()
        sections = _ETF_MD_SECTIONS if asset_type == "etf" else _MD_SECTIONS
        result = []
        gaps_acc: List[Tuple[str, Any]] = []
        for slug, title in sections:
            path = report_dir / f"{symbol.upper()}_{slug}.md"
            md_text = ""
            if path.exists():
                try:
                    md_text = path.read_text(encoding="utf-8")
                except Exception as exc:
                    _logger.warning("Could not read %s: %s", path, exc)
            elif slug == "investment_recommendation":
                # Recommendation may exist only as structured JSON (output_pydantic)
                json_path = report_dir / f"{symbol.upper()}_{slug}.json"
                if json_path.exists():
                    try:
                        data = json.loads(json_path.read_text(encoding="utf-8"))
                        md_text = self._rec_json_to_md(data)
                    except Exception as exc:
                        _logger.warning("Could not render %s: %s", json_path, exc)
            if not md_text:
                continue
            md_text = _strip_leading_title(md_text)
            md_text, gaps_md = _split_gaps(md_text)
            if gaps_md:
                gaps_acc.append((title, Markup(_md_to_html(gaps_md))))
            result.append((slug, title, Markup(_md_to_html(md_text))))
        return result, gaps_acc

    def _render_html(
        self, symbol: str, analysis_data: Dict[str, Any], timeframe: str, asset_type: str = "stock"
    ) -> Dict[str, Any]:
        from jinja2 import Environment
        from markupsafe import Markup

        env = Environment(autoescape=True)
        # Filter: convert a markdown string to safe HTML inline
        env.filters["md"] = lambda t: Markup(_md_to_html(str(t))) if t else Markup("")
        template = env.from_string(_HTML_TEMPLATE)

        # Support both new agent format and legacy flat format
        inv_rec = (
            analysis_data.get("investment_recommendation")
            or analysis_data.get("recommendation")
            or {}
        )
        rating = str(inv_rec.get("rating") or inv_rec.get("recommendation", "")).upper()
        if "BUY" in rating:
            rec_class = "buy"
        elif "SELL" in rating:
            rec_class = "sell"
        else:
            rec_class = "hold"

        # Fall back to parsing the markdown file when the LLM didn't pass structured JSON.
        if not inv_rec:
            inv_rec = self._extract_rec_from_md(symbol)
            rating = str(inv_rec.get("rating") or "").upper()
            if "BUY" in rating:
                rec_class = "buy"
            elif "SELL" in rating:
                rec_class = "sell"
            else:
                rec_class = "hold"

        exec_sum = analysis_data.get("executive_summary") or {}
        if not exec_sum:
            exec_sum = self._build_exec_summary(symbol, inv_rec, asset_type)

        detail = analysis_data.get("detailed_analysis") or {}
        supporting = analysis_data.get("supporting_evidence") or {}
        market_snap = (
            supporting.get("market_snapshot")
            or analysis_data.get("market_data")
            or {}
        )

        # Charts + branding (all degrade gracefully when data is unavailable)
        from ._svg_charts import _fmt, bar_chart_svg, line_chart_svg, range_bar_svg, rating_bar_svg

        chart_data = _load_chart_data(symbol)
        company = chart_data.get("company") or {}

        # Key statistics strip — deterministic, from collected data
        ks = chart_data.get("key_stats") or {}
        key_stats: List[Tuple[str, str]] = []
        if ks.get("current_price") is not None:
            key_stats.append(("Price", f"${_fmt(ks['current_price'])}"))
        if ks.get("market_cap"):
            key_stats.append(("Market Cap", f"${_fmt(ks['market_cap'])}"))
        if ks.get("pe_ratio"):
            key_stats.append(("P/E (TTM)", _fmt(ks["pe_ratio"])))
        if ks.get("low_52w") and ks.get("high_52w"):
            key_stats.append(("52-Week Range", f"${_fmt(ks['low_52w'])} – ${_fmt(ks['high_52w'])}"))
        if ks.get("beta"):
            key_stats.append(("Beta", _fmt(ks["beta"])))

        # Analyst consensus visuals
        analyst = chart_data.get("analyst") or {}
        pt = analyst.get("price_targets") or {}
        target_range_svg = ""
        if pt.get("low") and pt.get("high"):
            markers = [("Current", pt.get("current_price") or ks.get("current_price"), "#1a202c"),
                       ("Mean target", pt.get("mean"), "#2b6cb0")]
            target_range_svg = Markup(range_bar_svg(
                pt["low"], pt["high"],
                [(l, v, c) for l, v, c in markers if v is not None],
                title="Analyst Price Targets (12-month)",
            ))
        rating_svg = ""
        rc = analyst.get("rating_counts") or {}
        if any(rc.get(k) for k in ("strong_buy", "buy", "hold", "sell", "strong_sell")):
            rating_svg = Markup(rating_bar_svg(rc, title="Analyst Ratings"))
        range_52w_svg = ""
        if ks.get("low_52w") and ks.get("high_52w") and ks.get("current_price"):
            range_52w_svg = Markup(range_bar_svg(
                ks["low_52w"], ks["high_52w"],
                [("Current", ks["current_price"], "#1a202c")],
                title="52-Week Range", height=84,
            ))

        # Sentiment chips
        ss = chart_data.get("sentiment_snapshot") or {}
        sentiment_chips: List[Tuple[str, str]] = []
        if ss.get("stocktwits_bullish_pct") is not None:
            sentiment_chips.append((
                "Retail (Stocktwits)",
                f"{_fmt(ss['stocktwits_bullish_pct'])}% bullish of {ss.get('stocktwits_labeled', 0)} labeled",
            ))
        if ss.get("put_call_oi_ratio") is not None:
            pc = ss["put_call_oi_ratio"]
            tone = "bullish tilt" if pc < 0.7 else ("bearish tilt" if pc > 1.0 else "neutral")
            sentiment_chips.append(("Options Put/Call OI", f"{_fmt(pc)} ({tone})"))
        if ss.get("short_pct_of_float") is not None:
            sentiment_chips.append(("Short Interest", f"{_fmt(ss['short_pct_of_float'])}% of float"))
        if ss.get("fear_greed_score") is not None:
            # NB: must not be named `rating` — that variable holds the
            # investment recommendation shown in the badge.
            fg_label = (ss.get("fear_greed_rating") or "").replace("_", " ")
            sentiment_chips.append(("Market Mood (CNN)", f"{_fmt(ss['fear_greed_score'])} — {fg_label}"))
        if ss.get("watchers"):
            sentiment_chips.append(("Stocktwits Watchers", _fmt(ss["watchers"])))

        # Catalysts strip (next earnings, dividends)
        cat = chart_data.get("catalysts") or {}
        catalysts: List[Tuple[str, str]] = []
        if cat.get("next_earnings_date"):
            val = cat["next_earnings_date"]
            if cat.get("earnings_eps_estimate") is not None:
                val += f" (est. EPS ${_fmt(cat['earnings_eps_estimate'])})"
            catalysts.append(("Next Earnings", val))
        if cat.get("ex_dividend_date"):
            catalysts.append(("Ex-Dividend", cat["ex_dividend_date"]))
        if cat.get("dividend_date"):
            catalysts.append(("Dividend Payment", cat["dividend_date"]))

        # Peer comparison rows (subject company flagged)
        peers = chart_data.get("peers") or []

        # Valuation scenario grid (assumption-disclosed DCF)
        valuation_scenarios = chart_data.get("valuation_scenarios") or []
        current_px = ks.get("current_price")
        for sc in valuation_scenarios:
            iv = sc.get("intrinsic_per_share")
            sc["upside_pct"] = (
                round((iv - current_px) / current_px * 100, 1)
                if iv and current_px else None
            )

        # Sentiment trend across runs
        history = chart_data.get("sentiment_history") or []
        trend_points = [
            (h["date"][5:], h["stocktwits_bullish_pct"])
            for h in history
            if h.get("stocktwits_bullish_pct") is not None
        ]
        sentiment_trend_svg = ""
        if len(trend_points) >= 3:
            sentiment_trend_svg = Markup(line_chart_svg(
                trend_points, title="Retail Bullishness Over Time (% bullish, Stocktwits)",
                height=200, currency="",
            ))
        if len(trend_points) >= 2:
            prev_label, prev_val = trend_points[-2]
            _, last_val = trend_points[-1]
            sentiment_chips.append((
                "Retail Trend",
                f"{_fmt(last_val)}% bullish (was {_fmt(prev_val)}% on {prev_label})",
            ))
        if ss.get("search_momentum_pct") is not None:
            sm = ss["search_momentum_pct"]
            sentiment_chips.append((
                "Search Interest (Google)",
                f"{'+' if sm > 0 else ''}{_fmt(sm)}% vs 3-mo avg",
            ))


        price_chart_svg = ""
        prices = chart_data.get("price_history") or []
        if len(prices) >= 2:
            price_chart_svg = Markup(line_chart_svg(
                [(p["date"][5:], p["close"]) for p in prices],
                title=f"{symbol.upper()} — 1-Year Weekly Close",
            ))
        revenue_chart_svg = ""
        qrev = chart_data.get("quarterly_revenue_m") or {}
        if qrev:
            items = sorted(qrev.items())[-5:]
            revenue_chart_svg = Markup(bar_chart_svg(
                [k[2:7] for k, _ in items],
                [v for _, v in items],
                title="Quarterly Revenue (USD millions)",
            ))
        sector_chart_svg = ""
        sectors = chart_data.get("sector_weightings_pct") or {}
        if sectors:
            top = sorted(sectors.items(), key=lambda kv: kv[1], reverse=True)[:10]
            sector_chart_svg = Markup(bar_chart_svg(
                [k.replace("_", " ").title() for k, _ in top],
                [v for _, v in top],
                title="Sector Weightings (%)",
                unit="", suffix="%", horizontal=True,
                height=max(220, 36 * len(top) + 50),
            ))

        # Synthesized narrative = report body; specialist reports become appendices.
        # Visuals are interleaved INTO their matching narrative sections so the
        # document reads as one argument, not a dashboard followed by an essay.
        narrative_md = _load_narrative(symbol)
        narrative_html = Markup(_md_to_html(narrative_md)) if narrative_md else ""

        peers_table = _peers_table_html(peers)
        scenarios_table = _scenarios_table_html(valuation_scenarios)

        def _chips_html(chips: List[Tuple[str, str]]) -> str:
            if not chips:
                return ""
            cells = "".join(
                f'<div class="stat"><div class="label">{label}</div>'
                f'<div class="value" style="font-size:0.98em">{value}</div></div>'
                for label, value in chips
            )
            return f'<div class="stat-grid">{cells}</div>'

        visual_groups: Dict[str, Any] = {}
        if price_chart_svg:
            visual_groups["price"] = Markup(
                f'<div class="chart" id="price-chart">{price_chart_svg}</div>'
            )
        if revenue_chart_svg:
            visual_groups["revenue"] = Markup(
                f'<div class="chart" id="revenue-chart">{revenue_chart_svg}</div>'
            )
        if peers_table:
            visual_groups["peers"] = Markup(peers_table)
        consensus_parts = []
        if rating_svg:
            consensus_parts.append(f'<div class="chart">{rating_svg}</div>')
        consensus_parts.append(_chips_html(sentiment_chips))
        if sentiment_trend_svg:
            consensus_parts.append(f'<div class="chart">{sentiment_trend_svg}</div>')
        if any(consensus_parts):
            visual_groups["consensus"] = Markup(
                '<div id="analyst-consensus">' + "".join(consensus_parts) + "</div>"
            )
        valuation_parts = []
        if target_range_svg:
            valuation_parts.append(f'<div class="chart">{target_range_svg}</div>')
        if scenarios_table:
            valuation_parts.append(scenarios_table)
        if valuation_parts:
            visual_groups["valuation"] = Markup("".join(valuation_parts))
        if range_52w_svg:
            visual_groups["range52w"] = Markup(f'<div class="chart">{range_52w_svg}</div>')

        narrative_sections, consumed = _build_narrative_sections(narrative_md, visual_groups)
        # Visual groups not matched to a section render in standalone fallback spots
        unconsumed = {k: v for k, v in visual_groups.items() if k not in consumed}

        meta = analysis_data.get("report_metadata") or {}
        for key in ("exchange", "sector", "industry"):
            meta.setdefault(key, company.get(key))

        detail_sections, consolidated_gaps = self._load_detail_sections(symbol, asset_type)

        html = template.render(
            symbol=symbol.upper(),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            timeframe=timeframe,
            asset_type=asset_type,
            company_name=company.get("name"),
            logo_url=_logo_url(company),
            price_chart_svg=price_chart_svg,
            revenue_chart_svg=revenue_chart_svg,
            sector_chart_svg=sector_chart_svg,
            key_stats=key_stats,
            target_range_svg=target_range_svg,
            rating_svg=rating_svg,
            range_52w_svg=range_52w_svg,
            sentiment_chips=sentiment_chips,
            catalysts=catalysts,
            peers=peers,
            valuation_scenarios=valuation_scenarios,
            sentiment_trend_svg=sentiment_trend_svg,
            narrative_html=narrative_html,
            narrative_sections=narrative_sections,
            standalone=unconsumed,
            consolidated_gaps=consolidated_gaps,
            meta=meta,
            exec_sum=exec_sum,
            inv_rec=inv_rec,
            rating=rating or "N/A",
            rec_class=rec_class,
            market_snap=market_snap,
            technical=detail.get("technical_analysis") or {},
            fundamental=detail.get("fundamental_analysis") or {},
            etf_profile=analysis_data.get("etf_profile") or {},
            risk=detail.get("risk_assessment") or {},
            sentiment=detail.get("sentiment_analysis") or {},
            market_ctx=detail.get("market_context") or {},
            industry=detail.get("industry_context") or {},
            competitive=detail.get("competitive_analysis") or {},
            supporting=supporting,
            appendices=analysis_data.get("appendices") or {},
            detail_sections=detail_sections,
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
        """One canonical report file per symbol, overwritten on each render.

        A timestamped filename here caused two problems: report folders filled
        up across runs, and the report-generator agent could loop on the tool
        because every call returned a different path (defeating CrewAI's
        repeated-call detection). The generation time is shown inside the
        report itself.
        """
        output_dir = Path(settings.report_output_dir) / symbol.upper() / "html"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{symbol.upper()}_report.{ext}"
