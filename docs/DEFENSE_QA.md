# Defence Q&A

Likely examiner questions, with short, honest answers. Practise saying them
out loud. Where there's a limitation, state it first and calmly. Naming a gap
yourself sounds like you understand the system. Having it found for you sounds
like you don't.

Format: **Q**, then a 2–4 sentence answer, then *Limitation* where there is
one.

---

## The idea

**Q: Why not just use a fingerprint scanner at the door?**
Throughput and scale. A scanner takes about 2 s per student, so about 7 minutes
of queuing for a 200-student hall, while a phone tap takes under half a
second. Scanners also hold only a few hundred to ~1,000 templates and don't
sync well across doors. Here each fingerprint stays on the student's own
phone, so there's no enrolment limit.
*Limitation:* We rely on the phone's biometric check rather than our own
sensor.

**Q: What does the terminal actually do? Does it check anything?**
No. It reads the code from the phone and forwards it to the server with its
own terminal credentials. All checking happens on the server, which is the
only party holding the signing secret. That keeps the terminal cheap and means
a stolen terminal reveals no key that can forge codes.

**Q: Why not just send the student's login token over NFC?**
We did at first. It was about 360 bytes, needed six exchanges, and taps kept
failing. Long-lived login tokens are also the wrong thing to broadcast,
because a captured one is a full API credential. Now we send a 32-character
code that only means "this student, this session, for 10 seconds".

## Cheating

**Q: What stops a student giving their phone to a friend?**
The app won't produce a code until the phone's fingerprint/PIN check passes.
So the friend would need the owner's finger or PIN.
*Limitation:* The PIN is accepted as well as the fingerprint, so a student who
shares their PIN can still be buddy-punched. Binding to the fingerprint set
only is planned but not built.

**Q: What if two students share a phone?**
They can't. A phone can be bound to only one student account, and the server
refuses a second one with "DEVICE IN USE". Without that, one person could check
in a whole group with their own finger.
A student with no phone, or a broken one, is marked present by the
lecturer from the session screen. That record is stored as `manual`, along
with the name of the lecturer who vouched for it.

**Q: Can I log into my account on my friend's phone instead?**
No. Each account is locked to the first phone it logs in from. Another phone
gets "SECURITY LOCK", and the real phone gets a push alert about the attempt.
Only an admin can unbind it, after the student shows their physical ID.

**Q: Could someone add their fingerprint to a friend's phone?**
Yes, today. The friend adds a classmate's print in system settings, lets them
check in, then deletes it. The fix is to bind the check-in key to the phone's
*current* enrolled fingerprints, so any change invalidates it. That's designed
but not implemented yet.

**Q: Can the NFC code be copied and used later?**
Not usefully. It expires 10 seconds after minting, it's tied to one student
and one session, and changing any byte breaks the signature. A relay attacker
would need to capture it and present it to a reader, within ~4 cm, inside that
10 s.
*Limitation:* Within those 10 s it isn't strictly single-use. But a replay can
only re-mark the same student in the same session, which the database ignores
as a duplicate.

**Q: Can the Bluetooth code be relayed?**
Yes, and that is the honest weakness of BLE. Someone in the room can hear the
code and send it to an absent friend, who submits it within ~10 seconds.
The friend still needs their own bound phone, fingerprint and login, and the
standard app only takes codes from its own scan. That's why BLE is only the
fallback, and why every record stores `nfc` or `ble` for lecturers to see.

**Q: Why not use Bluetooth signal strength to prove closeness?**
The phone reports the signal strength, so a modified app could report any
number. We use it only to tell the student "move closer", never to accept a
check-in.

**Q: What about rooted or jailbroken phones?**
freeRASP checks the device at startup, and check-in is refused if it reports
the device as compromised. This runs *before* the fingerprint prompt, because
a hooking tool on a rooted phone could fake the fingerprint result.
*Limitation:* RASP is a detection arms race, not a guarantee.

**Q: Could someone fake a terminal?**
The server only accepts check-ins with the terminal's ID and secret. The
terminal verifies the server's TLS certificate against the public root CAs
built into the ESP32 core, so someone on the venue Wi-Fi can't pose as the
server and collect the secret.
*Limitation:* Every terminal shares one secret, so dumping one board's flash
exposes it. Per-terminal secrets are the next step.

## Reliability

**Q: What if the server is asleep?**
Render's free tier sleeps, and we measured 8.5 s to wake, which is longer
than a code lives. So the terminal keeps the server awake: it pings at boot,
every 4 minutes while idle, and right before a check-in if it hasn't confirmed
the server is warm in the last minute.
*Limitation:* A paid tier would remove the problem. This is a workaround.

**Q: What if the terminal loses Wi-Fi?**
It keeps reading taps and stores up to 16 in flash, which survives power loss.
It uploads them when it reconnects. The server records them as "pending
verification" with the tap time. It doesn't count them automatically, because
by then the codes have expired, and accepting expired codes would defeat the
10-second rule.
*Limitation:* The lecturer screen to review them isn't built yet.

**Q: Why 10 seconds? Isn't that long?**
It was 3 s. On real hardware the machine part takes about 0.5 s, and almost
all of the 3 s went on the student walking up and holding the phone steady,
so genuine students were rejected. 10 s is still a third of what
authenticator apps use (30 s), and too short to carry a code anywhere useful.

**Q: What if two lecturers run classes at the same time?**
The session is fixed in the code when it's minted, from courses the student is
actually enrolled in. A tap in room A can't be credited to room B.
*Limitation:* If one student is enrolled in two sessions running at the same
moment, the most recently started one is chosen.

**Q: What if the lecturer ends the class as a student taps?**
The server re-checks that the session is still active when the code arrives,
and refuses with "session has ended".

## Platforms

**Q: What about iPhones?**
iPhones can't emulate an NFC card (Apple allows it only in the EEA), so they
use the Bluetooth fallback.
*Limitation:* The iPhone Bluetooth path is built but hasn't been tested on a
real iPhone.

**Q: What about Android phones without NFC?**
They use Bluetooth too. The app picks automatically, or the student can choose
in their profile.

**Q: What if the phone can't read its hardware ID?**
It refuses to log in rather than sending a placeholder. A shared placeholder
would make every such phone look like the same device, and the server
rejects the old placeholder strings.

## Engineering

**Q: Why the PN532 instead of the cheaper MFRC522?**
The MFRC522 setup reads card UIDs. Talking to a phone doing card emulation
needs an ISO 14443-4 APDU exchange, which the PN532 supports.

**Q: How do you know the phone, terminal and server agree on the Bluetooth
code?**
There's a shared reference test vector. The server's tests check it, and the
terminal checks the same vector at boot and refuses to broadcast if it
doesn't match.

**Q: How are secrets handled?**
They're in environment variables (server) and a gitignored `secrets.h`
(terminal). The server won't start without its core secrets. Check-in turns
itself off, with a logged reason, if its secret is missing. There are no
fallback defaults.
*Limitation:* Early versions committed real credentials, which are still in
git history. They're treated as burned.

**Q: What would you do with more time?**
Biometric invalidation, offline-tap review,
automatic session start/stop from the timetable, per-terminal secrets, and a real iPhone test.
