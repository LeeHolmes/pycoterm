package com.leeholmes.pyco;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Rect;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.os.VibratorManager;
import android.view.View;
import android.view.WindowManager;
import android.view.ViewTreeObserver;
import android.view.inputmethod.InputMethodManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.view.WindowInsets;
import android.view.WindowInsetsController;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String APP_URL = "file:///android_asset/index.html";

    private final ExecutorService startupExecutor = Executors.newSingleThreadExecutor();
    private WebView webView;
    private PythonBridge pythonBridge;
    private ViewTreeObserver.OnGlobalLayoutListener viewportListener;
    private volatile int visibleViewportHeight;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(40, 40, 40));
        getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(false);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            settings.setAlgorithmicDarkeningAllowed(false);
        } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            settings.setForceDark(WebSettings.FORCE_DARK_OFF);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !request.getUrl().toString().startsWith("file:///android_asset/");
            }
        });
        pythonBridge = new PythonBridge();
        webView.addJavascriptInterface(pythonBridge, "AndroidPython");
        setContentView(webView);
        viewportListener = this::updateVisibleViewport;
        webView.getViewTreeObserver().addOnGlobalLayoutListener(viewportListener);
        hideSystemBars();
        webView.loadUrl(APP_URL);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }

    @Override
    public void onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        if (webView.getViewTreeObserver().isAlive()) {
            webView.getViewTreeObserver().removeOnGlobalLayoutListener(viewportListener);
        }
        pythonBridge.cancelInput();
        startupExecutor.shutdownNow();
        webView.removeJavascriptInterface("AndroidPython");
        webView.destroy();
        super.onDestroy();
    }

    private void updateVisibleViewport() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R
                && webView.getRootWindowInsets() != null) {
            WindowInsets insets = webView.getRootWindowInsets();
            boolean keyboardVisible = insets.isVisible(WindowInsets.Type.ime());
            int keyboardHeight = insets.getInsets(WindowInsets.Type.ime()).bottom;
            visibleViewportHeight = keyboardVisible
                    ? Math.max(0, webView.getHeight() - keyboardHeight)
                    : 0;
        } else {
            Rect visibleFrame = new Rect();
            webView.getWindowVisibleDisplayFrame(visibleFrame);
            int screenHeight = getResources().getDisplayMetrics().heightPixels;
            int obscuredHeight = Math.max(0, screenHeight - visibleFrame.bottom);
            boolean keyboardVisible = obscuredHeight > screenHeight * 0.15;
            visibleViewportHeight = keyboardVisible ? visibleFrame.height() : 0;
        }
        String javascript = "if(window.pycoAndroidSetViewportHeight){"
                + "window.pycoAndroidSetViewportHeight(" + visibleViewportHeight + ");}";
        webView.evaluateJavascript(javascript, null);
    }

    @SuppressWarnings("deprecation")
    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            WindowInsetsController controller = getWindow().getInsetsController();
            if (controller != null) {
                controller.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                controller.setSystemBarsBehavior(
                        WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(
                    View.SYSTEM_UI_FLAG_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }
    }

    @SuppressWarnings("deprecation")
    private void vibrateDevice(int durationMilliseconds) {
        int duration = Math.max(1, Math.min(durationMilliseconds, 100));
        Vibrator vibrator;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            VibratorManager manager =
                    (VibratorManager) getSystemService(Context.VIBRATOR_MANAGER_SERVICE);
            vibrator = manager.getDefaultVibrator();
        } else {
            vibrator = (Vibrator) getSystemService(Context.VIBRATOR_SERVICE);
        }
        if (vibrator == null || !vibrator.hasVibrator()) {
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            vibrator.vibrate(VibrationEffect.createOneShot(
                    duration, VibrationEffect.DEFAULT_AMPLITUDE));
        } else {
            vibrator.vibrate(duration);
        }
    }

    private final class PythonBridge {
        private final PyObject backend =
                Python.getInstance().getModule("android_backend");

        private PythonBridge() {
            backend.callAttr("set_input_callback", new InputCallback());
        }

        @JavascriptInterface
        public void initialize(String customizationUrl) {
            startupExecutor.execute(() -> {
                String result;
                try {
                    String customization = customizationUrl.trim().isEmpty()
                            ? ""
                            : fetchCustomization(customizationUrl);
                    result = call("initialize", customization);
                } catch (Exception exception) {
                    result = errorJson(exception.getMessage());
                }
                String javascript = "window.pycoAndroidReady(" + JSONObject.quote(result) + ")";
                webView.post(() -> webView.evaluateJavascript(javascript, null));
            });
        }

        @JavascriptInterface
        public void execute(String line) {
            startupExecutor.execute(() -> {
                String result = call("execute_line", line);
                String javascript = "window.pycoAndroidExecutionComplete("
                        + JSONObject.quote(result) + ")";
                webView.post(() -> webView.evaluateJavascript(javascript, null));
            });
        }

        @JavascriptInterface
        public void provideInput(String value) {
            backend.callAttr("provide_input", value);
        }

        @JavascriptInterface
        public String get(String name) {
            return call("get_value", name);
        }

        @JavascriptInterface
        public String callHelper(String name, String argument) {
            return call("call_helper", name, argument);
        }

        @JavascriptInterface
        public String getHelp() {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    getAssets().open("PYCO_README.md"), StandardCharsets.UTF_8))) {
                StringBuilder text = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    text.append(line).append('\n');
                }
                return call("render_markdown", text.toString());
            } catch (IOException exception) {
                return "Unable to load bundled help: " + exception.getMessage();
            }
        }

        @JavascriptInterface
        public String highlight(String source) {
            return call("highlight_python", source);
        }

        @JavascriptInterface
        public String complete(String text) {
            return call("get_completions", text);
        }

        @JavascriptInterface
        public void vibrate(int durationMilliseconds) {
            vibrateDevice(durationMilliseconds);
        }

        @JavascriptInterface
        public int getViewportHeight() {
            return visibleViewportHeight;
        }

        @JavascriptInterface
        public void showKeyboard() {
            webView.postDelayed(() -> {
                webView.requestFocus();
                InputMethodManager inputMethodManager =
                        (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                inputMethodManager.showSoftInput(webView, InputMethodManager.SHOW_IMPLICIT);
            }, 50);
        }

        @JavascriptInterface
        public void hideKeyboard() {
            webView.post(() -> {
                InputMethodManager inputMethodManager =
                        (InputMethodManager) getSystemService(Context.INPUT_METHOD_SERVICE);
                inputMethodManager.hideSoftInputFromWindow(webView.getWindowToken(), 0);
            });
        }

        private String call(String method, Object... args) {
            return backend.callAttr(method, args).toString();
        }

        private void cancelInput() {
            backend.callAttr("cancel_input");
        }
    }

    public final class InputCallback {
        public void requestInput(String pendingOutput, String prompt) {
            String javascript = "window.pycoAndroidRequestInput("
                    + JSONObject.quote(pendingOutput) + ","
                    + JSONObject.quote(prompt) + ")";
            webView.post(() -> webView.evaluateJavascript(javascript, null));
        }
    }

    private static String fetchCustomization(String value) throws Exception {
        Uri uri = Uri.parse(value);
        String scheme = uri.getScheme();
        if (!"https".equalsIgnoreCase(scheme)) {
            throw new IllegalArgumentException("Customization URL must use HTTPS.");
        }

        HttpURLConnection connection = (HttpURLConnection) new URL(value).openConnection();
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(10_000);
        connection.setInstanceFollowRedirects(true);
        connection.setRequestProperty("Accept", "text/plain,text/x-python,text/*;q=0.9");
        connection.setRequestProperty("User-Agent", "Pyco Android/1.0");
        try {
            int status = connection.getResponseCode();
            if (status < 200 || status >= 300) {
                throw new IllegalStateException("Customization request failed with HTTP " + status);
            }
            StringBuilder text = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    connection.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    text.append(line).append('\n');
                }
            }
            return text.toString();
        } finally {
            connection.disconnect();
        }
    }

    private static String errorJson(String message) {
        try {
            JSONObject result = new JSONObject();
            result.put("continuation", false);
            result.put("error", message == null ? "Unknown Android error" : message);
            return result.toString();
        } catch (Exception impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
