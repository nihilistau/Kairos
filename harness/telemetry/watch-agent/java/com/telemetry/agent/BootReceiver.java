package com.telemetry.agent;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * A watch reboots — on an update, on a flat battery, on a whim. Without this the agent
 * stops silently and the first anyone knows is a hole in his history, which is the failure
 * mode this whole package is written to avoid.
 */
public class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context c, Intent i) {
        c.startForegroundService(new Intent(c, AgentService.class));
    }
}
