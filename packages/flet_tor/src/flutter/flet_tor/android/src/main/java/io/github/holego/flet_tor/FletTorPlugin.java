package io.github.holego.flet_tor;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.List;

import io.flutter.embedding.engine.plugins.FlutterPlugin;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

/** Method channel "flet_tor": start(bridges) and status(). */
public class FletTorPlugin implements FlutterPlugin, MethodChannel.MethodCallHandler {
    private MethodChannel channel;
    private TorController tor;

    @Override
    public void onAttachedToEngine(@NonNull FlutterPluginBinding binding) {
        tor = TorController.get(binding.getApplicationContext());
        channel = new MethodChannel(binding.getBinaryMessenger(), "flet_tor");
        channel.setMethodCallHandler(this);
    }

    @Override
    public void onDetachedFromEngine(@NonNull FlutterPluginBinding binding) {
        channel.setMethodCallHandler(null);
    }

    @Override
    public void onMethodCall(@NonNull MethodCall call, @NonNull MethodChannel.Result result) {
        switch (call.method) {
            case "start":
                List<String> bridges = call.argument("bridges");
                tor.start(bridges != null ? bridges : new ArrayList<>());
                result.success(null);
                break;
            case "status":
                tor.status(result);
                break;
            default:
                result.notImplemented();
        }
    }
}
