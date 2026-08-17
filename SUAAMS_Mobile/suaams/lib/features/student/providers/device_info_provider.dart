import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/device_info.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

class DeviceInfoState {
  final bool isLoading;
  final DeviceInfo? data;
  final String? errorMessage;

  DeviceInfoState({this.isLoading = false, this.data, this.errorMessage});

  DeviceInfoState copyWith({
    bool? isLoading,
    DeviceInfo? data,
    String? errorMessage,
  }) {
    return DeviceInfoState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final deviceInfoProvider =
    NotifierProvider.autoDispose<DeviceInfoNotifier, DeviceInfoState>(
      DeviceInfoNotifier.new,
    );

class DeviceInfoNotifier extends Notifier<DeviceInfoState> {
  @override
  DeviceInfoState build() {
    state = DeviceInfoState();
    Future.microtask(() => loadDeviceInfo());
    return state;
  }

  Future<void> loadDeviceInfo() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final studentService = ref.read(studentServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => studentService.fetchDeviceInfo(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, data: data);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }
}
