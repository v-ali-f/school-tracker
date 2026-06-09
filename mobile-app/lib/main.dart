import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

const String defaultApiBaseUrl = 'http://10.172.85.55/mobile/api';

void main() {
  runApp(const SchoolSupportApp());
}

class SchoolSupportApp extends StatelessWidget {
  const SchoolSupportApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Сопровождение',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff246b5f),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      home: AppRoot(api: PortalApi(defaultApiBaseUrl)),
    );
  }
}

class AppRoot extends StatefulWidget {
  const AppRoot({super.key, required this.api});

  final PortalApi api;

  @override
  State<AppRoot> createState() => _AppRootState();
}

class _AppRootState extends State<AppRoot> {
  Map<String, dynamic>? user;

  void _setUser(Map<String, dynamic>? value) {
    setState(() => user = value);
  }

  @override
  Widget build(BuildContext context) {
    if (user == null) {
      return LoginScreen(api: widget.api, onLogin: _setUser);
    }

    return HomeShell(
      api: widget.api,
      user: user!,
      onLogout: () => _setUser(null),
    );
  }
}

class PortalApi {
  PortalApi(this.baseUrl);

  final String baseUrl;
  final HttpClient _client = HttpClient();
  String _cookie = '';

  Future<Map<String, dynamic>> login(String username, String password) async {
    final data = await post('/auth/login', {
      'username': username,
      'password': password,
    });
    return Map<String, dynamic>.from(data['user'] as Map);
  }

  Future<void> logout() async {
    await post('/auth/logout', {});
    _cookie = '';
  }

  Future<Map<String, dynamic>> me() => get('/me');

  Future<Map<String, dynamic>> notifications() => get('/notifications');

  Future<Map<String, dynamic>> myIncidents() => get('/incidents/mine');

  Future<Map<String, dynamic>> incidentMeta() => get('/incidents/meta');

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
    return _send(request);
  }

  Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body,
  ) async {
    final request = await _client.postUrl(_uri(path));
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

  Future<Map<String, dynamic>> _send(HttpClientRequest request) async {
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (_cookie.isNotEmpty) {
      request.headers.set(HttpHeaders.cookieHeader, _cookie);
    }

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

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key, required this.api, required this.onLogin});

  final PortalApi api;
  final ValueChanged<Map<String, dynamic>> onLogin;

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final username = TextEditingController();
  final password = TextEditingController();
  bool loading = false;
  String error = '';

  Future<void> submit() async {
    setState(() {
      loading = true;
      error = '';
    });

    try {
      final user = await widget.api.login(username.text.trim(), password.text);
      widget.onLogin(user);
    } catch (exception) {
      setState(() => error = _message(exception));
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              shrinkWrap: true,
              padding: const EdgeInsets.all(24),
              children: [
                const Icon(Icons.school_outlined, size: 56),
                const SizedBox(height: 18),
                Text(
                  'Система сопровождения',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const SizedBox(height: 8),
                Text(
                  'Войдите под учетной записью портала',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 28),
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
}

class HomeShell extends StatefulWidget {
  const HomeShell({
    super.key,
    required this.api,
    required this.user,
    required this.onLogout,
  });

  final PortalApi api;
  final Map<String, dynamic> user;
  final VoidCallback onLogout;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int index = 0;

  Future<void> logout() async {
    await widget.api.logout();
    widget.onLogout();
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      OverviewScreen(api: widget.api, user: widget.user),
      IncidentsScreen(api: widget.api),
      NewIncidentScreen(api: widget.api),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Сопровождение'),
        actions: [
          IconButton(
            tooltip: 'Выйти',
            onPressed: logout,
            icon: const Icon(Icons.logout),
          ),
        ],
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
            icon: Icon(Icons.assignment_outlined),
            label: 'Инциденты',
          ),
          NavigationDestination(
            icon: Icon(Icons.add_circle_outline),
            label: 'Создать',
          ),
        ],
      ),
    );
  }
}

class OverviewScreen extends StatelessWidget {
  const OverviewScreen({super.key, required this.api, required this.user});

  final PortalApi api;
  final Map<String, dynamic> user;

  @override
  Widget build(BuildContext context) {
    return RefreshableFuture(
      load: api.notifications,
      builder: (context, data, reload) {
        final items = List<dynamic>.from(data['items'] as List? ?? const []);
        final unread = data['unread'] ?? 0;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            InfoPanel(
              icon: Icons.account_circle_outlined,
              title:
                  user['fio']?.toString() ??
                  user['username']?.toString() ??
                  'Пользователь',
              subtitle: 'Новых уведомлений: $unread',
            ),
            const SizedBox(height: 16),
            Text('Уведомления', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            if (items.isEmpty)
              const EmptyState(text: 'Новых уведомлений нет')
            else
              ...items.map(
                (item) => NotificationTile(
                  item: Map<String, dynamic>.from(item as Map),
                ),
              ),
          ],
        );
      },
    );
  }
}

class IncidentsScreen extends StatelessWidget {
  const IncidentsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return RefreshableFuture(
      load: api.myIncidents,
      builder: (context, data, reload) {
        final authored = List<dynamic>.from(
          data['authored'] as List? ?? const [],
        );
        final assigned = List<dynamic>.from(
          data['assigned'] as List? ?? const [],
        );
        final items = [
          ...authored.map((item) => Map<String, dynamic>.from(item as Map)),
          ...assigned.map((item) => Map<String, dynamic>.from(item as Map)),
        ];
        final seen = <Object>{};
        final unique = items.where((item) => seen.add(item['id'])).toList();

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Мои инциденты',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            if (unique.isEmpty)
              const EmptyState(text: 'Инцидентов пока нет')
            else
              ...unique.map((item) => IncidentTile(item: item)),
          ],
        );
      },
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

  Future<void> loadMeta() async {
    setState(() {
      loading = true;
      error = '';
    });
    try {
      final meta = await widget.api.incidentMeta();
      final classRows = await widget.api.classes();
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
      setState(() => error = _message(exception));
    } finally {
      setState(() => loading = false);
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
      setState(() {
        children = rows
            .map((item) => Map<String, dynamic>.from(item as Map))
            .toList();
      });
    } catch (exception) {
      setState(() => error = _message(exception));
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
      description.clear();
      initialWork.clear();
      setState(() => selectedChildren.clear());
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Инцидент создан')));
    } catch (exception) {
      setState(() => error = _message(exception));
    } finally {
      setState(() => saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Center(child: CircularProgressIndicator());
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Новый инцидент', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          value: category,
          items: categories
              .map((item) => DropdownMenuItem(value: item, child: Text(item)))
              .toList(),
          onChanged: (value) => setState(() => category = value),
          decoration: const InputDecoration(
            labelText: 'Категория',
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        DropdownButtonFormField<int>(
          value: selectedClassId,
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
    setState(() => future = widget.load());
    await future;
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

class NotificationTile extends StatelessWidget {
  const NotificationTile({super.key, required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(
          item['kind'] == 'incident'
              ? Icons.report_outlined
              : Icons.task_outlined,
        ),
        title: Text(item['title']?.toString() ?? 'Уведомление'),
        subtitle: Text(item['message']?.toString() ?? ''),
        trailing: item['is_read'] == true
            ? null
            : const Icon(Icons.circle, size: 12),
      ),
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

String _message(Object? exception) {
  if (exception is PortalApiException) {
    return exception.message;
  }
  return 'Не удалось подключиться к серверу портала.';
}

String _dateLabel(DateTime date) {
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  return '$day.$month.${date.year}';
}
