package pk.schoolmanager.guard

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
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
import java.util.concurrent.Executors

/** Scans the connection QR code shown on the school computer and connects the phone. No typing. */
class PairActivity : AppCompatActivity() {

    private lateinit var previewView: PreviewView
    private lateinit var statusText: TextView
    private lateinit var permissionPanel: LinearLayout

    private val analysisExecutor = Executors.newSingleThreadExecutor()
    private val netExecutor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
    )

    @Volatile private var busy = false
    @Volatile private var lastRaw = ""
    @Volatile private var lastAt = 0L
    private var cameraStarted = false

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) startCamera() else permissionPanel.visibility = View.VISIBLE
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_pair)
        Net.useWifi(this)

        previewView = findViewById(R.id.previewView)
        statusText = findViewById(R.id.pairStatus)
        permissionPanel = findViewById(R.id.permissionPanel)

        findViewById<Button>(R.id.cancelButton).setOnClickListener { finish() }
        findViewById<Button>(R.id.permissionButton).setOnClickListener {
            startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.fromParts("package", packageName, null))
            )
        }

        if (hasCameraPermission()) startCamera() else permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    override fun onResume() {
        super.onResume()
        if (!cameraStarted && hasCameraPermission()) {
            permissionPanel.visibility = View.GONE
            startCamera()
        }
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        analysisExecutor.shutdown()
        netExecutor.shutdown()
        scanner.close()
        super.onDestroy()
    }

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
                provider.bindToLifecycle(this, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                cameraStarted = true
            } catch (e: Exception) {
                showStatus("The camera could not be started: ${e.message}", true)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @androidx.annotation.OptIn(ExperimentalGetImage::class)
    private fun analyze(proxy: ImageProxy) {
        val media = proxy.image
        if (media == null || busy) {
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
        if (busy) return
        if (raw == lastRaw && now - lastAt < 3000) return
        lastRaw = raw
        lastAt = now

        val code = parsePairCode(raw)
        if (code == null) {
            val message = if (raw.startsWith("SMQR1.")) {
                "That is a student ID card. Scan the connection code on the computer screen."
            } else {
                "That is not a School Manager connection code."
            }
            showStatus(message, true)
            return
        }

        busy = true
        showStatus("Connecting…", false)
        netExecutor.execute {
            try {
                val answer = Api.pair(code.addresses, code.token)
                val prefs = Prefs(this)
                prefs.server = answer.str("server").ifBlank { code.addresses.first() }
                prefs.username = answer.optJSONObject("user")?.str("username") ?: ""
                prefs.password = ""
                prefs.deviceToken = Api.deviceToken()
                runOnUiThread {
                    startActivity(
                        Intent(this, ScanActivity::class.java)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
                    )
                    finish()
                }
            } catch (e: ApiException) {
                val text = if (e.kind == ApiException.Kind.NETWORK) {
                    "Cannot reach the school computer. Check that the phone is on the same Wi-Fi, " +
                        "and that \"Allow guard phones\" is ON on the computer."
                } else {
                    e.message ?: "Connection failed."
                }
                runOnUiThread {
                    showStatus(text, true)
                    busy = false
                }
            }
        }
    }

    private fun showStatus(text: String, isError: Boolean) {
        runOnUiThread {
            statusText.text = text
            statusText.setTextColor(if (isError) 0xFFFF8A80.toInt() else 0xFFFFFFFF.toInt())
        }
    }
}
