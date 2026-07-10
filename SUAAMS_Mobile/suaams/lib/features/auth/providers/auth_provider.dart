import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/auth_service.dart';
import '../models/auth_user.dart';

// 1. The State Class: Holds the current status of the user
class AuthState {
  final bool isLoading;
  final AuthUser? user;
  final String? errorMessage;

  AuthState({this.isLoading = false, this.user, this.errorMessage});

  // A helper method to easily update specific parts of the state
  AuthState copyWith({bool? isLoading, AuthUser? user, String? errorMessage}) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      user: user ?? this.user,
      errorMessage:
          errorMessage, // We don't use ?? here so we can clear errors by passing null
    );
  }
}

// 2. Provide the AuthService so the Notifier can use it
final authServiceProvider = Provider<AuthService>((ref) => AuthService());

// 3. Provide the AuthNotifier globally
final authProvider = NotifierProvider<AuthNotifier, AuthState>(
  AuthNotifier.new,
);

// 4. The Brain: Controls the logic and updates the UI
class AuthNotifier extends Notifier<AuthState> with ChangeNotifier {
  //  final _storage = const FlutterSecureStorage();
  AuthService get _authService => ref.read(authServiceProvider);

  @override
  AuthState build() {
    return AuthState();
  }


  void update(AuthState Function(AuthState p1) cb) {
    state = cb(state);
    notifyListeners();
  }


  // Function called by the Splash Screen to check if a user is already logged in
  Future<void> checkExistingAuth() async {
    state = state.copyWith(isLoading: true);
    notifyListeners();

    final token = await _authService.getToken();
    final role = await _authService.getUserRole();
    final username = await _authService.getUsername();

    if (token != null && role != null && username != null) {
      // Rebuild the user object from the vault
      final restoredUser = AuthUser(
        id: 0, // ID isn't strictly necessary for routing, but you can store it if needed
        username: username,
        role: role,
        token: token,
      );
      state = state.copyWith(isLoading: false, user: restoredUser);
      notifyListeners();
    } else {
      state = state.copyWith(isLoading: false);
      notifyListeners();
    }
  }

  // Function called by the Login Screen when the button is tapped
  Future<bool> login(String username, String password) async {
    state = state.copyWith(
      isLoading: true,
      errorMessage: null,
    ); // Start loading, clear old errors

    try {
      // Calls the network service we built
      final user = await _authService.login(username, password);

      // We also save the username to storage so checkExistingAuth can rebuild the object later
      await _authService.saveUsername(username);

      // Update state with the successful user (this triggers the router to change screens)
      state = state.copyWith(isLoading: false, user: user);
      return true;
    } catch (e) {
      // If the password is wrong, catch the error from Flask and show it on the UI
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
      notifyListeners();
      return false;
    }
  }

  // Function called by the Logout button
  Future<void> logout() async {
    await _authService.logout();
    state = AuthState(); // Reset state completely
    notifyListeners();
  }
}
