import 'dart:async';

import 'package:flutter/foundation.dart';

import 'protocol.dart';

/// App state: connection, adapter info and the settings being edited.
/// Every edit is written to the adapter immediately (it applies live); [save]
/// stores the current settings in the adapter's flash.
class AdapterModel extends ChangeNotifier {
  AdapterModel() {
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => _tick());
    _tick();
  }

  Timer? _timer;

  /// Offline model with fixed data (README screenshots).
  AdapterModel.demo(this.info, this.settings, this._demoLive);

  LiveState? _demoLive;
  AdapterClient? _client;
  AdapterInfo? info;
  Settings? settings;
  bool dirty = false;
  String? lastError;

  bool get connected => (_client != null || _demoLive != null) && settings != null;

  void _tick() {
    if (_client == null) {
      final c = AdapterClient.connect();
      if (c == null) return;
      try {
        final i = c.info();
        _client = c;
        info = i;
        settings = c.readSettings(i.settingsSize);
        dirty = false;
        lastError = null;
        notifyListeners();
      } on ProtocolException catch (e) {
        c.close();
        lastError = e.message;
        notifyListeners();
      }
      return;
    }
    _guard(() => info = _client!.info());
  }

  void _drop(String message) {
    _client?.close();
    _client = null;
    settings = null;
    info = null;
    lastError = message;
    notifyListeners();
  }

  bool _guard(void Function() f) {
    final c = _client;
    if (c == null) return false;
    try {
      f();
      notifyListeners();
      return true;
    } on ProtocolException catch (e) {
      _drop(e.message);
      return false;
    }
  }

  /// Change a field with [mutate], then send it to the adapter.
  void edit(Field f, void Function(Settings s) mutate) {
    final s = settings;
    if (s == null || _demoLive != null) return;
    mutate(s);
    if (_guard(() => _client!.write(s, f))) dirty = true;
  }

  Future<bool> save() async {
    final ok = _guard(() => _client!.save());
    if (ok) {
      dirty = false;
      notifyListeners();
    }
    return ok;
  }

  void defaults() {
    _guard(() {
      _client!.defaults();
      settings = _client!.readSettings(info!.settingsSize);
      dirty = true;
    });
  }

  /// Current input (for the tester); polled often, so it doesn't notify listeners.
  LiveState? live() {
    if (_demoLive != null) return _demoLive;
    final c = _client;
    if (c == null) return null;
    try {
      return c.live();
    } on ProtocolException catch (e) {
      _drop(e.message);
      return null;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    _client?.close();
    super.dispose();
  }
}
