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
    await post('/auth/login', {'username': username, 'password': password});
    final profile = await me();
    return Map<String, dynamic>.from(profile['user'] as Map)
      ..['permissions'] = profile['permissions'];
  }

  Future<void> logout() async {
    await post('/auth/logout', {});
    _cookie = '';
  }

  Future<Map<String, dynamic>> me() => get('/me');

  Future<Map<String, dynamic>> notifications() => get('/notifications');

  Future<Map<String, dynamic>> myIncidents() => get('/incidents/mine');

  Future<Map<String, dynamic>> myTasks(String filter) =>
      get('/tasks/mine', query: {'filter': filter});

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

  void _prepareRequest(HttpClientRequest request) {
    request.headers.set(HttpHeaders.acceptHeader, 'application/json');
    if (_cookie.isNotEmpty) {
      request.headers.set(HttpHeaders.cookieHeader, _cookie);
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

  void openTab(int value) {
    setState(() => index = value);
  }

  Future<void> logout() async {
    await widget.api.logout();
    widget.onLogout();
  }

  Future<void> createIncident() async {
    final created = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => NewIncidentScreen(api: widget.api)),
    );
    if (created == true && mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Инцидент создан')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final permissions = Map<String, dynamic>.from(
      widget.user['permissions'] as Map? ?? const {},
    );
    final canCreateIncident =
        permissions['can_add_incident'] == true || permissions.isEmpty;
    final pages = [
      HomeScreen(api: widget.api, user: widget.user, openTab: openTab),
      NotificationsScreen(api: widget.api),
      TasksScreen(api: widget.api),
      DocumentsScreen(api: widget.api),
      ProfileScreen(user: widget.user, onLogout: logout),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Сопровождение'),
        actions: [
          if (canCreateIncident)
            IconButton(
              tooltip: 'Создать инцидент',
              onPressed: createIncident,
              icon: const Icon(Icons.add_circle_outline),
            ),
        ],
      ),
      body: pages[index],
      bottomNavigationBar: NavigationBar(
        height: 72,
        selectedIndex: index,
        onDestinationSelected: (value) => setState(() => index = value),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Главная',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_outlined),
            label: 'События',
          ),
          NavigationDestination(
            icon: Icon(Icons.task_alt_outlined),
            label: 'Задачи',
          ),
          NavigationDestination(
            icon: Icon(Icons.folder_open_outlined),
            label: 'Документы',
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
        final permissions = Map<String, dynamic>.from(
          user['permissions'] as Map? ?? const {},
        );
        final canCreateIncident =
            permissions['can_add_incident'] == true || permissions.isEmpty;

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            InfoPanel(
              icon: Icons.account_circle_outlined,
              title:
                  user['fio']?.toString() ??
                  user['username']?.toString() ??
                  'Пользователь',
              subtitle:
                  '${user['role'] ?? 'Сотрудник'} • новых уведомлений: $unread',
            ),
            const SizedBox(height: 16),
            Text(
              'Быстрые действия',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(44),
                      alignment: Alignment.center,
                    ),
                    onPressed: canCreateIncident
                        ? () async {
                            final created = await Navigator.of(context)
                                .push<bool>(
                                  MaterialPageRoute(
                                    builder: (_) => NewIncidentScreen(api: api),
                                  ),
                                );
                            if (created == true && context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('Инцидент создан'),
                                ),
                              );
                            }
                          }
                        : null,
                    icon: const Icon(Icons.report_outlined),
                    label: const Text('Инцидент'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size.fromHeight(44),
                      alignment: Alignment.center,
                    ),
                    onPressed: () => openTab(2),
                    icon: const Icon(Icons.add_task_outlined),
                    label: const Text('Задача'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Разделы', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            GridView.count(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              mainAxisExtent: 118,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              children: [
                ServiceCard(
                  icon: Icons.assignment_outlined,
                  title: 'Инциденты',
                  subtitle: 'Создание и реестр',
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => IncidentsScreen(
                          api: api,
                          canCreate: canCreateIncident,
                        ),
                      ),
                    );
                  },
                ),
                ServiceCard(
                  icon: Icons.task_alt_outlined,
                  title: 'Задачи',
                  subtitle: 'Мои поручения',
                  onTap: () => openTab(2),
                ),
                ServiceCard(
                  icon: Icons.chat_bubble_outline,
                  title: 'Обращения',
                  subtitle: 'Внутренние заявки',
                  onTap: () => _showPlanned(context),
                ),
                ServiceCard(
                  icon: Icons.folder_open_outlined,
                  title: 'Документы',
                  subtitle: 'Просмотр файлов',
                  onTap: () => openTab(3),
                ),
                ServiceCard(
                  icon: Icons.event_note_outlined,
                  title: 'План работы',
                  subtitle: 'День, неделя, месяц',
                  onTap: () => _showPlanned(context),
                ),
                ServiceCard(
                  icon: Icons.search,
                  title: 'Поиск',
                  subtitle: 'Ученики и документы',
                  onTap: () => _showPlanned(context),
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
                      item: Map<String, dynamic>.from(item as Map),
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
                  item: Map<String, dynamic>.from(item as Map),
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

  @override
  Widget build(BuildContext context) {
    return Column(
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
            key: ValueKey(filter),
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
                itemBuilder: (context, index) => TaskCard(
                  item: Map<String, dynamic>.from(items[index] as Map),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class DocumentsScreen extends StatelessWidget {
  const DocumentsScreen({super.key, required this.api});

  final PortalApi api;

  @override
  Widget build(BuildContext context) {
    return const ModulePlaceholder(
      icon: Icons.folder_open_outlined,
      title: 'Документы',
      text:
          'Раздел второй очереди по ТЗ. Здесь будет просмотр документов, приказов, избранное и последние открытые файлы.',
    );
  }
}

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key, required this.user, required this.onLogout});

  final Map<String, dynamic> user;
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

class ServiceCard extends StatelessWidget {
  const ServiceCard({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 26),
              const SizedBox(height: 8),
              Text(
                title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleMedium,
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

class TaskCard extends StatelessWidget {
  const TaskCard({super.key, required this.item});

  final Map<String, dynamic> item;

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

void _showPlanned(BuildContext context) {
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text('Раздел будет подключен на следующем этапе')),
  );
}

String describePortalError(Object? exception) => _message(exception);

String _message(Object? exception) {
  if (exception is PortalApiException) {
    return exception.message;
  }
  if (exception is SocketException) {
    final details = exception.osError?.message ?? exception.message;
    return 'Не удалось открыть $defaultApiBaseUrl. '
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
