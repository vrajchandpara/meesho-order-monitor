from playwright.sync_api import sync_playwright
import requests
import json
import re
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


# =========================================================
# CHECK TELEGRAM TOKEN
# =========================================================

if not BOT_TOKEN:

    print("❌ TELEGRAM_BOT_TOKEN secret is missing.")

    sys.exit(1)


# =========================================================
# CHECK SESSION FILE
# =========================================================

if not os.path.exists(SESSION_FILE):

    print("❌ meesho_session.json was not created.")

    sys.exit(1)


# =========================================================
# ORDER COUNTS
# =========================================================

counts = {
    "pending": 0,
    "ready-to-ship": 0,
    "shipped": 0,
    "cancelled": 0
}


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

            print("✅ Telegram message sent successfully!")

            return True

        print("❌ Telegram error:")
        print(response.text)

        return False

    except Exception as error:

        print("❌ Telegram connection error:")
        print(error)

        return False


# =========================================================
# MAIN
# =========================================================

with sync_playwright() as p:

    print("🚀 Starting Chromium...")

    browser = p.chromium.launch(
        headless=True
    )

    context = browser.new_context(
        storage_state=SESSION_FILE
    )

    page = context.new_page()

    print("🌐 Opening Meesho...")

    try:

        page.goto(
            MEESHO_URL,
            wait_until="domcontentloaded",
            timeout=60000
        )

    except Exception as error:

        print("❌ Could not open Meesho:")
        print(error)

        browser.close()
        sys.exit(1)


    page.wait_for_timeout(5000)

    print("URL:")
    print(page.url)

    print("Title:")
    print(page.title())


    # =====================================================
    # LOGIN CHECK
    # =====================================================

    if "login" in page.url.lower():

        print("❌ Meesho session is expired or invalid.")

        browser.close()
        sys.exit(1)


    print("✅ Meesho session appears active!")


    # =====================================================
    # CAPTURE MEESHO API RESPONSES
    # =====================================================

    def handle_response(response):

        if not response.url.endswith(
            "/api/fulfillment/orders"
        ):
            return

        if response.request.method != "POST":
            return

        try:

            payload = response.request.post_data

            if not payload:
                return

            request_data = json.loads(payload)

            order_type = request_data.get("type")

            if order_type not in counts:
                return

            data = response.json()

            count = data.get(
                "data",
                {}
            ).get(
                "count",
                data.get(
                    "total_count",
                    0
                )
            )

            count = int(count)

            # Meesho can send multiple responses.
            # Keep the highest count received.

            if count > counts[order_type]:

                counts[order_type] = count

            print(
                f"📦 {order_type}: {count}"
            )

        except Exception:
            pass


    page.on(
        "response",
        handle_response
    )


    # =====================================================
    # CHECK ORDER TABS
    # =====================================================

    tabs = [
        "Pending",
        "Ready to Ship",
        "Shipped",
        "Cancelled"
    ]


    print("\n📊 Collecting Meesho order counts...\n")


    for tab_name in tabs:

        print(
            f"🔄 Checking {tab_name}..."
        )

        try:

            tab = page.get_by_role(
                "tab",
                name=re.compile(
                    f"^{re.escape(tab_name)}"
                )
            )

            tab.click()

            page.wait_for_timeout(3000)

        except Exception as error:

            print(
                f"⚠️ Could not click {tab_name}: "
                f"{error}"
            )


    # =====================================================
    # SUMMARY
    # =====================================================

    print("\n")
    print("======================================")
    print("       MEESHO ORDER SUMMARY")
    print("======================================")

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

    print("======================================")


    # =====================================================
    # TELEGRAM MESSAGE
    # =====================================================

    message = f"""📊 MEESHO ORDER UPDATE

🟡 Pending: {counts['pending']}
📦 Ready to Ship: {counts['ready-to-ship']}
🚚 Shipped: {counts['shipped']}
❌ Cancelled: {counts['cancelled']}

⚡ Automated Meesho Report
"""


    print("\n📱 Sending Telegram report...")

    success = send_telegram(message)


    # =====================================================
    # CLOSE
    # =====================================================

    browser.close()

    if success:

        print("\n✅ Report completed!")

    else:

        print("\n❌ Report completed with Telegram error.")

        sys.exit(1)
