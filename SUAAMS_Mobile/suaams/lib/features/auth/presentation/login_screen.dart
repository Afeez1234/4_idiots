import 'package:suaams/shared/widgets/dashboard_background.dart';
// STREAMING_CHUNK: Importing core dependencies...
// This file is the login screen for the SUAAMS app.
// It provides a form for users to enter their credentials and handles
// the login process using Riverpod for state management.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';
import '../../../shared/widgets/suaams_logo.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final TextEditingController _idController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _isPasswordVisible = false;

  @override
  void dispose() {
    _idController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  // STREAMING_CHUNK: Processing credential verification...
  void _handleSignIn() async {
    if (_formKey.currentState!.validate()) {
      FocusScope.of(context).unfocus();

      final success = await ref
          .read(authProvider.notifier)
          .login(_idController.text.trim(), _passwordController.text);

      if (mounted && !success) {
        final error = ref.read(authProvider).errorMessage;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              error ?? 'ACCESS DENIED',
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
              ),
            ),
            backgroundColor: Theme.of(context).colorScheme.error,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(8),
            ),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // STREAMING_CHUNK: Caching hardware screen dimensions...
    // sizeOf guarantees the build method is bypassed during viewport transitions
    final screenSize = MediaQuery.sizeOf(context);
    final screenHeight = screenSize.height;
    final screenWidth = screenSize.width;

    final authState = ref.watch(authProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      resizeToAvoidBottomInset: true,
      body: Stack(
        clipBehavior: Clip.none,
        children: [
          // OPTIMIZATION 1: Marked background as const.
          // Dart loads this directly from pre-compiled memory.
          Positioned(
            top: 0,
            left: 0,
            width: screenWidth,
            height: screenHeight,
            child: RepaintBoundary(
              child: DashboardBackground(
                isDarkMode: isDarkMode,
                colorScheme: colorScheme,
                variant: AppBackgroundVariant.auth,
              ),
            ),
          ),

          // Foreground Content Layer
          // STREAMING_CHUNK: Isolating input repaints...
          Positioned.fill(
            child: SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  physics: const ClampingScrollPhysics(),
                  padding: const EdgeInsets.all(24.0),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Center(
                          child: RepaintBoundary(
                            child: SuaamsLogoFull(
                              size: 64,
                              color: colorScheme.primary,
                            ),
                          ),
                        ),

                        SizedBox(height: screenHeight * 0.05),

                        _buildInputLabel('USERNAME', colorScheme),
                        const SizedBox(height: 8),

                        // OPTIMIZATION 2: Isolated TextField inside its own RepaintBoundary.
                        // This prevents cursor blinking from forcing a repaint of the grid!
                        RepaintBoundary(
                          child: _buildTextField(
                            controller: _idController,
                            hintText: 'Enter your username',
                            icon: Icons.badge_rounded,
                            colorScheme: colorScheme,
                            validator: (value) =>
                                (value == null || value.trim().isEmpty)
                                ? 'USERNAME REQUIRED'
                                : null,
                          ),
                        ),

                        const SizedBox(height: 24),

                        _buildInputLabel('PASSWORD', colorScheme),
                        const SizedBox(height: 8),

                        // OPTIMIZATION 3: Isolated Password Field inside its own RepaintBoundary.
                        RepaintBoundary(
                          child: _buildTextField(
                            controller: _passwordController,
                            hintText: 'Enter password',
                            icon: Icons.lock_outline_rounded,
                            isPassword: true,
                            colorScheme: colorScheme,
                            validator: (value) =>
                                (value == null || value.isEmpty)
                                ? 'PASSWORD REQUIRED'
                                : null,
                          ),
                        ),

                        const SizedBox(height: 40),

                        ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.surface,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 0,
                          ),
                          onPressed: authState.isLoading ? null : _handleSignIn,
                          child: authState.isLoading
                              ? SizedBox(
                                  height: 24,
                                  width: 24,
                                  child: CircularProgressIndicator(
                                    color: colorScheme.surface,
                                    strokeWidth: 2.5,
                                  ),
                                )
                              : const Text(
                                  'LOG IN',
                                  style: TextStyle(
                                    letterSpacing: 3,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 14,
                                  ),
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInputLabel(String text, ColorScheme colorScheme) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 10,
        fontWeight: FontWeight.bold,
        letterSpacing: 1.5,
        color: colorScheme.onSurface.withValues(alpha: 0.6),
      ),
    );
  }

  // STREAMING_CHUNK: Configuring custom text fields...
  Widget _buildTextField({
    required TextEditingController controller,
    required String hintText,
    required IconData icon,
    required ColorScheme colorScheme,
    required String? Function(String?) validator,
    bool isPassword = false,
  }) {
    final borderStyle = OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide(
        color: colorScheme.outline.withValues(alpha: 0.15),
      ),
    );

    return TextFormField(
      controller: controller,
      obscureText: isPassword && !_isPasswordVisible,
      scrollPadding: const EdgeInsets.symmetric(vertical: 40),
      style: TextStyle(
        fontWeight: FontWeight.w600,
        color: colorScheme.onSurface,
      ),
      decoration: InputDecoration(
        filled: true,
        fillColor: colorScheme.surfaceContainer,
        hintText: hintText,
        hintStyle: TextStyle(
          color: colorScheme.onSurface.withValues(alpha: 0.3),
          fontWeight: FontWeight.normal,
        ),
        prefixIcon: Icon(
          icon,
          color: colorScheme.onSurface.withValues(alpha: 0.5),
          size: 20,
        ),
        suffixIcon: isPassword
            ? IconButton(
                icon: Icon(
                  _isPasswordVisible
                      ? Icons.visibility_rounded
                      : Icons.visibility_off_rounded,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                  size: 20,
                ),
                onPressed: () =>
                    setState(() => _isPasswordVisible = !_isPasswordVisible),
              )
            : null,
        border: borderStyle,
        enabledBorder: borderStyle,
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colorScheme.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colorScheme.error, width: 1.5),
        ),
      ),
      validator: validator,
    );
  }
}

// STREAMING_CHUNK: Allocating pre-compiled background...
