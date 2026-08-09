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
      default:
        return Scaffold(
          appBar: AppBar(title: const Text('غير مصرح')),
          body: Center(
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.block, size: 64, color: AppTheme.danger),
                  const SizedBox(height: 16),
                  const Text(
                    'دور الحساب غير مدعوم على تطبيق الهاتف.',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'حسابات المسؤولين (ADMIN) مخصصة فقط للوحة التحكم عبر الويب.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                  const SizedBox(height: 24),
                  ElevatedButton(
                    onPressed: () async {
                      await TokenStorage.clearAll();
                      if (context.mounted) {
                        Navigator.of(context).pushReplacement(
                          MaterialPageRoute(builder: (_) => const MobileLoginScreen()),
                        );
                      }
                    },
                    child: const Text('تسجيل الخروج'),
                  ),
                ],
              ),
            ),
          ),
        );
    }
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
  bool _isRateLimited = false;

  Future<void> _handleLogin() async {
    final username = _usernameController.text.trim();
    final password = _passwordController.text.trim();

    if (username.isEmpty || password.isEmpty) {
      setState(() {
        _errorMsg = 'يُرجى أدخال اسم المستخدم وكلمة المرور.';
        _isRateLimited = false;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _errorMsg = null;
      _isRateLimited = false;
    });

    try {
      final apiService = ApiService();
      final authRepo = AuthRepository(apiService);
      final user = await authRepo.login(
        username: username,
        password: password,
      );

      if (mounted) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => RoleShellScreen(user: user)),
        );
      }
    } on ApiException catch (e) {
      setState(() {
        _errorMsg = e.message;
        _isRateLimited = e.isRateLimited;
      });
    } catch (e) {
      setState(() {
        _errorMsg = e.toString().replaceAll('Exception: ', '');
        _isRateLimited = false;
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
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: _isRateLimited ? AppTheme.accent.withOpacity(0.15) : AppTheme.danger.withOpacity(0.1),
                      border: Border.all(
                        color: _isRateLimited ? AppTheme.accent : AppTheme.danger,
                        width: 1,
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _isRateLimited ? Icons.hourglass_top : Icons.error_outline,
                          color: _isRateLimited ? AppTheme.accent : AppTheme.danger,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            _errorMsg!,
                            style: TextStyle(
                              color: _isRateLimited ? Colors.brown : AppTheme.danger,
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
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
