import 'package:flutter/material.dart';
import '../../../shared/widgets/primary_button.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  // Controllers capture the raw text inputs from the form fields
  final TextEditingController _idController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  
  // A GlobalKey uniquely identifies this specific form to handle input validation
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  
  bool _isPasswordVisible = false;
  bool _isLoading = false;

  @override
  void dispose() {
    // Always clean up controllers when the widget is destroyed to prevent memory leaks
    _idController.dispose();
    _passwordController.dispose();
    super.overrideWidgetdispose();
  }

  void _handleSignIn() {
    if (_formKey.currentState!.validate()) {
      setState(() {
        _isLoading = true;
      });

      // TODO: Connect Riverpod auth provider here for Flask API call
      // Future deployment step: ref.read(authProvider.notifier).login(...)
    }
  }

  @override
  Widget build(BuildContext context) {
    // Mediaquery ensures the layout adapts gracefully to varying screen heights
    final screenHeight = MediaQuery.of(context).size.height;

    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24.0),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(height: screenHeight * 0.12),
                
                // Branding / Header Section
                Text(
                  'SUAAMS',
                  style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                        letterSpacing: 1.5,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Smart Universal Automated Attendance Management System',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Colors.grey[400],
                      ),
                  textAlign: TextAlign.center,
                ),
                
                SizedBox(height: screenHeight * 0.08),

                // Input Field: Identification
                TextFormField(
                  controller: _idController,
                  keyboardType: TextInputType.text,
                  decoration: InputDecoration(
                    labelText: 'User ID / Email',
                    hintText: 'Enter your unique identification',
                    prefixIcon: const Icon(Icons.person_outline),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  validator: (value) {
                    if (value == null || value.trim().isEmpty) {
                      return 'Please enter your User ID or Email';
                    }
                    return null;
                  },
                ),
                const SizedBox(height: 20),

                // Input Field: Password
                TextFormField(
                  controller: _passwordController,
                  obscureText: !_isPasswordVisible,
                  decoration: InputDecoration(
                    labelText: 'Password',
                    hintText: 'Enter your password',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      icon: Icon(
                        _isPasswordVisible ? Icons.visibility : Icons.visibility_off,
                      ),
                      onPressed: () {
                        setState(() {
                          _isPasswordVisible = !_isPasswordVisible;
                        });
                      },
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  validator: (value) {
                    if (value == null || value.isEmpty) {
                      return 'Please enter your password';
                    }
                    if (value.length < 6) {
                      return 'Password must be at least 6 characters';
                    }
                    return null;
                  },
                ),
                
                const SizedBox(height: 32),

                // Reusable Primary Button Component
                PrimaryButton(
                  text: 'Sign In',
                  isLoading: _isLoading,
                  onPressed: _handleSignIn,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}