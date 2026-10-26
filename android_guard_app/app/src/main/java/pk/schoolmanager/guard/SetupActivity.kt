package pk.schoolmanager.guard

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.util.concurrent.Executors

/**
 * First screen. The easy way is the big "Scan QR to connect" button (no typing).
 * Typing the address, username and password is still there, folded away.
 * With a saved connection it goes straight to the scanner.
 */
class SetupActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private lateinit var scanQrButton: Button
    private lateinit var manualToggle: TextView
    private lateinit var manualPanel: LinearLayout
    private lateinit var serverInput: EditText
    private lateinit var userInput: EditText
    private lateinit var passInput: EditText
    private lateinit var connectButton: Button
    private lateinit var statusText: TextView
    private val worker = Executors.newSingleThreadExecutor()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_setup)
        prefs = Prefs(this)
        Net.useWifi(this)

        scanQrButton = findViewById(R.id.scanQrButton)
        manualToggle = findViewById(R.id.manualToggle)
        manualPanel = findViewById(R.id.manualPanel)
        serverInput = findViewById(R.id.serverInput)
        userInput = findViewById(R.id.userInput)
        passInput = findViewById(R.id.passInput)
        connectButton = findViewById(R.id.connectButton)
        statusText = findViewById(R.id.statusText)

        serverInput.setText(prefs.server)
        userInput.setText(prefs.username)
        passInput.setText(prefs.password)

        scanQrButton.setOnClickListener {
            startActivity(Intent(this, PairActivity::class.java))
        }
        manualToggle.setOnClickListener {
            val show = manualPanel.visibility != View.VISIBLE
            manualPanel.visibility = if (show) View.VISIBLE else View.GONE
            manualToggle.text = if (show) "Hide typing option" else "Connect by typing the address instead"
        }
        connectButton.setOnClickListener { connectByTyping() }

        val auto = !intent.getBooleanExtra(EXTRA_NO_AUTO, false)
        if (auto && prefs.isComplete()) resumeSavedConnection()
    }

    override fun onResume() {
        super.onResume()
        Net.useWifi(this)
    }

    override fun onDestroy() {
        worker.shutdown()
        super.onDestroy()
    }

    /** A connection is saved: open the scanner. It shows a friendly screen itself if the computer is out of reach. */
    private fun resumeSavedConnection() {
        setBusy(true)
        showStatus("Connecting…", false)
        worker.execute {
            try {
                Api.restore(prefs)
                Api.reconnect(prefs.server)
                openScanner()
            } catch (e: ApiException) {
                if (e.kind == ApiException.Kind.NETWORK) {
                    openScanner()             // the scanner screen keeps looking for the computer
                } else {
                    runOnUiThread {
                        setBusy(false)
                        showStatus(e.message ?: "Please connect again.", true)
                    }
                }
            }
        }
    }

    private fun connectByTyping() {
        val server = Api.normalizeBase(serverInput.text.toString())
        val user = userInput.text.toString().trim()
        val pass = passInput.text.toString()
        if (server.isEmpty() || user.isEmpty() || pass.isEmpty()) {
            showStatus("Fill in the server address, username and password.", true)
            return
        }
        setBusy(true)
        showStatus("Connecting…", false)

        worker.execute {
            try {
                Api.login(server, user, pass)
                prefs.server = server
                prefs.username = user
                val token = Api.deviceToken()
                prefs.deviceToken = token
                prefs.password = if (token.isNotBlank()) "" else pass   // the token replaces the password
                openScanner()
            } catch (e: ApiException) {
                runOnUiThread {
                    setBusy(false)
                    showStatus(friendly(e), true)
                }
            }
        }
    }

    private fun openScanner() {
        runOnUiThread {
            startActivity(Intent(this, ScanActivity::class.java))
            finish()
        }
    }

    private fun friendly(e: ApiException): String = when (e.kind) {
        ApiException.Kind.NETWORK ->
            "${e.message}\n\nCheck that:\n• the phone and the computer are on the same Wi-Fi\n" +
                "• School Manager is open on the computer\n" +
                "• \"Allow guard phones\" is ON there (then close and reopen School Manager once)\n" +
                "• the firewall file was run once on the computer\n\n" +
                "Tip: \"Scan QR to connect\" is easier than typing the address."
        else -> e.message ?: "Something went wrong."
    }

    private fun setBusy(busy: Boolean) {
        runOnUiThread {
            scanQrButton.isEnabled = !busy
            connectButton.isEnabled = !busy
        }
    }

    private fun showStatus(text: String, isError: Boolean) {
        runOnUiThread {
            statusText.text = text
            statusText.setTextColor(if (isError) 0xFFC62828.toInt() else 0xFF455A64.toInt())
        }
    }

    companion object {
        const val EXTRA_NO_AUTO = "no_auto"
    }
}
