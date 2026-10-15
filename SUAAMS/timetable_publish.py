"""Publishing the timetable, and telling the people a change affects.

publish_drafts()
    Swaps every course's DRAFT slots (from a PDF import) in for its published
    ones, for one semester, in one transaction. Until then students and
    lecturers keep seeing the old published classes.

notify_schedule_changes()
    Tells each affected person once. For every course whose schedule changed:
      * its registered students and all its lecturers (co-lecturers too)
        are affected;
      * a course with no published classes before -> "published";
        a course whose classes changed -> "updated";
        a course that ended up identical -> nobody is told.
    Each person gets ONE notification covering all their affected courses,
    listing the new schedule ("MCT401: Mon 08:00-10:00 LR 1; ..."), not a
    diff -- the new times are what they need. People who would get the same
    text are sent it together (push_notifications.notify_users), so a whole
    level costs a handful of bulk sends, not one per student.

Also used when an admin adds, edits or deletes a published class by hand
on the timetable page, so later corrections reach exactly the people they
affect.
"""
from campus_time import campus_today
from models import db, Course, Enrollment, Session as SessionModel, Student, Timetable
from push_notifications import notify_users

DAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
KIND_SHORT = {'L': '', 'T': ' (tutorial)', 'P': ' (practical)'}
BODY_LIMIT = 500        # Notification.body is String(500)


def schedule_of(slots):
    """A course's schedule as comparable tuples, in display order."""
    return sorted((s.day_of_week, s.start_time, s.end_time, (s.room or '').strip().upper(), s.kind or '')
                  for s in slots)


def describe(schedule):
    """'Mon 08:00-10:00 LR 1; Tue 15:00-17:00 (tutorial) HALL B'"""
    if not schedule:
        return 'no classes'
    return '; '.join(f"{DAY_SHORT[d]} {a:%H:%M}-{b:%H:%M}{KIND_SHORT.get(k, '')}" + (f" {room}" if room else '')
                     for d, a, b, room, k in schedule)


def published_schedules(semester_id, course_ids):
    """{course_id: schedule} of what students can see right now."""
    out = {cid: [] for cid in course_ids}
    if not course_ids:
        return out
    rows = Timetable.query.filter(Timetable.semester_id == semester_id,
                                  Timetable.course_id.in_(course_ids),
                                  Timetable.is_published.is_(True)).all()
    for cid in course_ids:
        out[cid] = schedule_of([r for r in rows if r.course_id == cid])
    return out


def publish_drafts(semester, published_by):
    """Publish the semester's drafts. Returns {'courses', 'slots', 'notified'}.
    Commits (the swap and its notifications go together)."""
    drafts = Timetable.query.filter_by(semester_id=semester.id, is_published=False).all()
    if not drafts:
        return {'courses': 0, 'slots': 0, 'notified': 0}
    course_ids = sorted({d.course_id for d in drafts})
    before = published_schedules(semester.id, course_ids)

    old = Timetable.query.filter(Timetable.semester_id == semester.id,
                                 Timetable.course_id.in_(course_ids),
                                 Timetable.is_published.is_(True)).all()
    # A draft that repeats an old slot (same course, day and times) is the
    # same class re-issued -- often a sheet re-published to fix one room.
    # It takes over the old slot's start date and its sessions, so
    # Analytics keeps counting that class from when it really started. Any
    # other draft is a new or moved class and runs from today.
    def key(t):
        return (t.course_id, t.day_of_week, t.start_time, t.end_time)
    unchanged = {}
    for t in old:
        unchanged.setdefault(key(t), t)
    for d in drafts:
        same = unchanged.pop(key(d), None)
        if same is not None:
            d.effective_from = same.effective_from
            (SessionModel.query.filter(SessionModel.timetable_id == same.id)
             .update({SessionModel.timetable_id: d.id}, synchronize_session=False))
        else:
            d.effective_from = campus_today()
    old_ids = [t.id for t in old]
    if old_ids:
        # Sessions of slots that are going away keep their history, just
        # without a slot (Analytics then counts them as extra classes).
        (SessionModel.query.filter(SessionModel.timetable_id.in_(old_ids))
         .update({SessionModel.timetable_id: None}, synchronize_session=False))
        for t in old:
            db.session.delete(t)
    for d in drafts:
        d.is_published = True
    db.session.flush()

    after = published_schedules(semester.id, course_ids)
    db.session.commit()
    notified = notify_schedule_changes(semester, before, after)
    return {'courses': len(course_ids), 'slots': len(drafts), 'notified': notified}


def notify_schedule_changes(semester, before, after):
    """before/after: {course_id: schedule}. Notifies each affected person
    once. Returns how many people were notified."""
    changed = {cid: after.get(cid, []) for cid in set(before) | set(after)
               if before.get(cid, []) != after.get(cid, [])}
    if not changed:
        return 0
    courses = {c.id: c for c in Course.query.filter(Course.id.in_(changed)).all()}

    # person (user id) -> [(course_code, is_new, schedule)]
    affected = {}

    def add(user_id, cid):
        affected.setdefault(user_id, []).append(
            (courses[cid].course_code, not before.get(cid), changed[cid]))

    for user_id, cid in (db.session.query(Student.user_id, Enrollment.course_id)
                         .join(Enrollment, Enrollment.student_id == Student.id)
                         .filter(Enrollment.course_id.in_(changed))):
        add(user_id, cid)
    for cid, course in courses.items():
        for lecturer in course.all_lecturers:
            add(lecturer.user_id, cid)

    # Same text -> one bulk send.
    by_message = {}
    for user_id, items in affected.items():
        items.sort()
        all_new = all(is_new for _, is_new, _ in items)
        title = f"Timetable published: {semester.name}" if all_new else "Timetable updated"
        body = _body(items)
        by_message.setdefault((title, body), []).append(user_id)

    for (title, body), user_ids in by_message.items():
        notify_users(user_ids, 'timetable', title, body,
                     data={'semester_id': semester.id})
    return len(affected)


def _body(items):
    lines = [f"{code}: {describe(schedule)}" for code, _, schedule in items]
    body = ' | '.join(lines)
    if len(body) <= BODY_LIMIT:
        return body
    # Too long for one notification: as many courses as fit, then a pointer.
    kept, total = [], 0
    for line in lines:
        if total + len(line) + 3 > BODY_LIMIT - 60:
            break
        kept.append(line)
        total += len(line) + 3
    return ' | '.join(kept) + f" | +{len(lines) - len(kept)} more course(s) -- open your timetable"
