package pk.schoolmanager.guard

import android.Manifest
import android.animation.ObjectAnimator
import android.animation.ValueAnimator
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.media.AudioManager
import android.media.ToneGenerator
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/** The guard's screen: point at the ID card, see the result for a few seconds. */
class ScanActivity : AppCompatActivity() {

    private lateinit var previewView: PreviewView
    private lateinit var schoolText: TextView
    private lateinit var headerText: TextView
    private lateinit var hintText: TextView
    private lateinit var resultCard: LinearLayout
    private lateinit var resultTitle: TextView
    private lateinit var resultSub: TextView
    private lateinit var resultPhoto: ImageView
    private lateinit var resultName: TextView
    private lateinit var resultDetails: TextView
    private lateinit var resultMessage: TextView
    private lateinit var resultMessageUr: TextView
    private lateinit var permissionPanel: LinearLayout
    private lateinit var torchButton: Button
    private lateinit var offlinePanel: LinearLayout
    private lateinit var offlineIcon: ImageView
    private lateinit var offlineMessage: TextView
    private lateinit var offlineNote: TextView
    private lateinit var offlineStatus: TextView
    private lateinit var offlineProgress: ProgressBar
    private lateinit var prefs: Prefs

    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val netExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
    )
    private val tones = ToneGenerator(AudioManager.STREAM_MUSIC, 90)

    @Volatile private var busy = false
    @Volatile private var lastRaw = ""
    @Volatile private var lastAt = 0L
    private var camera: Camera? = null
    private var cameraStarted = false
    private var torchOn = false

    // connection state: the friendly "not connected" screen and the automatic retries
    @Volatile private var offline = false
    @Volatile private var signInBroken = false      // the computer refused this phone: retrying would not help
    @Volatile private var lostScan = false          // a card was scanned while there was no connection
    @Volatile private var offlineSince = 0L
    private val checking = AtomicBoolean(false)
    private var pulse: ObjectAnimator? = null
    private val heartbeat = object : Runnable {
        override fun run() {
            if (!signInBroken) checkConnection()
            handler.postDelayed(this, if (offline) 5000L else 20000L)
        }
    }

    private val dismissResult = Runnable { hideResult() }

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera() else permissionPanel.visibility = View.VISIBLE
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(R.layout.activity_scan)
        prefs = Prefs(this)
        Api.restore(prefs)
        Net.useWifi(this)

        previewView = findViewById(R.id.previewView)
        schoolText = findViewById(R.id.schoolText)
        headerText = findViewById(R.id.headerText)
        hintText = findViewById(R.id.hintText)
        resultCard = findViewById(R.id.resultCard)
        resultTitle = findViewById(R.id.resultTitle)
        resultSub = findViewById(R.id.resultSub)
        resultPhoto = findViewById(R.id.resultPhoto)
        resultName = findViewById(R.id.resultName)
        resultDetails = findViewById(R.id.resultDetails)
        resultMessage = findViewById(R.id.resultMessage)
        resultMessageUr = findViewById(R.id.resultMessageUr)
        permissionPanel = findViewById(R.id.permissionPanel)
        torchButton = findViewById(R.id.torchButton)
        offlinePanel = findViewById(R.id.offlinePanel)
        offlineIcon = findViewById(R.id.offlineIcon)
        offlineMessage = findViewById(R.id.offlineMessage)
        offlineNote = findViewById(R.id.offlineNote)
        offlineStatus = findViewById(R.id.offlineStatus)
        offlineProgress = findViewById(R.id.offlineProgress)

        schoolText.text = "School Guard"
        headerText.text = "Connecting…"

        resultCard.setOnClickListener { hideResult() }

        torchButton.setOnClickListener {
            torchOn = !torchOn
            camera?.cameraControl?.enableTorch(torchOn)
            torchButton.text = if (torchOn) "Flash: ON" else "Flash"
        }
        findViewById<Button>(R.id.settingsButton).setOnClickListener { openSettings() }
        findViewById<Button>(R.id.offlineSettingsButton).setOnClickListener { openSettings() }
        findViewById<Button>(R.id.retryButton).setOnClickListener {
            signInBroken = false
            checkConnection()
        }
        findViewById<Button>(R.id.reconnectQrButton).setOnClickListener {
            startActivity(Intent(this, PairActivity::class.java))
        }
        findViewById<Button>(R.id.permissionButton).setOnClickListener {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.fromParts("package", packageName, null))
            )
        }

        if (hasCameraPermission()) {
            startCamera()
        } else {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    override fun onResume() {
        super.onResume()
        // Came back from the settings screen after allowing the camera?
        if (!cameraStarted && hasCameraPermission()) {
            permissionPanel.visibility = View.GONE
            startCamera()
        }
        Net.useWifi(this)
        handler.removeCallbacks(heartbeat)
        handler.post(heartbeat)
    }

    override fun onPause() {
        handler.removeCallbacks(heartbeat)
        super.onPause()
    }

    private fun openSettings() {
        startActivity(
            Intent(this, SetupActivity::class.java).putExtra(SetupActivity.EXTRA_NO_AUTO, true)
        )
        finish()
    }

    override fun onDestroy() {
        pulse?.cancel()
        handler.removeCallbacksAndMessages(null)
        analysisExecutor.shutdown()
        netExecutor.shutdown()
        scanner.close()
        tones.release()
        super.onDestroy()
    }

    // -- camera ---------------------------------------------------------

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED

    private fun startCamera() {
        if (cameraStarted) return
        val providerFuture = ProcessCameraProvider.getInstance(this)
        providerFuture.addListener({
            try {
                val provider = providerFuture.get()
                val preview = Preview.Builder().build()
                preview.setSurfaceProvider(previewView.surfaceProvider)
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .build()
                analysis.setAnalyzer(analysisExecutor) { proxy -> analyze(proxy) }
                provider.unbindAll()
                camera = provider.bindToLifecycle(
                    this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis
                )
                cameraStarted = true
            } catch (e: Exception) {
                showError("CAMERA ERROR", "The camera could not be started: ${e.message}", "")
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @androidx.annotation.OptIn(ExperimentalGetImage::class)
    private fun analyze(proxy: ImageProxy) {
        val media = proxy.image
        if (media == null || busy || offline) {
            proxy.close()
            return
        }
        val image = InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees)
        scanner.process(image)
            .addOnSuccessListener { codes ->
                val raw = codes.firstOrNull { !it.rawValue.isNullOrBlank() }?.rawValue
                if (raw != null) onCodeFound(raw)
            }
            .addOnCompleteListener { proxy.close() }
    }

    private fun onCodeFound(raw: String) {
        val now = SystemClock.elapsedRealtime()
        if (busy || offline) return
        if (raw == lastRaw && now - lastAt < 4000) return      // same card still in view
        busy = true
        lastRaw = raw
        lastAt = now
        runOnUiThread { headerText.text = "Checking…" }

        netExecutor.execute {
            try {
                val result = Api.scan(raw)
                val photoPath = result.optJSONObject("student")?.str("photo_url") ?: ""
                val photo = Api.photo(photoPath)
                runOnUiThread { showResult(result, photo) }
            } catch (e: ApiException) {
                runOnUiThread { showApiError(e) }
            } catch (e: Exception) {
                runOnUiThread { showError("ERROR", e.message ?: "Something went wrong.", "") }
            }
        }
    }

    // -- showing results --------------------------------------------------

    private fun showResult(r: JSONObject, photo: Bitmap?) {
        val code = r.str("code")
        val status = r.str("status")
        val time = r.str("time")
        val lateMinutes = if (r.isNull("late_minutes")) -1 else r.optInt("late_minutes", -1)

        var color = "#C62828"
        var title = "INVALID QR"
        var sub = ""
        var good = false
        when {
            code == "marked" && status == "Late" -> {
                color = "#E65100"; title = "LATE"; good = true
                sub = listOf(
                    if (lateMinutes >= 0) "$lateMinutes min late" else "",
                    if (time.isNotBlank()) "arrived $time" else ""
                ).filter { it.isNotBlank() }.joinToString(" · ")
            }
            code == "marked" -> {
                color = "#2E7D32"; title = "PRESENT"; good = true
                sub = if (time.isNotBlank()) "arrived $time" else ""
            }
            code == "already_marked" -> {
                color = "#1565C0"; title = "ALREADY MARKED"; good = true
                sub = listOf(status, time).filter { it.isNotBlank() }.joinToString(" at ")
            }
            code == "on_leave" -> { color = "#6A1B9A"; title = "ON LEAVE" }
            code == "school_closed" -> { color = "#455A64"; title = "SCHOOL CLOSED" }
            code == "old_card" -> { color = "#C62828"; title = "OLD ID CARD" }
            code == "unknown_student" -> { color = "#C62828"; title = "UNKNOWN STUDENT" }
        }
        if (code == "marked" && r.str("previous_status") == "Absent") {
            sub = (sub + " (was marked Absent)").trim()
        }

        val student = r.optJSONObject("student")
        val classLine = student?.let {
            val section = it.str("section")
            val className = it.str("class_name") + if (section.isNotBlank()) " - $section" else ""
            val roll = it.str("roll_number")
            listOf(className, if (roll.isNotBlank()) "Roll $roll" else "")
                .filter { part -> part.isNotBlank() }.joinToString(" · ")
        } ?: ""

        r.optJSONObject("today")?.let { updateHeader(it) }
        presentCard(
            color, title, sub, student?.str("name") ?: "", classLine,
            r.str("message"), r.str("message_ur"), photo, if (good) 3500L else 5000L
        )
        beep(good)
    }

    private fun showApiError(e: ApiException) {
        when (e.kind) {
            ApiException.Kind.NETWORK -> {
                lostScan = true                  // this card was NOT saved
                busy = false
                goOffline(searching = true)
                checkConnection()
            }
            ApiException.Kind.AUTH -> showSignInProblem(e.message)
            ApiException.Kind.SERVER -> showError("SERVER ERROR", e.message ?: "Server error.", "")
        }
    }

    private fun showError(title: String, message: String, messageUr: String) {
        presentCard("#C62828", title, "", "", "", message, messageUr, null, 5000L)
        beep(false)
    }

    private fun presentCard(
        color: String, title: String, sub: String, name: String, details: String,
        message: String, messageUr: String, photo: Bitmap?, showForMs: Long
    ) {
        resultCard.setBackgroundColor(Color.parseColor(color))
        resultTitle.text = title
        resultSub.text = sub
        resultName.text = name
        resultDetails.text = details
        resultMessage.text = message
        resultMessageUr.text = messageUr
        if (photo != null) {
            resultPhoto.setImageBitmap(photo)
            resultPhoto.visibility = View.VISIBLE
        } else {
            resultPhoto.visibility = View.GONE
        }
        resultCard.visibility = View.VISIBLE
        handler.removeCallbacks(dismissResult)
        handler.postDelayed(dismissResult, showForMs)
    }

    private fun hideResult() {
        handler.removeCallbacks(dismissResult)
        resultCard.visibility = View.GONE
        busy = false
    }

    private fun beep(good: Boolean) {
        try {
            tones.startTone(if (good) ToneGenerator.TONE_PROP_ACK else ToneGenerator.TONE_SUP_ERROR, 250)
        } catch (e: RuntimeException) {
            // no sound is not a problem
        }
    }

    // -- connection: check, find the computer again, friendly offline screen --------------

    /** Pings the computer; if it does not answer, looks for it on the Wi-Fi (its address may have changed). */
    private fun checkConnection() {
        if (!checking.compareAndSet(false, true)) return
        if (offline) runOnUiThread { showOfflineText(searching = true) }
        netExecutor.execute {
            try {
                Net.useWifi(this)
                val ping = try {
                    Api.ping()
                } catch (e: ApiException) {
                    if (e.kind == ApiException.Kind.NETWORK) null else throw e
                }
                if (ping != null) {
                    runOnUiThread { applyPing(ping) }
                    return@execute
                }
                for (url in Api.discover()) {
                    try {
                        Api.reconnect(url)
                        prefs.server = url
                        val again = Api.ping()
                        runOnUiThread { applyPing(again) }
                        return@execute
                    } catch (e: ApiException) {
                        if (e.kind == ApiException.Kind.AUTH) throw e
                    }
                }
                runOnUiThread { goOffline(searching = false) }
            } catch (e: ApiException) {
                runOnUiThread {
                    if (e.kind == ApiException.Kind.AUTH) showSignInProblem(e.message)
                    else goOffline(searching = false)
                }
            } finally {
                checking.set(false)
            }
        }
    }

    private fun applyPing(ping: JSONObject) {
        schoolText.text = ping.str("school_name").ifBlank { "School Guard" }
        ping.optJSONObject("today")?.let { updateHeader(it) }
        if (offline) {
            hideOffline()
            if (lostScan) {
                headerText.text = "Connected again - please scan the last card again"
                lostScan = false
            }
        }
    }

    private fun goOffline(searching: Boolean) {
        if (!offline) {
            offline = true
            offlineSince = SystemClock.elapsedRealtime()
            busy = false
            handler.removeCallbacks(dismissResult)
            resultCard.visibility = View.GONE
        }
        offlinePanel.visibility = View.VISIBLE
        offlineNote.visibility = if (lostScan) View.VISIBLE else View.GONE
        if (pulse == null) {
            pulse = ObjectAnimator.ofFloat(offlineIcon, View.ALPHA, 1f, 0.35f).apply {
                duration = 1200
                repeatMode = ValueAnimator.REVERSE
                repeatCount = ValueAnimator.INFINITE
                start()
            }
        }
        showOfflineText(searching)
    }

    private fun showOfflineText(searching: Boolean) {
        offlineProgress.visibility = if (searching) View.VISIBLE else View.INVISIBLE
        offlineMessage.text = if (Net.isWifiConnected(this)) {
            "The school computer cannot be reached.\n\nMake sure School Manager is open on it " +
                "and that this phone is on the same Wi-Fi as the computer."
        } else {
            "This phone is not on Wi-Fi.\n\nConnect it to the school Wi-Fi " +
                "(or to the hotspot the computer uses)."
        }
        val minutes = ((SystemClock.elapsedRealtime() - offlineSince) / 60000L).toInt()
        offlineStatus.text = when {
            searching -> "Looking for the school computer…"
            minutes >= 1 -> "Not connected for $minutes min · trying again automatically"
            else -> "Trying again automatically every few seconds"
        }
    }

    private fun hideOffline() {
        offline = false
        pulse?.cancel()
        pulse = null
        offlineIcon.alpha = 1f
        offlinePanel.visibility = View.GONE
    }

    /** The computer does not accept this phone any more (guard password changed, account switched off...). */
    private fun showSignInProblem(message: String?) {
        signInBroken = true
        goOffline(searching = false)
        offlineProgress.visibility = View.INVISIBLE
        offlineMessage.text = (message ?: "The school computer no longer accepts this phone.") +
            "\n\nTap \"Scan QR to reconnect\" and scan the connection code on the computer."
        offlineStatus.text = "Waiting for you to reconnect"
    }

    private fun updateHeader(today: JSONObject) {
        headerText.text = "Present ${today.optInt("present")} · Late ${today.optInt("late")} · " +
            "Not arrived ${today.optInt("absent")}"
    }
}
