// Mirrors GET /api/v1/student/device-info's JSON shape -- see
// get_device_info in api/student.py.
class DeviceInfo {
  final bool deviceBound;

  DeviceInfo({required this.deviceBound});

  factory DeviceInfo.fromJson(Map<String, dynamic> json) {
    return DeviceInfo(deviceBound: json['device_bound'] as bool);
  }
}
