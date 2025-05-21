import os
import requests
import datetime
from dateutil import parser
from datetime import timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Environment variables (must be set)
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.company.local")  # Set your SMTP relay
SMTP_PORT = int(os.getenv("SMTP_PORT", "25"))  # Default port for non-authenticated relay

# Auth token for Microsoft Graph
def get_token():
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'scope': 'https://graph.microsoft.com/.default'
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()['access_token']

# Get app registrations with secrets expiring within 30 days
def get_expiring_secrets(token):
    url = "https://graph.microsoft.com/v1.0/applications?$expand=passwordCredentials"
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    apps = r.json()['value']

    today = datetime.datetime.now(timezone.utc)
    threshold = today + datetime.timedelta(days=30)

    expiring = []

    for app in apps:
        app_display_name = app.get('displayName', 'Unknown')
        app_id = app.get('appId', '')
        owners_url = f"https://graph.microsoft.com/v1.0/applications/{app['id']}/owners"
        owners_resp = requests.get(owners_url, headers=headers)
        owner_emails = [o.get('userPrincipalName', 'N/A') for o in owners_resp.json().get('value', [])]

        for secret in app.get("passwordCredentials", []):
            expiry = parser.isoparse(secret["endDateTime"])
            if today < expiry <= threshold:
                expiring.append({
                    "app": app_display_name,
                    "appId": app_id,
                    "owner": ", ".join(owner_emails),
                    "expiry": expiry.strftime("%Y-%m-%d %H:%M:%S")
                })
    return expiring

# Send email using Microsoft Graph API
def send_email_graph(token, rows):
    html_body = """
    <html><body>
    <h3>Secrets Expiring in Next 30 Days</h3>
    <table border="1" cellpadding="4" cellspacing="0">
      <tr><th>App Name</th><th>App ID</th><th>Owner(s)</th><th>Expiry Date</th></tr>
    """
    for row in rows:
        html_body += f"<tr><td>{row['app']}</td><td>{row['appId']}</td><td>{row['owner']}</td><td>{row['expiry']}</td></tr>"
    html_body += "</table></body></html>"

    url = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
    payload = {
        "message": {
            "subject": "Azure App Registration Secrets Expiring Soon",
            "body": {
                "contentType": "HTML",
                "content": html_body
            },
            "toRecipients": [{"emailAddress": {"address": RECIPIENT_EMAIL}}],
        },
        "saveToSentItems": "false"
    }

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }

    r = requests.post(url, headers=headers, json=payload)
    if r.status_code == 202:
        print("✅ Email sent via Microsoft Graph successfully.")
    else:
        raise Exception(f"Graph API email send failed: {r.text}")

# Fallback: Send email via SMTP (unauthenticated)
def send_email_smtp(rows):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Azure App Registration Secrets Expiring Soon"
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL

    html_body = """
    <html><body>
    <h3>Secrets Expiring in Next 30 Days</h3>
    <table border="1" cellpadding="4" cellspacing="0">
      <tr><th>App Name</th><th>App ID</th><th>Owner(s)</th><th>Expiry Date</th></tr>
    """
    for row in rows:
        html_body += f"<tr><td>{row['app']}</td><td>{row['appId']}</td><td>{row['owner']}</td><td>{row['expiry']}</td></tr>"
    html_body += "</table></body></html>"

    part = MIMEText(html_body, 'html')
    msg.attach(part)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print("✅ Email sent via SMTP successfully.")
    except Exception as e:
        print("❌ SMTP email send failed:", e)

# Main execution
if __name__ == "__main__":
    try:
        token = get_token()
        results = get_expiring_secrets(token)
        if results:
            try:
                send_email_graph(token, results)
            except Exception as e:
                print("⚠️ Microsoft Graph failed, falling back to SMTP. Error:", e)
                send_email_smtp(results)
        else:
            print("✅ No secrets expiring within 30 days.")
    except Exception as e:
        print("❌ Error:", e)
