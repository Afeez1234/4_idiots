// This screen is shown when a user logs in for the first time and needs to change their default password.
// It follows the same terminal aesthetic as the login screen for visual consistency.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';

class ChangePasswordScreen extends ConsumerStatefulWidget {
  const ChangePasswordScreen({super.key});

  @override
  ConsumerState<ChangePasswordScreen> createState() =>
      _ChangePasswordScreenState();
}

class _ChangePasswordScreenState
    extends ConsumerState<ChangePasswordScreen> {
  final TextEditingController _newPasswordController =
      TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();

  bool _isPasswordVisible = false;

  @override
  void dispose() {
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  void _handleUpdate() async {
    if (_formKey.currentState!.validate()) {
      FocusScope.of(context).unfocus();

      final success = await ref
          .read(authProvider.notifier)
          .changePassword(_newPasswordController.text);

      if (mounted && !success) {
        final error = ref.read(authProvider).errorMessage;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              error ?? 'UPDATE FAILED',
              style: const TextStyle(
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
              ),
            ),
            backgroundColor: Theme.of(context).colorScheme.error,
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.of(context).size.height;
    final authState = ref.watch(authProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          _ChangePasswordBackground(
            isDarkMode: isDarkMode,
            colorScheme: colorScheme,
          ),
          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 24.0),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Icon(
                        Icons.security_update_warning_rounded,
                        size: 48,
                        color: colorScheme.error,
                      ),
                      const SizedBox(height: 24),
                      Text(
                        'SECURITY ALERT',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.w900,
                          color: colorScheme.error,
                          letterSpacing: 4.0,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'PLEASE UPDATE YOUR DEFAULT AUTHORIZATION CODE',
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2.0,
                          color: colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                        textAlign: TextAlign.center,
                      ),

                      SizedBox(height: screenHeight * 0.06),

                      _buildInputLabel('NEW CODE', colorScheme),
                      const SizedBox(height: 8),
                      _buildTextField(
                        controller: _newPasswordController,
                        hintText: 'Enter new password',
                        icon: Icons.lock_outline_rounded,
                        isPassword: true,
                        colorScheme: colorScheme,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'PASSWORD REQUIRED';
                          }
                          if (value.length < 6) return 'MINIMUM 6 CHARACTERS';
                          return null;
                        },
                      ),

                      const SizedBox(height: 24),

                      _buildInputLabel('CONFIRM NEW CODE', colorScheme),
                      const SizedBox(height: 8),
                      _buildTextField(
                        controller: _confirmPasswordController,
                        hintText: 'Re-enter password',
                        icon: Icons.lock_clock_rounded,
                        isPassword: true,
                        colorScheme: colorScheme,
                        validator: (value) {
                          if (value == null || value.isEmpty) {
                            return 'CONFIRMATION REQUIRED';
                          }
                          if (value != _newPasswordController.text) {
                            return 'CODES DO NOT MATCH';
                          }
                          return null;
                        },
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
                        onPressed: authState.isLoading ? null : _handleUpdate,
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
                                'UPDATE PROTOCOL',
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
      borderSide:
          BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
    );

    return TextFormField(
      controller: controller,
      obscureText: isPassword && !_isPasswordVisible,
      style:
          TextStyle(fontWeight: FontWeight.w600, color: colorScheme.onSurface),
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

class _ChangePasswordBackground extends StatelessWidget {
  final bool isDarkMode;
  final ColorScheme colorScheme;

  const _ChangePasswordBackground({
    required this.isDarkMode,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: Container(
            decoration: BoxDecoration(color: colorScheme.surface),
          ),
        ),
        Positioned(
          top: -100,
          right: -50,
          child: Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF140A0A).withValues(alpha: 0.6)
                  : const Color(0xFFFFE0E0).withValues(alpha: 0.75),
            ),
          ),
        ),
        Positioned(
          bottom: -80,
          left: -60,
          child: Container(
            width: 200,
            height: 200,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF100808).withValues(alpha: 0.65)
                  : const Color(0xFFFEF3C7).withValues(alpha: 0.55),
            ),
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: GridOverlayPainter(
                color: isDarkMode ? Colors.white : Colors.black,
              ),
            ),
          ),
        ),
      ],
    );
  }
}