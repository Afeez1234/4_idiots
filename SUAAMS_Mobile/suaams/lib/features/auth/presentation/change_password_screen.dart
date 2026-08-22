/* STREAMING_CHUNK: Importing core dependencies... */
// This screen is shown when a user logs in for the first time and needs to change their default password.
// It follows the same terminal aesthetic as the login screen for visual consistency.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';

class ChangePasswordScreen extends ConsumerStatefulWidget {
  // Two entry points share this one screen: the forced first-login reset
  // (app_router.dart's redirect guard + splash_screen.dart, both via
  // context.go() -- no previous route to go back to, and going back would
  // let a user dodge a mandatory reset, so isMandatory defaults to true and
  // no back button is shown) and a voluntary visit from Profile > Account
  // Security (context.push() with isMandatory explicitly false). Only the
  // voluntary case gets a back button -- that's the one users can land on
  // by mistake.
  final bool isMandatory;

  const ChangePasswordScreen({super.key, this.isMandatory = true});

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

  /* STREAMING_CHUNK: Processing password modification... */
  void _handleUpdate() async {
    if (_formKey.currentState!.validate()) {
      FocusScope.of(context).unfocus();

      final success = await ref
          .read(authProvider.notifier)
          .changePassword(_newPasswordController.text);

      if (mounted) {
        if (success) {
          // DEEP FIX 1: Explicitly force navigation on success to bypass Router redirect lag
          final user = ref.read(authProvider).user;
          if (user?.role == 'student') {
            context.go('/student/home');
          } else if (user?.role == 'lecturer') {
            context.go('/lecturer/home');
          } else if (user?.role == 'admin') {
            context.go('/admin');
          }
        } else {
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
  }

  @override
  Widget build(BuildContext context) {
    /* STREAMING_CHUNK: Caching hardware screen dimensions... */
    // Use sizeOf so keyboard height modifications never trigger build rebuilds of the entire screen
    final screenSize = MediaQuery.sizeOf(context);
    final screenHeight = screenSize.height;
    final screenWidth = screenSize.width;

    final authState = ref.watch(authProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      resizeToAvoidBottomInset: true,
      // Only the voluntary flow gets an AppBar/back button -- see the
      // isMandatory doc comment on the widget above.
      appBar: widget.isMandatory
          ? null
          : AppBar(
              backgroundColor: colorScheme.surface,
              elevation: 0,
              leading: IconButton(
                icon: const Icon(Icons.close_rounded),
                tooltip: 'Cancel',
                onPressed: () => context.pop(),
              ),
            ),
      body: Stack(
        // Prevents background layouts from clipping when the keyboard appears
        clipBehavior: Clip.none,
        children: [
          // OPTIMIZATION 1: Marked background as const with fixed screen dimensions
          Positioned(
            top: 0,
            left: 0,
            width: screenWidth,
            height: screenHeight,
            child: RepaintBoundary(
              child: _ChangePasswordBackground(
                isDarkMode: isDarkMode,
                colorScheme: colorScheme,
              ),
            ),
          ),
          
          /* STREAMING_CHUNK: Rendering form fields... */
          Positioned.fill(
            child: SafeArea(
              child: Center(
                child: SingleChildScrollView(
                  physics: const ClampingScrollPhysics(),
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
                          'PASSWORD UPDATE REQUIRED',
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
                          'PLEASE UPDATE YOUR DEFAULT PASSWORD',
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 2.0,
                            color: colorScheme.onSurface.withValues(alpha: 0.5),
                          ),
                          textAlign: TextAlign.center,
                        ),

                        SizedBox(height: screenHeight * 0.06),

                        _buildInputLabel('NEW PASSWORD', colorScheme),
                        const SizedBox(height: 8),
                        
                        // OPTIMIZATION 2: Isolated TextFormField inside its own RepaintBoundary
                        RepaintBoundary(
                          child: _buildTextField(
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
                        ),

                        const SizedBox(height: 24),

                        _buildInputLabel('CONFIRM NEW PASSWORD', colorScheme),
                        const SizedBox(height: 8),
                        
                        // OPTIMIZATION 3: Isolated TextFormField inside its own RepaintBoundary
                        RepaintBoundary(
                          child: _buildTextField(
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
                                return 'PASSWORDS DO NOT MATCH';
                              }
                              return null;
                            },
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
                                  'UPDATE PASSWORD',
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
      borderSide:
          BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
    );

    return TextFormField(
      controller: controller,
      obscureText: isPassword && !_isPasswordVisible,
      scrollPadding: const EdgeInsets.symmetric(vertical: 40),
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

// STREAMING_CHUNK: Allocating pre-compiled background...
class _ChangePasswordBackground extends StatelessWidget {
  final bool isDarkMode;
  final ColorScheme colorScheme;

  // Added const constructor to allow full static memory allocation
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
              // PERF FIX: const painter instance per branch (see
              // grid_overlay_painter.dart) instead of allocating a new one.
              painter: isDarkMode
                  ? const GridOverlayPainter(color: Colors.white)
                  : const GridOverlayPainter(color: Colors.black),
            ),
          ),
        ),
      ],
    );
  }
}