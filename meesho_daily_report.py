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
# CHECK SESSION
# =========================================================

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
# ORDER COUNTS
# =========================================================

counts = {
    "pending": 0,
    "ready-to-ship": 0,
    "shipped": 0,
    "cancelled": 0
}


# =========================================================
# STATUS MAPPING
# =========================================================

STATUS_MAP = {
    1: "pending",
    3: "ready-to-ship",
    4: "shipped",
    5: "cancelled"
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
# EXTRACT COUNT
# =========================================================

def extract_count(data):

    if not isinstance(data, dict):
        return None


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

    except (
        TypeError,
        ValueError,
        AttributeError
    ):

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

    except (
        TypeError,
        ValueError
    ):

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

        print("❌ Could not create browser:")
        print(error)

        browser.close()
        sys.exit(1)


    # =====================================================
    # MEESHO API RESPONSE HANDLER
    # =====================================================

    def handle_response(response):

        try:

            # Only Meesho orders API
            if not response.url.endswith(
                "/api/fulfillment/orders"
            ):
                return


            # Only POST
            if response.request.method != "POST":
                return


            payload = response.request.post_data


            if not payload:
                return


            payload = payload.strip()


            # ---------------------------------------------
            # Parse request JSON safely
            # ---------------------------------------------

            try:

                request_data = json.loads(
                    payload
                )

            except json.JSONDecodeError:

                print(
                    "⚠️ Ignored non-JSON request."
                )

                return


            if not isinstance(
                request_data,
                dict
            ):
                return


            # ---------------------------------------------
            # Get type
            # ---------------------------------------------

            order_type = request_data.get(
                "type"
            )


            # ---------------------------------------------
            # Get status
            # ---------------------------------------------

            status = request_data.get(
                "status"
            )


            try:

                status = int(status)

            except (
                TypeError,
                ValueError
            ):

                status = None


            # ---------------------------------------------
            # Determine correct order category
            # ---------------------------------------------

            category = None


            # Prefer explicit type
            if order_type in counts:

                category = order_type


            # Otherwise use status
            elif status in STATUS_MAP:

                category = STATUS_MAP[
                    status
                ]


            if category is None:
                return


            # ---------------------------------------------
            # Read response JSON
            # ---------------------------------------------

            try:

                data = response.json()

            except Exception:

                print(
                    f"⚠️ Could not read "
                    f"{category} response."
                )

                return


            # ---------------------------------------------
            # Extract count
            # ---------------------------------------------

            count = extract_count(
                data
            )


            if count is None:

                print(
                    f"⚠️ No count found "
                    f"for {category}."
                )

                return


            # ---------------------------------------------
            # Store count
            # ---------------------------------------------

            counts[category] = max(
                counts[category],
                count
            )


            print(
                f"📦 {category}: {count} "
                f"(status={status})"
            )


        except Exception as error:

            print(
                "⚠️ API response processing error:"
            )

            print(error)


    # Attach listener BEFORE opening Meesho
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


    page.wait_for_timeout(
        7000
    )


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
            "❌ Meesho session expired."
        )

        browser.close()
        sys.exit(1)


    print(
        "✅ Meesho session appears active!"
    )


    # =====================================================
    # CHECK TABS
    # =====================================================

    tabs = [
        "Pending",
        "Ready to Ship",
        "Shipped",
        "Cancelled"
    ]


    print()
    print(
        "📊 Collecting Meesho order counts..."
    )
    print()


    for tab_name in tabs:

        print(
            f"🔄 Checking {tab_name}..."
        )


        try:

            # ---------------------------------------------
            # Find tab
            # ---------------------------------------------

            tab = page.get_by_role(
                "tab",
                name=re.compile(
                    f"^{re.escape(tab_name)}",
                    re.IGNORECASE
                )
            ).first


            # ---------------------------------------------
            # Click
            # ---------------------------------------------

            tab.click(
                timeout=15000
            )


            # ---------------------------------------------
            # Give API time to respond
            # ---------------------------------------------

            page.wait_for_timeout(
                5000
            )


        except Exception as error:

            print(
                f"⚠️ Could not click "
                f"{tab_name}:"
            )

            print(error)


    # =====================================================
    # EXTRA WAIT
    # =====================================================

    print()
    print(
        "⏳ Waiting for final Meesho responses..."
    )

    page.wait_for_timeout(
        5000
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
            "✅ Report completed!"
        )

    else:

        print()
        print(
            "❌ Report completed "
            "with Telegram error."
        )

        sys.exit(1)
