package com.leeholmes.pyco;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Process;

public final class RestartActivity extends Activity {
    static final String PROCESS_ID = "com.leeholmes.pyco.PROCESS_ID";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        int processId = getIntent().getIntExtra(PROCESS_ID, -1);
        if (processId <= 0 || processId == Process.myPid()) {
            throw new IllegalStateException("Invalid Pyco process to restart");
        }

        // CPython is process-wide: recreating the main activity would reuse old modules.
        Process.killProcess(processId);
        Intent launch = new Intent(this, MainActivity.class);
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        startActivity(launch);
        finish();
    }
}
