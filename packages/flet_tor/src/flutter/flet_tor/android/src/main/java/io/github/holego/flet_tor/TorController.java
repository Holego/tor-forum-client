package io.github.holego.flet_tor;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.util.Log;

import net.freehaven.tor.control.TorControlConnection;

import org.torproject.jni.TorService;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import IPtProxy.Controller;
import IPtProxy.IPtProxy;
import io.flutter.plugin.common.MethodChannel;

/**
 * Runs Tor in the app process and applies bridge settings.
 *
 * Tor is launched once with DisableNetwork=1 and a ClientTransportPlugin for every transport
 * IPtProxy provides. Connecting (or switching bridges) is then a SETCONF over the control
 * connection followed by DisableNetwork=0 — no Tor restart, which Tor doesn't support in-process.
 */
final class TorController {
    private static final String TAG = "FletTor";
    private static final long CONTROL_TIMEOUT_MS = 30_000;
    private static final String[] TRANSPORTS = {
        IPtProxy.Snowflake, IPtProxy.Obfs4, IPtProxy.Webtunnel, IPtProxy.MeekLite,
    };

    private static TorController instance;

    static synchronized TorController get(Context context) {
        if (instance == null) {
            instance = new TorController(context.getApplicationContext());
        }
        return instance;
    }

    private final Context context;
    // Serialises start/reconfigure; status has its own thread so it never waits behind a slow start.
    private final ExecutorService configExecutor = Executors.newSingleThreadExecutor();
    private final ExecutorService statusExecutor = Executors.newSingleThreadExecutor();
    private final Handler main = new Handler(Looper.getMainLooper());

    private volatile TorService service;
    private volatile String error;
    private volatile String lastPhase;
    private boolean launched;
    private Controller transports;

    private final ServiceConnection connection = new ServiceConnection() {
        @Override
        public void onServiceConnected(ComponentName name, IBinder binder) {
            service = ((TorService.LocalBinder) binder).getService();
            Log.i(TAG, "TorService connected");
        }

        @Override
        public void onServiceDisconnected(ComponentName name) {
            service = null;
            Log.w(TAG, "TorService disconnected");
        }
    };

    private TorController(Context context) {
        this.context = context;
    }

    void start(List<String> bridges) {
        List<String> copy = new ArrayList<>(bridges);
        configExecutor.execute(() -> {
            try {
                if (!launched) {
                    launch();
                }
                applyBridges(waitForControl(), copy);
                error = null;
            } catch (Exception e) {
                Log.e(TAG, "Could not start Tor", e);
                error = e.getMessage() != null ? e.getMessage() : e.toString();
            }
        });
    }

    void status(MethodChannel.Result result) {
        statusExecutor.execute(() -> {
            Map<String, Object> status = new HashMap<>();
            TorService svc = service;
            String phase = null;
            int socksPort = -1;
            if (svc != null && svc.getTorControlConnection() != null) {
                phase = svc.getInfo("status/bootstrap-phase");
                socksPort = svc.getSocksPort();
            }
            if (phase != null && !phase.equals(lastPhase)) {
                Log.i(TAG, "Bootstrap: " + phase);
                lastPhase = phase;
            }
            status.put("running", svc != null);
            status.put("phase", phase);
            status.put("socks_port", socksPort);
            status.put("error", error);
            main.post(() -> result.success(status));
        });
    }

    private void launch() throws Exception {
        File stateDir = new File(context.getNoBackupFilesDir(), "iptproxy");
        if (!stateDir.isDirectory() && !stateDir.mkdirs()) {
            throw new IllegalStateException("Cannot create " + stateDir);
        }
        transports = IPtProxy.newController(stateDir.getAbsolutePath(), false, false, "ERROR", null);

        StringBuilder torrc = new StringBuilder()
            .append("DisableNetwork 1\n")
            .append("HTTPTunnelPort 0\n")
            .append("AvoidDiskWrites 1\n");
        for (String transport : TRANSPORTS) {
            transports.start(transport, "");
            torrc.append("ClientTransportPlugin ").append(transport)
                .append(" socks5 127.0.0.1:").append(transports.port(transport)).append('\n');
        }
        try (FileOutputStream out = new FileOutputStream(TorService.getTorrc(context))) {
            out.write(torrc.toString().getBytes(StandardCharsets.UTF_8));
        }

        Intent intent = new Intent(context, TorService.class);
        if (!context.bindService(intent, connection, Context.BIND_AUTO_CREATE)) {
            throw new IllegalStateException("Cannot bind TorService");
        }
        launched = true;
        Log.i(TAG, "Tor launching with transports on " + torrc.toString().replace('\n', ' '));
    }

    private TorControlConnection waitForControl() throws InterruptedException {
        long deadline = System.currentTimeMillis() + CONTROL_TIMEOUT_MS;
        while (System.currentTimeMillis() < deadline) {
            TorService svc = service;
            if (svc != null && svc.getTorControlConnection() != null) {
                return svc.getTorControlConnection();
            }
            Thread.sleep(200);
        }
        throw new IllegalStateException("Tor did not start in time");
    }

    private void applyBridges(TorControlConnection control, List<String> bridges) throws Exception {
        control.setConf("DisableNetwork", "1");
        if (bridges.isEmpty()) {
            control.setConf("UseBridges", "0");
            control.resetConf(Collections.singletonList("Bridge"));
        } else {
            List<String> conf = new ArrayList<>();
            conf.add("UseBridges 1");
            for (String bridge : bridges) {
                conf.add("Bridge " + bridge);
            }
            control.setConf(conf);
        }
        control.setConf("DisableNetwork", "0");
        Log.i(TAG, "Connecting " + (bridges.isEmpty() ? "directly" : "via " + bridges.size() + " bridge(s)"));
    }
}
