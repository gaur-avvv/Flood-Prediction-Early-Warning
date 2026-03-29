"""
Flood Alert Email Notification Service

Sends email alerts for high-risk flood predictions using SMTP.
Supports:
- Ward-level flood alerts with readiness grades
- Micro-hotspot critical alerts
- Nowcast flood warnings
- Configurable SMTP (Gmail, SendGrid, or custom SMTP)

Configuration via environment variables:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  ALERT_RECIPIENTS (comma-separated emails)
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
ALERT_RECIPIENTS = [
    e.strip()
    for e in os.getenv("ALERT_RECIPIENTS", "").split(",")
    if e.strip()
]


def is_email_configured() -> bool:
    """Check if SMTP credentials are configured."""
    return bool(SMTP_USER and SMTP_PASSWORD)


# ── Email Templates ──────────────────────────────────────────────────────────


def _ward_alert_html(wards: List[Dict[str, Any]], location: str) -> str:
    """Generate HTML email for ward-level flood alerts."""
    grade_colors = {
        "A": "#22c55e",
        "B": "#3b82f6",
        "C": "#f59e0b",
        "D": "#ef4444",
        "F": "#7c3aed",
    }

    ward_rows = ""
    for w in wards:
        grade = w.get("readiness_grade", "?")
        color = grade_colors.get(grade, "#6b7280")
        ward_rows += f"""
        <tr>
            <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-weight:600;">{w.get('ward_name', 'Unknown')}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;text-align:center;">
                <span style="background:{color};color:#fff;padding:4px 12px;border-radius:6px;font-weight:700;font-size:14px;">{grade}</span>
            </td>
            <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;text-align:center;">{w.get('risk_score', 0):.1f}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;text-align:center;">{w.get('flood_probability', 0):.1%}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #e5e7eb;font-size:13px;">{', '.join(w.get('recommended_actions', [])[:2])}</td>
        </tr>"""

    critical_count = sum(1 for w in wards if w.get("readiness_grade") in ("D", "F"))
    high_count = sum(1 for w in wards if w.get("readiness_grade") == "C")

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;background:#f8fafc;">
        <div style="max-width:700px;margin:0 auto;padding:24px;">
            <!-- Header -->
            <div style="background:linear-gradient(135deg,#1e40af,#3b82f6);padding:28px 32px;border-radius:16px 16px 0 0;">
                <h1 style="color:#fff;margin:0;font-size:22px;">Flood Alert: Ward Readiness Report</h1>
                <p style="color:#bfdbfe;margin:6px 0 0;font-size:14px;">{location} &mdash; {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}</p>
            </div>

            <!-- Summary -->
            <div style="background:#fff;padding:24px 32px;border:1px solid #e5e7eb;">
                <div style="display:flex;gap:20px;margin-bottom:16px;">
                    <div style="flex:1;text-align:center;padding:14px;background:#fef2f2;border-radius:12px;">
                        <div style="font-size:28px;font-weight:800;color:#dc2626;">{critical_count}</div>
                        <div style="font-size:11px;font-weight:700;color:#991b1b;text-transform:uppercase;letter-spacing:1px;">Critical Wards</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:14px;background:#fffbeb;border-radius:12px;">
                        <div style="font-size:28px;font-weight:800;color:#d97706;">{high_count}</div>
                        <div style="font-size:11px;font-weight:700;color:#92400e;text-transform:uppercase;letter-spacing:1px;">High Risk Wards</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:14px;background:#f0f9ff;border-radius:12px;">
                        <div style="font-size:28px;font-weight:800;color:#2563eb;">{len(wards)}</div>
                        <div style="font-size:11px;font-weight:700;color:#1e40af;text-transform:uppercase;letter-spacing:1px;">Total Wards</div>
                    </div>
                </div>
            </div>

            <!-- Ward Table -->
            <div style="background:#fff;padding:24px 32px;border:1px solid #e5e7eb;border-top:none;">
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                    <thead>
                        <tr style="background:#f1f5f9;">
                            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Ward</th>
                            <th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Grade</th>
                            <th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Risk</th>
                            <th style="padding:10px 14px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Flood %</th>
                            <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Actions</th>
                        </tr>
                    </thead>
                    <tbody>{ward_rows}</tbody>
                </table>
            </div>

            <!-- Footer -->
            <div style="background:#f1f5f9;padding:18px 32px;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;">
                <p style="color:#64748b;font-size:12px;margin:0;">
                    Bio-SentinelX Flood Prediction &amp; Early Warning System<br>
                    This is an automated alert. Do not reply to this email.
                </p>
            </div>
        </div>
    </body>
    </html>"""


def _hotspot_alert_html(
    hotspots: List[Dict[str, Any]],
    location: str,
    total_scanned: int,
) -> str:
    """Generate HTML email for micro-hotspot critical alerts."""
    critical = [h for h in hotspots if h.get("risk_level") in ("CRITICAL", "HIGH")]

    rows = ""
    for h in critical[:20]:
        risk = h.get("risk_level", "UNKNOWN")
        color = "#dc2626" if risk == "CRITICAL" else "#f59e0b"
        rows += f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{h.get('cell_id', '?')}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">
                <span style="color:{color};font-weight:700;">{risk}</span>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">{h.get('flood_probability', 0):.1%}</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center;">{h.get('inundation_depth_m', 0):.2f}m</td>
            <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;">{h.get('dominant_factor', 'N/A')}</td>
        </tr>"""

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;font-family:'Segoe UI',sans-serif;background:#f8fafc;">
        <div style="max-width:700px;margin:0 auto;padding:24px;">
            <div style="background:linear-gradient(135deg,#991b1b,#dc2626);padding:28px 32px;border-radius:16px 16px 0 0;">
                <h1 style="color:#fff;margin:0;font-size:22px;">Micro-Hotspot Critical Alert</h1>
                <p style="color:#fecaca;margin:6px 0 0;font-size:14px;">{location} &mdash; {len(critical)} critical/high-risk zones detected</p>
            </div>
            <div style="background:#fff;padding:24px 32px;border:1px solid #e5e7eb;">
                <p style="color:#374151;font-size:14px;">Scanned <strong>{total_scanned}</strong> grid cells. Found <strong>{len(hotspots)}</strong> hotspots, of which <strong>{len(critical)}</strong> are critical/high risk.</p>
                <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:16px;">
                    <thead>
                        <tr style="background:#f1f5f9;">
                            <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Cell</th>
                            <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Risk</th>
                            <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Probability</th>
                            <th style="padding:8px 12px;text-align:center;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Depth</th>
                            <th style="padding:8px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;">Factor</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            <div style="background:#f1f5f9;padding:18px 32px;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;">
                <p style="color:#64748b;font-size:12px;margin:0;">Bio-SentinelX Flood Early Warning System</p>
            </div>
        </div>
    </body>
    </html>"""


def _nowcast_alert_html(nowcast: Dict[str, Any], location: str) -> str:
    """Generate HTML email for real-time nowcast alerts."""
    prob = nowcast.get("flood_probability", 0)
    risk = nowcast.get("flood_risk_level", "UNKNOWN")
    onset = nowcast.get("predicted_flood_onset_minutes")
    color = "#dc2626" if risk == "CRITICAL" else "#f59e0b" if risk == "HIGH" else "#3b82f6"

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;font-family:'Segoe UI',sans-serif;background:#f8fafc;">
        <div style="max-width:600px;margin:0 auto;padding:24px;">
            <div style="background:{color};padding:28px 32px;border-radius:16px 16px 0 0;">
                <h1 style="color:#fff;margin:0;font-size:22px;">Nowcast Flood Warning</h1>
                <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:14px;">{location} &mdash; {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}</p>
            </div>
            <div style="background:#fff;padding:24px 32px;border:1px solid #e5e7eb;">
                <div style="text-align:center;padding:20px;">
                    <div style="font-size:48px;font-weight:800;color:{color};">{prob:.0%}</div>
                    <div style="font-size:14px;font-weight:700;color:#64748b;margin-top:4px;">Flood Probability</div>
                </div>
                <div style="display:flex;gap:16px;margin:16px 0;">
                    <div style="flex:1;text-align:center;padding:12px;background:#f8fafc;border-radius:10px;">
                        <div style="font-size:18px;font-weight:700;color:#374151;">{risk}</div>
                        <div style="font-size:11px;color:#64748b;">Risk Level</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:12px;background:#f8fafc;border-radius:10px;">
                        <div style="font-size:18px;font-weight:700;color:#374151;">{onset or 'N/A'}</div>
                        <div style="font-size:11px;color:#64748b;">Onset (min)</div>
                    </div>
                    <div style="flex:1;text-align:center;padding:12px;background:#f8fafc;border-radius:10px;">
                        <div style="font-size:18px;font-weight:700;color:#374151;">{nowcast.get('current_rainfall_mm_hr', 0):.1f}</div>
                        <div style="font-size:11px;color:#64748b;">Rain mm/hr</div>
                    </div>
                </div>
                <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:10px;padding:14px;margin-top:16px;">
                    <p style="color:#991b1b;font-size:14px;margin:0;font-weight:600;">{nowcast.get('recommendation', '')}</p>
                </div>
            </div>
            <div style="background:#f1f5f9;padding:18px 32px;border-radius:0 0 16px 16px;border:1px solid #e5e7eb;border-top:none;">
                <p style="color:#64748b;font-size:12px;margin:0;">Bio-SentinelX Flood Early Warning System</p>
            </div>
        </div>
    </body>
    </html>"""


# ── Send Email ────────────────────────────────────────────────────────────────


def _send_email(
    subject: str,
    html_body: str,
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Send an HTML email via SMTP.

    Returns dict with status and details.
    """
    to_addrs = recipients or ALERT_RECIPIENTS
    if not to_addrs:
        return {"status": "skipped", "reason": "No recipients configured"}

    if not is_email_configured():
        logger.warning("SMTP not configured — email alert skipped")
        return {"status": "skipped", "reason": "SMTP credentials not configured"}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_addrs, msg.as_string())

        logger.info("Email sent to %s — subject: %s", to_addrs, subject)
        return {
            "status": "sent",
            "recipients": to_addrs,
            "subject": subject,
        }
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("SMTP authentication failed: %s", exc)
        return {"status": "error", "reason": f"SMTP auth failed: {exc}"}
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        return {"status": "error", "reason": str(exc)}


# ── Public Alert Functions ────────────────────────────────────────────────────


def send_ward_alert(
    wards: List[Dict[str, Any]],
    location: str = "Unknown Location",
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send email alert for ward readiness results."""
    critical_wards = [w for w in wards if w.get("readiness_grade") in ("D", "F")]
    if not critical_wards and not recipients:
        return {"status": "skipped", "reason": "No critical wards to alert"}

    subject = f"Flood Alert: {len(critical_wards)} Critical Wards — {location}"
    html = _ward_alert_html(wards, location)
    return _send_email(subject, html, recipients)


def send_hotspot_alert(
    hotspots: List[Dict[str, Any]],
    total_scanned: int,
    location: str = "Unknown Location",
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send email alert for micro-hotspot analysis results."""
    critical = [h for h in hotspots if h.get("risk_level") in ("CRITICAL", "HIGH")]
    if not critical and not recipients:
        return {"status": "skipped", "reason": "No critical hotspots"}

    subject = f"CRITICAL: {len(critical)} Flood Hotspots Detected — {location}"
    html = _hotspot_alert_html(hotspots, location, total_scanned)
    return _send_email(subject, html, recipients)


def send_nowcast_alert(
    nowcast: Dict[str, Any],
    location: str = "Unknown Location",
    recipients: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send real-time nowcast flood warning email."""
    prob = nowcast.get("flood_probability", 0)
    risk = nowcast.get("flood_risk_level", "SAFE")

    if prob < 0.4 and not recipients:
        return {"status": "skipped", "reason": "Risk below alert threshold"}

    subject = f"FLOOD NOWCAST {risk}: {prob:.0%} probability — {location}"
    html = _nowcast_alert_html(nowcast, location)
    return _send_email(subject, html, recipients)
