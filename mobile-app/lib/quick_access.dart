import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:local_auth/local_auth.dart';

class QuickAccessStore {
  static const _tokenKey = 'altair_mobile_token';
  static const _pinKey = 'altair_quick_pin';
  static const _biometricKey = 'altair_biometric_enabled';

  final FlutterSecureStorage _storage = const FlutterSecureStorage();

  Future<String?> readToken() async {
    try {
      return await _storage.read(key: _tokenKey);
    } catch (_) {
      return null;
    }
  }

  Future<String?> readPin() async {
    try {
      return await _storage.read(key: _pinKey);
    } catch (_) {
      return null;
    }
  }

  Future<bool> biometricEnabled() async {
    try {
      return await _storage.read(key: _biometricKey) == 'true';
    } catch (_) {
      return false;
    }
  }

  Future<void> saveToken(String token) async {
    try {
      await _storage.write(key: _tokenKey, value: token);
    } catch (_) {}
  }

  Future<void> configure({required String pin, required bool biometric}) async {
    try {
      await _storage.write(key: _pinKey, value: pin);
      await _storage.write(key: _biometricKey, value: biometric.toString());
    } catch (_) {}
  }

  Future<void> clear() async {
    try {
      await _storage.delete(key: _tokenKey);
      await _storage.delete(key: _pinKey);
      await _storage.delete(key: _biometricKey);
    } catch (_) {}
  }
}

class DeviceAuthentication {
  final LocalAuthentication _auth = LocalAuthentication();

  Future<bool> isAvailable() async {
    try {
      return await _auth.isDeviceSupported() &&
          (await _auth.getAvailableBiometrics()).isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  Future<bool> authenticate() async {
    try {
      return await _auth.authenticate(
        localizedReason: 'Подтвердите вход в Альтаир',
        biometricOnly: true,
        persistAcrossBackgrounding: true,
      );
    } catch (_) {
      return false;
    }
  }
}
