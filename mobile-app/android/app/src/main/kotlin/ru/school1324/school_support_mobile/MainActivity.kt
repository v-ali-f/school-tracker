package ru.school1324.school_support_mobile

import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterFragmentActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "altair/open_url")
            .setMethodCallHandler { call, result ->
                if (call.method != "openUrl") {
                    result.notImplemented()
                    return@setMethodCallHandler
                }
                val url = call.argument<String>("url")
                if (url.isNullOrBlank()) {
                    result.error("bad_url", "Empty URL", null)
                    return@setMethodCallHandler
                }
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
                result.success(true)
            }
    }
}
