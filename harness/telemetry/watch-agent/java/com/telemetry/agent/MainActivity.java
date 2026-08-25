package com.telemetry.agent;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.widget.TextView;

/**
 * A launcher, and not much more. It exists because an app with no activity cannot be
 * started from the watch, and because ONE screen that says where the readings are going is
 * worth more on a 1.4-inch display than any amount of UI: if the endpoint is wrong, that
 * is the only thing anybody needs to see.
 */
public class MainActivity extends Activity {
    @Override protected void onCreate(Bundle b) {
        super.onCreate(b);
        startForegroundService(new Intent(this, AgentService.class));
        String url = getSharedPreferences(AgentService.PREFS, Context.MODE_PRIVATE)
                .getString(AgentService.K_URL, AgentService.DEFAULT_URL);
        TextView t = new TextView(this);
        t.setPadding(24, 24, 24, 24);
        t.setTextSize(11f);
        t.setText("Telemetry running\n\n-> " + url);
        setContentView(t);
    }
}
