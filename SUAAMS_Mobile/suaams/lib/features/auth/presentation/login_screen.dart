// This file is the login screen for the SUAAMS app.
// It provides a form for users to enter their credentials and handles
// the login process using Riverpod for state management.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/auth_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';
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
  final FocusNode _passwordFocusNode = FocusNode();

  bool _isPasswordVisible = false;

  @override
  void dispose() {
    _idController.dispose();
    _passwordController.dispose();
    _passwordFocusNode.dispose();
    super.dispose();
  }

  Future<void> _handleSignIn() async {
    final formState = _formKey.currentState;
    if (formState == null || !formState.validate()) {
      return;
    }

    FocusScope.of(context).unfocus();
    ScaffoldMessenger.of(context).hideCurrentSnackBar();

    final success = await ref
        .read(authProvider.notifier)
        .login(_idController.text.trim(), _passwordController.text);

    if (!mounted) {
      return;
    }

    if (success) {
      TextInput.finishAutofillContext();
      return;
    }

    final error = ref.read(authProvider).errorMessage;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(error ?? 'Unable to sign in. Please try again.'),
        backgroundColor: Theme.of(context).colorScheme.error,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onTap: () => FocusScope.of(context).unfocus(),
        child: Stack(
          children: [
            _LoginBackground(isDarkMode: isDarkMode, colorScheme: colorScheme),
            SafeArea(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final isCompact = constraints.maxHeight < 680;
                  final verticalPadding = isCompact ? 16.0 : 32.0;
                  final availableHeight =
                      constraints.maxHeight - (verticalPadding * 2);

                  return SingleChildScrollView(
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    padding: EdgeInsets.fromLTRB(
                      24,
                      verticalPadding,
                      24,
                      verticalPadding,
                    ),
                    child: ConstrainedBox(
                      constraints: BoxConstraints(
                        minHeight: availableHeight > 0 ? availableHeight : 0,
                      ),
                      child: Center(
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 420),
                          child: AutofillGroup(
                            child: Form(
                              key: _formKey,
                              autovalidateMode:
                                  AutovalidateMode.onUserInteraction,
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  Center(
                                    child: SuaamsLogoFull(
                                      size: isCompact ? 52 : 64,
                                      color: colorScheme.primary,
                                    ),
                                  ),
                                  SizedBox(height: isCompact ? 28 : 44),
                                  Text(
                                    'Welcome back',
                                    style: Theme.of(context)
                                        .textTheme
                                        .headlineSmall
                                        ?.copyWith(
                                          color: colorScheme.onSurface,
                                          fontWeight: FontWeight.w800,
                                        ),
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Sign in with your assigned credentials.',
                                    style: Theme.of(context)
                                        .textTheme
                                        .bodyMedium
                                        ?.copyWith(
                                          color: colorScheme.onSurface
                                              .withValues(alpha: 0.6),
                                        ),
                                  ),
                                  SizedBox(height: isCompact ? 24 : 32),
                                  _buildInputLabel('USERNAME', colorScheme),
                                  const SizedBox(height: 8),
                                  _buildTextField(
                                    controller: _idController,
                                    hintText: 'Enter your username',
                                    icon: Icons.badge_rounded,
                                    colorScheme: colorScheme,
                                    enabled: !authState.isLoading,
                                    autofillHints: const [
                                      AutofillHints.username,
                                    ],
                                    textInputAction: TextInputAction.next,
                                    onFieldSubmitted: (_) =>
                                        _passwordFocusNode.requestFocus(),
                                    validator: (value) =>
                                        (value == null || value.trim().isEmpty)
                                        ? 'Enter your username'
                                        : null,
                                  ),
                                  const SizedBox(height: 20),
                                  _buildInputLabel(
                                    'AUTHORIZATION CODE',
                                    colorScheme,
                                  ),
                                  const SizedBox(height: 8),
                                  _buildTextField(
                                    controller: _passwordController,
                                    focusNode: _passwordFocusNode,
                                    hintText: 'Enter your authorization code',
                                    icon: Icons.lock_outline_rounded,
                                    isPassword: true,
                                    colorScheme: colorScheme,
                                    enabled: !authState.isLoading,
                                    autofillHints: const [
                                      AutofillHints.password,
                                    ],
                                    textInputAction: TextInputAction.done,
                                    onFieldSubmitted: (_) {
                                      if (!authState.isLoading) {
                                        _handleSignIn();
                                      }
                                    },
                                    validator: (value) =>
                                        (value == null || value.isEmpty)
                                        ? 'Enter your authorization code'
                                        : null,
                                  ),
                                  SizedBox(height: isCompact ? 28 : 36),
                                  ElevatedButton(
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: colorScheme.primary,
                                      foregroundColor: colorScheme.onPrimary,
                                      disabledBackgroundColor: colorScheme
                                          .primary
                                          .withValues(alpha: 0.6),
                                      disabledForegroundColor:
                                          colorScheme.onPrimary,
                                      minimumSize: const Size(
                                        double.infinity,
                                        56,
                                      ),
                                      shape: RoundedRectangleBorder(
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      elevation: 0,
                                    ),
                                    onPressed: authState.isLoading
                                        ? null
                                        : _handleSignIn,
                                    child: AnimatedSwitcher(
                                      duration: const Duration(
                                        milliseconds: 180,
                                      ),
                                      child: authState.isLoading
                                          ? SizedBox(
                                              key: const ValueKey('loading'),
                                              height: 24,
                                              width: 24,
                                              child: CircularProgressIndicator(
                                                color: colorScheme.onPrimary,
                                                strokeWidth: 2.5,
                                              ),
                                            )
                                          : const Text(
                                              'SIGN IN',
                                              key: ValueKey('label'),
                                              style: TextStyle(
                                                letterSpacing: 2,
                                                fontWeight: FontWeight.bold,
                                                fontSize: 14,
                                              ),
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
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputLabel(String text, ColorScheme colorScheme) {
    return Text(
      text,
      style: TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.bold,
        letterSpacing: 1.2,
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
    required bool enabled,
    required Iterable<String> autofillHints,
    required TextInputAction textInputAction,
    required ValueChanged<String> onFieldSubmitted,
    FocusNode? focusNode,
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
      focusNode: focusNode,
      enabled: enabled,
      obscureText: isPassword && !_isPasswordVisible,
      autofillHints: autofillHints,
      textInputAction: textInputAction,
      textCapitalization: TextCapitalization.none,
      autocorrect: false,
      enableSuggestions: false,
      onFieldSubmitted: onFieldSubmitted,
      scrollPadding: EdgeInsets.only(
        bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
      ),
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
                tooltip: _isPasswordVisible
                    ? 'Hide authorization code'
                    : 'Show authorization code',
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
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colorScheme.error, width: 2),
        ),
        errorMaxLines: 2,
      ),
      validator: validator,
    );
  }
}

class _LoginBackground extends StatelessWidget {
  final bool isDarkMode;
  final ColorScheme colorScheme;

  const _LoginBackground({required this.isDarkMode, required this.colorScheme});

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
                  ? const Color(0xFF0A0A14).withValues(alpha: 0.6)
                  : const Color(0xFFE0E7FF).withValues(alpha: 0.75),
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
                  ? const Color(0xFF080810).withValues(alpha: 0.65)
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
