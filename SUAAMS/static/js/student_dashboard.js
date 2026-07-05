// Reusable pattern:
// 1. Flask prepares data from the database.
// 2. The template injects that data into the page.
// 3. This JavaScript reads the data and renders it in the UI.

// ── Attendance ring renderer ──
function getInitials(value) {
    return value
        .split(/\s+/)
        .filter(Boolean)
        .map(part => part[0])
        .join('')
        .slice(0, 2)
        .toUpperCase() || '?';
}

function renderRing(pct) {
    const circumference = 314.16;
    const offset = circumference - (pct / 100) * circumference;
    const fill = document.getElementById('ringFill');
    const pctEl = document.getElementById('ringPct');
    const pill = document.getElementById('ringPill');
    const rateEl = document.getElementById('statRate');

    if (!fill || !pctEl || !pill || !rateEl) return;

    fill.style.strokeDashoffset = offset;
    pctEl.textContent = pct + '%';
    fill.classList.remove('danger', 'warning');
    pctEl.classList.remove('danger', 'warning');

    if (pct < 60) {
        fill.classList.add('danger');
        pctEl.classList.add('danger');
        pill.className = 'ring-warn-pill';
        pill.textContent = 'Critical — below 60%';
    } else if (pct < 75) {
        fill.classList.add('warning');
        pctEl.classList.add('warning');
        pill.className = 'ring-warn-pill';
        pill.textContent = 'At risk — below 75%';
    } else {
        pill.className = 'ring-ok-pill';
        pill.textContent = 'Good standing ✓';
    }

    rateEl.textContent = pct + '%';
}

// ── Course breakdown renderer ──
const COURSE_COLOURS = ['#00D4FF', '#00E676', '#FFB300', '#A78BFA', '#FF4D6A', '#34D399'];
function renderCourses(courses) {
    const list = document.getElementById('courseList');
    const riskEl = document.getElementById('statRisk');
    const courseCountEl = document.getElementById('statCourses');

    if (!list) return;

    if (!courses || courses.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                <p>No courses enrolled yet</p>
            </div>`;
        if (riskEl) riskEl.textContent = '0';
        if (courseCountEl) courseCountEl.textContent = '0';
        return;
    }

    let atRisk = 0;
    list.innerHTML = courses.map((c, i) => {
        const colour = COURSE_COLOURS[i % COURSE_COLOURS.length];
        if (c.pct < 75) atRisk++;
        return `
            <div class="course-item">
                <div class="course-dot" style="background:${colour};"></div>
                <div class="course-info">
                    <div class="course-code">${c.code}</div>
                    <div class="course-name">${c.name}</div>
                </div>
                <div class="course-pct" style="color:${c.pct < 75 ? 'var(--warning)' : 'var(--success)'};">
                    ${c.pct}%
                </div>
            </div>`;
    }).join('');

    if (riskEl) riskEl.textContent = atRisk;
    if (courseCountEl) courseCountEl.textContent = courses.length;
}

// ── Attendance log renderer ──
function renderLog(records) {
    const tbody = document.getElementById('attendanceLog');
    const attendedEl = document.getElementById('statAttended');

    if (!tbody) return;

    if (!records || records.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4">
                    <div class="empty-state">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                        <p>No attendance records found</p>
                    </div>
                </td>
            </tr>`;
        if (attendedEl) attendedEl.textContent = '0';
        return;
    }

    tbody.innerHTML = records.map(r => `
        <tr>
            <td>${r.course}</td>
            <td>${r.date}</td>
            <td>${r.time}</td>
            <td>
                ${r.present
                    ? '<span class="badge-present">✓ Present</span>'
                    : '<span class="badge-absent">✗ Absent</span>'}
            </td>
        </tr>`).join('');

    if (attendedEl) attendedEl.textContent = records.filter(r => r.present).length;
}

function populateProfile(profile = {}) {
    const name = profile.full_name || "{{ session['username'] }}";
    const avatarPicEl = document.getElementById('avatarPic');
    const profileNameEl = document.getElementById('profileName');
    const deptEl = document.getElementById('profileDept');
    const levelEl = document.getElementById('profileLevel');
    const matricEl = document.getElementById('profileMatric');
    const rfidEl = document.getElementById('rfidDisplay');

    if (avatarPicEl) avatarPicEl.textContent = getInitials(name);
    if (profileNameEl) profileNameEl.textContent = name;
    if (deptEl) deptEl.textContent = profile.department || '—';
    if (levelEl) levelEl.textContent = profile.level ? `${profile.level} Level` : '—';
    if (matricEl) matricEl.textContent = profile.matric_number || '—';
    if (rfidEl) rfidEl.textContent = profile.rfid_uid ? 'Linked ✓' : 'Not linked';
}

function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('overlay').classList.toggle('open');
}
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('overlay').classList.remove('open');
}

function updateClock() {
    const clockEl = document.getElementById('topbarClock');
    if (!clockEl) return;
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    clockEl.textContent = `${hours}:${minutes}:${seconds}`;
}

document.addEventListener('DOMContentLoaded', () => {
    // Read the data that Flask injected into the page.
    // If the data is missing, use empty defaults so the page still loads safely.
    const data = window.dashboardData || {};

    // Populate the profile section using the student object from Flask.
    populateProfile(data.student || {});

    // Render the attendance ring using the overall percentage from Flask.
    renderRing(Number(data.overall_rate) || 0);

    // Render the course cards from the course breakdown data.
    renderCourses(data.courses || []);

    // Render the recent attendance table from the history data.
    renderLog(data.recent_attendance || []);
});

updateClock();
setInterval(updateClock, 1000);