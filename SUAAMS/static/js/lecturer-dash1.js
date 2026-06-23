// ── Clock & date ──
function updateClock() {
    const now = new Date();
    document.getElementById('clockDisplay').textContent =
        now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    document.getElementById('currentDate').textContent =
        now.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}
updateClock();
setInterval(updateClock, 1000);

// ── Session state ──
let activeSessionId   = null;
let activeCourseId    = null;
let feedPollInterval  = null;
let checkinCount      = 0;
const renderedStudents = new Set();

function setStatusLive(courseId) {
    const el = document.getElementById('sessionStatus');
    el.className = 'session-status live';
    el.innerHTML = `<div class="status-dot"></div><span>Live — Course&nbsp;<strong>${courseId}</strong></span>`;
    document.getElementById('btnStop').classList.add('visible');
    document.getElementById('statStatus').textContent = 'Live';
}
function setStatusIdle() {
    const el = document.getElementById('sessionStatus');
    el.className = 'session-status idle';
    el.innerHTML = `<div class="status-dot"></div><span>No active session</span>`;
    document.getElementById('btnStop').classList.remove('visible');
    document.getElementById('statStatus').textContent = 'Idle';
}

// ── Start session ──
async function startSession() {
    const courseId   = document.getElementById('course_id').value.trim();
    const startTime  = document.getElementById('start_time').value;
    const stopTime   = document.getElementById('stop_time').value;

    if (!courseId || !startTime || !stopTime) {
        alert('Please fill in Course ID, Start Time, and End Time.');
        return;
    }

    try {
        const res = await fetch('/sessions/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ course_id: courseId, start_time: startTime, stop_time: stopTime })
        });
        const data = await res.json();
        if (data.success) {
            activeCourseId = courseId;
            setStatusLive(courseId);
            document.getElementById('statSessions').textContent =
                (parseInt(document.getElementById('statSessions').textContent) || 0) + 1;
            checkinCount = 0;
            renderedStudents.clear();
            document.getElementById('feedList').innerHTML = '<div class="feed-empty"><p>Waiting for first scan…</p></div>';
            startFeedPolling();
        } else {
            alert(data.error || 'Failed to start session.');
        }
    } catch (e) {
        alert('Could not reach the server. Please try again.');
    }
}

// ── Stop session (UI only — backend stops via session expiry) ──
function stopSession() {
    if (!confirm('End this session? No more attendance will be accepted.')) return;
    clearInterval(feedPollInterval);
    activeSessionId = null;
    activeCourseId  = null;
    setStatusIdle();
    document.getElementById('statCheckins').textContent = checkinCount;
}

// ── Poll for new check-ins ──
function startFeedPolling() {
    if (feedPollInterval) clearInterval(feedPollInterval);
    feedPollInterval = setInterval(pollAttendance, 5000);
}

async function pollAttendance() {
    if (!activeCourseId) return;
    try {
        const res  = await fetch(`/sessions/active/${activeCourseId}`);
        const data = await res.json();
        if (!data.success || !data.session) return;
        // session exists — we don't have a per-session attendance list endpoint yet,
        // so we just keep the feed primed and update the check-in count from local state.
        // When the student portal / ESP32 posts to /attendance, we reflect that here.
    } catch (_) {}
}

// ── Expose a function so the ESP/test endpoint can push a check-in into the feed ──
function pushCheckin(student) {
    if (renderedStudents.has(student.id)) return;
    renderedStudents.add(student.id);
    checkinCount++;
    document.getElementById('statCheckins').textContent = checkinCount;

    const feedList = document.getElementById('feedList');
    // Remove empty state
    const empty = feedList.querySelector('.feed-empty');
    if (empty) empty.remove();

    const initials = student.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
    const now      = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

    const item = document.createElement('div');
    item.className = 'feed-item';
    item.innerHTML = `
        <div class="feed-avatar">${initials}</div>
        <div class="feed-info">
            <div class="feed-name">${student.full_name}</div>
            <div class="feed-meta">${student.department} · Level ${student.level}</div>
        </div>
        <div class="feed-time">${now}</div>
    `;
    feedList.prepend(item);
}

// Initialise stat defaults
document.getElementById('statSessions').textContent  = '0';
document.getElementById('statCheckins').textContent  = '0';
document.getElementById('statStatus').textContent    = 'Idle';