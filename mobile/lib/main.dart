import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/api/api_service.dart';
import 'core/auth/auth_repository.dart';
import 'core/auth/token_storage.dart';
import 'core/theme/app_theme.dart';
import 'models/user_model.dart';
import 'screens/role_dashboards.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  final apiService = ApiService();
  final authRepository = AuthRepository(apiService);
  final initialUser = await authRepository.getCurrentUser();

  runApp(KinJoApp(initialUser: initialUser));
}

class KinJoApp extends StatelessWidget {
  final UserModel? initialUser;

  const KinJoApp({super.key, this.initialUser});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'KinJo - كينجو',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      
      // Native Arabic RTL & English LTR Localization
      locale: const Locale('ar', 'JO'),
      supportedLocales: const [
        Locale('ar', 'JO'),
        Locale('en', 'US'),
      ],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],

      home: initialUser != null
          ? RoleShellScreen(user: initialUser!)
          : const MobileLoginScreen(),
    );
  }
}

/// Dynamic Role-Based Shell Screen Router
class RoleShellScreen extends StatelessWidget {
  final UserModel user;

  const RoleShellScreen({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    switch (user.role) {
      case UserRole.parent:
        return ParentDashboardScreen(user: user);
      case UserRole.supervisor:
        return SupervisorDashboardScreen(user: user);
      case UserRole.manager:
        return ManagerDashboardScreen(user: user);
      case UserRole.admin:
      case UserRole.unknown:
        // Previously every unmatched role fell through to the parent screen, so
        // an admin silently landed on a parent's dashboard. Admin has no mobile
        // surface yet, so say that rather than show the wrong one.
        return _UnsupportedRoleScreen(user: user);
    }
  }
}

/// Shown to a role this app does not have a screen for.
class _UnsupportedRoleScreen extends StatelessWidget {
  final UserModel user;

  const _UnsupportedRoleScreen({required this.user});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('KinJo'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await TokenStorage.clearAll();
              if (!context.mounted) return;
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const MobileLoginScreen()),
              );
            },
          )
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.devices_other, size: 64, color: Colors.grey),
            const SizedBox(height: 16),
            Text(
              'لا توجد شاشة مخصّصة لدور ${user.role.value} في التطبيق بعد.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            const Text(
              'يرجى استخدام نسخة الويب للوصول إلى هذه الصلاحيات.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}

/// Mobile Login Screen
class MobileLoginScreen extends StatefulWidget {
  const MobileLoginScreen({super.key});

  @override
  State<MobileLoginScreen> createState() => _MobileLoginScreenState();
}

class _MobileLoginScreenState extends State<MobileLoginScreen> {
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLoading = false;
  String? _errorMsg;

  Future<void> _handleLogin() async {
    setState(() {
      _isLoading = true;
      _errorMsg = null;
    });

    try {
      final apiService = ApiService();
      final authRepo = AuthRepository(apiService);
      final user = await authRepo.login(
        username: _usernameController.text.trim(),
        password: _passwordController.text.trim(),
      );

      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => RoleShellScreen(user: user)),
        );
      }
    } catch (e) {
      setState(() {
        _errorMsg = e.toString().replaceAll('Exception: ', '');
      });
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Icon(Icons.child_care, size: 72, color: AppTheme.primary),
                const SizedBox(height: 12),
                const Text(
                  'KinJo - كينجو',
                  style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: AppTheme.primaryDark),
                ),
                const Text('المنصة الوطنية لإدارة وتتبع الحضانات', style: TextStyle(color: Colors.grey)),
                const SizedBox(height: 32),
                if (_errorMsg != null) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTheme.danger.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(_errorMsg!, style: const TextStyle(color: AppTheme.danger)),
                  ),
                  const SizedBox(height: 16),
                ],
                TextField(
                  controller: _usernameController,
                  decoration: const InputDecoration(
                    labelText: 'اسم المستخدم أو البريد الإلكتروني',
                    prefixIcon: Icon(Icons.person),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _passwordController,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: 'كلمة المرور',
                    prefixIcon: Icon(Icons.lock),
                  ),
                ),
                const SizedBox(height: 24),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: _isLoading ? null : _handleLogin,
                    child: _isLoading
                        ? const CircularProgressIndicator(color: Colors.white)
                        : const Text('تسجيل الدخول'),
                  ),
                )
              ],
            ),
          ),
        ),
      ),
    );
  }
}
