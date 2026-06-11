import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'quick_access.dart';

const String localApiBaseUrl = 'http://127.0.0.1:5001/mobile/api';
const String schoolApiBaseUrl = 'http://10.172.85.55/mobile/api';
const String apiBaseUrlPreferenceKey = 'api_base_url';
const String altairSlogan = 'Единая цифровая система управления школой';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const SchoolSupportApp());
}

class SchoolSupportApp extends StatefulWidget {
  const SchoolSupportApp({super.key});

  @override
  State<SchoolSupportApp> createState() => _SchoolSupportAppState();
}

class _SchoolSupportAppState extends State<SchoolSupportApp> {
  final SharedPreferencesAsync preferences = SharedPreferencesAsync();
  String apiBaseUrl = localApiBaseUrl;
  bool loading = true;

  @override
  void initState() {
    super.initState();
    loadServer();
  }

  Future<void> loadServer() async {
    String? savedUrl;
    try {
      savedUrl = await preferences.getString(apiBaseUrlPreferenceKey);
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      apiBaseUrl = savedUrl?.trim().isNotEmpty == true
          ? savedUrl!.trim()
          : localApiBaseUrl;
      loading = false;
    });
  }

  Future<void> changeServer(String value) async {
    final normalized = normalizeApiBaseUrl(value);
    await preferences.setString(apiBaseUrlPreferenceKey, normalized);
    if (!mounted) return;
    setState(() => apiBaseUrl = normalized);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Альтаир',
      theme: ThemeData(
        colorScheme:
            ColorScheme.fromSeed(
              seedColor: const Color(0xff3478e5),
              brightness: Brightness.light,
            ).copyWith(
              primary: const Color(0xff3478e5),
              secondary: const Color(0xff18a9bb),
              surface: Colors.white,
              surfaceContainer: const Color(0xfff2f5fa),
            ),
        scaffoldBackgroundColor: const Color(0xfff4f6fb),
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Color(0xff111827),
          surfaceTintColor: Colors.transparent,
          centerTitle: false,
          elevation: 0,
        ),
        navigationBarTheme: const NavigationBarThemeData(
          backgroundColor: Colors.white,
          indicatorColor: Color(0xffe2ebff),
          height: 68,
        ),
        cardTheme: const CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.all(Radius.circular(12)),
            side: BorderSide(color: Color(0xffe5eaf2)),
          ),
        ),
        inputDecorationTheme: const InputDecorationTheme(
          filled: true,
          fillColor: Colors.white,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.all(Radius.circular(10)),
            borderSide: BorderSide(color: Color(0xffdce3ee)),
          ),
        ),
        useMaterial3: true,
      ),
      home: loading
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : AppRoot(
              key: ValueKey(apiBaseUrl),
              api: PortalApi(apiBaseUrl),
              apiBaseUrl: apiBaseUrl,
              onServerChanged: changeServer,
            ),
    );
  }
}

String normalizeApiBaseUrl(String value) {
  var result = value.trim();
  if (!result.startsWith('http://') && !result.startsWith('https://')) {
    result = 'http://$result';
  }
  result = result.replaceFirst(RegExp(r'/+$'), '');
  if (!result.endsWith('/mobile/api')) {
    result = '$result/mobile/api';
  }
  return result;
}

class AppRoot extends StatefulWidget {
  const AppRoot({
    super.key,
    required this.api,
    required this.apiBaseUrl,
    required this.onServerChanged,
  });

  final PortalApi api;
  final String apiBaseUrl;
  final Future<void> Function(String value) onServerChanged;

  @override
  State<AppRoot> createState() => _AppRootState();
}

class _AppRootState extends State<AppRoot> with WidgetsBindingObserver {
  final QuickAccessStore quickAccess = QuickAccessStore();
  Map<String, dynamic>? user;
  bool starting = true;
  bool locked = false;
  bool needsQuickAccessSetup = false;
  bool quickAccessConfigured = false;
  DateTime? backgroundedAt;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    restoreSession();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive) {
      backgroundedAt ??= DateTime.now();
    } else if (state == AppLifecycleState.resumed &&
        user != null &&
        quickAccessConfigured &&
        backgroundedAt != null &&
        DateTime.now().difference(backgroundedAt!) >
            const Duration(seconds: 20)) {
      setState(() => locked = true);
      backgroundedAt = null;
    }
  }

  Future<void> restoreSession() async {
    final token = await quickAccess.readToken();
    final pin = await quickAccess.readPin();
    if (token != null && token.isNotEmpty) {
      widget.api.setToken(token);
      try {
        final profile = await widget.api.me();
        if (!mounted) return;
        user = Map<String, dynamic>.from(profile['user'] as Map)
          ..['permissions'] = profile['permissions'];
        quickAccessConfigured = pin != null && pin.length == 4;
        locked = quickAccessConfigured;
        needsQuickAccessSetup = !quickAccessConfigured;
      } catch (_) {
        await quickAccess.clear();
        widget.api.setToken('');
      }
    }
    if (mounted) setState(() => starting = false);
  }

  Future<void> _setUser(Map<String, dynamic> value) async {
    user = value;
    if (widget.api.token.isNotEmpty) {
      await quickAccess.saveToken(widget.api.token);
    }
    final pin = await quickAccess.readPin();
    if (!mounted) return;
    setState(() {
      quickAccessConfigured = pin != null && pin.length == 4;
      needsQuickAccessSetup = !quickAccessConfigured;
      locked = false;
    });
  }

  Future<void> _logout() async {
    try {
      await widget.api.logout();
    } catch (_) {}
    await quickAccess.clear();
    if (!mounted) return;
    setState(() {
      user = null;
      locked = false;
      quickAccessConfigured = false;
      needsQuickAccessSetup = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (starting) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (user == null) {
      return LoginScreen(
        api: widget.api,
        apiBaseUrl: widget.apiBaseUrl,
        onServerChanged: widget.onServerChanged,
        onLogin: _setUser,
      );
    }

    if (needsQuickAccessSetup) {
      return QuickAccessSetupScreen(
        store: quickAccess,
        onComplete: () => setState(() {
          needsQuickAccessSetup = false;
          quickAccessConfigured = true;
        }),
        onLogout: _logout,
      );
    }

    if (locked) {
      return UnlockScreen(
        store: quickAccess,
        onUnlocked: () => setState(() => locked = false),
        onLogout: _logout,
      );
    }

    return HomeShell(
      api: widget.api,
      user: user!,
      quickAccess: quickAccess,
      onLogout: _logout,
    );
  }
}

class PortalApi {
  PortalApi(this.baseUrl);

  final String baseUrl;
  final HttpClient _client = HttpClient();
  String _cookie = '';
  String token = '';

  void setToken(String value) {
    token = value;
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final loginData = await post('/auth/login', {
      'username': username,
      'password': password,
    });
    token = loginData['token']?.toString() ?? '';
    final profile = await me();
    return Map<String, dynamic>.from(profile['user'] as Map)
      ..['permissions'] = profile['permissions'];
  }

  Future<void> logout() async {
    await post('/auth/logout', {});
    _cookie = '';
    token = '';
  }

  Future<Map<String, dynamic>> me() => get('/me');

  Future<Map<String, dynamic>> branding() => get('/branding');

  Future<Map<String, dynamic>> notifications() => get('/notifications');

  Future<Map<String, dynamic>> markNotificationRead(String kind, int id) =>
      post('/notifications/$kind/$id/read', {});

  Future<Map<String, dynamic>> myIncidents() => get('/incidents/mine');

  Future<Map<String, dynamic>> myTasks(String filter) =>
      get('/tasks/mine', query: {'filter': filter});

  Future<Map<String, dynamic>> taskDetail(int id) => get('/tasks/$id');

  Future<Map<String, dynamic>> changeTaskStatus(
    int id,
    String status, {
    String comment = '',
  }) => post('/tasks/$id/status', {'status': status, 'comment': comment});

  Future<Map<String, dynamic>> addTaskComment(int id, String text) =>
      post('/tasks/$id/comments', {'text': text});

  Future<Map<String, dynamic>> incidentMeta() => get('/incidents/meta');

  Future<Map<String, dynamic>> taskMeta() => get('/tasks/meta');

  Future<Map<String, dynamic>> orders() => get('/orders');

  Future<Map<String, dynamic>> appeals() => get('/appeals');

  Future<Map<String, dynamic>> appealDetail(int id) => get('/appeals/$id');

  Future<Map<String, dynamic>> familiarizations() =>
      get('/familiarizations/mine');

  Future<Map<String, dynamic>> familiarizationDetail(int id) =>
      get('/familiarizations/$id');

  String familiarizationAttachmentUrl(int familiarizationId, Object? id) {
    final attachmentId = id == null ? 'main' : id.toString();
    return _uri(
      '/familiarizations/$familiarizationId/attachments/$attachmentId/download',
      {if (token.isNotEmpty) 'token': token},
    ).toString();
  }

  Future<void> acknowledgeFamiliarization(int id) async {
    await post('/familiarizations/$id/acknowledge', {});
  }

  Future<void> createTask({
    required String title,
    required String description,
    required int responsibleUserId,
    List<int> coexecutorUserIds = const [],
    int? taskTypeId,
    required String priority,
    DateTime? deadlineAt,
    bool isPrivate = false,
    bool isControlRequired = false,
  }) async {
    await post('/tasks', {
      'title': title,
      'description': description,
      'responsible_user_id': responsibleUserId,
      'coexecutor_user_ids': coexecutorUserIds,
      'task_type_id': taskTypeId,
      'priority': priority,
      'deadline_at': deadlineAt?.toIso8601String(),
      'is_private': isPrivate,
      'is_control_required': isControlRequired,
    });
  }

  Future<List<dynamic>> classes({int? grade}) async {
    final data = await get(
      '/classes',
      query: {if (grade != null) 'grade': '$grade'},
    );
    return List<dynamic>.from(data['items'] as List? ?? const []);
  }

  Future<List<dynamic>> children(int classId) async {
    final data = await get('/classes/$classId/children');
    return List<dynamic>.from(data['items'] as List? ?? const []);
  }

  Future<void> createIncident({
    required String category,
    required String description,
    required List<int> childIds,
    required DateTime occurredAt,
    String initialWork = '',
  }) async {
    await post('/incidents', {
      'category': category,
      'description': description,
      'initial_work': initialWork,
      'child_ids': childIds,
      'occurred_at': occurredAt.toIso8601String(),
    });
  }

  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String> query = const {},
  }) async {
    final uri = _uri(path, query);
    final request = await _client.getUrl(uri);
    _prepareRequest(request);
    return _send(request);
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final request = await _client.postUrl(_uri(path));
    _prepareRequest(request);
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode(body));
    return _send(request);
  }

  Uri _uri(String path, [Map<String, String> query = const {}]) {
    final cleanBase = baseUrl.replaceFirst(RegExp(r'/$'), '');
    return Uri.parse(
      '$cleanBase$path',
    ).replace(queryParameters: query.isEmpty ? null : query);
  }

  String mediaUrl(Object? value) {
    final raw = value?.toString().trim() ?? '';
    if (raw.isEmpty) return '';
    if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
    final origin = baseUrl.replaceFirst(RegExp(r'/mobile/api/?$'), '');
    if (raw.startsWith('/')) return '$origin$raw';
    return '$origin/$raw';
  }

  void _prepareRequest(HttpClientRequest request) {
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (_cookie.isNotEmpty) {
      request.headers.set(HttpHeaders.cookieHeader, _cookie);
    }
    if (token.isNotEmpty) {
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
    }
  }

  Future<Map<String, dynamic>> _send(HttpClientRequest request) async {
    final response = await request.close();
    _saveCookies(response);
    final text = await utf8.decodeStream(response);
    final decoded = text.isEmpty ? <String, dynamic>{} : jsonDecode(text);
    final data = Map<String, dynamic>.from(decoded as Map);

    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw PortalApiException(
        data['message']?.toString() ?? 'Сервер вернул ошибку.',
        response.statusCode,
      );
    }

    return data;
  }

  void _saveCookies(HttpClientResponse response) {
    if (response.cookies.isEmpty) {
      return;
    }
    final jar = <String, String>{};
    for (final item in _cookie.split(';')) {
      final trimmed = item.trim();
      final index = trimmed.indexOf('=');
      if (index > 0) {
        jar[trimmed.substring(0, index)] = trimmed.substring(index + 1);
      }
    }
    for (final cookie in response.cookies) {
      jar[cookie.name] = cookie.value;
    }
    _cookie = jar.entries.map((item) => '${item.key}=${item.value}').join('; ');
  }
}

class PortalApiException implements Exception {
  PortalApiException(this.message, this.statusCode);

  final String message;
  final int statusCode;

  @override
  String toString() => message;
}

class PlatformLinks {
  static const MethodChannel _channel = MethodChannel('altair/open_url');

  static Future<void> open(String url) async {
    await _channel.invokeMethod<void>('openUrl', {'url': url});
  }
}

class LoginScreen extends StatefulWidget {
  const LoginScreen({
    super.key,
    required this.api,
    required this.apiBaseUrl,
    required this.onServerChanged,
    required this.onLogin,
  });

  final PortalApi api;
  final String apiBaseUrl;
  final Future<void> Function(String value) onServerChanged;
  final Future<void> Function(Map<String, dynamic>) onLogin;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController();
  final password = TextEditingController();
  Map<String, dynamic> branding = const {};
  bool loading = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    loadBranding();
  }

  @override
  void dispose() {
    username.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> loadBranding() async {
    try {
      final data = await widget.api.branding();
      if (!mounted) return;
      setState(
        () => branding = Map<String, dynamic>.from(
          data['branding'] as Map? ?? const {},
        ),
      );
    } catch (_) {}
  }

  Future<void> submit() async {
    setState(() {
      loading = true;
      error = '';
    });

    try {
      final user = await widget.api.login(username.text.trim(), password.text);
      if (!mounted) return;
      setState(() => loading = false);
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted) return;
      await widget.onLogin(user);
      return;
    } catch (exception) {
      if (!mounted) return;
      setState(() => error = _message(exception, widget.api.baseUrl));
    }

    if (mounted) {
      setState(() => loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final organization = _organizationFromBranding(branding);
    final organizationName = _organizationName(organization);
    final organizationLogoUrl = widget.api.mediaUrl(organization['logo_url']);

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                Center(
                  child: Image.asset(
                    'assets/altair-app-icon.png',
                    width: 92,
                    height: 92,
                  ),
                ),
                const SizedBox(height: 14),
                Text(
                  'АЛЬТАИР',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    color: const Color(0xff061442),
                    fontWeight: FontWeight.w600,
                    letterSpacing: 4,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  altairSlogan,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                if (organizationName.isNotEmpty ||
                    organizationLogoUrl.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (organizationLogoUrl.isNotEmpty) ...[
                        OrganizationLogo(url: organizationLogoUrl, size: 42),
                        const SizedBox(width: 10),
                      ],
                      Flexible(
                        child: Text(
                          organizationName,
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.titleSmall
                              ?.copyWith(
                                color: const Color(0xff3478e5),
                                fontWeight: FontWeight.w600,
                              ),
                        ),
                      ),
                    ],
                  ),
                ],
                const SizedBox(height: 14),
                OutlinedButton.icon(
                  onPressed: loading ? null : chooseServer,
                  icon: const Icon(Icons.dns_outlined),
                  label: Text('Сервер: ${serverLabel(widget.apiBaseUrl)}'),
                ),
                const SizedBox(height: 20),
                TextField(
                  controller: username,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'Логин',
                    prefixIcon: Icon(Icons.person_outline),
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: password,
                  obscureText: true,
                  onSubmitted: (_) => submit(),
                  decoration: const InputDecoration(
                    labelText: 'Пароль',
                    prefixIcon: Icon(Icons.lock_outline),
                    border: OutlineInputBorder(),
                  ),
                ),
                if (error.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    error,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: loading ? null : submit,
                  icon: loading
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.login),
                  label: const Text('Войти'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> chooseServer() async {
    final value = await showServerDialog(context, widget.apiBaseUrl);
    if (value == null || value == widget.apiBaseUrl) return;
    await widget.onServerChanged(value);
  }
}

Map<String, dynamic> _organizationFromBranding(Map<String, dynamic> branding) {
  final value = branding['organization'];
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

Map<String, dynamic> _organizationFromUser(Map<String, dynamic> user) {
  final value = user['organization'];
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

String _organizationName(Map<String, dynamic> organization) {
  return (organization['short_name'] ??
          organization['name'] ??
          organization['full_name'] ??
          '')
      .toString()
      .trim();
}

class OrganizationLogo extends StatelessWidget {
  const OrganizationLogo({super.key, required this.url, required this.size});

  final String url;
  final double size;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: Image.network(
        url,
        width: size,
        height: size,
        fit: BoxFit.contain,
        errorBuilder: (_, __, ___) => SizedBox(
          width: size,
          height: size,
          child: const Icon(Icons.school_outlined, color: Color(0xff3478e5)),
        ),
      ),
    );
  }
}

String serverLabel(String url) {
  if (url == localApiBaseUrl) return 'Локальный компьютер';
  if (url == schoolApiBaseUrl) return 'Сервер школы';
  return url.replaceFirst(RegExp(r'/mobile/api$'), '');
}

Future<String?> showServerDialog(
  BuildContext context,
  String currentUrl,
) async {
  final customController = TextEditingController(
    text: currentUrl == localApiBaseUrl || currentUrl == schoolApiBaseUrl
        ? ''
        : currentUrl.replaceFirst(RegExp(r'/mobile/api$'), ''),
  );
  var selected = currentUrl == localApiBaseUrl
      ? 'local'
      : currentUrl == schoolApiBaseUrl
      ? 'school'
      : 'custom';

  final result = await showDialog<String>(
    context: context,
    builder: (dialogContext) => StatefulBuilder(
      builder: (context, setDialogState) => AlertDialog(
        title: const Text('Выбор сервера'),
        content: SingleChildScrollView(
          child: RadioGroup<String>(
            groupValue: selected,
            onChanged: (value) {
              if (value != null) {
                setDialogState(() => selected = value);
              }
            },
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                RadioListTile<String>(
                  value: 'local',
                  title: const Text('Локальный компьютер'),
                  subtitle: const Text('Для симулятора на этом Mac'),
                ),
                RadioListTile<String>(
                  value: 'school',
                  title: const Text('Сервер школы'),
                  subtitle: const Text('10.172.85.55'),
                ),
                RadioListTile<String>(
                  value: 'custom',
                  title: const Text('Другой адрес'),
                ),
                if (selected == 'custom')
                  TextField(
                    controller: customController,
                    keyboardType: TextInputType.url,
                    decoration: const InputDecoration(
                      labelText: 'Адрес сервера',
                      hintText: '192.168.1.20:5001',
                      border: OutlineInputBorder(),
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () {
              final value = switch (selected) {
                'local' => localApiBaseUrl,
                'school' => schoolApiBaseUrl,
                _ => customController.text,
              };
              if (value.trim().isEmpty) return;
              Navigator.pop(dialogContext, normalizeApiBaseUrl(value));
            },
            child: const Text('Сохранить'),
          ),
        ],
      ),
    ),
  );
  customController.dispose();
  return result;
}

class QuickAccessSetupScreen extends StatefulWidget {
  const QuickAccessSetupScreen({
    super.key,
    required this.store,
    required this.onComplete,
    required this.onLogout,
    this.showLogout = true,
  });

  final QuickAccessStore store;
  final VoidCallback onComplete;
  final VoidCallback onLogout;
  final bool showLogout;

  @override
  State<QuickAccessSetupScreen> createState() => _QuickAccessSetupScreenState();
}

class _QuickAccessSetupScreenState extends State<QuickAccessSetupScreen> {
  final pin = TextEditingController();
  final repeatPin = TextEditingController();
  final DeviceAuthentication authentication = DeviceAuthentication();
  bool biometricAvailable = false;
  bool biometricEnabled = false;
  bool saving = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    loadBiometrics();
  }

  Future<void> loadBiometrics() async {
    final available = await authentication.isAvailable();
    if (mounted) {
      setState(() {
        biometricAvailable = available;
        biometricEnabled = available;
      });
    }
  }

  Future<void> save() async {
    if (!RegExp(r'^\d{4}$').hasMatch(pin.text)) {
      setState(() => error = 'Придумайте PIN из четырёх цифр.');
      return;
    }
    if (pin.text != repeatPin.text) {
      setState(() => error = 'PIN-коды не совпадают.');
      return;
    }
    setState(() {
      saving = true;
      error = '';
    });
    await widget.store.configure(
      pin: pin.text,
      biometric: biometricAvailable && biometricEnabled,
    );
    if (mounted) widget.onComplete();
  }

  @override
  void dispose() {
    pin.dispose();
    repeatPin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Быстрый вход'),
        actions: widget.showLogout
            ? [
                TextButton(
                  onPressed: widget.onLogout,
                  child: const Text('Выйти'),
                ),
              ]
            : null,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const Icon(
              Icons.shield_outlined,
              size: 60,
              color: Color(0xff3478e5),
            ),
            const SizedBox(height: 16),
            Text(
              'Защитите вход в приложение',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            const Text(
              'После этого пароль от портала вводить не потребуется. Для входа будет использоваться PIN или Face ID.',
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            TextField(
              controller: pin,
              obscureText: true,
              keyboardType: TextInputType.number,
              maxLength: 4,
              decoration: const InputDecoration(
                labelText: 'PIN-код',
                prefixIcon: Icon(Icons.pin_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: repeatPin,
              obscureText: true,
              keyboardType: TextInputType.number,
              maxLength: 4,
              decoration: const InputDecoration(
                labelText: 'Повторите PIN-код',
                prefixIcon: Icon(Icons.lock_outline),
              ),
            ),
            if (biometricAvailable)
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: biometricEnabled,
                onChanged: (value) => setState(() => biometricEnabled = value),
                title: const Text('Использовать Face ID'),
                subtitle: const Text('PIN останется запасным способом входа'),
                secondary: const Icon(Icons.face_outlined),
              ),
            if (error.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: saving ? null : save,
              icon: saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.check),
              label: const Text('Сохранить'),
            ),
          ],
        ),
      ),
    );
  }
}

class UnlockScreen extends StatefulWidget {
  const UnlockScreen({
    super.key,
    required this.store,
    required this.onUnlocked,
    required this.onLogout,
  });

  final QuickAccessStore store;
  final VoidCallback onUnlocked;
  final VoidCallback onLogout;

  @override
  State<UnlockScreen> createState() => _UnlockScreenState();
}

class _UnlockScreenState extends State<UnlockScreen> {
  final pin = TextEditingController();
  final DeviceAuthentication authentication = DeviceAuthentication();
  bool biometricEnabled = false;
  bool checking = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    prepare();
  }

  Future<void> prepare() async {
    biometricEnabled = await widget.store.biometricEnabled();
    if (mounted) setState(() {});
    if (biometricEnabled) await useBiometric();
  }

  Future<void> useBiometric() async {
    if (checking) return;
    setState(() => checking = true);
    final accepted = await authentication.authenticate();
    if (!mounted) return;
    setState(() => checking = false);
    if (accepted) widget.onUnlocked();
  }

  Future<void> submitPin() async {
    final savedPin = await widget.store.readPin();
    if (!mounted) return;
    if (pin.text == savedPin) {
      widget.onUnlocked();
    } else {
      setState(() => error = 'Неверный PIN-код.');
      pin.clear();
    }
  }

  @override
  void dispose() {
    pin.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 380),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(28),
              children: [
                Image.asset(
                  'assets/altair-app-icon.png',
                  width: 88,
                  height: 88,
                ),
                const SizedBox(height: 18),
                Text(
                  'Альтаир',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 24),
                TextField(
                  controller: pin,
                  autofocus: !biometricEnabled,
                  obscureText: true,
                  keyboardType: TextInputType.number,
                  maxLength: 4,
                  onSubmitted: (_) => submitPin(),
                  decoration: const InputDecoration(
                    labelText: 'PIN-код',
                    prefixIcon: Icon(Icons.lock_outline),
                  ),
                ),
                if (error.isNotEmpty)
                  Text(
                    error,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                const SizedBox(height: 12),
                FilledButton(onPressed: submitPin, child: const Text('Войти')),
                if (biometricEnabled) ...[
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: checking ? null : useBiometric,
                    icon: const Icon(Icons.face_outlined),
                    label: const Text('Войти с Face ID'),
                  ),
                ],
                TextButton(
                  onPressed: widget.onLogout,
                  child: const Text('Войти под другой учётной записью'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.api,
    required this.user,
    required this.quickAccess,
    required this.onLogout,
  });

  final PortalApi api;
  final Map<String, dynamic> user;
  final QuickAccessStore quickAccess;
  final VoidCallback onLogout;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int index = 0;

  void openTab(int value) {
    setState(() => index = value);
  }

  @override
  Widget build(BuildContext context) {
    final organization = _organizationFromUser(widget.user);
    final organizationName = _organizationName(organization);
    final organizationLogoUrl = widget.api.mediaUrl(organization['logo_url']);
    final pages = [
      HomeScreen(api: widget.api, user: widget.user, openTab: openTab),
      NotificationsScreen(api: widget.api),
      ProfileScreen(
        user: widget.user,
        quickAccess: widget.quickAccess,
        onLogout: widget.onLogout,
      ),
    ];
    final titles = [
      organizationName.isEmpty ? 'Альтаир' : 'Альтаир · $organizationName',
      'Уведомления',
      'Профиль',
    ];

    return Scaffold(
      appBar: AppBar(
        title: index == 0
            ? Row(
                children: [
                  if (organizationLogoUrl.isNotEmpty) ...[
                    OrganizationLogo(url: organizationLogoUrl, size: 30),
                    const SizedBox(width: 10),
                  ],
                  Expanded(
                    child: Text(
                      titles[index],
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              )
            : Text(
                titles[index],
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                ),
              ),
      ),
      body: pages[index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Главная',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_outlined),
            label: 'Уведомления',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Профиль',
          ),
        ],
      ),
    );
  }
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({
    super.key,
    required this.api,
    required this.user,
    required this.openTab,
  });

  final PortalApi api;
  final Map<String, dynamic> user;
  final ValueChanged<int> openTab;

  @override
  Widget build(BuildContext context) {
    return RefreshableFuture(
      load: api.notifications,
      builder: (context, data, reload) {
        final items = List<dynamic>.from(data['items'] as List? ?? const []);
        final unread = data['unread'] ?? 0;
        final counts = Map<String, dynamic>.from(
          data['counts'] as Map? ?? const {},
        );
        final permissions = Map<String, dynamic>.from(
          user['permissions'] as Map? ?? const {},
        );
        final canCreateIncident =
            permissions['can_add_incident'] == true || permissions.isEmpty;

        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
          children: [
            InfoPanel(
              icon: Icons.account_circle_outlined,
              title:
                  user['fio']?.toString() ??
                  user['username']?.toString() ??
                  'Пользователь',
              subtitle:
                  '${user['role'] ?? 'Сотрудник'} • непрочитанных: $unread',
            ),
            const SizedBox(height: 20),
            Text(
              'Рабочие разделы',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 10),
            GridView.count(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              mainAxisExtent: 128,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              children: [
                ServiceCard(
                  icon: Icons.assignment_outlined,
                  title: 'Инциденты',
                  subtitle: 'Создание и реестр',
                  accent: const Color(0xffeaf1ff),
                  iconColor: const Color(0xff3478e5),
                  badgeCount: counts['incidents'] as int? ?? 0,
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => IncidentsScreen(
                          api: api,
                          canCreate: canCreateIncident,
                        ),
                      ),
                    );
                    await reload();
                  },
                ),
                ServiceCard(
                  icon: Icons.task_alt_outlined,
                  title: 'Задачи',
                  subtitle: 'Мои поручения',
                  accent: const Color(0xffeaf8f2),
                  iconColor: const Color(0xff15966a),
                  badgeCount: counts['tasks'] as int? ?? 0,
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => TasksScreen(api: api)),
                    );
                    await reload();
                  },
                ),
                ServiceCard(
                  icon: Icons.gavel_outlined,
                  title: 'Реестр приказов',
                  subtitle: 'Приказы школы',
                  accent: const Color(0xfffff3e5),
                  iconColor: const Color(0xffd97706),
                  badgeCount: counts['orders'] as int? ?? 0,
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => OrdersScreen(api: api)),
                    );
                    await reload();
                  },
                ),
                ServiceCard(
                  icon: Icons.forum_outlined,
                  title: 'Обращения',
                  subtitle: 'Заявки и ответы',
                  accent: const Color(0xffffeceb),
                  iconColor: const Color(0xffdf6559),
                  badgeCount: counts['appeals'] as int? ?? 0,
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => AppealsScreen(api: api),
                      ),
                    );
                    await reload();
                  },
                ),
                ServiceCard(
                  icon: Icons.mark_email_read_outlined,
                  title: 'Мои ознакомления',
                  subtitle: 'Информирование',
                  accent: const Color(0xfff1edff),
                  iconColor: const Color(0xff7357c7),
                  badgeCount: counts['familiarizations'] as int? ?? 0,
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => FamiliarizationsScreen(api: api),
                      ),
                    );
                    await reload();
                  },
                ),
                ServiceCard(
                  icon: Icons.folder_open_outlined,
                  title: 'Документы',
                  subtitle: 'Файлы и материалы',
                  accent: const Color(0xffe7f7fa),
                  iconColor: const Color(0xff1593a5),
                  onTap: () async {
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => DocumentsScreen(api: api),
                      ),
                    );
                    await reload();
                  },
                ),
              ],
            ),
            const SizedBox(height: 20),
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Последние уведомления',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                TextButton(
                  onPressed: () => openTab(1),
                  child: const Text('Все'),
                ),
              ],
            ),
            if (items.isEmpty)
              const EmptyState(text: 'Новых уведомлений нет')
            else
              ...items
                  .take(5)
                  .map(
                    (item) => NotificationTile(
                      api: api,
                      item: Map<String, dynamic>.from(item as Map),
                      onOpened: reload,
                    ),
                  ),
          ],
        );
      },
    );
  }
}

class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return RefreshableFuture(
      load: api.notifications,
      builder: (context, data, reload) {
        final items = List<dynamic>.from(data['items'] as List? ?? const []);
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Центр уведомлений',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            if (items.isEmpty)
              const EmptyState(text: 'Уведомлений пока нет')
            else
              ...items.map(
                (item) => NotificationTile(
                  api: api,
                  item: Map<String, dynamic>.from(item as Map),
                  onOpened: reload,
                ),
              ),
          ],
        );
      },
    );
  }
}

class IncidentsScreen extends StatefulWidget {
  const IncidentsScreen({
    super.key,
    required this.api,
    required this.canCreate,
  });

  final PortalApi api;
  final bool canCreate;

  @override
  State<IncidentsScreen> createState() => _IncidentsScreenState();
}

class _IncidentsScreenState extends State<IncidentsScreen> {
  int refreshVersion = 0;

  Future<void> createIncident() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => NewIncidentScreen(api: widget.api)),
    );
    if (created == true && mounted) {
      setState(() => refreshVersion++);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Инцидент создан')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Инциденты')),
      body: RefreshableFuture(
        key: ValueKey(refreshVersion),
        load: widget.api.myIncidents,
        builder: (context, data, reload) {
          final authored = List<dynamic>.from(
            data['authored'] as List? ?? const [],
          );
          final assigned = List<dynamic>.from(
            data['assigned'] as List? ?? const [],
          );
          final registry = List<dynamic>.from(
            data['registry'] as List? ?? const [],
          );
          final items = [
            ...registry.map((item) => Map<String, dynamic>.from(item as Map)),
            ...authored.map((item) => Map<String, dynamic>.from(item as Map)),
            ...assigned.map((item) => Map<String, dynamic>.from(item as Map)),
          ];
          final seen = <Object>{};
          final unique = items.where((item) => seen.add(item['id'])).toList();

          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: [
              if (unique.isEmpty)
                const EmptyState(text: 'Инцидентов пока нет')
              else
                ...unique.map((item) => IncidentTile(item: item)),
            ],
          );
        },
      ),
      floatingActionButton: widget.canCreate
          ? FloatingActionButton(
              tooltip: 'Создать инцидент',
              onPressed: createIncident,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }
}

class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key, required this.api});

  final PortalApi api;

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  String filter = 'active';
  int refreshVersion = 0;

  Future<void> createTask() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => NewTaskScreen(api: widget.api)),
    );
    if (created == true && mounted) {
      setState(() => refreshVersion++);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Задача создана')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Задачи')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: SizedBox(
              width: double.infinity,
              child: SegmentedButton<String>(
                showSelectedIcon: false,
                expandedInsets: EdgeInsets.zero,
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                  textStyle: WidgetStatePropertyAll(TextStyle(fontSize: 12)),
                ),
                segments: const [
                  ButtonSegment(value: 'active', label: Text('Активные')),
                  ButtonSegment(value: 'overdue', label: Text('Просроч.')),
                  ButtonSegment(value: 'completed', label: Text('Готово')),
                ],
                selected: {filter},
                onSelectionChanged: (value) {
                  setState(() => filter = value.first);
                },
              ),
            ),
          ),
          Expanded(
            child: RefreshableFuture(
              key: ValueKey('$filter-$refreshVersion'),
              load: () => widget.api.myTasks(filter),
              builder: (context, data, reload) {
                final items = List<dynamic>.from(
                  data['items'] as List? ?? const [],
                );
                if (items.isEmpty) {
                  return ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(16),
                    children: [EmptyState(text: _emptyTasksLabel(filter))],
                  );
                }
                return ListView.separated(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  itemCount: items.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, index) {
                    final item = Map<String, dynamic>.from(items[index] as Map);
                    return TaskCard(
                      item: item,
                      onTap: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => TaskDetailScreen(
                              api: widget.api,
                              taskId: item['id'] as int,
                            ),
                          ),
                        );
                        if (mounted) setState(() => refreshVersion++);
                      },
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FutureBuilder<Map<String, dynamic>>(
        future: widget.api.taskMeta(),
        builder: (context, snapshot) => snapshot.data?['can_create'] == true
            ? FloatingActionButton(
                tooltip: 'Создать задачу',
                onPressed: createTask,
                child: const Icon(Icons.add),
              )
            : const SizedBox.shrink(),
      ),
    );
  }
}

class NewTaskScreen extends StatefulWidget {
  const NewTaskScreen({super.key, required this.api});

  final PortalApi api;

  @override
  State<NewTaskScreen> createState() => _NewTaskScreenState();
}

class _NewTaskScreenState extends State<NewTaskScreen> {
  final title = TextEditingController();
  final description = TextEditingController();
  late Future<Map<String, dynamic>> metaFuture;
  final List<Map<String, dynamic>> selectedResponsibleUsers = [];
  int? taskTypeId;
  String priority = 'обычный';
  DateTime? deadline;
  bool isPrivate = false;
  bool isControlRequired = false;
  bool saving = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    metaFuture = widget.api.taskMeta();
  }

  @override
  void dispose() {
    title.dispose();
    description.dispose();
    super.dispose();
  }

  Future<void> chooseDeadline() async {
    final date = await showDatePicker(
      context: context,
      initialDate: deadline ?? DateTime.now().add(const Duration(days: 1)),
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 730)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: const TimeOfDay(hour: 18, minute: 0),
    );
    if (time == null) return;
    setState(() {
      deadline = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  Future<void> submit() async {
    if (title.text.trim().isEmpty) {
      setState(() => error = 'Укажите название задачи.');
      return;
    }
    if (selectedResponsibleUsers.isEmpty) {
      setState(() => error = 'Выберите хотя бы одного ответственного.');
      return;
    }
    setState(() {
      saving = true;
      error = '';
    });
    try {
      await widget.api.createTask(
        title: title.text.trim(),
        description: description.text.trim(),
        responsibleUserId: selectedResponsibleUsers.first['id'] as int,
        coexecutorUserIds: selectedResponsibleUsers
            .skip(1)
            .map((user) => user['id'] as int)
            .toList(),
        taskTypeId: taskTypeId,
        priority: priority,
        deadlineAt: deadline,
        isPrivate: isPrivate,
        isControlRequired: isControlRequired,
      );
      if (mounted) Navigator.pop(context, true);
    } catch (exception) {
      if (mounted) {
        setState(() {
          saving = false;
          error = describePortalError(exception);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Новая задача')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: metaFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return ErrorState(
              message: describePortalError(snapshot.error),
              onRetry: () async =>
                  setState(() => metaFuture = widget.api.taskMeta()),
            );
          }
          final data = snapshot.data ?? const <String, dynamic>{};
          final users = List<dynamic>.from(data['users'] as List? ?? const []);
          final types = List<dynamic>.from(
            data['task_types'] as List? ?? const [],
          );
          final priorities = List<String>.from(
            (data['priorities'] as List? ?? const ['обычный']).map(
              (item) => item.toString(),
            ),
          );
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              TextField(
                controller: title,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Название задачи',
                  prefixIcon: Icon(Icons.task_alt_outlined),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: description,
                minLines: 3,
                maxLines: 6,
                decoration: const InputDecoration(
                  labelText: 'Описание',
                  alignLabelWithHint: true,
                ),
              ),
              const SizedBox(height: 12),
              _UserMultiPickerField(
                label: 'Ответственные',
                users: users
                    .map((raw) => Map<String, dynamic>.from(raw as Map))
                    .toList(),
                selectedUsers: selectedResponsibleUsers,
                onChanged: (value) => setState(() {
                  selectedResponsibleUsers
                    ..clear()
                    ..addAll(value);
                }),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int?>(
                initialValue: taskTypeId,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Тип задачи',
                  prefixIcon: Icon(Icons.category_outlined),
                ),
                items: [
                  const DropdownMenuItem<int?>(
                    value: null,
                    child: Text('Без типа'),
                  ),
                  ...types.map((raw) {
                    final type = Map<String, dynamic>.from(raw as Map);
                    return DropdownMenuItem<int?>(
                      value: type['id'] as int,
                      child: Text(type['name']?.toString() ?? ''),
                    );
                  }),
                ],
                onChanged: (value) => setState(() => taskTypeId = value),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: priority,
                decoration: const InputDecoration(
                  labelText: 'Приоритет',
                  prefixIcon: Icon(Icons.flag_outlined),
                ),
                items: priorities
                    .map(
                      (item) =>
                          DropdownMenuItem(value: item, child: Text(item)),
                    )
                    .toList(),
                onChanged: (value) =>
                    setState(() => priority = value ?? 'обычный'),
              ),
              const SizedBox(height: 12),
              ListTile(
                tileColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                  side: const BorderSide(color: Color(0xffdce3ee)),
                ),
                leading: const Icon(Icons.event_outlined),
                title: const Text('Срок выполнения'),
                subtitle: Text(
                  deadline == null ? 'Не указан' : _taskDeadlineLabel(deadline),
                ),
                trailing: const Icon(Icons.chevron_right),
                onTap: chooseDeadline,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: isControlRequired,
                onChanged: (value) => setState(() => isControlRequired = value),
                title: const Text('Требуется контроль'),
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                value: isPrivate,
                onChanged: (value) => setState(() => isPrivate = value),
                title: const Text('Приватная задача'),
              ),
              if (error.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    error,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ),
              FilledButton.icon(
                onPressed: saving ? null : submit,
                icon: saving
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.check),
                label: const Text('Создать задачу'),
              ),
            ],
          );
        },
      ),
    );
  }
}

class TaskDetailScreen extends StatefulWidget {
  const TaskDetailScreen({super.key, required this.api, required this.taskId});

  final PortalApi api;
  final int taskId;

  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  int refreshVersion = 0;
  bool saving = false;

  Future<void> changeStatus(String status) async {
    final comment = await showDialog<String>(
      context: context,
      builder: (context) {
        final controller = TextEditingController();
        return AlertDialog(
          title: Text(
            status == 'Возвращена на доработку'
                ? 'Вернуть на доработку'
                : 'Изменить статус',
          ),
          content: TextField(
            controller: controller,
            minLines: 2,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Комментарий',
              alignLabelWithHint: true,
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, controller.text),
              child: const Text('Сохранить'),
            ),
          ],
        );
      },
    );
    if (comment == null) return;
    setState(() => saving = true);
    try {
      await widget.api.changeTaskStatus(
        widget.taskId,
        status,
        comment: comment,
      );
      if (!mounted) return;
      setState(() {
        saving = false;
        refreshVersion++;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() => saving = false);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(describePortalError(error))));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Задача')),
      body: RefreshableFuture(
        key: ValueKey(refreshVersion),
        load: () => widget.api.taskDetail(widget.taskId),
        builder: (context, data, reload) {
          final task = Map<String, dynamic>.from(data['task'] as Map);
          final responsible = Map<String, dynamic>.from(
            task['responsible'] as Map? ?? const {},
          );
          final creator = Map<String, dynamic>.from(
            task['creator'] as Map? ?? const {},
          );
          final coexecutors = List<dynamic>.from(
            task['coexecutors'] as List? ?? const [],
          );
          final statuses = List<String>.from(
            (task['available_statuses'] as List? ?? const []).map(
              (item) => item.toString(),
            ),
          );
          final comments = List<dynamic>.from(
            task['comments'] as List? ?? const [],
          );
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                task['title']?.toString() ?? 'Задача',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  Chip(
                    label: Text(task['display_status']?.toString() ?? 'Статус'),
                  ),
                  Chip(label: Text(task['priority']?.toString() ?? 'обычный')),
                  if (task['deadline_at'] != null)
                    Chip(
                      label: Text(
                        'Срок: ${_taskDeadlineLabel(task['deadline_at'])}',
                      ),
                    ),
                ],
              ),
              if ((task['description']?.toString() ?? '').isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(task['description'].toString()),
              ],
              const SizedBox(height: 12),
              _DetailLine(
                label: 'Ответственный',
                value: responsible['fio'] ?? responsible['username'],
              ),
              if (coexecutors.isNotEmpty)
                _DetailLine(
                  label: 'Соисполнители',
                  value: coexecutors
                      .map((raw) => Map<String, dynamic>.from(raw as Map))
                      .map((user) => user['fio'] ?? user['username'])
                      .where((value) => value != null)
                      .join(', '),
                ),
              _DetailLine(
                label: 'Поставил',
                value: creator['fio'] ?? creator['username'],
              ),
              if (statuses.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  'Действия',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: statuses.map((status) {
                    final isRework = status == 'Возвращена на доработку';
                    return FilledButton.tonalIcon(
                      onPressed: saving ? null : () => changeStatus(status),
                      icon: Icon(
                        isRework ? Icons.undo : Icons.change_circle_outlined,
                      ),
                      label: Text(isRework ? 'Вернуть на доработку' : status),
                    );
                  }).toList(),
                ),
              ],
              if (comments.isNotEmpty) ...[
                const SizedBox(height: 18),
                Text(
                  'Комментарии',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                ...comments.map((raw) {
                  final comment = Map<String, dynamic>.from(raw as Map);
                  final author = Map<String, dynamic>.from(
                    comment['author'] as Map? ?? const {},
                  );
                  return Card(
                    child: ListTile(
                      title: Text(comment['text']?.toString() ?? ''),
                      subtitle: Text(
                        [
                              author['fio'] ?? author['username'],
                              _dateFromValue(comment['created_at']),
                            ]
                            .where(
                              (value) => (value?.toString() ?? '').isNotEmpty,
                            )
                            .join(' · '),
                      ),
                    ),
                  );
                }),
              ],
            ],
          );
        },
      ),
    );
  }
}

class OrdersScreen extends StatelessWidget {
  const OrdersScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Реестр приказов')),
      body: RefreshableFuture(
        load: api.orders,
        builder: (context, data, reload) {
          final items = List<dynamic>.from(data['items'] as List? ?? const []);
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: items.isEmpty
                ? [const EmptyState(text: 'Доступных приказов пока нет')]
                : items.map((raw) {
                    final item = Map<String, dynamic>.from(raw as Map);
                    final isRead = item['is_read'] == true;
                    return Card(
                      child: ListTile(
                        leading: Stack(
                          clipBehavior: Clip.none,
                          children: [
                            const Icon(Icons.gavel_outlined),
                            if (!isRead)
                              const Positioned(
                                right: -2,
                                top: -2,
                                child: _UnreadDot(),
                              ),
                          ],
                        ),
                        title: Text(
                          '№ ${item['number'] ?? '—'} • ${item['title'] ?? ''}',
                        ),
                        subtitle: Text(
                          '${_dateFromValue(item['order_date'])}${(item['executor']?.toString() ?? '').isEmpty ? '' : ' • ${item['executor']}'}',
                        ),
                        onTap: () async {
                          await api.markNotificationRead(
                            'order',
                            item['id'] as int,
                          );
                          await reload();
                        },
                      ),
                    );
                  }).toList(),
          );
        },
      ),
    );
  }
}

class AppealsScreen extends StatelessWidget {
  const AppealsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Обращения')),
      body: RefreshableFuture(
        load: api.appeals,
        builder: (context, data, reload) {
          final items = List<dynamic>.from(data['items'] as List? ?? const []);
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: items.isEmpty
                ? [const EmptyState(text: 'Обращений пока нет')]
                : items.map((raw) {
                    final item = Map<String, dynamic>.from(raw as Map);
                    final overdue = item['is_overdue'] == true;
                    final isRead = item['is_read'] == true;
                    return Card(
                      child: ListTile(
                        leading: Stack(
                          clipBehavior: Clip.none,
                          children: [
                            Icon(
                              Icons.forum_outlined,
                              color: overdue
                                  ? Theme.of(context).colorScheme.error
                                  : null,
                            ),
                            if (!isRead)
                              const Positioned(
                                right: -2,
                                top: -2,
                                child: _UnreadDot(),
                              ),
                          ],
                        ),
                        title: Text(item['subject']?.toString() ?? 'Обращение'),
                        subtitle: Text(
                          '${item['applicant_name'] ?? ''} • ${item['status'] ?? ''}',
                        ),
                        trailing: (item['number']?.toString() ?? '').isEmpty
                            ? null
                            : Text('№ ${item['number']}'),
                        onTap: () async {
                          await api.markNotificationRead(
                            'appeal',
                            item['id'] as int,
                          );
                          await Navigator.of(context).push(
                            MaterialPageRoute(
                              builder: (_) => AppealDetailScreen(
                                api: api,
                                appealId: item['id'] as int,
                              ),
                            ),
                          );
                          await reload();
                        },
                      ),
                    );
                  }).toList(),
          );
        },
      ),
    );
  }
}

class FamiliarizationsScreen extends StatefulWidget {
  const FamiliarizationsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  State<FamiliarizationsScreen> createState() => _FamiliarizationsScreenState();
}

class _FamiliarizationsScreenState extends State<FamiliarizationsScreen> {
  int refreshVersion = 0;

  Future<void> openDetail(int id) async {
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            FamiliarizationDetailScreen(api: widget.api, familiarizationId: id),
      ),
    );
    if (changed == true && mounted) {
      setState(() => refreshVersion++);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Мои ознакомления')),
      body: RefreshableFuture(
        key: ValueKey(refreshVersion),
        load: widget.api.familiarizations,
        builder: (context, data, reload) {
          final items = List<dynamic>.from(data['items'] as List? ?? const []);
          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            children: items.isEmpty
                ? [const EmptyState(text: 'Новых ознакомлений нет')]
                : items.map((raw) {
                    final item = Map<String, dynamic>.from(raw as Map);
                    final canAcknowledge = item['can_acknowledge'] == true;
                    final acknowledged = item['acknowledged_at'] != null;
                    final statusLabel = canAcknowledge
                        ? 'Новое'
                        : acknowledged
                        ? 'Ознакомлен'
                        : 'Контроль';
                    final statusColor = canAcknowledge
                        ? const Color(0xff7357c7)
                        : acknowledged
                        ? const Color(0xff15966a)
                        : const Color(0xff64748b);
                    return Card(
                      child: InkWell(
                        borderRadius: BorderRadius.circular(12),
                        onTap: () => openDetail(item['id'] as int),
                        child: Padding(
                          padding: const EdgeInsets.all(14),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    canAcknowledge
                                        ? Icons.mark_email_unread_outlined
                                        : acknowledged
                                        ? Icons.check_circle_outline
                                        : Icons.fact_check_outlined,
                                    color: statusColor,
                                  ),
                                  const SizedBox(width: 10),
                                  Expanded(
                                    child: Text(
                                      item['title']?.toString() ??
                                          'Ознакомление',
                                      style: Theme.of(
                                        context,
                                      ).textTheme.titleMedium,
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  _StatusPill(
                                    label: statusLabel,
                                    color: statusColor,
                                  ),
                                ],
                              ),
                              if ((item['description']?.toString() ?? '')
                                  .isNotEmpty) ...[
                                const SizedBox(height: 8),
                                Text(item['description'].toString()),
                              ],
                              if (item['deadline_at'] != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  'Срок: ${_dateFromValue(item['deadline_at'])}',
                                ),
                              ],
                            ],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
          );
        },
      ),
    );
  }
}

class FamiliarizationDetailScreen extends StatefulWidget {
  const FamiliarizationDetailScreen({
    super.key,
    required this.api,
    required this.familiarizationId,
  });

  final PortalApi api;
  final int familiarizationId;

  @override
  State<FamiliarizationDetailScreen> createState() =>
      _FamiliarizationDetailScreenState();
}

class _FamiliarizationDetailScreenState
    extends State<FamiliarizationDetailScreen> {
  int refreshVersion = 0;
  bool changed = false;

  Future<void> acknowledge() async {
    await widget.api.acknowledgeFamiliarization(widget.familiarizationId);
    if (!mounted) return;
    setState(() {
      changed = true;
      refreshVersion++;
    });
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Ознакомление подтверждено')));
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.of(context).pop(changed);
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('Ознакомление')),
        body: RefreshableFuture(
          key: ValueKey(refreshVersion),
          load: () =>
              widget.api.familiarizationDetail(widget.familiarizationId),
          builder: (context, data, reload) {
            final item = Map<String, dynamic>.from(
              data['familiarization'] as Map? ?? const {},
            );
            final attachments = List<dynamic>.from(
              item['attachments'] as List? ?? const [],
            );
            final recipients = List<dynamic>.from(
              item['recipients'] as List? ?? const [],
            );
            final stats = Map<String, dynamic>.from(
              item['stats'] as Map? ?? const {},
            );
            return ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  item['title']?.toString() ?? 'Ознакомление',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                if ((item['description']?.toString() ?? '').isNotEmpty)
                  Text(item['description'].toString()),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    Chip(label: Text('Ознакомились: ${stats['done'] ?? 0}')),
                    Chip(label: Text('Ожидают: ${stats['pending'] ?? 0}')),
                    if (item['deadline_at'] != null)
                      Chip(
                        label: Text(
                          'Срок: ${_dateFromValue(item['deadline_at'])}',
                        ),
                      ),
                  ],
                ),
                if (attachments.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Text(
                    'Документы',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  ...attachments.map((raw) {
                    final attachment = Map<String, dynamic>.from(raw as Map);
                    return Card(
                      child: ListTile(
                        leading: const Icon(Icons.description_outlined),
                        title: Text(
                          attachment['filename']?.toString() ?? 'Документ',
                        ),
                        trailing: const Icon(Icons.open_in_new),
                        onTap: () => PlatformLinks.open(
                          widget.api.familiarizationAttachmentUrl(
                            widget.familiarizationId,
                            attachment['id'],
                          ),
                        ),
                      ),
                    );
                  }),
                ],
                if (item['can_acknowledge'] == true) ...[
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: acknowledge,
                    icon: const Icon(Icons.check),
                    label: const Text('Ознакомлен'),
                  ),
                ],
                if (recipients.isNotEmpty) ...[
                  const SizedBox(height: 18),
                  Text(
                    'Сотрудники',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  ...recipients.map((raw) {
                    final row = Map<String, dynamic>.from(raw as Map);
                    final user = Map<String, dynamic>.from(
                      row['user'] as Map? ?? const {},
                    );
                    final done = row['acknowledged_at'] != null;
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        done ? Icons.check_circle_outline : Icons.schedule,
                        color: done ? const Color(0xff15966a) : null,
                      ),
                      title: Text(user['fio']?.toString() ?? 'Сотрудник'),
                      subtitle: Text(
                        done
                            ? 'Ознакомлен: ${_dateFromValue(row['acknowledged_at'])}'
                            : 'Не ознакомлен',
                      ),
                    );
                  }),
                ],
              ],
            );
          },
        ),
      ),
    );
  }
}

class AppealDetailScreen extends StatelessWidget {
  const AppealDetailScreen({
    super.key,
    required this.api,
    required this.appealId,
  });

  final PortalApi api;
  final int appealId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Обращение')),
      body: RefreshableFuture(
        load: () => api.appealDetail(appealId),
        builder: (context, data, reload) {
          final item = Map<String, dynamic>.from(data['appeal'] as Map);
          final responsible = Map<String, dynamic>.from(
            item['responsible'] as Map? ?? const {},
          );
          final attachments = List<dynamic>.from(
            item['attachments'] as List? ?? const [],
          );
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                item['subject']?.toString() ?? 'Обращение',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  Chip(label: Text(item['status']?.toString() ?? 'Статус')),
                  if ((item['number']?.toString() ?? '').isNotEmpty)
                    Chip(label: Text('№ ${item['number']}')),
                  if (item['deadline_at'] != null)
                    Chip(
                      label: Text(
                        'Срок: ${_dateFromValue(item['deadline_at'])}',
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              _DetailLine(label: 'Заявитель', value: item['applicant_name']),
              _DetailLine(label: 'Контакт', value: item['applicant_contact']),
              _DetailLine(label: 'Канал', value: item['channel']),
              _DetailLine(
                label: 'Ответственный',
                value: responsible['fio'] ?? responsible['username'],
              ),
              if ((item['description']?.toString() ?? '').isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(
                  'Содержание',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 6),
                Text(item['description'].toString()),
              ],
              if ((item['result_text']?.toString() ?? '').isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('Ответ', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 6),
                Text(item['result_text'].toString()),
              ],
              if (attachments.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text(
                  'Вложения',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                ...attachments.map((raw) {
                  final attachment = Map<String, dynamic>.from(raw as Map);
                  return ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.attach_file),
                    title: Text(attachment['filename']?.toString() ?? 'Файл'),
                  );
                }),
              ],
            ],
          );
        },
      ),
    );
  }
}

class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Документы')),
      body: const ModulePlaceholder(
        icon: Icons.folder_open_outlined,
        title: 'Документы',
        text:
            'Просмотр файлов и материалов будет подключён к мобильному API следующим этапом.',
      ),
    );
  }
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({
    super.key,
    required this.user,
    required this.quickAccess,
    required this.onLogout,
  });

  final Map<String, dynamic> user;
  final QuickAccessStore quickAccess;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    final permissions = Map<String, dynamic>.from(
      user['permissions'] as Map? ?? const {},
    );
    final available = [
      if (permissions['can_add_incident'] == true) 'создание инцидентов',
      if (permissions['can_view_incident_registry'] == true)
        'реестр инцидентов',
      if (permissions['can_view_incident_dashboard'] == true)
        'аналитика инцидентов',
    ];

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        InfoPanel(
          icon: Icons.badge_outlined,
          title:
              user['fio']?.toString() ??
              user['username']?.toString() ??
              'Пользователь',
          subtitle: user['role']?.toString() ?? 'Сотрудник',
        ),
        const SizedBox(height: 16),
        Text('Доступ', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              available.isEmpty
                  ? 'Права будут отображаться после расширения мобильного API.'
                  : available.join(', '),
            ),
          ),
        ),
        const SizedBox(height: 16),
        OutlinedButton.icon(
          onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (settingsContext) => QuickAccessSetupScreen(
                  store: quickAccess,
                  onComplete: () => Navigator.pop(settingsContext),
                  onLogout: () => Navigator.pop(settingsContext),
                  showLogout: false,
                ),
              ),
            );
          },
          icon: const Icon(Icons.face_outlined),
          label: const Text('Изменить PIN и Face ID'),
        ),
        const SizedBox(height: 8),
        OutlinedButton.icon(
          onPressed: onLogout,
          icon: const Icon(Icons.logout),
          label: const Text('Выйти'),
        ),
      ],
    );
  }
}

class NewIncidentScreen extends StatefulWidget {
  const NewIncidentScreen({super.key, required this.api});

  final PortalApi api;

  @override
  State<NewIncidentScreen> createState() => _NewIncidentScreenState();
}

class _NewIncidentScreenState extends State<NewIncidentScreen> {
  final description = TextEditingController();
  final initialWork = TextEditingController();
  String? category;
  int? selectedClassId;
  DateTime date = DateTime.now();
  TimeOfDay time = TimeOfDay.now();
  List<String> categories = [];
  List<Map<String, dynamic>> classes = [];
  List<Map<String, dynamic>> children = [];
  final selectedChildren = <int>{};
  bool loading = true;
  bool saving = false;
  String error = '';

  @override
  void initState() {
    super.initState();
    loadMeta();
  }

  @override
  void dispose() {
    description.dispose();
    initialWork.dispose();
    super.dispose();
  }

  Future<void> loadMeta() async {
    setState(() {
      loading = true;
      error = '';
    });
    try {
      final meta = await widget.api.incidentMeta();
      final classRows = await widget.api.classes();
      if (!mounted) {
        return;
      }
      setState(() {
        categories = List<dynamic>.from(
          meta['categories'] as List? ?? const [],
        ).map((item) => item.toString()).toList();
        classes = classRows
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
        category = categories.isEmpty ? null : categories.first;
      });
    } catch (exception) {
      if (mounted) {
        setState(() => error = _message(exception));
      }
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
    }
  }

  Future<void> loadChildren(int classId) async {
    setState(() {
      selectedClassId = classId;
      children = [];
      selectedChildren.clear();
    });
    try {
      final rows = await widget.api.children(classId);
      if (!mounted) {
        return;
      }
      setState(() {
        children = rows
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
      });
    } catch (exception) {
      if (mounted) {
        setState(() => error = _message(exception));
      }
    }
  }

  Future<void> pickDate() async {
    final value = await showDatePicker(
      context: context,
      initialDate: date,
      firstDate: DateTime.now().subtract(const Duration(days: 2)),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (value != null) {
      setState(() => date = value);
    }
  }

  Future<void> pickTime() async {
    final value = await showTimePicker(context: context, initialTime: time);
    if (value != null) {
      setState(() => time = value);
    }
  }

  Future<void> submit() async {
    if (category == null ||
        selectedChildren.isEmpty ||
        description.text.trim().isEmpty) {
      setState(
        () => error = 'Заполните категорию, описание и выберите ученика.',
      );
      return;
    }

    final occurredAt = DateTime(
      date.year,
      date.month,
      date.day,
      time.hour,
      time.minute,
    );
    setState(() {
      saving = true;
      error = '';
    });

    try {
      await widget.api.createIncident(
        category: category!,
        description: description.text.trim(),
        initialWork: initialWork.text.trim(),
        childIds: selectedChildren.toList(),
        occurredAt: occurredAt,
      );
      if (!mounted) {
        return;
      }
      Navigator.of(context).pop(true);
    } catch (exception) {
      if (mounted) {
        setState(() => error = _message(exception));
      }
    } finally {
      if (mounted) {
        setState(() => saving = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Новый инцидент')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Новый инцидент')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          children: [
            DropdownButtonFormField<String>(
              initialValue: category,
              items: categories
                  .map(
                    (item) => DropdownMenuItem(value: item, child: Text(item)),
                  )
                  .toList(),
              onChanged: (value) => setState(() => category = value),
              decoration: const InputDecoration(
                labelText: 'Категория',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              initialValue: selectedClassId,
              items: classes
                  .map(
                    (item) => DropdownMenuItem<int>(
                      value: item['id'] as int,
                      child: Text(item['name'].toString()),
                    ),
                  )
                  .toList(),
              onChanged: (value) {
                if (value != null) {
                  loadChildren(value);
                }
              },
              decoration: const InputDecoration(
                labelText: 'Класс',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            if (children.isNotEmpty)
              Card(
                child: Column(
                  children: children.map((item) {
                    final id = item['id'] as int;
                    return CheckboxListTile(
                      value: selectedChildren.contains(id),
                      onChanged: (checked) {
                        setState(() {
                          if (checked == true) {
                            selectedChildren.add(id);
                          } else {
                            selectedChildren.remove(id);
                          }
                        });
                      },
                      title: Text(item['fio'].toString()),
                    );
                  }).toList(),
                ),
              ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: pickDate,
                    icon: const Icon(Icons.calendar_today_outlined),
                    label: Text(_dateLabel(date)),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: pickTime,
                    icon: const Icon(Icons.schedule),
                    label: Text(time.format(context)),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: description,
              minLines: 4,
              maxLines: 8,
              decoration: const InputDecoration(
                labelText: 'Описание',
                alignLabelWithHint: true,
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: initialWork,
              minLines: 2,
              maxLines: 5,
              decoration: const InputDecoration(
                labelText: 'Что уже сделано',
                alignLabelWithHint: true,
                border: OutlineInputBorder(),
              ),
            ),
            if (error.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: saving ? null : submit,
              icon: saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send_outlined),
              label: const Text('Отправить'),
            ),
          ],
        ),
      ),
    );
  }
}

class RefreshableFuture extends StatefulWidget {
  const RefreshableFuture({
    super.key,
    required this.load,
    required this.builder,
  });

  final Future<Map<String, dynamic>> Function() load;
  final Widget Function(
    BuildContext context,
    Map<String, dynamic> data,
    Future<void> Function() reload,
  )
  builder;

  @override
  State<RefreshableFuture> createState() => _RefreshableFutureState();
}

class _RefreshableFutureState extends State<RefreshableFuture> {
  late Future<Map<String, dynamic>> future;

  @override
  void initState() {
    super.initState();
    future = widget.load();
  }

  Future<void> reload() async {
    final nextFuture = widget.load();
    setState(() {
      future = nextFuture;
    });
    await nextFuture;
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: future,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return ErrorState(message: _message(snapshot.error), onRetry: reload);
        }
        return RefreshIndicator(
          onRefresh: reload,
          child: widget.builder(context, snapshot.data ?? {}, reload),
        );
      },
    );
  }
}

class InfoPanel extends StatelessWidget {
  const InfoPanel({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, size: 36),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 4),
                  Text(subtitle),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class ServiceCard extends StatelessWidget {
  const ServiceCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.accent = const Color(0xffeef3fb),
    this.iconColor = const Color(0xff3478e5),
    this.badgeCount = 0,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color accent;
  final Color iconColor;
  final int badgeCount;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: accent,
      borderRadius: BorderRadius.circular(12),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 38,
                    height: 38,
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.82),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Icon(icon, size: 23, color: iconColor),
                  ),
                  const Spacer(),
                  if (badgeCount > 0)
                    Container(
                      constraints: const BoxConstraints(minWidth: 26),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xffe5484d),
                        borderRadius: BorderRadius.circular(999),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.12),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                      child: Text(
                        badgeCount > 99 ? '99+' : badgeCount.toString(),
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(
                  context,
                ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 2),
              Text(
                subtitle,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _UnreadDot extends StatelessWidget {
  const _UnreadDot();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 9,
      height: 9,
      decoration: BoxDecoration(
        color: const Color(0xffe5484d),
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 1.5),
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: color,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class ModulePlaceholder extends StatelessWidget {
  const ModulePlaceholder({
    super.key,
    required this.icon,
    required this.title,
    required this.text,
  });

  final IconData icon;
  final String title;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 460),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 52),
              const SizedBox(height: 16),
              Text(title, style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              Text(text, textAlign: TextAlign.center),
            ],
          ),
        ),
      ),
    );
  }
}

class _UserMultiPickerField extends StatelessWidget {
  const _UserMultiPickerField({
    required this.label,
    required this.users,
    required this.selectedUsers,
    required this.onChanged,
  });

  final String label;
  final List<Map<String, dynamic>> users;
  final List<Map<String, dynamic>> selectedUsers;
  final ValueChanged<List<Map<String, dynamic>>> onChanged;

  @override
  Widget build(BuildContext context) {
    final text = selectedUsers.isEmpty
        ? 'Выбрать'
        : selectedUsers
              .map(
                (user) =>
                    user['fio']?.toString() ??
                    user['username']?.toString() ??
                    '',
              )
              .where((value) => value.isNotEmpty)
              .join(', ');
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: () async {
        final result = await showModalBottomSheet<List<Map<String, dynamic>>>(
          context: context,
          isScrollControlled: true,
          builder: (_) => _UserMultiPickerSheet(
            users: users,
            selectedIds: selectedUsers.map((user) => user['id'] as int).toSet(),
          ),
        );
        if (result != null) onChanged(result);
      },
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          prefixIcon: const Icon(Icons.group_outlined),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                text,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: selectedUsers.isEmpty ? const Color(0xff6b7280) : null,
                ),
              ),
            ),
            const Icon(Icons.search),
          ],
        ),
      ),
    );
  }
}

class _UserMultiPickerSheet extends StatefulWidget {
  const _UserMultiPickerSheet({required this.users, required this.selectedIds});

  final List<Map<String, dynamic>> users;
  final Set<int> selectedIds;

  @override
  State<_UserMultiPickerSheet> createState() => _UserMultiPickerSheetState();
}

class _UserMultiPickerSheetState extends State<_UserMultiPickerSheet> {
  final search = TextEditingController();
  late final Set<int> selectedIds = {...widget.selectedIds};

  @override
  void dispose() {
    search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final query = search.text.trim().toLowerCase();
    final filtered = widget.users.where((user) {
      final label = '${user['fio'] ?? ''} ${user['username'] ?? ''}'
          .toLowerCase();
      return query.isEmpty || label.contains(query);
    }).toList();
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 12,
          bottom: MediaQuery.of(context).viewInsets.bottom + 12,
        ),
        child: SizedBox(
          height: MediaQuery.of(context).size.height * 0.78,
          child: Column(
            children: [
              TextField(
                controller: search,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Поиск сотрудника',
                  prefixIcon: Icon(Icons.search),
                ),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView.builder(
                  itemCount: filtered.length,
                  itemBuilder: (context, index) {
                    final user = filtered[index];
                    final id = user['id'] as int;
                    return CheckboxListTile(
                      value: selectedIds.contains(id),
                      onChanged: (value) => setState(() {
                        if (value == true) {
                          selectedIds.add(id);
                        } else {
                          selectedIds.remove(id);
                        }
                      }),
                      title: Text(
                        user['fio']?.toString() ??
                            user['username']?.toString() ??
                            '',
                      ),
                      subtitle: user['username'] == null
                          ? null
                          : Text(user['username'].toString()),
                    );
                  },
                ),
              ),
              FilledButton(
                onPressed: () {
                  Navigator.pop(
                    context,
                    widget.users
                        .where((user) => selectedIds.contains(user['id']))
                        .toList(),
                  );
                },
                child: Text('Выбрать: ${selectedIds.length}'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({required this.label, required this.value});

  final String label;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    final text = value?.toString() ?? '';
    if (text.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 120,
            child: Text(label, style: Theme.of(context).textTheme.labelMedium),
          ),
          Expanded(child: Text(text)),
        ],
      ),
    );
  }
}

class NotificationTile extends StatelessWidget {
  const NotificationTile({
    super.key,
    required this.api,
    required this.item,
    this.onOpened,
  });

  final PortalApi api;
  final Map<String, dynamic> item;
  final Future<void> Function()? onOpened;

  Future<void> _open(BuildContext context) async {
    final id = item['entity_id'] as int?;
    if (id == null) return;
    switch (item['kind']) {
      case 'task':
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => TaskDetailScreen(api: api, taskId: id),
          ),
        );
        await onOpened?.call();
        return;
      case 'familiarization':
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) =>
                FamiliarizationDetailScreen(api: api, familiarizationId: id),
          ),
        );
        await onOpened?.call();
        return;
      case 'appeal':
        await api.markNotificationRead('appeal', id);
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => AppealDetailScreen(api: api, appealId: id),
          ),
        );
        await onOpened?.call();
        return;
      case 'order':
        await api.markNotificationRead('order', id);
        await Navigator.of(
          context,
        ).push(MaterialPageRoute(builder: (_) => OrdersScreen(api: api)));
        await onOpened?.call();
        return;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(switch (item['kind']) {
          'incident' => Icons.report_outlined,
          'familiarization' => Icons.mark_email_unread_outlined,
          'appeal' => Icons.forum_outlined,
          'order' => Icons.gavel_outlined,
          _ => Icons.task_outlined,
        }),
        title: Text(item['title']?.toString() ?? 'Уведомление'),
        subtitle: Text(item['message']?.toString() ?? ''),
        trailing: item['is_read'] == true
            ? null
            : const Icon(Icons.circle, size: 12),
        onTap: () => _open(context),
      ),
    );
  }
}

class TaskCard extends StatelessWidget {
  const TaskCard({super.key, required this.item, this.onTap});

  final Map<String, dynamic> item;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final responsible = Map<String, dynamic>.from(
      item['responsible'] as Map? ?? const {},
    );
    final status = item['display_status']?.toString() ?? 'Без статуса';
    final isOverdue = item['is_overdue'] == true;
    final checklistDone = item['checklist_done'] as int? ?? 0;
    final checklistTotal = item['checklist_total'] as int? ?? 0;
    final accent = isOverdue
        ? Theme.of(context).colorScheme.error
        : Theme.of(context).colorScheme.primary;

    return Card(
      margin: EdgeInsets.zero,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      item['title']?.toString() ?? 'Задача',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Container(
                    constraints: const BoxConstraints(maxWidth: 132),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: accent.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      status,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        color: accent,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
              if ((item['description']?.toString() ?? '').isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  item['description'].toString(),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
              const SizedBox(height: 10),
              Wrap(
                spacing: 14,
                runSpacing: 6,
                children: [
                  _TaskMeta(
                    icon: Icons.event_outlined,
                    text: _taskDeadlineLabel(item['deadline_at']),
                    color: isOverdue ? accent : null,
                  ),
                  if (responsible.isNotEmpty)
                    _TaskMeta(
                      icon: Icons.person_outline,
                      text:
                          responsible['fio']?.toString() ??
                          responsible['username']?.toString() ??
                          'Ответственный',
                    ),
                  if (checklistTotal > 0)
                    _TaskMeta(
                      icon: Icons.checklist_outlined,
                      text: '$checklistDone из $checklistTotal',
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TaskMeta extends StatelessWidget {
  const _TaskMeta({required this.icon, required this.text, this.color});

  final IconData icon;
  final String text;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(width: 4),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 210),
          child: Text(
            text,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: color),
          ),
        ),
      ],
    );
  }
}

class IncidentTile extends StatelessWidget {
  const IncidentTile({super.key, required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final children = List<dynamic>.from(item['children'] as List? ?? const [])
        .map(
          (child) => Map<String, dynamic>.from(child as Map)['fio'].toString(),
        )
        .join(', ');
    return Card(
      child: ListTile(
        leading: const Icon(Icons.assignment_outlined),
        title: Text(item['category']?.toString() ?? 'Инцидент'),
        subtitle: Text(
          [
            item['status_label']?.toString() ??
                item['status']?.toString() ??
                '',
            if (children.isNotEmpty) children,
            item['description']?.toString() ?? '',
          ].where((item) => item.isNotEmpty).join('\n'),
        ),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 42),
      child: Center(
        child: Text(text, style: Theme.of(context).textTheme.bodyLarge),
      ),
    );
  }
}

class ErrorState extends StatelessWidget {
  const ErrorState({super.key, required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 42),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Повторить'),
            ),
          ],
        ),
      ),
    );
  }
}

String describePortalError(Object? exception) => _message(exception);

String _message(Object? exception, [String? apiBaseUrl]) {
  if (exception is PortalApiException) {
    return exception.message;
  }
  if (exception is SocketException) {
    final details = exception.osError?.message ?? exception.message;
    final target = apiBaseUrl ?? 'сервер портала';
    return 'Не удалось открыть $target. '
        'Проверьте доступ приложения к локальной сети. Причина: $details';
  }
  if (exception is HandshakeException) {
    return 'Ошибка защищенного соединения с сервером: '
        '${exception.message}';
  }
  if (exception is HttpException) {
    return 'Сервер вернул некорректный HTTP-ответ: ${exception.message}';
  }
  if (exception is FormatException) {
    return 'Сервер ответил, но данные мобильного API имеют неверный формат.';
  }
  return 'Не удалось подключиться к серверу портала.';
}

String _dateLabel(DateTime date) {
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  return '$day.$month.${date.year}';
}

String _dateFromValue(Object? value) {
  final parsed = DateTime.tryParse(value?.toString() ?? '');
  return parsed == null ? 'Дата не указана' : _dateLabel(parsed);
}

String _emptyTasksLabel(String filter) {
  switch (filter) {
    case 'overdue':
      return 'Просроченных задач нет';
    case 'completed':
      return 'Выполненных задач пока нет';
    default:
      return 'Активных задач нет';
  }
}

String _taskDeadlineLabel(Object? value) {
  if (value == null || value.toString().isEmpty) {
    return 'Без срока';
  }
  final date = DateTime.tryParse(value.toString());
  if (date == null) {
    return 'Срок не указан';
  }
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  final hour = date.hour.toString().padLeft(2, '0');
  final minute = date.minute.toString().padLeft(2, '0');
  return '$day.$month.${date.year} $hour:$minute';
}
