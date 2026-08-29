from playwright.sync_api import sync_playwright
import requests
import json
import os
import sys


# =========================================================
# CONFIGURATION
# =========================================================

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


# =========================================================
# STATUS MAPPING
# =========================================================

STATUS_MAP = {
    1: "pending",
    3: "ready-to-ship",
    4: "shipped",
    5: "cancelled"
}


counts = {
    "pending": 0,
    "ready-to-ship": 0,
    "shipped": 0,
    "cancelled": 0
}


# =========================================================
# BASIC CHECKS
# =========================================================

if not BOT_TOKEN:
    print("❌ TELEGRAM_BOT_TOKEN secret is missing.")
    sys.exit(1)


if not os.path.exists(SESSION_FILE):
    print("❌ meesho_session.json was not created.")
    sys.exit(1)


try:

    with open(
        SESSION_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        json.load(f)

    print("✅ Meesho session JSON is valid.")

except Exception as error:

    print("❌ Invalid Meesho session:")
    print(error)

    sys.exit(1)


# =========================================================
# TELEGRAM
# =========================================================

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

            print(
                "✅ Telegram message sent successfully!"
            )

            return True

        print("❌ Telegram error:")
        print(response.text)

        return False

    except Exception as error:

        print("❌ Telegram connection error:")
        print(error)

        return False


# =========================================================
# EXTRACT COUNT
# =========================================================

def extract_count(data):

    if not isinstance(data, dict):
        return 0


    # ---------------------------------------------
    # data.count
    # ---------------------------------------------

    try:

        value = data.get(
            "data",
            {}
        ).get(
            "count"
        )

        if value is not None:
            return int(value)

    except Exception:
        pass


    # ---------------------------------------------
    # total_count
    # ---------------------------------------------

    try:

        value = data.get(
            "total_count"
        )

        if value is not None:
            return int(value)

    except Exception:
        pass


    return 0


# =========================================================
# MAIN
# =========================================================

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


    # =====================================================
    # OPEN MEESHO
    # =====================================================

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


    # =====================================================
    # LOGIN CHECK
    # =====================================================

    current_url = page.url.lower()

    if (
        "login" in current_url
        or "signin" in current_url
        or "sign-in" in current_url
    ):

        print(
            "❌ Meesho session has expired."
        )

        browser.close()
        sys.exit(1)


    print(
        "✅ Meesho session appears active!"
    )


    # =====================================================
    # DIRECT MEESHO API FUNCTION
    # =====================================================

    def get_order_count(status):

        order_type = STATUS_MAP[status]

        print()
        print(
            f"🔎 Requesting {order_type} "
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


        # -------------------------------------------------
        # Run fetch INSIDE authenticated Meesho browser
        # -------------------------------------------------

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

                    const text = await response.text();

                    return {
                        status: response.status,
                        text: text
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
                f"❌ Browser API request failed "
                f"for {order_type}:"
            )

            print(error)

            return 0


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


        # -------------------------------------------------
        # HTTP error
        # -------------------------------------------------

        if http_status != 200:

            print(
                f"❌ Meesho rejected "
                f"{order_type} request."
            )

            print(
                response_text[:1000]
            )

            return 0


        # -------------------------------------------------
        # Parse response
        # -------------------------------------------------

        try:

            data = json.loads(
                response_text
            )

        except json.JSONDecodeError:

            print(
                f"❌ Meesho returned "
                f"non-JSON for {order_type}."
            )

            print(
                response_text[:500]
            )

            return 0


        # -------------------------------------------------
        # Extract count
        # -------------------------------------------------

        count = extract_count(
            data
        )


        print(
            f"📦 {order_type}: {count}"
        )


        # -------------------------------------------------
        # Show useful debugging info
        # -------------------------------------------------

        if order_type == "cancelled":

            print(
                "🔍 Cancelled API response:"
            )

            print(
                json.dumps(
                    data,
                    indent=2
                )[:3000]
            )


        return count


    # =====================================================
    # REQUEST ALL FOUR STATUSES
    # =====================================================

    print()
    print(
        "======================================"
    )

    print(
        "   DIRECT MEESHO API CHECK"
    )

    print(
        "======================================"
    )


    for status, order_type in STATUS_MAP.items():

        counts[order_type] = get_order_count(
            status
        )

        page.wait_for_timeout(
            1500
        )


    # =====================================================
    # SUMMARY
    # =====================================================

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
        f"🟡 Pending:       "
        f"{counts['pending']}"
    )

    print(
        f"📦 Ready to Ship: "
        f"{counts['ready-to-ship']}"
    )

    print(
        f"🚚 Shipped:       "
        f"{counts['shipped']}"
    )

    print(
        f"❌ Cancelled:     "
        f"{counts['cancelled']}"
    )

    print(
        "======================================"
    )


    # =====================================================
    # TELEGRAM
    # =====================================================

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


    # =====================================================
    # CLOSE
    # =====================================================

    browser.close()


    if success:

        print()
        print(
            "======================================"
        )

        print(
            "✅ REPORT COMPLETED!"
        )

        print(
            "======================================"
        )

    else:

        print(
            "\n❌ Report completed "
            "with Telegram error."
        )

        sys.exit(1)
