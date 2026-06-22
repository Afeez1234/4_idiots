async function loadSessions() {
  try {
    const res = await fetch('/sessions/active');
    const data = await res.json();
    const tbody = document.getElementById('sessions-body');

    if (!tbody) return;

    if (!data.active_sessions || data.active_sessions.length === 0) return;

    tbody.innerHTML = data.active_sessions.map((s) => `
      <tr>
        <td>#${s.id}</td>
        <td>${s.course_id}</td>
        <td>${s.session_date}</td>
        <td>${s.start_time}</td>
        <td>${s.stop_time}</td>
        <td>
          <span class="badge-active">
            <span style="width:6px;height:6px;border-radius:50%;background:#00E676;display:inline-block;"></span>
            Active
          </span>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    // silently fail — server may not be available
  }
}

loadSessions();
