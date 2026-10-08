import 'dart:async';
import 'dart:io' show Platform;

import 'package:device_info_plus/device_info_plus.dart';
import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:permission_handler/permission_handler.dart';

final bleScanServiceProvider = Provider<BleScanService>(
  (ref) => BleScanService(),
);

/// Whether this phone can listen for the terminal's Bluetooth code right
/// now. Checked before the fingerprint prompt, like NfcAvailability, so a
/// student is never asked to authenticate for a scan that can't run.
enum BleReadiness {
  ready,

  /// Bluetooth is switched off. Android can show its own "turn on" prompt.
  off,

  /// Permission not granted yet, but the OS will still ask.
  needsPermission,

  /// Permission denied for good (Android "don't ask again", or any iOS
  /// denial). Only the app's settings page can fix it.
  permissionBlocked,

  /// Android 11 and older only: scanning there needs Location switched on.
  locationOff,

  /// No Bluetooth LE on this device.
  unsupported,
}

/// One reading of the terminal's advertisement.
class BleHeard {
  /// The 14 bytes after the company ID, as lowercase hex -- forwarded to
  /// the server unparsed, so the byte layout lives only in ble_beacon.py
  /// and the firmware.
  final String payloadHex;
  final int rssi;

  const BleHeard(this.payloadHex, this.rssi);
}

/// Listens for the terminal's rotating check-in code (see
/// SUAAMS/ble_beacon.py and the "Bluetooth check-in beacon" section of
/// SUAAMS_HCE.ino).
class BleScanService {
  /// Bluetooth SIG's reserved "testing / no company" ID, which the terminal
  /// advertises under. Must match BLE_COMPANY_ID in the firmware.
  static const int companyId = 0xFFFF;
  static const int payloadLength = 14;

  /// Signal strength above which a reading is good enough to submit at
  /// once. Below it the scan keeps listening for a stronger one, and the UI
  /// says "move closer". Phone-reported, so a UX threshold only -- the
  /// server never uses RSSI to accept or reject. Tune at the bench.
  static const int strongRssi = -75;

  Future<int?> _androidSdk() async {
    if (!Platform.isAndroid) return null;
    return (await DeviceInfoPlugin().androidInfo).version.sdkInt;
  }

  /// The runtime permissions a scan needs on this Android version. Empty on
  /// iOS, where the adapter state reports a denial instead.
  ///
  /// Android 12+: the "Nearby devices" group -- SCAN, plus CONNECT, because
  /// flutter_blue_plus reads device names while scanning and refuses to
  /// start without it (checked in its startScan). Android shows both as one
  /// prompt. Android 11 and older: location, which those versions require
  /// for any Bluetooth scan.
  Future<List<Permission>> _scanPermissions() async {
    final sdk = await _androidSdk();
    if (sdk == null) return const [];
    return sdk >= 31
        ? const [Permission.bluetoothScan, Permission.bluetoothConnect]
        : const [Permission.locationWhenInUse];
  }

  Future<BleReadiness> readiness() async {
    try {
      if (!await FlutterBluePlus.isSupported) return BleReadiness.unsupported;

      final permissions = await _scanPermissions();
      for (final permission in permissions) {
        final status = await permission.status;
        if (status.isPermanentlyDenied) return BleReadiness.permissionBlocked;
        if (!status.isGranted) return BleReadiness.needsPermission;
      }
      if (permissions.contains(Permission.locationWhenInUse) &&
          await Permission.locationWhenInUse.serviceStatus !=
              ServiceStatus.enabled) {
        return BleReadiness.locationOff;
      }

      // The adapter state starts as `unknown` while the platform side
      // initialises; wait briefly for a real value.
      final state = await FlutterBluePlus.adapterState
          .firstWhere((s) => s != BluetoothAdapterState.unknown)
          .timeout(
            const Duration(seconds: 3),
            onTimeout: () => FlutterBluePlus.adapterStateNow,
          );
      switch (state) {
        case BluetoothAdapterState.on:
          return BleReadiness.ready;
        case BluetoothAdapterState.unauthorized:
          // iOS: the student denied Bluetooth for this app.
          return BleReadiness.permissionBlocked;
        case BluetoothAdapterState.unavailable:
          return BleReadiness.unsupported;
        default:
          return BleReadiness.off;
      }
    } catch (e) {
      debugPrint('[BLE] readiness check failed: $e');
      return BleReadiness.unsupported;
    }
  }

  /// Asks for the scan permission (Android). Returns the new readiness.
  Future<BleReadiness> requestPermission() async {
    final permissions = await _scanPermissions();
    if (permissions.isNotEmpty) await permissions.request();
    return readiness();
  }

  /// Android shows its own "turn on Bluetooth?" dialog. iOS has no API for
  /// this; the caller tells the student to use Control Centre instead.
  Future<void> turnOn() async {
    if (!Platform.isAndroid) return;
    try {
      await FlutterBluePlus.turnOn();
    } catch (e) {
      debugPrint('[BLE] turnOn declined or failed: $e');
    }
  }

  Future<void> openSettings() => openAppSettings();

  /// Listens for up to [window] and returns the best reading, or null if
  /// the terminal was never heard.
  ///
  /// Returns early on the first reading at or above [strongRssi]. Otherwise
  /// returns the most RECENT reading at the end of the window, not the
  /// strongest: the code rotates every 5s, and an older strong reading may
  /// already have expired, while signal strength only affects the UI.
  /// [onWeakSignal] fires when the terminal is heard but faintly, so the UI
  /// can say "move closer" while listening continues.
  Future<BleHeard?> scanForTerminal({
    Duration window = const Duration(seconds: 8),
    void Function()? onWeakSignal,
  }) async {
    BleHeard? latest;
    final done = Completer<BleHeard?>();

    final subscription = FlutterBluePlus.onScanResults.listen((results) {
      for (final r in results) {
        final data = r.advertisementData.manufacturerData[companyId];
        if (data == null || data.length != payloadLength) continue;
        final heard = BleHeard(_hex(data), r.rssi);
        latest = heard;
        if (heard.rssi >= strongRssi) {
          if (!done.isCompleted) done.complete(heard);
          return;
        }
        onWeakSignal?.call();
      }
    }, onError: (Object e) => debugPrint('[BLE] scan error: $e'));

    try {
      await FlutterBluePlus.startScan(
        withMsd: [MsdFilter(companyId)],
        // Keep reporting repeat adverts: the code changes every 5s and
        // the RSSI moves as the student walks up.
        continuousUpdates: true,
        // The plugin's own check refuses to scan whenever Location is off,
        // even on Android 12+ where Bluetooth scanning doesn't need it.
        // readiness() already checks Location on the versions that do.
        androidCheckLocationServices: false,
        timeout: window,
      );
      final heard = await done.future.timeout(
        window,
        onTimeout: () => latest,
      );
      return heard;
    } finally {
      await subscription.cancel();
      try {
        await FlutterBluePlus.stopScan();
      } catch (_) {}
    }
  }

  static String _hex(List<int> bytes) =>
      bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
}
