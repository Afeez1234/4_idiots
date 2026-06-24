// ── Attendance ring renderer ──
function renderRing(pct) {
const circumference = 314.16;
const offset = circumference - (pct / 100) * circumference;
const fill = document.getElementById('ringFill');
const pctEl = document.getElementById('ringPct');
const pill  = document.getElementById('ringPill');

fill.style.strokeDashoffset = offset;
pctEl.textContent = pct + '%';

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

document.getElementById('statRate').textContent = pct + '%';
}

// ── Course breakdown renderer ──
const COURSE_COLOURS = ['#00D4FF','#00E676','#FFB300','#A78BFA','#FF4D6A','#34D399'];
function renderCourses(courses) {
const list   = document.getElementById('courseList');
const riskEl = document.getElementById('statRisk');
let atRisk   = 0;

if (!courses || courses.length === 0) return;

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
    </div>
        `;
}).join('');

riskEl.textContent = atRisk;
document.getElementById('statCourses').textContent = courses.length;
}

// ── Attendance log renderer ──
function renderLog(records) {
const tbody = document.getElementById('attendanceLog');
if (!records || records.length === 0) return;
tbody.innerHTML = records.map(r => `
<tr>
    <td>${r.course}</td>
    <td>${r.date}</td>
    <td>${r.time}</td>
    <td>
        ${r.present
        ? `<span class="badge-present">✓ Present</span>`
        : `<span class="badge-absent">✗ Absent</span>`}
    </td>
</tr>
`).join('');
document.getElementById('statAttended').textContent = records.filter(r => r.present).length;
}

// ── Profile population ──
// These will be filled by backend context variables when the student blueprint
// passes student data to the template. Placeholders shown until that endpoint is built.
const username = "{{ session['username'] }}";
document.getElementById('avatarPic').textContent =
username.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || username[0].toUpperCase();

// Demo data — remove once backend student.dashboard route passes real context
renderRing(82);
renderCourses([
{ code: 'CSC401', name: 'Artificial Intelligence',   pct: 90 },
{ code: 'CSC403', name: 'Computer Networks',          pct: 82 },
{ code: 'CSC405', name: 'Software Engineering',       pct: 75 },
{ code: 'MTH401', name: 'Numerical Methods',          pct: 68 },
]);
renderLog([
{ course: 'CSC401', date: '23 Jun 2025', time: '08:00', present: true  },
{ course: 'MTH401', date: '22 Jun 2025', time: '10:00', present: true  },
{ course: 'CSC403', date: '21 Jun 2025', time: '14:00', present: false },
{ course: 'CSC405', date: '20 Jun 2025', time: '09:00', present: true  },
]);


function toggleSidebar() {
    document.getElementById('sidebar').classList.toggle('open');
    document.getElementById('overlay').classList.toggle('open');
}
function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('overlay').classList.remove('open');
}

// Populate avatar initials
// Once backend passes `student.full_name`, replace the session username with that value
const nameEl   = document.getElementById('studentName');
const avatarEl = document.getElementById('studentAvatar');
const name = nameEl.textContent.trim();
avatarEl.textContent = name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || name[0].toUpperCase();

// Populate profile fields from backend context when available
// e.g. document.getElementById('studentFaculty').textContent = "{{ student.faculty }}";
//      document.getElementById('studentDept').textContent    = "{{ student.department }}";
//      document.getElementById('studentLevel').textContent   = "{{ student.level }} Level";
//      document.getElementById('studentRfid').textContent    = "{{ student.rfid_uid }}";
//      document.getElementById('studentMatric').textContent  = "{{ student.matric_number }}";
//      document.getElementById('studentName').textContent    = "{{ student.full_name }}";

function updateClock() {
    const clockEl = document.getElementById('topbarClock');
    if (!clockEl) return;
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    clockEl.textContent = `${hours}:${minutes}:${seconds}`;
}
updateClock();
setInterval(updateClock, 1000);