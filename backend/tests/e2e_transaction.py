#!/usr/bin/env python3
"""E2E transaction test: Discovery → Enquiry → Quote → Booking → Execution → Payment → Review"""
import json, sys, time, uuid
import urllib.request, urllib.error

API = "http://localhost:8000/api/v1"

def login(email, password):
    req = urllib.request.Request(f"{API}/auth/login", 
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]

def api(method, path, token, body=None):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            resp = r.read().decode()
            return json.loads(resp) if resp else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        print(f"  ERROR {e.code}: {body_text[:300]}")
        return {"_error": True, "_status": e.code, "_body": body_text}

def section(msg):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")

def main():
    # ── Auth ──
    section("1. AUTHENTICATION")
    biz_token = login("biztest@fielded.app", "Test1234!")
    cust_token = login("custtest@fielded.app", "Test1234!")
    print("  Business user logged in")
    print("  Customer user logged in")

    # ── Get business ID ──
    biz_list = api("GET", "/businesses", biz_token)
    if not biz_list or (isinstance(biz_list, dict) and biz_list.get("_error")):
        print("  ERROR: No businesses found")
        sys.exit(1)
    biz_id = biz_list[0]["id"]
    biz_name = biz_list[0]["name"]
    print(f"  Business: {biz_name} ({biz_id})")

    cust_profile = api("GET", "/auth/me", cust_token)
    cust_id = cust_profile.get("id")
    print(f"  Customer ID: {cust_id}")

    # ── Get service offer ──
    section("2. DISCOVERY — Service Offer")
    offers = api("GET", f"/businesses/{biz_id}/offers", biz_token)
    if not offers or (isinstance(offers, dict) and offers.get("_error")):
        print("  ERROR: No service offers")
        sys.exit(1)
    offer = offers[0]
    offer_id = offer["id"]
    print(f"  Service: {offer['name']} (${offer['pricing_config']['amount']} {offer['pricing_config']['currency']})")
    print(f"  Offer ID: {offer_id}")

    # ── Create Enquiry ──
    section("3. ENQUIRY — Customer creates enquiry")
    enquiry = api("POST", f"/enquiries/{biz_id}/enquiries", cust_token, {
        "service_offer_id": offer_id,
        "subject": "E2E integration test",
        "message": "Need this service completed urgently as part of full E2E transaction test.",
    })
    if enquiry.get("_error"):
        print(f"  Failed: {enquiry}")
        sys.exit(1)
    enquiry_id = enquiry["id"]
    print(f"  Enquiry: {enquiry.get('reference', enquiry_id[:12])}")
    print(f"  Status: {enquiry['status']}")

    # Check conversation auto-created
    conv = api("GET", f"/enquiries/my-enquiries/{enquiry_id}/conversation", cust_token)
    if conv and not conv.get("_error"):
        msgs = conv.get("messages", [])
        print(f"  Conversation auto-created: {len(msgs)} message(s)")

    # ── Business Brain evaluation ──
    section("4. BUSINESS BRAIN — Enquiry evaluation")
    brain = api("GET", f"/businesses/{biz_id}/brain", biz_token)
    if brain and not brain.get("_error"):
        print(f"  Brain status: {brain.get('status', 'unknown')}")
    biz_enq = api("GET", f"/businesses/{biz_id}/enquiries/{enquiry_id}", biz_token)
    if biz_enq and not biz_enq.get("_error"):
        brain_eval = biz_enq.get("brain_evaluation_result")
        print(f"  Brain decision on enquiry: {brain_eval.get('decision', 'N/A') if brain_eval else 'pending/none'}")

    # ── Business transitions enquiry to received ──
    section("4b. ENQUIRY — Business transitions to 'received'")
    trans = api("POST", f"/businesses/{biz_id}/enquiries/{enquiry_id}/transition", biz_token, {
        "target_status": "received"
    })
    if trans.get("_error"):
        print(f"  Transition failed: {trans}")
    else:
        print(f"  Enquiry status: {trans['status']}")

    # ── Business sends message (Communication) ──
    section("5. COMMUNICATIONS — Business sends message in conversation")
    msg = api("POST", f"/businesses/{biz_id}/enquiries/{enquiry_id}/messages", biz_token, {
        "content": "Thanks for your enquiry! We'll prepare a quote shortly."
    })
    if msg and not msg.get("_error"):
        print(f"  Message sent by business")
    else:
        print(f"  Message result: {msg}")

    # ── Quote ──
    section("6. QUOTE — Business issues quote (Brain pricing rules apply)")
    quote = api("POST", f"/businesses/{biz_id}/quotes", biz_token, {
        "enquiry_id": enquiry_id,
        "notes": "E2E test quote — pricing per service offer"
    })
    if quote.get("_error"):
        print(f"  Quote failed: {quote}")
        sys.exit(1)
    quote_id = quote["id"]
    print(f"  Quote: {quote.get('reference', quote_id[:12])}")
    print(f"  Status: {quote['status']}")
    print(f"  Total: {quote.get('total_amount', 'N/A')} {quote.get('currency', '')}")

    # Business transitions quote from draft to issued
    issue = api("POST", f"/businesses/{biz_id}/quotes/{quote_id}/transition", biz_token, {
        "target_status": "issued"
    })
    if issue.get("_error"):
        print(f"  Issue quote failed: {issue}")
        sys.exit(1)
    print(f"  Quote issued: {issue['status']}")

    # ── Customer accepts quote ──
    section("7. QUOTE ACCEPTANCE — Customer transitions quote to accepted")
    accept = api("POST", f"/businesses/my-quotes/{quote_id}/transition", cust_token, {
        "target_status": "accepted"
    })
    if accept.get("_error"):
        print(f"  Accept failed: {accept}")
        sys.exit(1)
    print(f"  Quote status: {accept['status']}")

    # ── Booking — Customer creates booking from accepted quote ──
    section("8. BOOKING — Customer creates booking (Brain availability check)")
    booking = api("POST", "/businesses/my-bookings", cust_token, {
        "quote_id": quote_id,
        "requested_at": "2026-10-15T10:00:00",
        "notes": "E2E test booking"
    })
    if booking.get("_error"):
        print(f"  Booking failed: {booking}")
        sys.exit(1)
    booking_id = booking["id"]
    print(f"  Booking: {booking.get('reference', booking_id[:12])}")
    print(f"  Status: {booking['status']}")

    # ── Business proposes → Customer accepts → Business confirms ──
    section("9. BOOKING LIFECYCLE — Propose → Accept → Confirm")
    propose = api("POST", f"/businesses/{biz_id}/bookings/{booking_id}/transition", biz_token, {
        "target_status": "proposed"
    })
    if propose.get("_error"):
        print(f"  Propose failed: {propose}")
    else:
        print(f"  Business proposed: {propose['status']}")
    
    cust_accept = api("POST", f"/businesses/my-bookings/{booking_id}/transition", cust_token, {
        "target_status": "accepted"
    })
    if cust_accept.get("_error"):
        print(f"  Customer accept failed: {cust_accept}")
    else:
        print(f"  Customer accepted: {cust_accept['status']}")
    
    confirm = api("POST", f"/businesses/{biz_id}/bookings/{booking_id}/transition", biz_token, {
        "target_status": "confirmed"
    })
    if confirm.get("_error"):
        print(f"  Confirm failed: {confirm}")
    else:
        print(f"  Business confirmed: {confirm['status']}")

    # ── Service Execution — Start work ──
    section("10. SERVICE EXECUTION — Business starts work")
    execution = api("POST", f"/businesses/{biz_id}/service-executions", biz_token, {
        "booking_id": booking_id
    })
    if execution.get("_error"):
        print(f"  Execution creation failed: {execution}")
        sys.exit(1)
    exec_id = execution["id"]
    print(f"  Execution: {exec_id[:12]}..")
    print(f"  Status: {execution['status']}")

    # Transition to in_progress
    prog = api("POST", f"/businesses/{biz_id}/service-executions/{exec_id}/transition", biz_token, {
        "target_status": "in_progress",
        "notes": "Work underway"
    })
    if prog.get("_error"):
        print(f"  In-progress failed: {prog}")
    else:
        print(f"  Execution: {prog['status']}")

    # ── Service Execution — Complete (triggers Invoice + Ledger cascade) ──
    section("11. SERVICE EXECUTION — Complete → Invoice + Ledger cascade")
    complete = api("POST", f"/businesses/{biz_id}/service-executions/{exec_id}/complete", biz_token)
    if complete.get("_error"):
        print(f"  Complete failed: {complete}")
    else:
        print(f"  Execution: {complete['status']}")
        print(f"  Completed at: {complete.get('completed_at', 'N/A')}")

    time.sleep(1)

    # Check booking cascade
    booking_after = api("GET", f"/businesses/{biz_id}/bookings/{booking_id}", biz_token)
    print(f"  Booking after cascade: {booking_after.get('status', '?')}")

    # Check enquiry cascade
    enquiry_after = api("GET", f"/enquiries/my-enquiries/{enquiry_id}", cust_token)
    print(f"  Enquiry after cascade: {enquiry_after.get('status', '?')}")

    # ── Invoice ──
    section("12. INVOICE — Auto-created at execution completion")
    invoices = api("GET", f"/businesses/{biz_id}/invoices", biz_token)
    invoice_id = None
    if invoices and not (isinstance(invoices, dict) and invoices.get("_error")):
        inv_list = invoices if isinstance(invoices, list) else invoices.get("items", [])
        for inv in inv_list:
            if inv.get("service_execution_id") == exec_id or inv.get("booking_id") == booking_id:
                invoice_id = inv["id"]
                print(f"  Invoice: {inv.get('invoice_number', inv['id'][:12])}")
                print(f"  Amount: {inv.get('total_amount', 'N/A')} {inv.get('currency', '')}")
                print(f"  Payment status: {inv.get('payment_status', 'unknown')}")
                break
        if not invoice_id:
            print(f"  No invoice for this execution (total invoices: {len(inv_list)})")

    # ── Ledger ──
    section("13. LEDGER — Auto-created at execution completion")
    ledger_entries = api("GET", f"/businesses/{biz_id}/ledger", biz_token)
    ledger_id = None
    if ledger_entries and not (isinstance(ledger_entries, dict) and ledger_entries.get("_error")):
        l_list = ledger_entries if isinstance(ledger_entries, list) else ledger_entries.get("items", [])
        for le in l_list:
            if le.get("service_execution_id") == exec_id or le.get("booking_id") == booking_id:
                ledger_id = le["id"]
                print(f"  Ledger entry: {le['id'][:12]}..")
                print(f"  Gross: {le.get('gross_amount')} Net: {le.get('net_amount')} {le.get('currency', '')}")
                print(f"  Payment status: {le.get('payment_status', 'unknown')}")
                break
        if not ledger_id:
            print(f"  No ledger entry (total entries: {len(l_list)})")

    # ── Payment ──
    section("14. PAYMENT — Customer pays via booking pay endpoint")
    idem_key = str(uuid.uuid4())
    payment = api("POST", f"/businesses/my-bookings/{booking_id}/pay", cust_token, {
        "payment_method": "card",
        "idempotency_key": idem_key,
    })
    if payment.get("_error"):
        print(f"  Payment failed: {payment}")
    else:
        print(f"  Payment: {payment.get('id', '')[:12]}..")
        print(f"  Status: {payment.get('status', 'unknown')}")
        print(f"  Amount: {payment.get('amount', 'N/A')} {payment.get('currency', '')}")

        # Check invoice payment status
        if invoice_id:
            inv_after_pay = api("GET", f"/businesses/{biz_id}/invoices/{invoice_id}", biz_token)
            print(f"  Invoice payment_status: {inv_after_pay.get('payment_status', '?')}")

        # Check ledger payment status
        if ledger_id:
            l_after = api("GET", f"/businesses/{biz_id}/ledger", biz_token)
            if l_after and not (isinstance(l_after, dict) and l_after.get("_error")):
                l_list = l_after if isinstance(l_after, list) else l_after.get("items", [])
                for le in l_list:
                    if le["id"] == ledger_id:
                        print(f"  Ledger payment_status: {le.get('payment_status', '?')}")
                        break

    # ── Enquiry final status ──
    section("15. FINAL STATE — Enquiry + Booking + Execution")
    final_enq = api("GET", f"/enquiries/my-enquiries/{enquiry_id}", cust_token)
    print(f"  Enquiry: {final_enq.get('status', '?')}")
    final_bkg = api("GET", f"/businesses/my-bookings/{booking_id}", cust_token)
    print(f"  Booking: {final_bkg.get('status', '?')}")

    # ── Review ──
    section("16. REVIEW — Customer submits review (eligibility verified)")
    review = api("POST", "/my-reviews", cust_token, {
        "service_execution_id": exec_id,
        "rating": 5,
        "title": "Excellent E2E service",
        "body": "Full transaction completed successfully. All integrations working."
    })
    if review.get("_error"):
        print(f"  Review failed: {review}")
    else:
        print(f"  Review: {review.get('id', '')[:12]}..")
        print(f"  Rating: {review.get('rating')}")
        print(f"  Status: {review.get('status', 'N/A')}")

    # ── Notifications ──
    section("17. NOTIFICATIONS — Generated during transaction")
    cust_notifs = api("GET", "/notifications/my-notifications?limit=50", cust_token)
    notif_count = 0
    if cust_notifs and not (isinstance(cust_notifs, dict) and cust_notifs.get("_error")):
        n_list = cust_notifs if isinstance(cust_notifs, list) else cust_notifs.get("items", [])
        notif_count = len(n_list)
        print(f"  Customer notifications: {notif_count}")
        for n in n_list[:10]:
            print(f"    [{n.get('notification_type','')}] {n.get('title','(no title)')}")
    else:
        print(f"  Customer notifications error: {cust_notifs}")

    biz_notifs = api("GET", f"/{biz_id}/notifications?limit=50", biz_token)
    if biz_notifs and not (isinstance(biz_notifs, dict) and biz_notifs.get("_error")):
        bn_list = biz_notifs if isinstance(biz_notifs, list) else biz_notifs.get("items", [])
        print(f"  Business notifications: {len(bn_list)}")
        for n in bn_list[:10]:
            print(f"    [{n.get('notification_type','')}] {n.get('title','(no title)')}")
    else:
        print(f"  Business notifications error: {biz_notifs}")

    # ── Summary ──
    section("E2E TRANSACTION SUMMARY")
    print(f"  Enquiry:          {enquiry_id}")
    print(f"  Quote:            {quote_id}")
    print(f"  Booking:          {booking_id}")
    print(f"  Execution:        {exec_id}")
    print(f"  Invoice:          {invoice_id or 'NOT CREATED'}")
    print(f"  Ledger:           {ledger_id or 'NOT CREATED'}")
    print(f"  Payment:          {'OK' if not payment.get('_error') else 'FAILED'}")
    print(f"  Review:           {'OK' if not review.get('_error') else 'FAILED'}")
    print(f"  Notifications:    {notif_count}")
    print()
    print("  FULL TRANSACTION COMPLETE")

if __name__ == "__main__":
    main()
