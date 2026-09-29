import 'package:flet/flet.dart';
import 'package:flutter/services.dart';

/// Bridges Python's TorManager to the Android plugin (FletTorPlugin.java).
class TorManagerService extends FletService {
  TorManagerService({required super.control});

  static const _channel = MethodChannel("flet_tor");

  @override
  void init() {
    super.init();
    control.addInvokeMethodListener(_invokeMethod);
  }

  Future<dynamic> _invokeMethod(String name, dynamic args) async {
    switch (name) {
      case "start":
        final bridges = ((args?["bridges"] as List?) ?? const [])
            .map((line) => line.toString())
            .toList();
        await _channel.invokeMethod("start", {"bridges": bridges});
        return null;
      case "status":
        final status = await _channel.invokeMethod<Map>("status");
        return status == null ? null : Map<String, dynamic>.from(status);
      default:
        throw Exception("Unknown TorManager method: $name");
    }
  }

  @override
  void dispose() {
    control.removeInvokeMethodListener(_invokeMethod);
    super.dispose();
  }
}
