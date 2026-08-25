package com.telemetry.agent;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.BroadcastReceiver;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.BatteryManager;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.util.Log;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;

/**
 * The agent. Listens to the wrist, reduces, and posts batches to the harness.
 *
 * THREE THINGS IT WILL NOT DO, and each is the reason a naive version of this is useless:
 *
 *  1. IT DOES NOT POST RAW MOTION. The accelerometer runs at 100+ Hz and the gyroscope
 *     with it. Sending that up a Wi-Fi link would flatten the battery and hand the harness
 *     a firehose nobody reads. It reduces to ONE NUMBER PER WINDOW — the RMS magnitude —
 *     which is the thing a person in the room would actually notice: pacing, fidgeting,
 *     turning over. Everything downstream was built expecting that number.
 *
 *  2. IT DOES NOT POST EVERY HEARTBEAT THE INSTANT IT ARRIVES. The HR sensor on this watch
 *     reports at 1 Hz with a 600-event FIFO, so the hardware is happy to buffer ten
 *     minutes. Posting per sample would be 3,600 requests an hour. It batches.
 *
 *  3. IT DOES NOT DROP WHAT IT COULD NOT SEND. The wrist leaves the house; the Wi-Fi drops;
 *     the gateway restarts. Failed batches go back on the front of the queue and are
 *     retried, bounded — because the alternative is a hole in his history exactly when he
 *     was somewhere interesting. The bound exists so a week offline does not OOM the watch.
 */
public class AgentService extends Service implements SensorEventListener {

    private static final String TAG = "telemetry-agent";
    private static final String CH = "telemetry";
    static final String PREFS = "agent";
    static final String K_URL = "url";
    /** Where batches go. A DEFAULT, not a setting: pass --es url (build.py --arm does,
     *  from TELEMETRY_ENDPOINT) and it is remembered in SharedPreferences. MainActivity
     *  prints whatever is live, because on a 1.4-inch screen the endpoint is the only
     *  thing worth showing -- if it is wrong, nothing else on the watch will tell you. */
    static final String DEFAULT_URL = "http://10.0.0.150:8800/v1/telemetry/ingest";

    /** How often a batch goes up. Not a knob for its own sake: shorter means her view of
     *  his heart is fresher, longer means less radio. 30 s is a compromise that keeps the
     *  "climbing" trend visible within a turn of conversation. */
    private static final long POST_EVERY_MS = 30_000L;
    /** One motion number per this window. */
    private static final long MOTION_WINDOW_MS = 10_000L;
    /** The queue bound — roughly a day of ordinary sampling. Past this the OLDEST go,
     *  because when the link comes back what he wants is the recent shape, not the start
     *  of an outage. */
    private static final int MAX_QUEUE = 20_000;

    private SensorManager sm;
    private PowerManager.WakeLock wake;
    private HandlerThread thread;
    private Handler handler;

    private final List<String> queue = new ArrayList<String>();
    private final Object lock = new Object();

    // motion accumulators for the current window
    private double gyroSq = 0.0; private int gyroN = 0;
    private double accSq = 0.0;  private int accN = 0;
    private long windowStart = 0L;
    private long lastLight = 0L;
    private long lastPressure = 0L;

    private String endpoint = DEFAULT_URL;
    private volatile boolean running = false;

    /** "watch" or "phone" — DETECTED, not configured.
     *
     *  ONE AGENT FOR BOTH, and that is the whole reason this field exists. A separate phone
     *  app would be a second implementation of "read sensors, reduce, batch, retry" and this
     *  codebase already knows what two implementations of one thing cost. The sensor set
     *  differs (a phone has no heart rate; a watch has no useful ambient light in a sleeve)
     *  and `reg()` already skips what is absent, so the only real difference is what the
     *  readings MEAN — and that is a question for the harness, which is why the source is
     *  reported rather than assumed. */
    private String source = "phone";

    @Override public IBinder onBind(Intent i) { return null; }

    @Override public void onCreate() {
        super.onCreate();
        SharedPreferences p = getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        endpoint = p.getString(K_URL, DEFAULT_URL);

        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel ch = new NotificationChannel(CH, "Telemetry",
                NotificationManager.IMPORTANCE_MIN);
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);
        Notification n = new Notification.Builder(this, CH)
                .setContentTitle("Telemetry")
                .setContentText("reading")
                .setSmallIcon(android.R.drawable.ic_menu_compass)
                .setOngoing(true)
                .build();
        startForeground(1, n);

        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wake = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "telemetry:agent");
        wake.setReferenceCounted(false);
        wake.acquire();

        thread = new HandlerThread("telemetry-post");
        thread.start();
        handler = new Handler(thread.getLooper());

        source = getPackageManager().hasSystemFeature(PackageManager.FEATURE_WATCH)
                ? "watch" : "phone";

        sm = (SensorManager) getSystemService(Context.SENSOR_SERVICE);
        windowStart = System.currentTimeMillis();
        register();
        registerDeviceState();
        running = true;
        handler.postDelayed(poster, POST_EVERY_MS);
        Log.i(TAG, "started as " + source + ", posting to " + endpoint);
    }

    private void reg(int type, int usDelay) {
        Sensor s = sm.getDefaultSensor(type);
        if (s != null) {
            // maxReportLatency lets the HARDWARE batch (600-event FIFO on the HR sensor),
            // which is the difference between a wakeup per sample and a wakeup per minute.
            sm.registerListener(this, s, usDelay, 60_000_000);
            Log.i(TAG, "listening: " + s.getName());
        } else {
            Log.w(TAG, "no sensor of type " + type);
        }
    }

    private void register() {
        // Absent sensors are skipped by reg(), so this list is the UNION of both devices
        // rather than two lists that have to be kept in step. A phone has no heart rate and
        // no off-body detector; a watch usually has no barometer worth reading indoors.
        reg(Sensor.TYPE_HEART_RATE, SensorManager.SENSOR_DELAY_NORMAL);
        reg(Sensor.TYPE_GYROSCOPE, SensorManager.SENSOR_DELAY_NORMAL);
        reg(Sensor.TYPE_ACCELEROMETER, SensorManager.SENSOR_DELAY_NORMAL);
        reg(Sensor.TYPE_STEP_COUNTER, SensorManager.SENSOR_DELAY_NORMAL);
        reg(Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT, SensorManager.SENSOR_DELAY_NORMAL);
        // AMBIENT, and mostly a phone's job: a watch spends its life inside a sleeve, so
        // its light reading says more about his cuff than about the room.
        reg(Sensor.TYPE_LIGHT, SensorManager.SENSOR_DELAY_NORMAL);
        reg(Sensor.TYPE_PRESSURE, SensorManager.SENSOR_DELAY_NORMAL);
    }

    /** Screen, charging and battery. NOT sensors — broadcasts — and worth having because
     *  they are the cheapest presence signal there is: a screen that came on thirty seconds
     *  ago is a person who is awake, whatever anything else thinks. */
    private final BroadcastReceiver deviceState = new BroadcastReceiver() {
        @Override public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (Intent.ACTION_SCREEN_ON.equals(a)) {
                pushState("screen", "on");
            } else if (Intent.ACTION_SCREEN_OFF.equals(a)) {
                pushState("screen", "off");
            } else if (Intent.ACTION_BATTERY_CHANGED.equals(a)) {
                int lvl = i.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = i.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
                if (lvl >= 0 && scale > 0) push("battery", 100f * lvl / scale);
                int t = i.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, -1);
                if (t > 0) push("battery_temp", t / 10f);      // tenths of a degree
                int st = i.getIntExtra(BatteryManager.EXTRA_STATUS, -1);
                pushState("charging", (st == BatteryManager.BATTERY_STATUS_CHARGING
                        || st == BatteryManager.BATTERY_STATUS_FULL) ? "on" : "off");
            }
        }
    };

    private void registerDeviceState() {
        IntentFilter f = new IntentFilter();
        f.addAction(Intent.ACTION_SCREEN_ON);
        f.addAction(Intent.ACTION_SCREEN_OFF);
        // BATTERY_CHANGED is sticky and CHATTY -- it fires on every percent and every
        // temperature wobble. That is fine: the store is one line per sample and the panel
        // wants the shape, but it is the reason batteries are not polled on top of this.
        f.addAction(Intent.ACTION_BATTERY_CHANGED);
        registerReceiver(deviceState, f);
        // ── AND THE STATE IT IS IN RIGHT NOW (2026-08-26) ────────────────────────────
        // SCREEN_ON/OFF are TRANSITIONS, not sticky. Registering alone means the harness
        // learns nothing about the screen until he next toggles it -- so after every
        // restart the screen veto (the cheapest "he is awake" signal there is, and the one
        // that stops her calling a man reading in bed asleep) was silently unavailable for
        // an unbounded time. Found by watching for a `screen` row that never came.
        // BATTERY_CHANGED is sticky and needs no equivalent; the receiver got it at once.
        try {
            PowerManager p2 = (PowerManager) getSystemService(Context.POWER_SERVICE);
            pushState("screen", p2.isInteractive() ? "on" : "off");
        } catch (Throwable ignored) { }
    }

    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && intent.hasExtra("url")) {
            endpoint = intent.getStringExtra("url");
            getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                    .edit().putString(K_URL, endpoint).apply();
            Log.i(TAG, "endpoint set to " + endpoint);
        }
        return START_STICKY;
    }

    @Override public void onAccuracyChanged(Sensor s, int a) { }

    @Override public void onSensorChanged(SensorEvent e) {
        long now = System.currentTimeMillis();
        switch (e.sensor.getType()) {
            case Sensor.TYPE_HEART_RATE:
                // 0 means "no reading" on this hardware, not a heart that stopped. The
                // harness would reject it as out of bounds anyway; dropping it here saves
                // the round trip and keeps `rejected` meaningful for real faults.
                if (e.values[0] > 0) push("heart_rate", e.values[0]);
                break;
            case Sensor.TYPE_STEP_COUNTER:
                push("steps", e.values[0]);
                break;
            case Sensor.TYPE_LIGHT:
                // RATE-LIMITED: an ambient light sensor fires on every flicker and a room
                // does not change that often. One reading a minute is the shape she can use
                // ("the room went dark"); sixty a minute is a firehose about a lamp.
                if (now - lastLight >= 60_000L) { lastLight = now; push("light", e.values[0]); }
                break;
            case Sensor.TYPE_PRESSURE:
                if (now - lastPressure >= 60_000L) { lastPressure = now; push("pressure", e.values[0]); }
                break;
            case Sensor.TYPE_LOW_LATENCY_OFFBODY_DETECT:
                pushState("on_body", e.values[0] > 0.5f ? "on" : "off");
                break;
            case Sensor.TYPE_GYROSCOPE: {
                double m = e.values[0] * e.values[0] + e.values[1] * e.values[1]
                        + e.values[2] * e.values[2];
                gyroSq += m; gyroN++;
                break;
            }
            case Sensor.TYPE_ACCELEROMETER: {
                // gravity removed crudely: what matters is CHANGE, and subtracting 9.81
                // from the magnitude is enough to tell a still wrist from a moving one.
                double mag = Math.sqrt(e.values[0] * e.values[0] + e.values[1] * e.values[1]
                        + e.values[2] * e.values[2]) - 9.81;
                accSq += mag * mag; accN++;
                break;
            }
        }
        if (now - windowStart >= MOTION_WINDOW_MS) closeWindow(now);
    }

    /** One number per window, for each of gyro and accel. See the class comment. */
    private void closeWindow(long now) {
        if (gyroN > 0) push("gyro_rms", (float) Math.sqrt(gyroSq / gyroN));
        if (accN > 0) push("accel_rms", (float) Math.sqrt(accSq / accN));
        gyroSq = 0; gyroN = 0; accSq = 0; accN = 0;
        windowStart = now;
    }

    private void push(String kind, float v) {
        add("{\"kind\":\"" + kind + "\",\"value\":" + String.format("%.3f", v) + "}");
    }

    private void pushState(String kind, String v) {
        add("{\"kind\":\"" + kind + "\",\"value\":\"" + v + "\"}");
    }

    private void add(String json) {
        synchronized (lock) {
            queue.add(json);
            // Oldest first when over the bound: coming back online, the recent shape is
            // what he wants, not the first minute of the outage.
            while (queue.size() > MAX_QUEUE) queue.remove(0);
        }
    }

    private final Runnable poster = new Runnable() {
        @Override public void run() {
            try { flush(); } catch (Throwable t) { Log.w(TAG, "flush: " + t); }
            if (running) handler.postDelayed(this, POST_EVERY_MS);
        }
    };

    private void flush() {
        List<String> batch;
        synchronized (lock) {
            if (queue.isEmpty()) return;
            batch = new ArrayList<String>(queue);
            queue.clear();
        }
        StringBuilder b = new StringBuilder();
        b.append("{\"source\":\"" + source + "\",\"samples\":[");
        for (int i = 0; i < batch.size(); i++) {
            if (i > 0) b.append(',');
            b.append(batch.get(i));
        }
        b.append("]}");

        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(endpoint).openConnection();
            c.setRequestMethod("POST");
            c.setRequestProperty("Content-Type", "application/json");
            c.setConnectTimeout(8000);
            c.setReadTimeout(12000);
            c.setDoOutput(true);
            OutputStream os = c.getOutputStream();
            os.write(b.toString().getBytes("UTF-8"));
            os.close();
            int code = c.getResponseCode();
            if (code / 100 != 2) throw new RuntimeException("HTTP " + code);
            Log.i(TAG, "posted " + batch.size());
        } catch (Throwable t) {
            // PUT IT BACK, at the FRONT, so order survives an outage.
            synchronized (lock) {
                queue.addAll(0, batch);
                while (queue.size() > MAX_QUEUE) queue.remove(0);
            }
            Log.w(TAG, "post failed (" + t + "), queued " + batch.size());
        } finally {
            if (c != null) c.disconnect();
        }
    }

    @Override public void onDestroy() {
        running = false;
        try { sm.unregisterListener(this); } catch (Throwable ignored) { }
        try { unregisterReceiver(deviceState); } catch (Throwable ignored) { }
        try { if (wake.isHeld()) wake.release(); } catch (Throwable ignored) { }
        try { thread.quitSafely(); } catch (Throwable ignored) { }
        super.onDestroy();
    }
}
