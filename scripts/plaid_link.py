"""
One-time Plaid Link authorization script.
Run: uv run python scripts/plaid_link.py
Then open http://localhost:5123 in your browser to complete the Link flow.
The access_token will be saved to .env.plaid automatically.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv, set_key
from flask import Flask, jsonify, request

import plaid
from plaid.api import plaid_api
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

ENV_FILE = Path(__file__).parent.parent / ".env.plaid"
load_dotenv(ENV_FILE)

PLAID_CLIENT_ID = os.environ.get("PLAID_CLIENT_ID", "")
PLAID_SECRET = os.environ.get("PLAID_SECRET", "")
PLAID_ENV = os.environ.get("PLAID_ENV", "sandbox")

ENV_MAP = {
    "sandbox": plaid.Environment.Sandbox,
    "development": "https://development.plaid.com",
    "production": plaid.Environment.Production,
}

config = plaid.Configuration(
    host=ENV_MAP.get(PLAID_ENV, plaid.Environment.Sandbox),
    api_key={"clientId": PLAID_CLIENT_ID, "secret": PLAID_SECRET},
)
api_client = plaid.ApiClient(config)
client = plaid_api.PlaidApi(api_client)

app = Flask(__name__)

HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Plaid Link — Portfolio Tracking</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        body { font-family: -apple-system, sans-serif; max-width: 600px; margin: 80px auto; text-align: center; }
        button { font-size: 18px; padding: 12px 32px; cursor: pointer; border-radius: 8px; border: 1px solid #ccc; }
        button:hover { background: #f0f0f0; }
        #status { margin-top: 24px; color: #666; white-space: pre-line; }
        .success { color: #2e7d32 !important; font-weight: bold; }
        .error { color: #c62828 !important; }
    </style>
</head>
<body>
    <h1>Plaid Link</h1>
    <p>Connect your brokerage account to retrieve holdings.</p>
    <p style="color: #999; font-size: 14px;">Environment: <strong>PLAID_ENV</strong></p>
    <button id="link-btn" onclick="startLink()">Connect Account</button>
    <div id="status"></div>

    <script>
        const statusEl = document.getElementById('status');

        async function startLink() {
            statusEl.textContent = 'Creating link token...';
            const resp = await fetch('/create_link_token', { method: 'POST' });
            const data = await resp.json();

            if (data.error) {
                statusEl.textContent = 'Error: ' + data.error;
                statusEl.className = 'error';
                return;
            }

            const handler = Plaid.create({
                token: data.link_token,
                onSuccess: async (public_token, metadata) => {
                    statusEl.textContent = 'Exchanging token...';
                    const exResp = await fetch('/exchange_token', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ public_token }),
                    });
                    const exData = await exResp.json();
                    if (exData.error) {
                        statusEl.textContent = 'Error: ' + exData.error;
                        statusEl.className = 'error';
                    } else {
                        statusEl.textContent = 'access_token saved to .env.plaid\\nYou can close this page and stop the server (Ctrl+C).';
                        statusEl.className = 'success';
                    }
                },
                onExit: (err) => {
                    if (err) {
                        statusEl.textContent = 'Link exited: ' + JSON.stringify(err);
                        statusEl.className = 'error';
                    }
                },
            });
            handler.open();
        }
    </script>
</body>
</html>
""".replace("PLAID_ENV", PLAID_ENV)


@app.route("/")
def index():
    return HTML_PAGE


@app.route("/create_link_token", methods=["POST"])
def create_link_token():
    try:
        req = LinkTokenCreateRequest(
            products=[Products("investments")],
            client_name="Portfolio Tracking",
            country_codes=[CountryCode("US")],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id="portfolio-user"),
        )
        response = client.link_token_create(req)
        return jsonify({"link_token": response.link_token})
    except plaid.ApiException as e:
        body = json.loads(e.body)
        return jsonify({"error": body.get("error_message", str(e))}), 400


@app.route("/exchange_token", methods=["POST"])
def exchange_token():
    try:
        public_token = request.json["public_token"]
        req = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(req)
        access_token = response.access_token
        item_id = response.item_id

        set_key(str(ENV_FILE), "PLAID_ACCESS_TOKEN", access_token)
        set_key(str(ENV_FILE), "PLAID_ITEM_ID", item_id)

        print(f"\n{'='*50}")
        print(f"Access token saved to {ENV_FILE}")
        print(f"Item ID: {item_id}")
        print(f"{'='*50}\n")

        return jsonify({"success": True, "item_id": item_id})
    except plaid.ApiException as e:
        body = json.loads(e.body)
        return jsonify({"error": body.get("error_message", str(e))}), 400


if __name__ == "__main__":
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        print("Error: PLAID_CLIENT_ID and PLAID_SECRET must be set in .env.plaid")
        raise SystemExit(1)

    print(f"Environment: {PLAID_ENV}")
    print(f"Open http://localhost:5123 to start Plaid Link")
    app.run(port=5123, debug=False)
