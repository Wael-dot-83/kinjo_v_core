import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/api/api_service.dart';
import 'core/auth/auth_repository.dart';
import 'core/auth/token_storage.dart';
import 'core/theme/app_theme.dart';
import 'models/user_model.dart';

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
        return ParentDashboardShell(user: user);
      case UserRole.supervisor:
        return SupervisorDashboardShell(user: user);
      case UserRole.manager:
        return ManagerDashboardShell(user: user);
      default:
        return ParentDashboardShell(user: user);
    }
  }
}

/// Parent Mobile Interface Shell
class ParentDashboardShell extends StatelessWidget {
  final UserModel user;

  const ParentDashboardShell({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('لوحة ولي الأمر - KinJo'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await TokenStorage.clearAll();
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const MobileLoginScreen()),
              );
            },
          )
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Hero Welcome Card
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [AppTheme.primary, AppTheme.primaryDark],
                ),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'أهلاً بك، ${user.fullName}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'تابع أنشطة أطفالك اليومية، وحالة الحضور، وتقارير الروضة أولاً بأول.',
                    style: TextStyle(color: Colors.white70, fontSize: 14),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'الخدمات السريعة',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              children: [
                _buildQuickTile(Icons.person_add, 'تسجيل طفل', 'تقديم طلب جديد', AppTheme.primary),
                _buildQuickTile(Icons.assignment, 'التقارير اليومية', 'متابعة السجلات', AppTheme.secondary),
                _buildQuickTile(Icons.calendar_today, 'سجل الحضور', 'الدخول والخروج', AppTheme.accent),
                _buildQuickTile(Icons.chat, 'الرسائل', 'التواصل مع الروضة', AppTheme.purpleAccent),
              ],
            )
          ],
        ),
      ),
    );
  }

  Widget _buildQuickTile(IconData icon, String title, String subtitle, Color color) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircleAvatar(
              backgroundColor: color.withOpacity(0.15),
              child: Icon(icon, color: color),
            ),
            const SizedBox(height: 10),
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
            const SizedBox(height: 4),
            Text(subtitle, style: const TextStyle(color: Colors.grey, fontSize: 12), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

/// Supervisor Mobile Interface Shell
class SupervisorDashboardShell extends StatelessWidget {
  final UserModel user;

  const SupervisorDashboardShell({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('لوحة المشرف الميداني')),
      body: Center(
        child: Text('مرحباً بك ${user.fullName} - قسم التفتيش والزيارات الميدانية'),
      ),
    );
  }
}

/// Manager Mobile Interface Shell
class ManagerDashboardShell extends StatelessWidget {
  final UserModel user;

  const ManagerDashboardShell({super.key, required this.user});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('إدارة الحضانة')),
      body: Center(
        child: Text('مرحباً بك ${user.fullName} - لوحة عمليات مدير الحضانة'),
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
