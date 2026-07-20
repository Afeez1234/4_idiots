# SUAAMS — Smart University Attendance and Administrative Management System

> **High-performance, security-hardened IoT hybrid system for university attendance tracking and administrative management**

## 📋 Overview

SUAAMS is a **capstone project** (Mechatronics Engineering, final year) that provides a modern, efficient solution for university attendance management. The system combines a mobile-first approach with NFC/BLE hardware integration for seamless student check-in at lectures.

### Key Features
- 🔐 **Security-hardened**: Biometric verification, device binding, relay attack protection
- 📱 **Mobile-first**: Flutter frontend with Riverpod state management
- 🏗️ **Backend**: Flask API with SQLAlchemy ORM, MySQL database on Clever Cloud
- 🔌 **IoT Ready**: ESP32 hardware support via NFC HCE and BLE proximity
- ⚡ **High-performance**: Optimized UI rendering, efficient database pooling

---

## 🏗️ Repository Structure

```
4_idiots/
├── SUAAMS/                    # Flask API backend
│   ├── api/                   # Mobile endpoint blueprints
│   ├── blueprints/            # Web dashboards (admin, lecturer, student)
│   ├── models.py              # SQLAlchemy ORM entities
│   ├── app.py                 # Flask application factory
│   └── ...
├── SUAAMS_Mobile/             # Flutter frontend
│   └── suaams/
│       ├── lib/
│       │   ├── core/          # Constants, theme, providers
│       │   ├── features/      # Feature modules (auth, student)
│       │   ├── shared/        # Custom painters, widgets
│       │   └── main.dart
│       └── pubspec.yaml
└── README.md
```

---

## 🚀 Getting Started

### Backend (Flask API)

**Prerequisites**: Python 3.8+, MySQL

```bash
cd SUAAMS
pip install -r requirements.txt
export FLASK_APP=app.py
export FLASK_ENV=development
flask run
```

**Database Setup**:
```bash
flask db upgrade
```

### Frontend (Flutter)

**Prerequisites**: Flutter SDK 3.0+, Android SDK / Xcode

```bash
cd SUAAMS_Mobile/suaams
flutter pub get
flutter run
```

---

## 🔒 Security Architecture

### Anti-Spoofing Measures

| Threat | Defense |
|--------|---------|
| **Buddy Punching** | Mandatory biometric (FaceID/fingerprint) or device PIN before NFC/BLE transactions |
| **Device Binding** | Accounts locked to primary phone hardware ID (`device_id`) at first login |
| **Biometric Invalidation** | Keys bind to OS biometric set; adding/deleting prints invalidates keys instantly |
| **Relay Attacks** | **3-second TTL** on server-side token validation; cryptographically signed timestamps |
| **Rooted/Jailbroken Devices** | Runtime integrity checking (freerasp); refuses token generation on compromised OS |

---

## 📐 Architecture Details

### Frontend Stack
- **Framework**: Flutter (Dart)
- **State Management**: Riverpod v3.x
- **Routing**: GoRouter (declarative)
- **Secure Storage**: Flutter Secure Storage (hardware key store)
- **Design**: Midnight-black theme, Plus Jakarta Sans, custom SUAAMS logo

### Backend Stack
- **Framework**: Python Flask
- **ORM**: Flask-SQLAlchemy
- **Authentication**: Flask-JWT-Extended (stateless)
- **Database**: MySQL (Clever Cloud)
- **Deployment**: Render
- **Migrations**: Flask-Migrate

### Hardware
- **Microcontroller**: ESP32
- **Proximity**: NFC HCE (ISO 7816-4 APDU), BLE (RSSI)

---

## 📝 Coding Standards

### Frontend (Flutter)

**Imports**: Always use absolute package imports
```dart
// ✓ Correct
import 'package:suaams/features/auth/providers/auth_provider.dart';

// ✗ Wrong — causes duplicate type definitions
import '../providers/auth_provider.dart';
```

**UI Performance**:
- Wrap `TextFormField` / dynamic widgets in `RepaintBoundary`
- Static backgrounds in fixed-size box with `const` constructors
- Use `resizeToAvoidBottomInset: true` + `ClampingScrollPhysics`

**Riverpod 3.x**:
- Extend `Notifier<StateT>` (no legacy `StateNotifier`)
- Use `NotifierProvider.autoDispose<MyNotifier, MyState>(MyNotifier.new)`
- Check `ref.mounted` for async lifecycle safety

### Backend (Flask)

**Database**: ORM-only — no raw SQL or direct cursors
```python
# ✓ Correct
user = User.query.filter_by(email=email).first()
db.session.add(record)

# ✗ Wrong — thread leaks under concurrent load
cursor = connection.cursor()
cursor.execute("SELECT ...")
```

**Timestamps**: Always UTC
```python
from datetime import datetime, timezone
created_at = datetime.now(timezone.utc)
```

**Cascades**: Define strict cascades for clean orphan pruning
```python
class Parent(db.Model):
    children = db.relationship('Child', cascade='all, delete-orphan')
```

---

## 🎯 Core Differentiator

**Smart ID via NFC HCE** — Primary check-in mechanism replaces traditional fingerprint scanners:

- **Speed**: NFC/BLE handshake (<0.5s) vs. physical scanner (~2s) → **200-student lecture: 2 min vs. 6.7 min**
- **Scalability**: Phone's secure enclave stores biometric; ESP32 only handles 32-byte JWT → unlimited enrollment
- **Sync**: No template-sync issues across distributed terminals

---

## 🗺️ Roadmap

### Planned (Not Yet Built)

#### Timetable Automation
- Soft version: Web dashboard banner shows "Open Terminal" when class is due
- Full version: Flask-APScheduler background worker auto-starts/stops sessions
- **Offline resilience**: ESP32 caches daily timetable; syncs backlog on reconnection

#### Enrollment at Scale
- Self-service course registration in Flutter app
- Admin bulk CSV uploader (parses IDs, links courses, generates auth codes)

---

## 📚 Development Workflow

**Key Principle**: Discuss logic and reasoning **first**, before writing code. Explain approach, tradeoffs, confirm direction, then implement.

### API Boundary Changes
When modifying API response shapes (backend) or models (frontend), always update both sides:
- API response schema ↔ Flutter model
- This prevents silent field-mismatch bugs at runtime

---
