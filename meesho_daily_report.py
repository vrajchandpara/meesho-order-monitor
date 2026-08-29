from playwright.sync_api import sync_playwright
import requests
import json
import os
import sys


SESSION_FILE = "meesho_session.json"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = "5787890761"

MEESHO_URL = (
    "https://supplier.meesho.com/"
    "panel/v3/new/fulfillment/"
    "exmqx/orders/pending"
)

API_URL = (
    "https://supplier.meesho.com/"
    "api/fulfillment/orders"
)

SUPPLIER_ID = 4779751
IDENTIFIER = "exmqx"


STATUS_MAP = {
    1: "pending",
    3: "ready-to-ship",
    4: "shipped",
    5: "cancelled"
}


counts = {
    "pending": None,
    "ready-to-ship": None,
    "shipped": None,
    "cancelled": None
}


if not BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN is missing.")
    sys.exit(1)


if not os.path.exists(SESSION_FILE):
    print("❌ Meesho session file is missing.")
    sys.exit(1)


def send_telegram(message):

    url = (
        "https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=30
        )

        if response.ok:
            print("✅ Telegram message sent!")
            return True

        print("❌ Telegram error:")
        print(response.text)
        return False

    except Exception as error:

        print("❌ Telegram connection error:")
        print(error)
        return False


def extract_count(data):

    if not isinstance(data, dict):
        return None

    try:

        value = data.get(
            "data",
            {}
        ).get("count")

        if value is not None:
            return int(value)

    except Exception:
        pass

    try:

        value = data.get("total_count")

        if value is not None:
            return int(value)

    except Exception:
        pass

    return None


with sync_playwright() as p:

    print("🚀 Starting Chromium...")

    try:

        browser = p.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            storage_state=SESSION_FILE
        )

        page = context.new_page()

    except Exception as error:

        print("❌ Could not start browser:")
        print(error)

        sys.exit(1)


    print("🌐 Opening Meesho...")

    try:

        page.goto(
            MEESHO_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

        page.wait_for_timeout(7000)

    except Exception as error:

        print("❌ Could not open Meesho:")
        print(error)

        browser.close()
        sys.exit(1)


    print()
    print("URL:")
    print(page.url)

    print()
    print("Title:")
    print(page.title())


    # ==============================================
    # DETECT ACCESS DENIED
    # ==============================================

    if (
        "access denied" in page.title().lower()
        or "access denied" in page.url.lower()
    ):

        print("❌ Meesho returned ACCESS DENIED.")

        message = """🚨 MEESHO CHECK FAILED

❌ Meesho returned Access Denied / 403.

⚠️ Order counts could not be retrieved.

No order count has been reported as zero.
"""

        send_telegram(message)

        browser.close()
        sys.exit(1)


    # ==============================================
    # LOGIN CHECK
    # ==============================================

    current_url = page.url.lower()

    if (
        "login" in current_url
        or "signin" in current_url
        or "sign-in" in current_url
    ):

        print("❌ Meesho session expired.")

        message = """🚨 MEESHO CHECK FAILED

🔐 Meesho login session has expired.

⚠️ Order counts could not be retrieved.
"""

        send_telegram(message)

        browser.close()
        sys.exit(1)


    print("✅ Meesho page opened.")


    # ==============================================
    # DIRECT API REQUEST
    # ==============================================

    def get_order_count(status):

        order_type = STATUS_MAP[status]

        print()
        print(
            f"🔎 Checking {order_type} "
            f"(status={status})..."
        )


        payload = {

            "enable_hold": True,

            "supplier_details": {
                "id": SUPPLIER_ID,
                "identifier": IDENTIFIER,
                "name": "VIHAL FASHION STORE"
            },

            "cursor": None,

            "limit": 50,

            "status": status,

            "type": order_type,

            "identifier": IDENTIFIER,

            "child_supplier_identifier": None,

            "child_supplier_id": None
        }


        try:

            result = page.evaluate(
                """
                async ({url, payload}) => {

                    const response = await fetch(
                        url,
                        {
                            method: "POST",

                            credentials: "include",

                            headers: {
                                "Accept":
                                    "application/json, text/plain, */*",

                                "Content-Type":
                                    "application/json",

                                "Client-Type":
                                    "d-web",

                                "Client-Package-Version":
                                    "1.0.4"
                            },

                            body: JSON.stringify(payload)
                        }
                    );

                    return {
                        status: response.status,
                        text: await response.text()
                    };
                }
                """,
                {
                    "url": API_URL,
                    "payload": payload
                }
            )

        except Exception as error:

            print(
                f"❌ Request failed for {order_type}:"
            )

            print(error)

            return None


        http_status = result.get(
            "status",
            0
        )

        response_text = result.get(
            "text",
            ""
        )


        print(
            f"HTTP Status: {http_status}"
        )


        # ==========================================
        # 403 / OTHER ERROR
        # ==========================================

        if http_status != 200:

            print(
                f"❌ Meesho rejected {order_type}."
            )

            return None


        # ==========================================
        # JSON
        # ==========================================

        try:

            data = json.loads(
                response_text
            )

        except Exception:

            print(
                f"❌ Invalid JSON for {order_type}."
            )

            return None


        count = extract_count(data)


        if count is None:

            print(
                f"⚠️ Count unavailable for "
                f"{order_type}."
            )

            return None


        print(
            f"📦 {order_type}: {count}"
        )

        return count


    # ==============================================
    # CHECK ALL STATUSES
    # ==============================================

    for status, order_type in STATUS_MAP.items():

        counts[order_type] = get_order_count(
            status
        )

        page.wait_for_timeout(1500)


    # ==============================================
    # CHECK WHETHER ANY REQUEST FAILED
    # ==============================================

    failed = [
        name
        for name, value in counts.items()
        if value is None
    ]


    if failed:

        print()
        print(
            "❌ Could not retrieve:"
        )

        for item in failed:
            print(
                f"   - {item}"
            )


        message = f"""🚨 MEESHO CHECK FAILED

❌ Could not retrieve all order counts.

Unavailable:
{chr(10).join("- " + x for x in failed)}

⚠️ No unavailable count has been reported as 0.

Please check Meesho manually.
"""


        send_telegram(message)

        browser.close()
        sys.exit(1)


    # ==============================================
    # SUMMARY
    # ==============================================

    print()
    print(
        "======================================"
    )

    print(
        "       MEESHO ORDER SUMMARY"
    )

    print(
        "======================================"
    )

    print(
        f"🟡 Pending:       {counts['pending']}"
    )

    print(
        f"📦 Ready to Ship: {counts['ready-to-ship']}"
    )

    print(
        f"🚚 Shipped:       {counts['shipped']}"
    )

    print(
        f"❌ Cancelled:     {counts['cancelled']}"
    )

    print(
        "======================================"
    )


    # ==============================================
    # TELEGRAM
    # ==============================================

    message = f"""📊 MEESHO ORDER UPDATE

🟡 Pending: {counts['pending']}
📦 Ready to Ship: {counts['ready-to-ship']}
🚚 Shipped: {counts['shipped']}
❌ Cancelled: {counts['cancelled']}

⚡ Automated Meesho Report
"""


    print()
    print(
        "📱 Sending Telegram report..."
    )

    success = send_telegram(
        message
    )


    browser.close()


    if success:

        print()
        print(
            "✅ REPORT COMPLETED!"
        )

    else:

        sys.exit(1)
