import 'package:flet/flet.dart';

import 'tor_manager.dart';

class Extension extends FletExtension {
  @override
  FletService? createService(Control control) {
    switch (control.type) {
      case "TorManager":
        return TorManagerService(control: control);
      default:
        return null;
    }
  }
}
