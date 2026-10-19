# College Event Kit Relay System — LLD Architecture & Implementation

An executable Low-Level Design (LLD) implementation for the **College Event Kit Relay System**, featuring:
1. **Timing, Dates & Operational Gap Validations**: Strict enforcement of college operating hours (09:00 - 17:00), past time-slot prevention, minimum slot duration (15 min), single-day slot bounds, and mandatory 15-minute post-event inspection gap buffers between bookings.
2. **Kit Availability & Completeness Checks**: Kit handover and booking are strictly validated against physical equipment readiness. All components (Camera, Microphone, Tripod) must be assigned and in USABLE condition with zero active maintenance blocks.
3. **Immediate College Buffer Replacement**: When a team returns a damaged or missing component, the college replaces the item immediately from campus spare buffer inventory so the shared primary kit remains 100% complete and usable for subsequent reservations.
4. **Conditional Damage Invoicing in Indian Rupees (₹ / INR)**:
   - **Undamaged Return**: If all items pass inspection in `GOOD` condition, **no invoice is issued**, and zero penalty is billed.
   - **Damaged or Missing Return**: If damage occurs, an itemized penalty invoice in **Indian Rupees (₹)** is generated based on standard quotes (repair fee or replacement valuation + 15% college handling surcharge, min ₹100).
5. **Financial Standing & Booking Debarment**: Clubs with overdue or unsettled damage claims are automatically placed in `DEBARRED` standing, restricting further kit reservations (HTTP 403) via the **Chain of Responsibility** validation pipeline.
6. **Transparent Payment Portal & Real-Time Standing Restoration**: Supports online payment settlement in INR (₹). Once all dues are cleared, club booking privileges are instantly restored.

---

## 1. Indian Rupee (INR / ₹) Standardized Rate Card

| Component | Equipment Type | Base Repair Quote (₹) | Full Replacement Valuation (₹) | Handling Surcharge |
| :--- | :--- | :--- | :--- | :--- |
| **Camera** | `CAMERA` | ₹2,500.00 | ₹38,000.00 | 15% (min ₹100) |
| **Microphone** | `MICROPHONE` | ₹700.00 | ₹6,500.00 | 15% (min ₹100) |
| **Tripod** | `TRIPOD` | ₹450.00 | ₹3,200.00 | 15% (min ₹100) |

---

## 2. Architecture & Directory Structure

```
student_kit/
├── domain/
│   ├── models.py             # Pydantic domain models, state machines & enums
│   └── rate_card.py          # Repair quotes, replacement valuations & admin fee logic (INR / ₹)
├── repository/
│   └── memory_repo.py        # Thread-safe in-memory repository for kits, clubs & invoices
├── services/
│   ├── cost_evaluator.py     # Damage cost evaluation service (INR / ₹)
│   ├── kit_replacement.py    # College buffer swap logic ensuring kit continuity
│   ├── billing_service.py    # Invoicing, payment validation & club financial ledger (INR / ₹)
│   ├── reservation_pipeline.py # Chain of Responsibility filter pipeline (timing, gap & debarment)
│   ├── reservation_service.py  # Slot booking, checkout, and return inspection
│   └── availability_service.py # Calendar slot availability and buffer calculations
├── api/
│   ├── schemas.py            # API request/response DTOs
│   └── routes.py             # REST API routes
├── static/                   # Interactive Glassmorphic Control Dashboard
│   ├── index.html            # User and Admin portals
│   ├── style.css             # Glassmorphic UI styling
│   └── app.js                # Dynamic client controller (INR formatting & validation)
├── tests/
│   └── test_lld_flow.py      # Automated LLD acceptance test suite
├── main.py                   # FastAPI server entry point
└── README.md
```

---

## 3. Running the Automated Test Suite

Run the full end-to-end acceptance test suite covering:
- Slot booking with 15-minute gap validation
- Past time-slot and operating hours (09:00 - 17:00) validation
- Handover and checkout inspection
- Return with damage (assessed in Indian Rupees)
- Immediate college spare replacement
- Debarment booking restriction enforcement in INR (₹)
- Settlement and privilege restoration
- Clean return with 100% intact items (verifying **zero invoice issued**)

```bash
python tests/test_lld_flow.py
```

---

## 4. Running the Live Interactive Web Controller

Launch the interactive web dashboard:

```bash
python main.py
```

Dashboard is accessible at: `http://127.0.0.1:8085` (or configured port).
