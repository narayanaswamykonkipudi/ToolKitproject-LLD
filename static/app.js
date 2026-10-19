// College Event Kit Relay System - Student & Admin Portal Controller

let currentState = null;
let currentSlots = [];
let activeModule = "user"; // 'user' (Student) or 'admin' (College Desk)
let activeUserTab = "book"; // 'book', 'my-bookings', 'payments'
let bookingMode = "hours"; // 'hours' or 'days'
let selectedStudentId =null;

document.addEventListener("DOMContentLoaded", async () => {
  // Set default booking date to today
  const today = new Date().toISOString().split("T")[0];
  const userDateInput = document.getElementById("user-booking-date");
  if (userDateInput) userDateInput.value = today;

  const daysStartDateInput = document.getElementById("days-start-date");
  if (daysStartDateInput) daysStartDateInput.value = today;

  // Dismiss modal if clicking backdrop outside content
  document.querySelectorAll(".modal-backdrop").forEach(m => {
    m.addEventListener("click", (e) => {
      if (e.target === m) {
        m.classList.add("modal-hidden");
      }
    });
  });

  await fetchState();

  // Bind Form Events
  document.getElementById("user-booking-form").addEventListener("submit", handleUserBookingSubmit);
  document.getElementById("return-inspection-form").addEventListener("submit", (e) => e.preventDefault());
  document.getElementById("maint-form").addEventListener("submit", handleMaintSubmit);
  document.getElementById("reschedule-form").addEventListener("submit", handleRescheduleSubmit);

  // Initial calculation preview
  updateBookingPreview();
});

// ==========================================
// DATA FETCHING & STATE MANAGEMENTS
// ==========================================
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    currentState = await res.json();

    // Populate student options
    populateStudentSelector();
    
    // Refresh currently visible module
    if (activeModule === "user") {
      await refreshUserModule();
    } else {
      await refreshAdminModule();
    }

    renderGlobalKitStatus();
  } catch (err) {
    console.error("Failed to fetch state:", err);
  }
}

function renderGlobalKitStatus() {
  if (!currentState || !currentState.kits || currentState.kits.length === 0) return;
  const primaryKit = currentState.kits[0];
  const badge = document.getElementById("kit-health-badge");
  if (primaryKit.is_complete_and_usable) {
    badge.className = "badge badge-success";
    badge.innerHTML = `<span class="status-dot"></span> Kit Complete & Usable`;
  } else {
    badge.className = "badge badge-danger";
    badge.innerHTML = `<span class="status-dot"></span> Kit Incomplete / Defective`;
  }
}

// ==========================================
// MODULE & TAB SWITCHING
// ==========================================
function switchModule(moduleName) {
  activeModule = moduleName;
  const userMod = document.getElementById("user-module");
  const adminMod = document.getElementById("admin-module");
  const btnUser = document.getElementById("btn-user-mode");
  const btnAdmin = document.getElementById("btn-admin-mode");

  if (moduleName === "user") {
    userMod.classList.remove("module-hidden");
    adminMod.classList.add("module-hidden");
    btnUser.classList.add("active");
    btnAdmin.classList.remove("active");
    refreshUserModule();
  } else {
    userMod.classList.add("module-hidden");
    adminMod.classList.remove("module-hidden");
    btnUser.classList.remove("active");
    btnAdmin.classList.add("active");
    refreshAdminModule();
  }
}

function switchUserTab(tabName) {
  activeUserTab = tabName;
  const tabs = ["book", "my-bookings", "payments"];
  tabs.forEach(t => {
    const content = document.getElementById(`user-tab-${t}`);
    if (content) {
      if (t === tabName) {
        content.classList.add("active");
        content.style.display = "block";
      } else {
        content.classList.remove("active");
        content.style.display = "none";
      }
    }
  });

  // Update tab button styles
  const tabBtns = document.querySelectorAll(".tab-nav .tab-btn");
  tabBtns.forEach((btn, idx) => {
    if (tabs[idx] === tabName) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  if (tabName === "book") {
    fetchUserSlots();
    updateBookingPreview();
  } else if (tabName === "my-bookings") {
    renderUserMyBookings();
  } else if (tabName === "payments") {
    renderUserPayments();
  }
}

// ==========================================
// BOOKING MODE TOGGLE (Hours vs Days)
// ==========================================
function switchBookingMode(mode) {
  bookingMode = mode;
  const btnHours = document.getElementById("btn-mode-hours");
  const btnDays = document.getElementById("btn-mode-days");
  const controlsHours = document.getElementById("controls-hours-mode");
  const controlsDays = document.getElementById("controls-days-mode");
  const formHoursRow = document.getElementById("form-hours-time-row");

  if (mode === "hours") {
    btnHours.classList.add("active");
    btnDays.classList.remove("active");
    controlsHours.style.display = "block";
    controlsDays.style.display = "none";
    formHoursRow.style.display = "flex";
    document.getElementById("preview-mode-tag").textContent = "HOURS MODE";
    fetchUserSlots();
  } else {
    btnHours.classList.remove("active");
    btnDays.classList.add("active");
    controlsHours.style.display = "none";
    controlsDays.style.display = "block";
    formHoursRow.style.display = "none";
    document.getElementById("preview-mode-tag").textContent = "MULTI-DAY MODE";
  }

  updateBookingPreview();
}

function applyHourPreset(hours) {
  const startInput = document.getElementById("user-start-time");
  const endInput = document.getElementById("user-end-time");
  if (hours === 8) {
    startInput.value = "09:00";
    endInput.value = "17:00";
  } else {
    let startHour = 9;
    let endHour = Math.min(17, startHour + hours);
    startInput.value = `${String(startHour).padStart(2, '0')}:00`;
    endInput.value = `${String(endHour).padStart(2, '0')}:00`;
  }
  onHoursInputsChanged();
}

function applyDayPreset(days) {
  const select = document.getElementById("days-count-select");
  if (select) {
    select.value = String(days);
    onDaysConfigChanged();
  }
  document.querySelectorAll("#controls-days-mode .preset-pill").forEach(p => {
    if (p.textContent.startsWith(String(days)) || (days === 7 && p.textContent.includes("1 Week")) || (days === 14 && p.textContent.includes("2 Weeks"))) {
      p.classList.add("active");
    } else {
      p.classList.remove("active");
    }
  });
}

function onHoursInputsChanged() {
  updateBookingPreview();
}

function onDaysConfigChanged() {
  updateBookingPreview();
}

// Helper to format values in Indian Rupees (INR / ₹)
function formatINR(val) {
  const num = Number(val) || 0;
  return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ==========================================
// STUDENT PROFILE & SELECTION
// ==========================================
function populateStudentSelector() {
  const select = document.getElementById("user-active-team");
  if (!select) return;

  const prevVal = select.value || selectedStudentId;
  select.innerHTML = "";

  const students = currentState.students || currentState.clubs || [];
  students.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s.student_id || s.club_id;
    const roll = s.roll_number ? `(${s.roll_number})` : '';
    const statusNote = s.financial_standing === 'DEBARRED' ? ' [DEBARRED — PENALTY UNPAID]' : '';
    opt.textContent = `${s.name} ${roll}${statusNote}`;
    select.appendChild(opt);
  });

  if (prevVal && students.some(s => (s.student_id || s.club_id) === prevVal)) {
    select.value = prevVal;
    selectedStudentId = prevVal;
  } else if (students.length > 0) {
    selectedStudentId = students[0].student_id || students[0].club_id;
    select.value = selectedStudentId;
  }
}

async function onUserTeamChanged() {
  selectedStudentId = document.getElementById("user-active-team").value;
  await refreshUserModule();
}

async function refreshUserModule() {
  const students = currentState.students || currentState.clubs || [];
  if (!selectedStudentId && students.length > 0) {
    selectedStudentId = students[0].student_id || students[0].club_id;
  }
  const student = students.find(s => (s.student_id || s.club_id) === selectedStudentId);
  if (!student) return;

  // 1. Update Profile & Standing Header
  document.getElementById("user-form-team-name").value = `${student.name} ${student.roll_number ? '(' + student.roll_number + ')' : ''}`;
  document.getElementById("user-balance-amount").textContent = formatINR(student.outstanding_balance);

  const standingBadge = document.getElementById("user-standing-badge");
  const debarmentNotice = document.getElementById("user-debarment-alert");
  const debarBlockMessage = document.getElementById("debarred-block-message");
  const submitBtn = document.getElementById("btn-user-submit-booking");

  const isDebarred = (student.financial_standing === "DEBARRED" || student.outstanding_balance > 0);

  if (isDebarred) {
    standingBadge.className = "badge badge-danger";
    standingBadge.textContent = "DEBARRED - BOOKING RESTRICTED";
    debarmentNotice.classList.remove("alert-hidden");
    debarBlockMessage.classList.remove("alert-hidden");
    submitBtn.disabled = true;
    submitBtn.textContent = "🚫 Booking Blocked — Settle Damage Fine First";
    submitBtn.className = "btn btn-danger";
  } else {
    standingBadge.className = "badge badge-success";
    standingBadge.textContent = "GOOD STANDING - ELIGIBLE";
    debarmentNotice.classList.add("alert-hidden");
    debarBlockMessage.classList.add("alert-hidden");
    submitBtn.disabled = false;
    submitBtn.textContent = "Confirm Reservation Request";
    submitBtn.className = "btn btn-primary";
  }

  // 2. Refresh active subtab
  if (activeUserTab === "book") {
    await fetchUserSlots();
    await updateBookingPreview();
  } else if (activeUserTab === "my-bookings") {
    renderUserMyBookings();
  } else if (activeUserTab === "payments") {
    renderUserPayments();
  }
}

// ==========================================
// AVAILABLE SLOTS (HOURS MODE)
// ==========================================
async function fetchUserSlots() {
  const dateInput = document.getElementById("user-booking-date");
  if (!dateInput || !currentState.kits[0]) return;
  const dateStr = dateInput.value;
  const kitId = currentState.kits[0].kit_id;

  try {
    const res = await fetch(`/api/availability?date=${dateStr}&team_id=${selectedStudentId}&kit_id=${kitId}`);
    const data = await res.json();
    if (data.success) {
      currentSlots = data.slots;
      renderUserSlotsGrid();
    }
  } catch (err) {
    console.error("Failed to fetch slots:", err);
  }
}

function renderUserSlotsGrid() {
  const container = document.getElementById("user-slots-grid");
  if (!container) return;

  if (!currentSlots || currentSlots.length === 0) {
    container.innerHTML = `<div class="empty-log">No operating slots generated for this date.</div>`;
    return;
  }

  container.innerHTML = currentSlots.map(s => {
    const startStr = s.start_time.substring(11, 16);
    const endStr = s.end_time.substring(11, 16);

    let stateClass = "slot-available";
    let stateLabel = "AVAILABLE";

    if (s.state === "RESERVED") {
      stateClass = "slot-reserved";
      stateLabel = "RESERVED";
    } else if (s.state === "INSPECTION_BUFFER") {
      stateClass = "slot-buffer";
      stateLabel = "15m BUFFER";
    } else if (s.state === "MAINTENANCE_BLOCKED") {
      stateClass = "slot-blocked";
      stateLabel = "MAINTENANCE";
    } else if (s.state === "EQUIPMENT_BLOCKED") {
      stateClass = "slot-blocked";
      stateLabel = "KIT UNUSABLE";
    }

    const isSelectable = (s.state === "AVAILABLE");
    const clickHandler = isSelectable ? `onclick="selectSlotTimes('${startStr}', '${endStr}')"` : '';

    return `
      <div class="slot-card ${stateClass}" ${clickHandler} title="${s.reason}">
        <div class="slot-time">${startStr} - ${endStr}</div>
        <div class="slot-state-tag">${stateLabel}</div>
      </div>
    `;
  }).join("");
}

function selectSlotTimes(startStr, endStr) {
  document.getElementById("user-start-time").value = startStr;
  document.getElementById("user-end-time").value = endStr;
  onHoursInputsChanged();
  showAlert(`Selected slot: ${startStr} - ${endStr}. Click 'Confirm Reservation Request' to proceed.`, "success");
}

// ==========================================
// DYNAMIC BOOKING PREVIEW & AVAILABILITY CHECK
// ==========================================
async function updateBookingPreview() {
  const kit = (currentState && currentState.kits && currentState.kits[0]) ? currentState.kits[0] : null;
  const kitNameEl = document.getElementById("preview-kit-name");
  if (kitNameEl && kit) kitNameEl.textContent = kit.name;

  let startIso, endIso;
  let durationDesc = "";
  let startDesc = "";
  let endDesc = "";

  if (bookingMode === "hours") {
    const dateStr = document.getElementById("user-booking-date")?.value || new Date().toISOString().split("T")[0];
    const startTimeStr = document.getElementById("user-start-time")?.value || "09:00";
    const endTimeStr = document.getElementById("user-end-time")?.value || "10:00";

    startIso = `${dateStr}T${startTimeStr}:00Z`;
    endIso = `${dateStr}T${endTimeStr}:00Z`;

    const sMillis = new Date(startIso).getTime();
    const eMillis = new Date(endIso).getTime();
    const diffMinutes = Math.max(0, (eMillis - sMillis) / (1000 * 60));

    startDesc = `${dateStr}, ${startTimeStr}`;
    endDesc = `${dateStr}, ${endTimeStr}`;
    
    if (diffMinutes < 60) {
      durationDesc = `${diffMinutes} Minutes`;
    } else {
      const hrs = (diffMinutes / 60).toFixed(1);
      durationDesc = `${hrs.endsWith('.0') ? hrs.slice(0, -2) : hrs} Hours`;
    }
  } else {
    // Multi-Day Mode
    const startDateStr = document.getElementById("days-start-date")?.value || new Date().toISOString().split("T")[0];
    const daysCount = parseInt(document.getElementById("days-count-select")?.value || "3", 10);
    const handoverTime = document.getElementById("days-handover-time")?.value || "09:00";
    const returnTime = document.getElementById("days-return-time")?.value || "17:00";

    const sDate = new Date(`${startDateStr}T00:00:00Z`);
    const eDate = new Date(sDate);
    eDate.setUTCDate(eDate.getUTCDate() + (daysCount - 1));
    const endDateStr = eDate.toISOString().split("T")[0];

    startIso = `${startDateStr}T${handoverTime}:00Z`;
    endIso = `${endDateStr}T${returnTime}:00Z`;
    startDesc = `${startDateStr}, ${handoverTime}`;
    endDesc = `${endDateStr}, ${returnTime}`;
    durationDesc = `${daysCount} Days (${daysCount * 8} Operating Hours)`;
  }

  document.getElementById("preview-start-time").textContent = startDesc;
  document.getElementById("preview-end-time").textContent = endDesc;
  document.getElementById("preview-duration").textContent = durationDesc;

  // Real-time server range check
  await verifyRangeAvailability(startIso, endIso);
}

async function verifyRangeAvailability(startIso, endIso) {
  const box = document.getElementById("preview-availability-box");
  const icon = document.getElementById("preview-avail-icon");
  const text = document.getElementById("preview-avail-text");
  if (!box || !kitId()) return;

  try {
    box.className = "availability-status-box avail-checking";
    icon.textContent = "⏳";
    text.textContent = "Checking schedule availability...";

    const res = await fetch("/api/availability/check-range", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start_time: startIso,
        end_time: endIso,
        kit_id: kitId(),
        club_id: selectedStudentId
      })
    });
    const data = await res.json();

    if (data.is_available) {
      box.className = "availability-status-box avail-free";
      icon.textContent = "✅";
      text.textContent = "Single kit is completely free & available for this duration!";
    } else {
      box.className = "availability-status-box avail-blocked";
      icon.textContent = "❌";
      text.textContent = data.reason || "Slot conflicts with an existing booking or buffer.";
    }
  } catch (err) {
    box.className = "availability-status-box avail-free";
    icon.textContent = "ℹ️";
    text.textContent = "Ready to submit reservation request.";
  }
}

function kitId() {
  return (currentState && currentState.kits && currentState.kits[0]) ? currentState.kits[0].kit_id : null;
}

// ==========================================
// RESERVATION CREATION SUBMISSION
// ==========================================
async function handleUserBookingSubmit(e) {
  e.preventDefault();
  showAlert("", "");

  let startIso, endIso;

  if (bookingMode === "hours") {
    const dateStr = document.getElementById("user-booking-date").value;
    const startTimeStr = document.getElementById("user-start-time").value;
    const endTimeStr = document.getElementById("user-end-time").value;

    if (!dateStr || !startTimeStr || !endTimeStr) {
      showAlert("Please select a date and valid time range.", "danger");
      return;
    }

    if (startTimeStr >= endTimeStr) {
      showAlert("Invalid Time Window: End time must be strictly after start time.", "danger");
      return;
    }

    if (startTimeStr < "09:00" || endTimeStr > "17:00") {
      showAlert("Campus Operating Hours Policy: Relay kit reservations are only allowed between 09:00 AM and 05:00 PM.", "danger");
      return;
    }

    startIso = `${dateStr}T${startTimeStr}:00Z`;
    endIso = `${dateStr}T${endTimeStr}:00Z`;

    const diffMinutes = (new Date(endIso).getTime() - new Date(startIso).getTime()) / (1000 * 60);

    if (diffMinutes < 15) {
      showAlert("Slot Duration Policy: Minimum booking duration is 15 minutes.", "danger");
      return;
    }

    if (new Date(endIso).getTime() < (Date.now() - 5 * 60 * 1000)) {
      showAlert("Invalid Schedule: Cannot reserve a time slot in the past.", "danger");
      return;
    }
  } else {
    // Days Mode
    const startDateStr = document.getElementById("days-start-date").value;
    const daysCount = parseInt(document.getElementById("days-count-select").value, 10);
    const handoverTime = document.getElementById("days-handover-time").value || "09:00";
    const returnTime = document.getElementById("days-return-time").value || "17:00";

    if (!startDateStr) {
      showAlert("Please choose a start date.", "danger");
      return;
    }

    if (handoverTime < "09:00" || handoverTime > "17:00" || returnTime < "09:00" || returnTime > "17:00") {
      showAlert("Campus Operating Hours Policy: Handover and return times must be within 09:00 AM - 05:00 PM.", "danger");
      return;
    }

    const sDate = new Date(`${startDateStr}T00:00:00Z`);
    const eDate = new Date(sDate);
    eDate.setUTCDate(eDate.getUTCDate() + (daysCount - 1));
    const endDateStr = eDate.toISOString().split("T")[0];

    startIso = `${startDateStr}T${handoverTime}:00Z`;
    endIso = `${endDateStr}T${returnTime}:00Z`;
  }

  try {
    const res = await fetch("/api/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        club_id: selectedStudentId,
        kit_id: kitId(),
        start_time: startIso,
        end_time: endIso
      })
    });

    const data = await res.json();

    if (!res.ok) {
      showAlert(data.detail || "Booking failed", "danger");
    } else {
      showAlert(data.message || "Reservation successfully confirmed!", "success");
      await fetchState();
      switchUserTab("my-bookings");
    }
  } catch (err) {
    showAlert("Network error during booking submission.", "danger");
  }
}

// ==========================================
// MY BOOKINGS (STUDENT RELAY ACTIONS)
// ==========================================
function renderUserMyBookings() {
  const container = document.getElementById("user-my-reservations-list");
  if (!container) return;

  const studentReservations = currentState.reservations.filter(r => (r.student_id === selectedStudentId || r.club_id === selectedStudentId));

  if (studentReservations.length === 0) {
    container.innerHTML = `
      <div class="empty-log" style="padding: 2.5rem; font-size: 0.9rem;">
        No bookings found for this student.<br>
        Click the <button class="btn btn-primary btn-sm" style="margin-top: 0.5rem;" onclick="switchUserTab('book')">Book Relay Kit</button> tab to reserve your equipment!
      </div>
    `;
    return;
  }

  container.innerHTML = studentReservations.map(res => {
    const sDate = res.start_time.substring(0, 10);
    const eDate = res.end_time.substring(0, 10);
    const sTime = res.start_time.substring(11, 16);
    const eTime = res.end_time.substring(11, 16);

    const isMultiDay = sDate !== eDate;
    const timeDisplay = isMultiDay 
      ? `📅 ${sDate} ${sTime} → ${eDate} ${eTime}`
      : `📅 ${sDate} · ⏰ ${sTime} - ${eTime}`;

    let actionButtons = "";
    let statusPill = "";

    if (res.status === "CONFIRMED") {
      statusPill = `<span class="badge badge-success">CONFIRMED</span>`;
      actionButtons = `
        <button class="btn btn-take btn-sm" onclick="studentTakeKit('${res.reservation_id}')">
          📥 Take Kit (Checkout)
        </button>
        <button class="btn btn-outline btn-sm" onclick="openRescheduleModal('${res.reservation_id}')">
          Reschedule
        </button>
        <button class="btn btn-danger btn-sm" onclick="cancelReservation('${res.reservation_id}')">
          Cancel
        </button>
      `;
    } else if (res.status === "CHECKED_OUT") {
      statusPill = `<span class="badge badge-warning">IN-USE (WITH STUDENT)</span>`;
      actionButtons = `
        <button class="btn btn-submit-kit btn-sm" onclick="studentSubmitKitAtDesk('${res.reservation_id}')">
          📤 Submit Kit at Desk for Inspection
        </button>
      `;
    } else if (res.status === "RETURNED_PENDING_INSPECTION") {
      statusPill = `<span class="badge badge-warning">RETURNED — PENDING INSPECTION</span>`;
      actionButtons = `
        <span style="font-size: 0.8rem; color: #fbbf24;">⏳ Kit handed over at desk. Awaiting official Admin defect inspection.</span>
      `;
    } else if (res.status === "COMPLETED") {
      const isDefect = res.inspection_verdict === "DEFECT_PENALTY_ISSUED";
      statusPill = isDefect 
        ? `<span class="badge badge-danger">DEFECT PENALTY BILLED</span>`
        : `<span class="badge badge-success">CLEAN RETURN (ZERO PENALTY)</span>`;
      actionButtons = `<span style="font-size: 0.8rem; color: #94a3b8;">${res.inspection_verdict || 'COMPLETED'}</span>`;
    } else {
      statusPill = `<span class="badge badge-danger">${res.status}</span>`;
    }

    return `
      <div class="my-res-card">
        <div class="res-header-info">
          <div style="display: flex; align-items: center; gap: 0.75rem;">
            <h4>Reservation #${res.reservation_id.substring(0, 8)}</h4>
            ${statusPill}
          </div>
          <div class="res-time-window">${timeDisplay}</div>
        </div>
        <div class="res-action-buttons">
          ${actionButtons}
        </div>
      </div>
    `;
  }).join("");
}

async function studentTakeKit(reservationId) {
  try {
    const res = await fetch(`/api/reservations/${reservationId}/checkout`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert("Kit collected ('Taken')! Handover complete. Equipment is now checked out to student.", "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to take kit", "danger");
  }
}

async function studentSubmitKitAtDesk(reservationId) {
  try {
    const res = await fetch(`/api/reservations/${reservationId}/submit-return`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ student_notes: "Physical kit returned to campus equipment counter" })
    });
    const data = await res.json();
    if (res.ok) {
      showAlert("Kit submitted at campus desk! Ready for official Admin physical inspection.", "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to submit kit return", "danger");
  }
}

// ==========================================
// PAYMENTS & INVOICES (STUDENT LIABILITY)
// ==========================================
async function renderUserPayments() {
  try {
    const res = await fetch(`/api/clubs/${selectedStudentId}/billing`);
    const data = await res.json();
    if (!res.ok) return;

    const b = data.billing_data;
    document.getElementById("user-billing-total").textContent = formatINR(b.outstanding_balance);

    const pill = document.getElementById("user-billing-standing-pill");
    if (b.outstanding_balance > 0 || b.financial_standing === "DEBARRED") {
      pill.className = "badge badge-danger";
      pill.textContent = "RESTRICTED / DEBARRED";
    } else {
      pill.className = "badge badge-success";
      pill.textContent = "GOOD STANDING";
    }

    // Invoices list
    const invContainer = document.getElementById("user-invoices-list");
    if (b.invoices.length === 0) {
      invContainer.innerHTML = `<div class="empty-log">No penalty invoices issued for this student. You have zero debt!</div>`;
    } else {
      invContainer.innerHTML = b.invoices.map(inv => `
        <div class="invoice-item">
          <div class="invoice-header">
            <strong>${inv.equipment_type} Defect / Damage Claim</strong>
            <span class="badge ${inv.status === 'PAID' ? 'badge-success' : 'badge-danger'}">${inv.status}</span>
          </div>
          <div class="invoice-cost-row">
            <span>Base Repair / Replacement Assessment:</span>
            <span>${formatINR(inv.base_cost)}</span>
          </div>
          <div class="invoice-cost-row">
            <span>College Administrative Handling Surcharge (15%):</span>
            <span>${formatINR(inv.handling_fee)}</span>
          </div>
          <div class="invoice-cost-row" style="border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.35rem;">
            <span>Total Payable:</span>
            <span class="invoice-total">${formatINR(inv.total_amount_due)}</span>
          </div>
          <div class="invoice-cost-row" style="margin-top: 0.35rem;">
            <span style="font-size: 0.75rem;">Due Date: ${new Date(inv.due_date).toLocaleDateString()}</span>
            ${inv.status !== 'PAID' ? `
              <button class="btn btn-success btn-sm" onclick="payStudentInvoice('${inv.invoice_id}')">
                💳 Pay Now via College Portal (${formatINR(inv.total_amount_due)})
              </button>
            ` : `<span style="color: #34d399; font-size: 0.75rem;">✓ Paid in full on ${new Date(inv.paid_at).toLocaleDateString()}</span>`}
          </div>
        </div>
      `).join("");
    }

    // Payment Receipts
    const payContainer = document.getElementById("user-payments-list");
    if (b.payments_history.length === 0) {
      payContainer.innerHTML = `<div class="empty-log">No past payment transactions.</div>`;
    } else {
      payContainer.innerHTML = b.payments_history.map(p => `
        <div class="log-entry" style="color: #34d399;">
          &gt; Paid ${formatINR(p.amount_paid)} [Ref: ${p.reference_id.substring(0, 8)}] on ${new Date(p.paid_at).toLocaleDateString()}
        </div>
      `).join("");
    }
  } catch (err) {
    console.error("Error rendering student payments:", err);
  }
}

async function payStudentInvoice(invoiceId) {
  try {
    const res = await fetch(`/api/invoices/${invoiceId}/pay`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert(data.message || "Payment settled! All dues cleared. Booking privileges RESTORED.", "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Payment transaction failed", "danger");
  }
}

// ==========================================
// ADMIN MODULE IMPLEMENTATION
// ==========================================
async function refreshAdminModule() {
  renderAdminStation();
  renderAdminKitComponents();
  renderAdminBufferComponents();
  renderAdminReplacementLogs();
  await renderAdminTimeline();
  renderAdminBlocks();
  renderAdminStudentsList();
}

// Top Section: Active Relay Handover & Defect Inspection Station
function renderAdminStation() {
  const handoverList = document.getElementById("admin-handover-list");
  const inuseList = document.getElementById("admin-inuse-list");
  const pendingList = document.getElementById("admin-pending-inspection-list");
  if (!handoverList || !inuseList || !pendingList) return;

  const reservations = currentState.reservations || [];
  const students = currentState.students || currentState.clubs || [];

  const getStudentName = (id) => {
    const s = students.find(item => (item.student_id || item.club_id) === id);
    return s ? `${s.name} ${s.roll_number ? '(' + s.roll_number + ')' : ''}` : "Student";
  };

  // 1. Ready for Handover (CONFIRMED)
  const confirmed = reservations.filter(r => r.status === "CONFIRMED");
  document.getElementById("count-handover-ready").textContent = confirmed.length;
  if (confirmed.length === 0) {
    handoverList.innerHTML = `<div class="empty-log">No bookings awaiting handover.</div>`;
  } else {
    handoverList.innerHTML = confirmed.map(r => `
      <div class="station-item-card">
        <div class="station-item-team">
          <span>${getStudentName(r.student_id || r.club_id)}</span>
          <span class="badge badge-success">CONFIRMED</span>
        </div>
        <div class="station-item-time">
          Slot: ${r.start_time.substring(11, 16)} - ${r.end_time.substring(11, 16)} (${r.start_time.substring(0, 10)})
        </div>
        <button class="btn btn-take btn-sm" style="margin-top: 0.35rem;" onclick="adminGiveKit('${r.reservation_id}')">
          🤝 Give Kit to Student (Handover)
        </button>
      </div>
    `).join("");
  }

  // 2. Currently In-Use (CHECKED_OUT)
  const inuse = reservations.filter(r => r.status === "CHECKED_OUT");
  document.getElementById("count-inuse").textContent = inuse.length;
  if (inuse.length === 0) {
    inuseList.innerHTML = `<div class="empty-log">No kits currently checked out.</div>`;
  } else {
    inuseList.innerHTML = inuse.map(r => `
      <div class="station-item-card">
        <div class="station-item-team">
          <span>${getStudentName(r.student_id || r.club_id)}</span>
          <span class="badge badge-warning">IN-USE</span>
        </div>
        <div class="station-item-time">
          Expected Return: ${r.end_time.substring(11, 16)} (${r.end_time.substring(0, 10)})
        </div>
        <button class="btn btn-warning btn-sm" style="margin-top: 0.35rem;" onclick="openAdminInspectionModal('${r.reservation_id}')">
          🔍 Inspect Return & Check Defects
        </button>
      </div>
    `).join("");
  }

  // 3. Pending Defect Inspection (RETURNED_PENDING_INSPECTION)
  const pending = reservations.filter(r => r.status === "RETURNED_PENDING_INSPECTION");
  document.getElementById("count-pending-inspection").textContent = pending.length;
  if (pending.length === 0) {
    pendingList.innerHTML = `<div class="empty-log">No returned kits pending inspection.</div>`;
  } else {
    pendingList.innerHTML = pending.map(r => `
      <div class="station-item-card" style="border-color: rgba(244, 63, 94, 0.4);">
        <div class="station-item-team">
          <span>${getStudentName(r.student_id || r.club_id)}</span>
          <span class="badge badge-danger">PENDING INSPECTION</span>
        </div>
        <div class="station-item-time">
          Submitted at desk. Ready for Admin physical defect check.
        </div>
        <button class="btn btn-danger btn-sm" style="margin-top: 0.35rem;" onclick="openAdminInspectionModal('${r.reservation_id}')">
          ⚖️ Evaluate Damage & Assess Fine
        </button>
      </div>
    `).join("");
  }

  const activeCountEl = document.getElementById("admin-station-active-count");
  if (activeCountEl) {
    activeCountEl.textContent = `${confirmed.length + inuse.length + pending.length} Active Operations`;
  }
}

async function adminGiveKit(reservationId) {
  try {
    const res = await fetch(`/api/reservations/${reservationId}/checkout`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert("Admin Handover Complete: Kit given to student! Status updated to IN-USE.", "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to handover kit", "danger");
  }
}

function renderAdminKitComponents() {
  const container = document.getElementById("admin-kit-components");
  if (!container) return;
  container.innerHTML = "";

  const primaryKit = currentState.kits[0];
  if (!primaryKit) return;

  const itemsMap = primaryKit.assigned_items || {};
  const types = ["CAMERA", "MICROPHONE", "TRIPOD"];

  types.forEach(type => {
    const itemId = itemsMap[type];
    const item = currentState.equipment.find(e => e.item_id === itemId);

    const card = document.createElement("div");
    card.className = "item-card";

    if (item) {
      const condBadge = item.condition === "GOOD" 
        ? '<span class="badge badge-success">USABLE</span>' 
        : '<span class="badge badge-danger">DEFECTIVE</span>';

      card.innerHTML = `
        <div class="item-icon-title">
          <div class="item-type-icon">${type.substring(0, 3)}</div>
          <div class="item-details">
            <h4>${type}</h4>
            <span class="item-serial">${item.serial_number}</span>
          </div>
        </div>
        ${condBadge}
      `;
    } else {
      card.innerHTML = `
        <div class="item-icon-title">
          <div class="item-type-icon">${type.substring(0, 3)}</div>
          <div class="item-details">
            <h4>${type}</h4>
            <span class="item-serial">No item assigned</span>
          </div>
        </div>
        <span class="badge badge-danger">MISSING</span>
      `;
    }
    container.appendChild(card);
  });
}

function renderAdminBufferComponents() {
  const container = document.getElementById("admin-buffer-components");
  if (!container) return;
  container.innerHTML = "";

  const bufferItems = currentState.equipment.filter(e => e.kit_id === null && e.availability === "USABLE");

  if (bufferItems.length === 0) {
    container.innerHTML = `<div class="empty-log">College spare inventory pool is empty!</div>`;
    return;
  }

  bufferItems.forEach(item => {
    const card = document.createElement("div");
    card.className = "item-card";
    card.innerHTML = `
      <div class="item-icon-title">
        <div class="item-type-icon" style="background: rgba(16, 185, 129, 0.1); color: #10b981;">
          ${item.equipment_type.substring(0, 3)}
        </div>
        <div class="item-details">
          <h4>${item.equipment_type} (College Buffer Spare)</h4>
          <span class="item-serial">${item.serial_number}</span>
        </div>
      </div>
      <span class="badge badge-success">READY TO SWAP</span>
    `;
    container.appendChild(card);
  });
}

function renderAdminReplacementLogs() {
  const container = document.getElementById("admin-replacement-logs");
  if (!container) return;
  const logs = currentState.replacement_logs || [];

  if (logs.length === 0) {
    container.innerHTML = `<div class="empty-log">No replacements logged yet.</div>`;
    return;
  }

  container.innerHTML = logs.map(l => `
    <div class="log-entry">
      &gt; [${new Date(l.replaced_at).toLocaleTimeString()}] Replaced ${l.equipment_type}: Swapped in spare item (${l.organizer_notes})
    </div>
  `).join("");
}

async function renderAdminTimeline() {
  const container = document.getElementById("admin-calendar-timeline");
  if (!container || !currentState.kits[0]) return;

  try {
    const res = await fetch(`/api/admin/calendar`);
    const data = await res.json();
    if (!data.success || data.timeline.length === 0) {
      container.innerHTML = `<div class="empty-log">No reservations or buffers scheduled for today.</div>`;
      return;
    }

    container.innerHTML = data.timeline.map(t => {
      const s = t.start_time.substring(11, 16);
      const e = t.end_time.substring(11, 16);
      return `
        <div class="log-entry" style="color: ${t.type === 'RESERVATION' ? '#38bdf8' : t.type === 'MAINTENANCE_BLOCK' ? '#f43f5e' : '#fbbf24'};">
          &gt; [${s} - ${e}] ${t.title} (${t.status})
        </div>
      `;
    }).join("");
  } catch (err) {
    container.innerHTML = `<div class="empty-log">Failed to load admin calendar timeline.</div>`;
  }
}

function renderAdminBlocks() {
  const container = document.getElementById("admin-blocks-list");
  if (!container) return;

  const blocks = currentState.maintenance_blocks || [];
  if (blocks.length === 0) {
    container.innerHTML = `<div class="empty-log">No active maintenance blocks.</div>`;
    return;
  }

  container.innerHTML = blocks.map(b => {
    const s = b.start_time.substring(11, 16);
    const e = b.end_time.substring(11, 16);
    const d = b.start_time.substring(0, 10);
    return `
      <div class="log-entry" style="color: #f43f5e;">
        &gt; [${d} ${s} - ${e}] ${b.reason} (by ${b.created_by})
      </div>
    `;
  }).join("");
}

function renderAdminStudentsList() {
  const container = document.getElementById("admin-clubs-list");
  if (!container) return;
  container.innerHTML = "";

  const students = currentState.students || currentState.clubs || [];

  students.forEach(student => {
    const card = document.createElement("div");
    card.className = "club-card";

    let standingBadge = '<span class="badge badge-success">GOOD STANDING</span>';
    if (student.financial_standing === "DEBARRED" || student.outstanding_balance > 0) {
      standingBadge = '<span class="badge badge-danger">RESTRICTED / DEBARRED</span>';
    }

    const sid = student.student_id || student.club_id;

    card.innerHTML = `
      <div class="club-card-header">
        <div>
          <h3>${student.name}</h3>
          <span style="font-size: 0.75rem; color: var(--text-muted);">${student.roll_number || student.contact_email}</span>
        </div>
        ${standingBadge}
      </div>
      <div class="club-balance-row">
        <span>Damage Fine Balance:</span>
        <span class="club-balance-amount">${formatINR(student.outstanding_balance)}</span>
      </div>
      <div class="club-actions">
        ${student.financial_standing !== 'DEBARRED' && student.outstanding_balance === 0 ? `
          <button class="btn btn-warning btn-sm" onclick="adminToggleDebarment('${sid}')">
            Enforce Debarment
          </button>
        ` : student.outstanding_balance === 0 ? `
          <button class="btn btn-success btn-sm" onclick="adminLiftDebarment('${sid}')">
            ✅ Restore Standing
          </button>
        ` : `
          <span style="font-size: 0.75rem; color: #fb7185;">🚫 Booking blocked until fine cleared</span>
        `}
      </div>
    `;
    container.appendChild(card);
  });
}

async function triggerAdminOverdueAudit() {
  try {
    const res = await fetch("/api/admin/trigger-overdue", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert(data.message, "warning");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to run overdue audit", "danger");
  }
}

async function adminToggleDebarment(studentId) {
  try {
    const res = await fetch(`/api/clubs/${studentId}/debar`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert(data.message, "danger");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to debar student", "danger");
  }
}

async function adminLiftDebarment(studentId) {
  try {
    const res = await fetch(`/api/clubs/${studentId}/lift-debar`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showAlert(data.message, "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to restore student standing", "danger");
  }
}

// ==========================================
// ADMIN RETURN INSPECTION & PENALTY MODAL
// ==========================================
function openAdminInspectionModal(reservationId) {
  document.getElementById("return-res-id").value = reservationId;

  const res = currentState.reservations.find(r => r.reservation_id === reservationId);
  const students = currentState.students || currentState.clubs || [];
  const student = res ? students.find(s => (s.student_id || s.club_id) === (res.student_id || res.club_id)) : null;

  const banner = document.getElementById("inspect-student-name");
  if (banner && student) {
    banner.textContent = `Target Student: ${student.name} ${student.roll_number ? '(' + student.roll_number + ')' : ''}`;
  }
  const tag = document.getElementById("inspect-res-tag");
  if (tag && res) tag.textContent = res.status;

  // Reset defaults
  document.getElementById("inspect-camera").value = "GOOD";
  document.getElementById("inspect-microphone").value = "GOOD";
  document.getElementById("inspect-tripod").value = "GOOD";
  document.getElementById("return-notes").value = "All equipment inspected and intact.";
  document.getElementById("waiver-reason-group").style.display = "none";

  calculateInspectionPenaltyPreview();
  openModal("return-modal");
}

function calculateInspectionPenaltyPreview() {
  const cam = document.getElementById("inspect-camera").value;
  const mic = document.getElementById("inspect-microphone").value;
  const tri = document.getElementById("inspect-tripod").value;

  const quotes = {
    CAMERA: { DAMAGED: 2500, MISSING: 38000 },
    MICROPHONE: { DAMAGED: 700, MISSING: 6500 },
    TRIPOD: { DAMAGED: 450, MISSING: 3200 }
  };

  let baseTotal = 0;
  let handlingTotal = 0;
  let hasDefects = false;

  const assess = (type, cond) => {
    if (cond === "GOOD") return;
    hasDefects = true;
    const base = quotes[type][cond] || 0;
    const handling = Math.max(100, round2(base * 0.15));
    baseTotal += base;
    handlingTotal += handling;
  };

  assess("CAMERA", cam);
  assess("MICROPHONE", mic);
  assess("TRIPOD", tri);

  const grandTotal = baseTotal + handlingTotal;

  document.getElementById("penalty-base-cost").textContent = formatINR(baseTotal);
  document.getElementById("penalty-handling-fee").textContent = formatINR(handlingTotal);
  document.getElementById("penalty-total-due").textContent = formatINR(grandTotal);

  const badge = document.getElementById("penalty-verdict-badge");
  const warn = document.getElementById("penalty-debarment-warning");

  if (hasDefects) {
    badge.className = "badge badge-danger";
    badge.textContent = `DEFECT PENALTY: ${formatINR(grandTotal)}`;
    warn.style.display = "block";
    document.getElementById("return-notes").value = `Returned with defective component(s). Damage penalty assessed.`;
  } else {
    badge.className = "badge badge-success";
    badge.textContent = "ZERO DEFECT — CLEAN";
    warn.style.display = "none";
    document.getElementById("return-notes").value = "All items returned in good condition.";
  }
}

function round2(num) {
  return Math.round((num + Number.EPSILON) * 100) / 100;
}

function toggleWaiverInput() {
  const grp = document.getElementById("waiver-reason-group");
  const submitContainer = document.getElementById("waiver-submit-container");
  const isHidden = (grp.style.display === "none");
  grp.style.display = isHidden ? "block" : "none";
  if (submitContainer) submitContainer.style.display = isHidden ? "block" : "none";
  if (isHidden) {
    document.getElementById("return-waiver-reason").value = "Campus faculty exemption granted";
  }
}

async function submitInspectionDecision(imposePenalty, isClean, isWaiver = false) {
  const resId = document.getElementById("return-res-id").value;
  let cam = document.getElementById("inspect-camera").value;
  let mic = document.getElementById("inspect-microphone").value;
  let tri = document.getElementById("inspect-tripod").value;
  let notes = document.getElementById("return-notes").value;
  const waiverReason = document.getElementById("return-waiver-reason")?.value;

  if (isClean) {
    cam = "GOOD";
    mic = "GOOD";
    tri = "GOOD";
    notes = "Inspected and confirmed in good condition.";
  }

  try {
    const res = await fetch(`/api/reservations/${resId}/return`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inspections: {
          "CAMERA": cam,
          "MICROPHONE": mic,
          "TRIPOD": tri
        },
        defect_notes: notes,
        impose_penalty: imposePenalty,
        waiver_reason: isWaiver ? waiverReason : null,
        inspector_name: "College Desk Administrator"
      })
    });

    const data = await res.json();
    closeModal("return-modal");

    if (res.ok) {
      if (data.data.penalty_imposed) {
        showAlert(
          `⚠️ Defect Recorded & Penalty Imposed: Item replaced from college spare stock. Penalty invoice of ${formatINR(data.data.total_invoiced_inr)} issued. Student is DEBARRED until payment is cleared!`,
          "danger"
        );
      } else if (data.data.waiver_reason) {
        showAlert(
          `🤝 Penalty Waived: Item replaced from college spare stock. Admin granted exemption (${data.data.waiver_reason}). No invoice issued!`,
          "warning"
        );
      } else {
        showAlert(
          "✅ Clean Return Verified: All components intact. Reservation completed with zero penalty!",
          "success"
        );
      }
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to process inspection", "danger");
  }
}

// ==========================================
// MAINTENANCE, RESCHEDULE & CANCEL MODALS
// ==========================================
function openMaintenanceModal() {
  const maintDateInput = document.getElementById("maint-date");
  if (maintDateInput) maintDateInput.value = new Date().toISOString().split("T")[0];
  openModal("maint-modal");
}

async function handleMaintSubmit(e) {
  e.preventDefault();
  const dateStr = document.getElementById("maint-date")?.value || new Date().toISOString().split("T")[0];
  const startStr = document.getElementById("maint-start-time").value;
  const endStr = document.getElementById("maint-end-time").value;
  const reason = document.getElementById("maint-reason").value;

  if (startStr >= endStr) {
    showAlert("Invalid Maintenance Window: End time must be after start time.", "danger");
    return;
  }

  const startIso = `${dateStr}T${startStr}:00Z`;
  endIso = `${dateStr}T${endStr}:00Z`;

  try {
    const res = await fetch(`/api/kits/${kitId()}/maintenance-blocks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kit_id: kitId(),
        start_time: startIso,
        end_time: endIso,
        reason: reason
      })
    });
    const data = await res.json();
    closeModal("maint-modal");
    if (res.ok) {
      showAlert(data.message, "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Failed to create maintenance block", "danger");
  }
}

function openRescheduleModal(resId) {
  document.getElementById("reschedule-res-id").value = resId;
  const res = currentState && currentState.reservations ? currentState.reservations.find(r => r.reservation_id === resId) : null;
  if (res) {
    const resDate = res.start_time.substring(0, 10);
    const dateInput = document.getElementById("reschedule-date");
    if (dateInput) dateInput.value = resDate;
    document.getElementById("reschedule-start-time").value = res.start_time.substring(11, 16);
    document.getElementById("reschedule-end-time").value = res.end_time.substring(11, 16);
  } else {
    const dateInput = document.getElementById("reschedule-date");
    if (dateInput) dateInput.value = new Date().toISOString().split("T")[0];
  }
  openModal("reschedule-modal");
}

async function handleRescheduleSubmit(e) {
  e.preventDefault();
  const resId = document.getElementById("reschedule-res-id").value;
  const dateStr = document.getElementById("reschedule-date")?.value || new Date().toISOString().split("T")[0];
  const startStr = document.getElementById("reschedule-start-time").value;
  const endStr = document.getElementById("reschedule-end-time").value;

  if (!startStr || !endStr) {
    showAlert("Please specify both new start and end times.", "danger");
    return;
  }

  if (startStr >= endStr) {
    showAlert("Invalid Reschedule Window: End time must be strictly after start time.", "danger");
    return;
  }

  if (startStr < "09:00" || endStr > "17:00") {
    showAlert("Campus Operating Hours Policy: Rescheduled slots must fall between 09:00 AM and 05:00 PM.", "danger");
    return;
  }

  const startIso = `${dateStr}T${startStr}:00Z`;
  const endIso = `${dateStr}T${endStr}:00Z`;

  try {
    const res = await fetch(`/api/reservations/${resId}/reschedule`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        new_start_time: startIso,
        new_end_time: endIso
      })
    });
    const data = await res.json();
    closeModal("reschedule-modal");
    if (res.ok) {
      showAlert(data.message, "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Reschedule request failed", "danger");
  }
}

async function cancelReservation(resId) {
  try {
    const res = await fetch(`/api/reservations/${resId}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "Student requested cancellation" })
    });
    const data = await res.json();
    if (res.ok) {
      showAlert(data.message, "success");
      await fetchState();
    } else {
      showAlert(data.detail, "danger");
    }
  } catch (err) {
    showAlert("Cancellation failed", "danger");
  }
}

// Modal helpers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("modal-hidden");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("modal-hidden");
}

function showAlert(msg, type) {
  const box = document.getElementById("action-alert");
  const msgEl = document.getElementById("alert-message");

  if (!msg) {
    box.className = "alert-box alert-hidden";
    return;
  }

  box.className = `alert-box alert-${type}`;
  msgEl.textContent = msg;
}
