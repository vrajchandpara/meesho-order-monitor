from playwright.sync_api import sync_playwright
import requests
import json
import re
import os
import sys
import time


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
# VERIFY SESSION JSON
# =========================================================

try:

    with open(
        SESSION_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        session_data = json.load(f)

    if not isinstance(session_data, dict):
        print("❌ Meesho session file is invalid.")
        sys.exit(1)

    print("✅ Meesho session JSON is valid.")

except Exception as error:

    print("❌ Could not read Meesho session:")
    print(error)
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
# RESPONSE TRACKING
# =========================================================

responses_received = {
    "pending": False,
    "ready-to-ship": False,
    "shipped": False,
    "cancelled": False
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
# EXTRACT COUNT FROM RESPONSE
# =========================================================

def extract_count(data):

    if not isinstance(data, dict):
        return None

    # Preferred location
    try:

        value = data.get(
            "data",
            {}
        ).get(
            "count"
        )

        if value is not None:
            return int(value)

    except (TypeError, ValueError, AttributeError):
        pass


    # Alternative location
    try:

        value = data.get("total_count")

        if value is not None:
            return int(value)

    except (TypeError, ValueError):
        pass


    return None


# =========================================================
# MAIN
# =========================================================

with sync_playwright() as p:

    print("🚀 Starting Chromium...")

    try:

        browser = p.chromium.launch(
            headless=True
        )

    except Exception as error:

        print("❌ Could not start Chromium:")
        print(error)

        sys.exit(1)


    try:

        context = browser.new_context(
            storage_state=SESSION_FILE
        )

        page = context.new_page()

    except Exception as error:

        print("❌ Could not create browser context:")
        print(error)

        browser.close()
        sys.exit(1)


    # =====================================================
    # CAPTURE MEESHO API RESPONSES
    # =====================================================

    def handle_response(response):

        # Only the Meesho orders API
        if not response.url.endswith(
            "/api/fulfillment/orders"
        ):
            return


        # Only POST requests
        if response.request.method != "POST":
            return


        try:

            payload = response.request.post_data


            # -------------------------------------------------
            # Some requests have no payload
            # -------------------------------------------------

            if not payload:
                return


            payload = payload.strip()


            # -------------------------------------------------
            # Ignore obviously non-JSON payloads
            # -------------------------------------------------

            if not (
                payload.startswith("{")
                or payload.startswith("[")
            ):
                return


            # -------------------------------------------------
            # Safely parse request JSON
            # -------------------------------------------------

            try:

                request_data = json.loads(
                    payload
                )

            except json.JSONDecodeError:

                print(
                    "⚠️ Ignored invalid JSON request payload."
                )

                return


            if not isinstance(
                request_data,
                dict
            ):
                return


            # -------------------------------------------------
            # Identify order type
            # -------------------------------------------------

            order_type = request_data.get(
                "type"
            )


            if order_type not in counts:
                return


            # -------------------------------------------------
            # Read response JSON safely
            # -------------------------------------------------

            try:

                data = response.json()

            except Exception:

                print(
                    f"⚠️ Could not read "
                    f"{order_type} response as JSON."
                )

                return


            # -------------------------------------------------
            # Extract count
            # -------------------------------------------------

            count = extract_count(data)


            if count is None:
                print(
                    f"⚠️ No count found for "
                    f"{order_type}."
                )

                return


            # -------------------------------------------------
            # Keep highest valid count
            # -------------------------------------------------

            if count > counts[order_type]:

                counts[order_type] = count


            responses_received[
                order_type
            ] = True


            print(
                f"📦 {order_type}: {count}"
            )


        except Exception as error:

            # Never allow one unexpected Meesho
            # request to crash the entire workflow.

            print(
                "⚠️ Ignored unexpected response:"
            )

            print(error)


    page.on(
        "response",
        handle_response
    )


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

    except Exception as error:

        print("❌ Could not open Meesho:")
        print(error)

        browser.close()
        sys.exit(1)


    # Give Meesho time to initialize
    page.wait_for_timeout(7000)


    print("\nURL:")
    print(page.url)

    print("\nTitle:")
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
            "❌ Meesho session is expired or invalid."
        )

        browser.close()
        sys.exit(1)


    print(
        "✅ Meesho session appears active!"
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


    print(
        "\n📊 Collecting Meesho order counts...\n"
    )


    for tab_name in tabs:

        print(
            f"🔄 Checking {tab_name}..."
        )


        try:

            # ---------------------------------------------
            # Find the tab
            # ---------------------------------------------

            tab = page.get_by_role(
                "tab",
                name=re.compile(
                    f"^{re.escape(tab_name)}"
                )
            )


            # ---------------------------------------------
            # Click tab
            # ---------------------------------------------

            tab.first.click(
                timeout=15000
            )


            # ---------------------------------------------
            # Wait for Meesho API request
            # ---------------------------------------------

            page.wait_for_timeout(4000)


        except Exception as error:

            print(
                f"⚠️ Could not click "
                f"{tab_name}:"
            )

            print(error)


    # =====================================================
    # EXTRA WAIT
    # =====================================================

    # Allow final API responses to arrive.
    page.wait_for_timeout(3000)


    # =====================================================
    # SUMMARY
    # =====================================================

    print("\n")
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
    # SHOW CAPTURE STATUS
    # =====================================================

    print("\n📡 API capture status:")

    for order_type, received in responses_received.items():

        if received:

            print(
                f"   ✅ {order_type}"
            )

        else:

            print(
                f"   ⚠️ {order_type} "
                f"response not detected"
            )


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


    print(
        "\n📱 Sending Telegram report..."
    )


    success = send_telegram(
        message
    )


    # =====================================================
    # CLOSE BROWSER
    # =====================================================

    browser.close()


    if success:

        print(
            "\n✅ Report completed!"
        )

    else:

        print(
            "\n❌ Report completed "
            "with Telegram error."
        )

        sys.exit(1)
